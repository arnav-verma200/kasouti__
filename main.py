import os
import json
import asyncio
import random
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Literal
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# Gemini Client Setup
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 
gemini_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        pass

# Pydantic Schemas for Structured Outputs
class SalesDraft(BaseModel):
    metal: str = Field(description="Must be 'Gold' or 'Silver'")
    karat_or_purity: str = Field(description="Purity code like '18K', '22K', '92.5%'")
    weight_g: float = Field(description="Estimated weight in grams")
    complexity: str = Field(description="Must be 'low', 'medium', or 'high'")
    technique: str = Field(description="Must be 'filigree', 'stone-setting', 'polishing', or 'engraving'")
    gemstone: str = Field(description="Gemstone selection or 'None'")
    proposed_price: float = Field(description="Proposed sales quote in USD")
    rationale: str = Field(description="Brief explanation of the design choices and price")

class CostingValidation(BaseModel):
    true_cost: float = Field(description="Calculated manufacturing cost in USD")
    margin_ok: bool = Field(description="True if profit margin is >= 15%")
    suggested_price: float = Field(description="Minimum retail price to hit 15% margin")
    pushback_needed: bool = Field(description="True if margin is deficient and we should negotiate")
    rationale: str = Field(description="Detail of metal cost, making charge, gem surcharge, and margin")

class ProductionValidation(BaseModel):
    feasible: bool = Field(description="True if total estimated days <= deadline_days")
    assigned_artisan: str = Field(description="Name of the assigned artisan")
    estimated_days: int = Field(description="Total days including backlog, fabrication, and QC buffer")
    rationale: str = Field(description="Breakdown of backlog, fabrication days, and feasibility assessment")

class NegotiationTurn(BaseModel):
    round: int = Field(description="Negotiation round number, 1 or 2")
    agent: Literal["Sales", "Costing", "Production", "System"] = Field(description="Which agent produced this turn")
    turn_type: Literal["proposal", "pushback", "final", "fallback", "cap_hit"] = Field(
        description="What kind of turn this is, so the UI can style it distinctly"
    )
    text: str = Field(description="The reasoning or message for this turn")
    timestamp: str = Field(description="ISO timestamp of this turn")

app = FastAPI(title="Kasauti — Agentic Retail OS")


# Rule-Based fallback logic for Sales Agent
def run_rule_based_sales(req_data: dict, costing_pushback: str = None, production_pushback: str = None, suggested_price: float = None) -> SalesDraft:
    # Spot rate calculations
    metal_lower = req_data["metal"].lower()
    spot_rate = state["spot"]["gold_usd_g"] if metal_lower == "gold" else state["spot"]["silver_usd_g"]
    purity_ratio = calculate_purity_ratio(req_data["metal"], req_data["karat_or_purity"])
    metal_rate_per_g = spot_rate * purity_ratio
    making_charge = get_making_charge(req_data["complexity"])
    gemstone_cost = get_gemstone_surcharge(req_data["gemstone"])
    
    true_cost = (metal_rate_per_g * req_data["weight_g"]) + (making_charge * req_data["weight_g"]) + gemstone_cost + 45.00
    true_cost = round(true_cost, 2)
    
    proposed_price = req_data.get("budget")
    if proposed_price and proposed_price > 0:
        if suggested_price and suggested_price > proposed_price:
            proposed_price = suggested_price
    else:
        if suggested_price and suggested_price > 0:
            proposed_price = suggested_price
        else:
            proposed_price = round(true_cost * 1.22, 2)
            
    rationale = f"Rule-based fallback sales quote. Estimated cost: ${true_cost:.2f}."
    if costing_pushback:
        rationale += f" Costing pushback received: {costing_pushback}."
    if production_pushback:
        rationale += f" Production pushback received: {production_pushback}."
        
    return SalesDraft(
        metal=req_data["metal"],
        karat_or_purity=req_data["karat_or_purity"],
        weight_g=req_data["weight_g"],
        complexity=req_data["complexity"],
        technique=req_data["technique"],
        gemstone=req_data.get("gemstone") or "None",
        proposed_price=proposed_price,
        rationale=rationale
    )

# Rule-Based fallback logic for Costing Agent
def run_rule_based_costing(sales_draft: SalesDraft) -> CostingValidation:
    metal_lower = sales_draft.metal.lower()
    spot_rate = state["spot"]["gold_usd_g"] if metal_lower == "gold" else state["spot"]["silver_usd_g"]
    purity_ratio = calculate_purity_ratio(sales_draft.metal, sales_draft.karat_or_purity)
    metal_rate_per_g = spot_rate * purity_ratio
    making_charge = get_making_charge(sales_draft.complexity)
    gemstone_cost = get_gemstone_surcharge(sales_draft.gemstone)
    
    true_cost = (metal_rate_per_g * sales_draft.weight_g) + (making_charge * sales_draft.weight_g) + gemstone_cost + 45.00
    true_cost = round(true_cost, 2)
    
    net_margin = (sales_draft.proposed_price - true_cost) / sales_draft.proposed_price if sales_draft.proposed_price > 0 else 0
    margin_ok = net_margin >= 0.15
    suggested_price = round(true_cost / 0.85, 2)
    pushback_needed = not margin_ok
    
    rationale = f"Rule-based costing calculation. Metal: ${metal_rate_per_g * sales_draft.weight_g:.2f}, making: ${making_charge * sales_draft.weight_g:.2f}, gem surcharge: ${gemstone_cost:.2f}, premium: $45.00. Margin: {net_margin * 100:.2f}%."
    
    return CostingValidation(
        true_cost=true_cost,
        margin_ok=margin_ok,
        suggested_price=suggested_price,
        pushback_needed=pushback_needed,
        rationale=rationale
    )

# Rule-Based fallback logic for Production Agent
def run_rule_based_production(sales_draft: SalesDraft, deadline_days: int) -> ProductionValidation:
    artisan = get_matching_artisan(sales_draft.technique)
    base_fab = get_base_fabrication_days(sales_draft.complexity)
    estimated_days = artisan["backlog_days"] + base_fab + 2
    feasible = estimated_days <= deadline_days
    
    rationale = f"Rule-based production check. Artisan {artisan['name']} (backlog: {artisan['backlog_days']}d), fabrication: {base_fab}d, QC buffer: 2d. Total: {estimated_days}d."
    
    return ProductionValidation(
        feasible=feasible,
        assigned_artisan=artisan["name"],
        estimated_days=estimated_days,
        rationale=rationale
    )

# Helper to execute LLM calls with a multi-model fallback sequence
def call_llm_with_model_fallback(prompt: str, schema: Any, temperature: float = 0.1) -> Any:
    models_to_try = [
        "gemini-3.5-flash",
        "gemini-3.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-1.5-flash",
        "gemini-1.5-pro"
    ]
    from google.genai import types
    last_error = None
    
    for model_name in models_to_try:
        try:
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=temperature
                )
            )
            # Validate output immediately to ensure it parses successfully
            data = schema.model_validate_json(response.text)
            return data
        except Exception as e:
            last_error = e
            log_audit(f"LLM model {model_name} failed: {str(e)}. Trying next fallback model...", "SYSTEM")
            
    raise last_error if last_error else Exception("All LLM fallback models failed.")

# Wrapper to call Sales Agent with LLM & fallback
def call_sales_agent(req_data: dict, costing_pushback: str = None, production_pushback: str = None, suggested_price: float = None, round_num: int = 1) -> tuple[SalesDraft, str]:
    if not gemini_client:
        return run_rule_based_sales(req_data, costing_pushback, production_pushback, suggested_price), "LLM call failed — used rule-based fallback for this step."
        
    catalog_str = json.dumps(state["catalog"], indent=2)
    spot_str = json.dumps(state["spot"], indent=2)
    
    prompt = f"""
Act as luxury jewelry sales agent. Parse request, output SalesDraft JSON. Be fast. Keep rationale extremely brief (1 sentence).
Context:
Request: {json.dumps(req_data)}
Catalog: {catalog_str}
Spot rates: {spot_str}
Rules:
1. metal: 'Gold' or 'Silver'. karat_or_purity: purity code. weight_g. complexity: 'low'/'medium'/'high'. technique: 'filigree'/'stone-setting'/'polishing'/'engraving'. gemstone.
2. Defend customer budget if provided, else propose premium price.
3. If round_num > 1, adjust design/price based on costing pushback: {costing_pushback} (suggested price: {suggested_price}) and production pushback: {production_pushback}.
"""
    try:
        data = call_llm_with_model_fallback(prompt, SalesDraft, temperature=0.2)
        return data, data.rationale
    except Exception as e:
        log_audit(f"Sales Agent LLM call failed on all models: {str(e)}. Falling back to rule-based.", "SYSTEM")
        fallback_data = run_rule_based_sales(req_data, costing_pushback, production_pushback, suggested_price)
        return fallback_data, "LLM call failed — used rule-based fallback for this step."

# Wrapper to call Costing Agent with LLM & fallback
def call_costing_agent(sales_draft: SalesDraft, round_num: int = 1) -> tuple[CostingValidation, str]:
    if not gemini_client:
        return run_rule_based_costing(sales_draft), "LLM call failed — used rule-based fallback for this step."
        
    spot_str = json.dumps(state["spot"], indent=2)
    gem_surcharges = {"diamond": 150.0, "ruby": 80.0, "emerald": 90.0, "sapphire": 110.0, "pearl": 40.0}
    
    prompt = f"""
Act as financial estimator. Evaluate SalesDraft, output CostingValidation JSON. Be fast. Keep rationale extremely brief (1 sentence).
Context:
SalesDraft: {sales_draft.model_dump_json()}
Spot rates: {spot_str}
Surcharges: {json.dumps(gem_surcharges)}
Formula:
- Metal Rate = Spot rate * Purity ratio (Gold: 18K=18/24, 22K=22/24. Silver: 92.5%=0.925, else 1.0)
- Making Charge: low=$5/g, medium=$8/g, high=$12/g
- True Cost = (Metal Rate * weight_g) + (Making Charge * weight_g) + surcharge + $45.00
- Net Profit Margin = (proposed_price - true_cost) / proposed_price
Rules:
1. Calculate true_cost.
2. Check if profit margin >= 15% (margin_ok = True).
3. If margin < 15%, set margin_ok=False, pushback_needed=True, and suggest suggested_price = true_cost / 0.85.
"""
    try:
        data = call_llm_with_model_fallback(prompt, CostingValidation, temperature=0.1)
        return data, data.rationale
    except Exception as e:
        log_audit(f"Costing Agent LLM call failed on all models: {str(e)}. Falling back to rule-based.", "SYSTEM")
        fallback_data = run_rule_based_costing(sales_draft)
        return fallback_data, "LLM call failed — used rule-based fallback for this step."

# Wrapper to call Production Agent with LLM & fallback
def call_production_agent(sales_draft: SalesDraft, deadline_days: int, round_num: int = 1) -> tuple[ProductionValidation, str]:
    if not gemini_client:
        return run_rule_based_production(sales_draft, deadline_days), "LLM call failed — used rule-based fallback for this step."
        
    artisans_str = json.dumps(state["artisans"], indent=2)
    
    prompt = f"""
Act as production scheduler. Evaluate SalesDraft, output ProductionValidation JSON. Be fast. Keep rationale extremely brief (1 sentence).
Context:
SalesDraft: {sales_draft.model_dump_json()}
Deadline: {deadline_days} days
Artisans: {artisans_str}
Rules:
1. Assign matching artisan with lowest backlog, or lowest backlog overall if no match.
2. Fab duration: low=2, medium=5, high=9 days. QC buffer = 2 days.
3. Total estimated_days = backlog_days + Fab + 2.
4. Feasible = estimated_days <= deadline_days.
"""
    try:
        data = call_llm_with_model_fallback(prompt, ProductionValidation, temperature=0.1)
        return data, data.rationale
    except Exception as e:
        log_audit(f"Production Agent LLM call failed on all models: {str(e)}. Falling back to rule-based.", "SYSTEM")
        fallback_data = run_rule_based_production(sales_draft, deadline_days)
        return fallback_data, "LLM call failed — used rule-based fallback for this step."


# Seed State
def get_initial_state() -> dict:
    return {
        "spot": {"gold_usd_g": 78.50, "silver_usd_g": 1.12, "usd_inr": 84.0, "feed_online": True},
        "trust": {"sales": 0.82, "costing": 0.90, "production": 0.88},
        "artisans": [
            {"name": "Shankar Das", "specialty": "filigree", "backlog_days": 2},
            {"name": "Vikram Verma", "specialty": "stone-setting", "backlog_days": 5},
            {"name": "Laxman Lohar", "specialty": "polishing", "backlog_days": 0},
            {"name": "Amit Sharma", "specialty": "engraving", "backlog_days": 6},
        ],
        "catalog": [
            {"name": "Royal Filigree Bridal Set", "weight_g": 35.0, "complexity": "high", "technique": "filigree", "gemstone": "Ruby", "size": "Collar 420mm", "finish": "Antique"},
            {"name": "Classic Solitaire Engagement Ring", "weight_g": 4.5, "complexity": "medium", "technique": "stone-setting", "gemstone": "Diamond", "size": "7", "finish": "High Polish"},
            {"name": "Heritage Gold Kada", "weight_g": 20.0, "complexity": "medium", "technique": "polishing", "gemstone": "None", "size": "Diam 62mm", "finish": "Matte"},
        ],
        "ledger": [],       # in-memory cache of resolved orders (Notion is the durable store)
        "pending": None,    # the single order currently awaiting human override, or None
        "audit_log": [],    # list of {ts, text} lines for the terminal-style trail
    }

state = get_initial_state()

# Helper to log audit messages
def log_audit(text: str, status: str = "SYSTEM"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["audit_log"].append({"ts": ts, "text": text, "status": status})

# Notion is the durable ledger store — no local file needed
log_audit("System startup: Using Notion as durable ledger store. No local ledger.json.", "SYSTEM")

# Background Task for Spot Jitter
async def jitter_rates_loop():
    while True:
        await asyncio.sleep(600)
        if state["spot"]["feed_online"]:
            # Jitter gold and silver by ±1.5%
            jitter_gold = 1 + random.uniform(-0.015, 0.015)
            jitter_silver = 1 + random.uniform(-0.015, 0.015)
            state["spot"]["gold_usd_g"] = round(state["spot"]["gold_usd_g"] * jitter_gold, 2)
            state["spot"]["silver_usd_g"] = round(state["spot"]["silver_usd_g"] * jitter_silver, 2)
            # Rounding to sensible cents
            log_audit(
                f"Market Feed Update: Gold spot rate jittered to ${state['spot']['gold_usd_g']:.2f}/g, "
                f"Silver spot rate jittered to ${state['spot']['silver_usd_g']:.2f}/g.",
                "SYSTEM"
            )

# Register background task on startup
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(jitter_rates_loop())
    try:
        from notion_sync import start_notion_sync_loop
        asyncio.create_task(start_notion_sync_loop())
    except Exception as e:
        log_audit(f"System startup: Failed to start Notion sync loop: {str(e)}", "SYSTEM")

# Math Utilities
def calculate_purity_ratio(metal: str, karat_or_purity: str) -> float:
    metal_clean = metal.strip().lower()
    purity_clean = karat_or_purity.strip().lower()
    
    if metal_clean == "gold":
        # extract karat number
        num_str = "".join([c for c in purity_clean if c.isdigit() or c == "."])
        if num_str:
            try:
                karat = float(num_str)
                return karat / 24.0
            except ValueError:
                pass
        return 22.0 / 24.0 # default to 22k
    else: # silver
        if "92.5" in purity_clean or "925" in purity_clean or "sterling" in purity_clean:
            return 0.925
        return 1.0 # Pure silver

def get_making_charge(complexity: str) -> float:
    comp = complexity.strip().lower()
    if comp == "low":
        return 5.0
    elif comp == "high":
        return 12.0
    else:
        return 8.0 # medium is default

def get_base_fabrication_days(complexity: str) -> int:
    comp = complexity.strip().lower()
    if comp == "low":
        return 2
    elif comp == "high":
        return 9
    else:
        return 5 # medium is default

def get_matching_artisan(technique: str) -> Dict[str, Any]:
    tech = technique.strip().lower()
    candidates = []
    for artisan in state["artisans"]:
        if artisan["specialty"].strip().lower() == tech:
            candidates.append(artisan)
    
    if not candidates:
        # Fallback to the one with the least backlog overall
        return min(state["artisans"], key=lambda x: x["backlog_days"])
    
    # Pick the matching artisan with the minimum backlog
    return min(candidates, key=lambda x: x["backlog_days"])

def get_gemstone_surcharge(gemstone: Optional[str]) -> float:
    if not gemstone:
        return 0.0
    g = gemstone.strip().lower()
    surcharges = {"diamond": 150.0, "ruby": 80.0, "emerald": 90.0, "sapphire": 110.0, "pearl": 40.0}
    for gem, charge in surcharges.items():
        if gem in g:
            return charge
    return 0.0

def save_ledger():
    # No-op: Notion is the durable store. In-memory state["ledger"] is kept for dashboard reads.
    pass

def _next_order_num() -> int:
    """Get next order number using Notion ledger count + in-memory count."""
    try:
        from notion_sync import get_ledger_count_sync
        notion_count = get_ledger_count_sync()
    except Exception:
        notion_count = 0
    return 1001 + max(notion_count, len(state["ledger"]))

# Pydantic Schemas
class IntakeRequest(BaseModel):
    customer_name: str
    metal: str  # "Gold" or "Silver"
    karat_or_purity: str  # e.g., "18K", "22K", "92.5%", "Pure"
    weight_g: float
    budget: Optional[float] = None
    deadline_days: int
    complexity: str  # "low", "medium", "high"
    technique: str  # "filigree", "stone-setting", "polishing", "engraving"
    gemstone: Optional[str] = "None"
    size: Optional[str] = "Standard"
    finish: Optional[str] = "High Polish"
    photo_filename: Optional[str] = None
    workshop_notes: Optional[str] = None
    is_custom: Optional[bool] = False

class OverrideRequest(BaseModel):
    decision: str  # "approve" or "reject"
    adjusted_price: Optional[float] = None
    memo: Any

class ConfigRequest(BaseModel):
    feed_online: Optional[bool] = None
    gold_usd_g: Optional[float] = None
    silver_usd_g: Optional[float] = None
    usd_inr: Optional[float] = None

class PaymentRequest(BaseModel):
    order_id: str
    amount: float
    method: Optional[str] = None
    memo: Optional[str] = None

def create_invoice(order_id: str, final_price: float) -> dict:
    return {
        "invoice_id": f"INV-{order_id}",
        "payment_status": "paid" if final_price <= 0 else "unpaid",
        "amount_paid": 0.0,
        "tax_amount": 0.0,
        "paid_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S") if final_price <= 0 else None
    }

# Endpoints
@app.get("/api/dashboard")
def get_dashboard():
    # Return the entire dashboard state
    return state

@app.get("/api/external/spot-rates")
def get_external_spot_rates():
    return state["spot"]

@app.post("/api/config")
def post_config(req: ConfigRequest):
    if req.feed_online is not None:
        state["spot"]["feed_online"] = req.feed_online
        log_audit(f"Config change: Market Feed state toggled to {'ONLINE' if req.feed_online else 'OFFLINE'}.", "SYSTEM")
    
    if req.gold_usd_g is not None:
        state["spot"]["gold_usd_g"] = round(req.gold_usd_g, 2)
        log_audit(f"Config change: Gold spot rate manually set to ${req.gold_usd_g:.2f}/g.", "SYSTEM")
        
    if req.silver_usd_g is not None:
        state["spot"]["silver_usd_g"] = round(req.silver_usd_g, 2)
        log_audit(f"Config change: Silver spot rate manually set to ${req.silver_usd_g:.2f}/g.", "SYSTEM")
        
    if req.usd_inr is not None:
        state["spot"]["usd_inr"] = round(req.usd_inr, 2)
        log_audit(f"Config change: USD-INR conversion multiplier manually set to {req.usd_inr:.2f}.", "SYSTEM")
        
    return {"status": "success", "spot": state["spot"]}

@app.post("/api/reset")
def post_reset():
    state.clear()
    state.update(get_initial_state())
    log_audit("System Reset: All in-memory structures reset to factory seeds. Notion ledger preserved.", "SYSTEM")
    return {"status": "success", "message": "State reset successfully. Notion ledger is preserved."}

@app.post("/api/intake")
def post_intake(req: IntakeRequest):
    log_audit(f"Intake initiated for customer: {req.customer_name} ({req.weight_g}g {req.karat_or_purity} {req.metal}).", "DRAFT")
    
    negotiation_log: List[NegotiationTurn] = []
    
    # Check if spot rates feed is online
    if not state["spot"]["feed_online"]:
        log_audit("SYSTEM_EXCEPTION: External spot-rate feed is offline. Halting execution.", "COST_VALIDATED")
        
        # Formulate rule-based fallback details for the drawer
        sales_draft = run_rule_based_sales(req.model_dump())
        true_cost = sales_draft.proposed_price
        suggested_price = round(true_cost / 0.85, 2)
        
        negotiation_log.append(NegotiationTurn(
            round=1,
            agent="System",
            turn_type="fallback",
            text="SYSTEM_EXCEPTION: Spot rate feed offline. Cost calculations disabled.",
            timestamp=datetime.now().isoformat()
        ))
        
        order_id = f"KAS-{_next_order_num()}"
        pending_order = {
            "id": order_id,
            "customer_name": req.customer_name,
            "metal": req.metal,
            "karat_or_purity": req.karat_or_purity,
            "weight_g": req.weight_g,
            "budget": req.budget,
            "deadline_days": req.deadline_days,
            "complexity": req.complexity,
            "technique": req.technique,
            "gemstone": req.gemstone,
            "size": req.size,
            "finish": req.finish,
            "photo_filename": req.photo_filename,
            "workshop_notes": req.workshop_notes,
            "is_custom": req.is_custom,
            "proposed_price": sales_draft.proposed_price,
            "true_cost": true_cost,
            "net_margin": None,
            "deficit": None,
            "suggested_price": suggested_price,
            "artisan": None,
            "estimated_days": None,
            "feasibility_note": "SYSTEM_EXCEPTION: Spot rate feed offline. Cost recalcs disabled.",
            "critical_override": True,
            "override_reason": "SYSTEM_EXCEPTION: Market rates feed offline.",
            "timestamp": datetime.now().isoformat(),
            "status": "PENDING_HUMAN",
            "negotiation_log": [turn.model_dump() for turn in negotiation_log]
        }
        state["pending"] = pending_order
        log_audit(f"Orchestrator: Routing Order {order_id} to Human Approval Gate (feed offline).", "PENDING_HUMAN")
        return {"status": "pending", "order_id": order_id, "reason": "feed_offline"}
        
    # Standard flow: run multi-agent negotiation
    req_dict = req.model_dump()
    
    # Round 1: Sales Agent proposal
    log_audit("Sales Agent -> Beginning Round 1 proposal formulation...", "DRAFT")
    sales_draft, sales_text = call_sales_agent(req_dict, round_num=1)
    sales_turn_type = "fallback" if "LLM call failed" in sales_text else "proposal"
    negotiation_log.append(NegotiationTurn(
        round=1,
        agent="Sales",
        turn_type=sales_turn_type,
        text=sales_text,
        timestamp=datetime.now().isoformat()
    ))
    log_audit(f"Sales Agent (round 1, proposed price: ${sales_draft.proposed_price:.2f})", "DRAFT")
    
    # Costing check (Round 1)
    costing_cap_hit = False
    costing_val, costing_text = call_costing_agent(sales_draft, round_num=1)
    costing_turn_type = "fallback" if "LLM call failed" in costing_text else ("pushback" if costing_val.pushback_needed else "proposal")
    negotiation_log.append(NegotiationTurn(
        round=1,
        agent="Costing",
        turn_type=costing_turn_type,
        text=costing_text,
        timestamp=datetime.now().isoformat()
    ))
    
    # Costing negotiation if pushback is needed
    if costing_val.pushback_needed:
        log_audit(f"Costing Agent (round 1, pushback: margin {((sales_draft.proposed_price - costing_val.true_cost)/sales_draft.proposed_price)*100:.1f}%)", "COST_VALIDATED")
        
        # Round 2: Sales Agent adjusts price
        log_audit("Sales Agent -> Beginning Round 2 costing pushback resolution...", "DRAFT")
        sales_draft, sales_text = call_sales_agent(
            req_dict,
            costing_pushback=costing_val.rationale,
            suggested_price=costing_val.suggested_price,
            round_num=2
        )
        sales_turn_type = "fallback" if "LLM call failed" in sales_text else "proposal"
        negotiation_log.append(NegotiationTurn(
            round=2,
            agent="Sales",
            turn_type=sales_turn_type,
            text=sales_text,
            timestamp=datetime.now().isoformat()
        ))
        log_audit(f"Sales Agent (round 2, proposed price: ${sales_draft.proposed_price:.2f})", "DRAFT")
        
        # Re-check Costing in Round 2
        costing_val, costing_text = call_costing_agent(sales_draft, round_num=2)
        costing_turn_type = "fallback" if "LLM call failed" in costing_text else ("final" if not costing_val.pushback_needed else "pushback")
        negotiation_log.append(NegotiationTurn(
            round=2,
            agent="Costing",
            turn_type=costing_turn_type,
            text=costing_text,
            timestamp=datetime.now().isoformat()
        ))
        
        if costing_val.pushback_needed:
            # Bounded negotiation limit hit
            costing_cap_hit = True
            log_audit(f"Costing Agent (round 2, still unresolved: margin {((sales_draft.proposed_price - costing_val.true_cost)/sales_draft.proposed_price)*100:.1f}%)", "COST_VALIDATED")
            cap_hit_text = f"Negotiation Cap Hit: Sales proposed ${sales_draft.proposed_price:.2f}, Costing suggested ${costing_val.suggested_price:.2f}."
            negotiation_log.append(NegotiationTurn(
                round=2,
                agent="System",
                turn_type="cap_hit",
                text=cap_hit_text,
                timestamp=datetime.now().isoformat()
            ))
            log_audit(cap_hit_text, "COST_VALIDATED")
        else:
            log_audit(f"Costing Agent (round 2, resolved: margin {((sales_draft.proposed_price - costing_val.true_cost)/sales_draft.proposed_price)*100:.1f}%)", "COST_VALIDATED")
    else:
        log_audit(f"Costing Agent (round 1, approved: margin {((sales_draft.proposed_price - costing_val.true_cost)/sales_draft.proposed_price)*100:.1f}%)", "COST_VALIDATED")

    # Production check (Round 1)
    production_cap_hit = False
    prod_val, prod_text = call_production_agent(sales_draft, req.deadline_days, round_num=1)
    prod_turn_type = "fallback" if "LLM call failed" in prod_text else ("proposal" if prod_val.feasible else "pushback")
    negotiation_log.append(NegotiationTurn(
        round=1,
        agent="Production",
        turn_type=prod_turn_type,
        text=prod_text,
        timestamp=datetime.now().isoformat()
    ))
    
    # Production negotiation if unfeasible
    if not prod_val.feasible:
        log_audit(f"Production Agent (round 1, pushback: timeline conflict, estimated {prod_val.estimated_days} days)", "PRODUCTION_CHECKED")
        
        # Round 2: Sales Agent adjusts for production
        log_audit("Sales Agent -> Beginning Round 2 production pushback resolution...", "DRAFT")
        sales_draft, sales_text = call_sales_agent(
            req_dict,
            production_pushback=prod_val.rationale,
            round_num=2
        )
        sales_turn_type = "fallback" if "LLM call failed" in sales_text else "proposal"
        negotiation_log.append(NegotiationTurn(
            round=2,
            agent="Sales",
            turn_type=sales_turn_type,
            text=sales_text,
            timestamp=datetime.now().isoformat()
        ))
        log_audit(f"Sales Agent (round 2, proposed price: ${sales_draft.proposed_price:.2f})", "DRAFT")
        
        # Re-check Production in Round 2
        prod_val, prod_text = call_production_agent(sales_draft, req.deadline_days, round_num=2)
        prod_turn_type = "fallback" if "LLM call failed" in prod_text else ("final" if prod_val.feasible else "pushback")
        negotiation_log.append(NegotiationTurn(
            round=2,
            agent="Production",
            turn_type=prod_turn_type,
            text=prod_text,
            timestamp=datetime.now().isoformat()
        ))
        
        if not prod_val.feasible:
            # Bounded negotiation limit hit
            production_cap_hit = True
            log_audit(f"Production Agent (round 2, still unresolved: estimated {prod_val.estimated_days} days)", "PRODUCTION_CHECKED")
            cap_hit_text = f"Negotiation Cap Hit: Production timeline unfeasible. Estimated: {prod_val.estimated_days} days, Deadline: {req.deadline_days} days."
            negotiation_log.append(NegotiationTurn(
                round=2,
                agent="System",
                turn_type="cap_hit",
                text=cap_hit_text,
                timestamp=datetime.now().isoformat()
            ))
            log_audit(cap_hit_text, "PRODUCTION_CHECKED")
        else:
            log_audit(f"Production Agent (round 2, resolved: estimated {prod_val.estimated_days} days)", "PRODUCTION_CHECKED")
    else:
        log_audit(f"Production Agent (round 1, approved: estimated {prod_val.estimated_days} days)", "PRODUCTION_CHECKED")

    # Orchestrator evaluation variables
    true_cost = costing_val.true_cost
    proposed_price = sales_draft.proposed_price
    net_margin = (proposed_price - true_cost) / proposed_price if proposed_price > 0 else 0
    total_days = prod_val.estimated_days
    feasible = prod_val.feasible
    feasibility_note = prod_val.rationale
    matching_artisan_name = prod_val.assigned_artisan
    
    order_id = f"KAS-{_next_order_num()}"
    
    # Prepare pending details object
    pending_details = {
        "id": order_id,
        "customer_name": req.customer_name,
        "metal": sales_draft.metal,
        "karat_or_purity": sales_draft.karat_or_purity,
        "weight_g": sales_draft.weight_g,
        "budget": req.budget,
        "deadline_days": req.deadline_days,
        "complexity": sales_draft.complexity,
        "technique": sales_draft.technique,
        "gemstone": sales_draft.gemstone,
        "size": req.size,
        "finish": req.finish,
        "photo_filename": req.photo_filename,
        "workshop_notes": req.workshop_notes,
        "is_custom": req.is_custom,
        "proposed_price": proposed_price,
        "true_cost": true_cost,
        "net_margin": round(net_margin, 4),
        "suggested_price": costing_val.suggested_price,
        "artisan": matching_artisan_name,
        "estimated_days": total_days,
        "feasibility_note": feasibility_note,
        "timestamp": datetime.now().isoformat(),
        "status": "PENDING_HUMAN",
        "negotiation_log": [turn.model_dump() for turn in negotiation_log]
    }
    
    # Routing reasons checklist
    override_reasons = []
    if req.is_custom:
        override_reasons.append("Bespoke custom order")
    if net_margin < 0.15:
        override_reasons.append(f"Margin deficit ({net_margin * 100:.1f}%)")
    if not feasible:
        override_reasons.append("Production timeline unfeasible")
        
    t_sales = state["trust"]["sales"]
    t_costing = state["trust"]["costing"]
    t_production = state["trust"]["production"]
    if t_sales < 0.85 or t_costing < 0.85 or t_production < 0.85:
        override_reasons.append(f"Trust below 0.85 gate (Sales: {t_sales:.2f}, Cost: {t_costing:.2f}, Prod: {t_production:.2f})")
        
    if costing_cap_hit or production_cap_hit:
        override_reasons.append("Negotiation round cap hit")
        
    is_auto_execute_possible = (
        (not req.is_custom) and
        (net_margin >= 0.15) and
        (t_sales >= 0.85 and t_costing >= 0.85 and t_production >= 0.85) and
        feasible and
        (not costing_cap_hit) and
        (not production_cap_hit)
    )
    
    if is_auto_execute_possible:
        # Auto-execute immediately
        log_audit(f"Orchestrator: Auto-executing Order {order_id}. All trust metrics clear (Sales: {t_sales:.2f}, Cost: {t_costing:.2f}, Prod: {t_production:.2f}).", "AUTO_CONFIRMED")
        
        purity_ratio = calculate_purity_ratio(sales_draft.metal, sales_draft.karat_or_purity)
        spot_rate = state["spot"]["gold_usd_g"] if sales_draft.metal.lower() == "gold" else state["spot"]["silver_usd_g"]
        
        ledger_entry = {
            "order_id": order_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "customer_name": req.customer_name,
            "details": f"{sales_draft.weight_g}g {sales_draft.karat_or_purity} {sales_draft.metal} ({sales_draft.complexity}) | Gem: {sales_draft.gemstone} | Size: {req.size} | Finish: {req.finish}",
            "sales_quote": proposed_price,
            "final_price": proposed_price,
            "true_cost": true_cost,
            "net_margin": round(net_margin * 100, 2),
            "live_metal_rate": round(spot_rate * purity_ratio, 2),
            "inr_value": round(proposed_price * state["spot"]["usd_inr"], 2),
            "trust_score_changes": "Sales +0.01, Cost +0.01, Prod +0.01",
            "resolution_pathway": "Auto-Executed",
            "approval_memo": "N/A - Autonomous execution",
            "status": "AUTO_CONFIRMED",
            "invoice": create_invoice(order_id, proposed_price),
            "negotiation_log": [turn.model_dump() for turn in negotiation_log]
        }
        
        # Apply trust score improvements
        state["trust"]["sales"] = min(1.0, round(t_sales + 0.01, 3))
        state["trust"]["costing"] = min(1.0, round(t_costing + 0.01, 3))
        state["trust"]["production"] = min(1.0, round(t_production + 0.01, 3))
        
        state["ledger"].append(ledger_entry)
        save_ledger()
        
        # Update artisan backlog (increment by base_fab)
        base_fab = get_base_fabrication_days(sales_draft.complexity)
        for art in state["artisans"]:
            if art["name"] == matching_artisan_name:
                art["backlog_days"] += base_fab
                log_audit(f"Production Agent: Updated backlog for {art['name']} to {art['backlog_days']} days.", "AUTO_CONFIRMED")
                break
            
        # Trigger Notion sync
        try:
            from notion_sync import sync_order_to_notion
            notion_order_details = {
                "customer_name": req.customer_name,
                "metal": sales_draft.metal,
                "karat_or_purity": sales_draft.karat_or_purity,
                "weight_g": sales_draft.weight_g,
                "proposed_price": proposed_price,
                "true_cost": true_cost,
                "net_margin": net_margin,
                "suggested_price": costing_val.suggested_price,
                "artisan": matching_artisan_name,
                "estimated_days": total_days,
                "feasibility_note": feasibility_note,
                "is_custom": req.is_custom,
                "complexity": sales_draft.complexity,
                "technique": sales_draft.technique,
                "gemstone": sales_draft.gemstone,
                "status": "AUTO_CONFIRMED"
            }
            asyncio.run(sync_order_to_notion(order_id, notion_order_details))
        except Exception as e:
            log_audit(f"Notion Sync Error (auto-execute): {str(e)}", "SYSTEM")
            
        return {"status": "auto_executed", "order_id": order_id}
        
    else:
        # Route to human override
        # Setup override reasons and criticality
        override_reason_str = "; ".join(override_reasons)
        pending_details["override_reason"] = override_reason_str
        
        # Critical if deficit is more than 5% (net margin below 10%)
        deficit = 0.15 - net_margin
        pending_details["deficit"] = round(deficit, 4) if deficit > 0 else 0.0
        pending_details["critical_override"] = True if (net_margin < 0.10) else False
        pending_details["status"] = "PENDING_HUMAN"
        
        state["pending"] = pending_details
        log_audit(f"Orchestrator: Routing Order {order_id} to Human Approval Gate. Reason: {override_reason_str}.", "PENDING_HUMAN")
        
        # Trigger Notion sync
        try:
            from notion_sync import sync_order_to_notion
            asyncio.run(sync_order_to_notion(order_id, pending_details))
        except Exception as e:
            log_audit(f"Notion Sync Error (pending): {str(e)}", "SYSTEM")
            
        return {"status": "pending", "order_id": order_id, "reason": override_reasons[0] if override_reasons else "other"}


def execute_override(decision: str, adjusted_price: Optional[float] = None, memo: Any = None) -> dict:
    pending = state["pending"]
    if not pending:
        raise HTTPException(status_code=400, detail="No pending order to override.")
    decision = decision.strip().lower()
    memo_val = memo
    if not memo_val:
        raise HTTPException(status_code=400, detail="A manual verification justification/memo is required.")
        
    if isinstance(memo_val, dict):
        chips_str = ", ".join(memo_val.get("chips", []))
        note_str = memo_val.get("note", "")
        memo_summary = f"Chips: [{chips_str}]"
        if note_str:
            memo_summary += f" | Note: {note_str}"
        memo_to_save = memo_val
    else:
        memo_summary = str(memo_val).strip()
        memo_to_save = memo_summary
        
    order_id = pending["id"]
    cust_name = pending["customer_name"]
    proposed_price = pending["proposed_price"]
    true_cost = pending["true_cost"]
    
    t_sales = state["trust"]["sales"]
    t_costing = state["trust"]["costing"]
    t_production = state["trust"]["production"]
    
    if decision == "approve":
        # Resolve final price
        final_price = adjusted_price if adjusted_price is not None else proposed_price
        margin_final = (final_price - true_cost) / final_price if final_price > 0 else 0
        
        log_audit(f"Human Override: Order {order_id} APPROVED by operator. Final sales price: ${final_price:.2f}. Memo: {memo_summary}", "RESOLVED")
        
        # Attribute trust updates
        if adjusted_price is None or abs(adjusted_price - proposed_price) < 0.01:
            trust_changes = "Sales +0.01, Cost +0.01, Prod +0.01"
            state["trust"]["sales"] = min(1.0, round(t_sales + 0.01, 3))
            state["trust"]["costing"] = min(1.0, round(t_costing + 0.01, 3))
            state["trust"]["production"] = min(1.0, round(t_production + 0.01, 3))
        else:
            trust_changes = "Sales -0.03, Cost +0.01, Prod +0.01"
            state["trust"]["sales"] = max(0.0, round(t_sales - 0.03, 3))
            state["trust"]["costing"] = min(1.0, round(t_costing + 0.01, 3))
            state["trust"]["production"] = min(1.0, round(t_production + 0.01, 3))
            log_audit("Trust update: Sales Agent penalized (-0.03) for pricing override. Costing/Production validated (+0.01).", "RESOLVED")
            
        # Get live spot details for mapping
        spot_rate = state["spot"]["gold_usd_g"] if pending["metal"].lower() == "gold" else state["spot"]["silver_usd_g"]
        purity_ratio = calculate_purity_ratio(pending["metal"], pending["karat_or_purity"])
        metal_rate_per_g = spot_rate * purity_ratio
 
        ledger_entry = {
            "order_id": order_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "customer_name": cust_name,
            "details": f"{pending['weight_g']}g {pending['karat_or_purity']} {pending['metal']} ({pending['complexity']}) | Gem: {pending.get('gemstone', 'None')} | Size: {pending.get('size', 'Standard')} | Finish: {pending.get('finish', 'High Polish')}",
            "sales_quote": proposed_price,
            "final_price": final_price,
            "true_cost": true_cost,
            "net_margin": round(margin_final * 100, 2),
            "live_metal_rate": round(metal_rate_per_g, 2),
            "inr_value": round(final_price * state["spot"]["usd_inr"], 2),
            "trust_score_changes": trust_changes,
            "resolution_pathway": "Human Approved",
            "approval_memo": memo_to_save,
            "status": "RESOLVED",
            "invoice": create_invoice(order_id, final_price),
            "negotiation_log": pending.get("negotiation_log", [])
        }
        
        state["ledger"].append(ledger_entry)
        save_ledger()
        
        # Update artisan backlog (increment by base_fab)
        if pending["artisan"]:
            base_fab = get_base_fabrication_days(pending["complexity"])
            for art in state["artisans"]:
                if art["name"] == pending["artisan"]:
                    art["backlog_days"] += base_fab
                    log_audit(f"Production Agent: Updated backlog for {art['name']} to {art['backlog_days']} days.", "RESOLVED")
                    break
        
    else: # reject
        log_audit(f"Human Override: Order {order_id} REJECTED by operator. Memo: {memo_summary}", "RESOLVED")
        
        penalized_agents = ["Sales (-0.03)"]
        state["trust"]["sales"] = max(0.0, round(t_sales - 0.03, 3))
        
        if pending["estimated_days"] and pending["deadline_days"]:
            if pending["estimated_days"] > pending["deadline_days"]:
                state["trust"]["production"] = max(0.0, round(t_production - 0.03, 3))
                penalized_agents.append("Production (-0.03)")
                
        trust_changes = " | ".join(penalized_agents) + " penalized"
        log_audit(f"Trust update: {trust_changes} due to intake rejection.", "RESOLVED")
        
        ledger_entry = {
            "order_id": order_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "customer_name": cust_name,
            "details": f"{pending['weight_g']}g {pending['karat_or_purity']} {pending['metal']} ({pending['complexity']}) | Gem: {pending.get('gemstone', 'None')} | Size: {pending.get('size', 'Standard')} | Finish: {pending.get('finish', 'High Polish')}",
            "sales_quote": proposed_price,
            "final_price": 0.0,
            "true_cost": true_cost,
            "net_margin": 0.0,
            "live_metal_rate": 0.0,
            "inr_value": 0.0,
            "trust_score_changes": ", ".join(penalized_agents),
            "resolution_pathway": "Human Rejected",
            "approval_memo": memo_to_save,
            "status": "RESOLVED",
            "invoice": create_invoice(order_id, 0.0),
            "negotiation_log": pending.get("negotiation_log", [])
        }
        state["ledger"].append(ledger_entry)
        save_ledger()
 
    # Clear pending order
    state["pending"] = None
    
    # Notify Notion sync if enabled
    try:
        from notion_sync import update_ledger_row_status_async
        asyncio.run(update_ledger_row_status_async(order_id, decision, memo_summary))
    except Exception as e:
        log_audit(f"Notion Sync Error (override): {str(e)}", "SYSTEM")
        
    return {"status": "success", "resolved_id": order_id}

@app.post("/api/override")
def post_override(req: OverrideRequest):
    return execute_override(req.decision, req.adjusted_price, req.memo)

class HandoffRequest(BaseModel):
    customer_name: str
    notes: str

class HandoffOutcomeRequest(BaseModel):
    handoff_id: str
    customer_name: str
    agreed_price: float
    notes: str

@app.post("/api/upload")
async def post_upload(file: UploadFile = File(...)):
    os.makedirs("static/uploads", exist_ok=True)
    file_path = os.path.join("static/uploads", file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    return {"status": "success", "filename": file.filename}

@app.post("/api/handoff")
def post_handoff(req: HandoffRequest):
    handoff_id = f"KAS-HANDOFF-{_next_order_num()}"
    log_audit(f"Escalated to Head Karigar — {req.customer_name}, {req.notes}, design too complex for standard capture.", "PENDING_HUMAN")
    
    # Create ledger entry to keep audit trail alive
    ledger_entry = {
        "order_id": handoff_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "customer_name": req.customer_name,
        "details": f"Bespoke Handoff to Head Karigar (Shankar Das)",
        "sales_quote": 0.0,
        "final_price": 0.0,
        "true_cost": 0.0,
        "net_margin": 0.0,
        "live_metal_rate": 0.0,
        "inr_value": 0.0,
        "trust_score_changes": "Sales +0.01 (Compliance Handoff)",
        "resolution_pathway": "Karigar Handoff",
        "approval_memo": req.notes,
        "status": "PENDING_HUMAN",
        "invoice": create_invoice(handoff_id, 0.0)
    }
    
    # Reward compliance
    t_sales = state["trust"]["sales"]
    state["trust"]["sales"] = min(1.0, round(t_sales + 0.01, 3))
    
    state["ledger"].append(ledger_entry)
    save_ledger()
    
    return {"status": "handoff_completed", "handoff_id": handoff_id, "customer_name": req.customer_name, "notes": req.notes}

@app.post("/api/handoff-outcome")
def post_handoff_outcome(req: HandoffOutcomeRequest):
    log_audit(f"Escalation outcome recorded for {req.handoff_id}: Resolved with agreed price ${req.agreed_price:.2f}. Memo: {req.notes}", "RESOLVED")
    
    # Create second ledger entry for outcome
    ledger_entry = {
        "order_id": req.handoff_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "customer_name": req.customer_name,
        "details": f"Bespoke Handoff Resolution (Agreed Price: ${req.agreed_price:.2f})",
        "sales_quote": req.agreed_price,
        "final_price": req.agreed_price,
        "true_cost": 0.0,
        "net_margin": 0.0,
        "live_metal_rate": 0.0,
        "inr_value": round(req.agreed_price * state["spot"]["usd_inr"], 2),
        "trust_score_changes": "N/A (Handoff Resolution)",
        "resolution_pathway": "Karigar Resolution",
        "approval_memo": req.notes,
        "status": "RESOLVED",
        "invoice": create_invoice(req.handoff_id, req.agreed_price)
    }
    
    state["ledger"].append(ledger_entry)
    save_ledger()
    return {"status": "handoff_outcome_completed", "handoff_id": req.handoff_id}

@app.get("/api/invoice/{order_id}")
def get_invoice(order_id: str):
    # Check in-memory cache first
    for entry in state["ledger"]:
        if entry["order_id"] == order_id:
            return entry
    # Fall back to Notion query
    try:
        from notion_sync import query_ledger_entry_sync
        page = query_ledger_entry_sync(order_id)
        if page:
            props = page.get("properties", {})
            sales_quote = props.get("Sales Quote", {}).get("number") or 0.0
            true_cost = props.get("True Cost", {}).get("number") or 0.0
            margin = props.get("Margin %", {}).get("number") or 0.0
            status_sel = props.get("Status", {}).get("select")
            status = status_sel.get("name") if status_sel else "Unknown"
            customer_rt = props.get("Customer", {}).get("rich_text", [])
            customer = customer_rt[0].get("text", {}).get("content", "") if customer_rt else ""
            design_rt = props.get("Design", {}).get("rich_text", [])
            design = design_rt[0].get("text", {}).get("content", "") if design_rt else ""
            return {
                "order_id": order_id,
                "customer_name": customer,
                "details": design,
                "sales_quote": sales_quote,
                "final_price": sales_quote,
                "true_cost": true_cost,
                "net_margin": margin,
                "status": status,
                "source": "notion"
            }
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Order not found in ledger.")

@app.post("/api/payment")
def post_payment(req: PaymentRequest):
    target_entry = None
    for entry in state["ledger"]:
        if entry["order_id"] == req.order_id:
            target_entry = entry
            break
            
    if not target_entry:
        raise HTTPException(status_code=404, detail="Order not found in ledger.")
        
    invoice = target_entry.get("invoice")
    if not invoice:
        invoice = create_invoice(req.order_id, target_entry["final_price"])
        target_entry["invoice"] = invoice
        
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero.")
        
    total_price = target_entry["final_price"]
    current_paid = invoice["amount_paid"]
    remaining = round(total_price - current_paid, 2)
    
    if req.amount > remaining:
        raise HTTPException(status_code=400, detail=f"Payment exceeds remaining balance. Remaining: ${remaining:.2f}")
        
    invoice["amount_paid"] = round(current_paid + req.amount, 2)
    
    if invoice["amount_paid"] >= total_price:
        invoice["payment_status"] = "paid"
        invoice["paid_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif invoice["amount_paid"] > 0:
        invoice["payment_status"] = "partial"
        invoice["paid_at"] = None
    else:
        invoice["payment_status"] = "unpaid"
        invoice["paid_at"] = None
        
    log_audit(f"Payment of ${req.amount:.2f} recorded for Order {req.order_id}. New Status: {invoice['payment_status'].upper()}.", "SYSTEM")
    save_ledger()
    return invoice

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

# Redirection from root to index.html
@app.get("/")
def read_root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

