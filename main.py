import os
import json
import asyncio
import random
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

app = FastAPI(title="Kasauti — Agentic Retail OS")

# Allow CORS for easier local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Seed State
state = {
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
    "ledger": [],       # list of resolved order records, also mirrored to data/ledger.json
    "pending": None,    # the single order currently awaiting human override, or None
    "audit_log": [],    # list of {ts, text} lines for the terminal-style trail
}

# Helper to log audit messages
def log_audit(text: str, status: str = "SYSTEM"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["audit_log"].append({"ts": ts, "text": text, "status": status})

# Try to load existing ledger from disk on startup
if os.path.exists("data/ledger.json"):
    try:
        with open("data/ledger.json", "r") as f:
            state["ledger"] = json.load(f)
        log_audit("System startup: Ledger successfully restored from data/ledger.json.", "SYSTEM")
    except Exception as e:
        log_audit(f"System startup: Failed to load data/ledger.json: {str(e)}", "SYSTEM")
else:
    log_audit("System startup: No existing ledger found. Initializing empty ledger.", "SYSTEM")

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
    if "diamond" in g:
        return 150.0
    elif "ruby" in g:
        return 80.0
    elif "emerald" in g:
        return 90.0
    elif "sapphire" in g:
        return 110.0
    elif "pearl" in g:
        return 40.0
    return 0.0

def save_ledger():
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/ledger.json", "w") as f:
            json.dump(state["ledger"], f, indent=2)
        # TODO(notion): sync this ledger entry to Notion here. Left as a no-op for now.
    except Exception as e:
        log_audit(f"System Error: Failed to write to data/ledger.json: {str(e)}")

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

# Endpoints
@app.get("/api/dashboard")
def get_dashboard():
    # Return the entire dashboard state
    return state

@app.get("/api/external/spot-rates")
def get_external_spot_rates():
    return {
        "gold_usd_g": state["spot"]["gold_usd_g"],
        "silver_usd_g": state["spot"]["silver_usd_g"],
        "usd_inr": state["spot"]["usd_inr"],
        "feed_online": state["spot"]["feed_online"]
    }

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
    state["spot"] = {"gold_usd_g": 78.50, "silver_usd_g": 1.12, "usd_inr": 84.0, "feed_online": True}
    state["trust"] = {"sales": 0.82, "costing": 0.90, "production": 0.88}
    state["artisans"] = [
        {"name": "Shankar Das", "specialty": "filigree", "backlog_days": 2},
        {"name": "Vikram Verma", "specialty": "stone-setting", "backlog_days": 5},
        {"name": "Laxman Lohar", "specialty": "polishing", "backlog_days": 0},
        {"name": "Amit Sharma", "specialty": "engraving", "backlog_days": 6},
    ]
    state["ledger"] = []
    state["pending"] = None
    state["audit_log"] = []
    
    # Remove file if it exists
    if os.path.exists("data/ledger.json"):
        try:
            os.remove("data/ledger.json")
        except Exception:
            pass
            
    log_audit("System Reset: All in-memory structures and local JSON ledger reset to factory seeds.", "SYSTEM")
    return {"status": "success", "message": "State reset successfully."}

@app.post("/api/intake")
def post_intake(req: IntakeRequest):
    log_audit(f"Intake initiated for customer: {req.customer_name} ({req.weight_g}g {req.karat_or_purity} {req.metal}).", "DRAFT")
    
    # Step 1: Sales Agent Price Formulation
    spot_rate = state["spot"]["gold_usd_g"] if req.metal.lower() == "gold" else state["spot"]["silver_usd_g"]
    purity_ratio = calculate_purity_ratio(req.metal, req.karat_or_purity)
    metal_rate_per_g = spot_rate * purity_ratio
    making_charge_per_g = get_making_charge(req.complexity)
    gemstone_cost = get_gemstone_surcharge(req.gemstone)
    
    # Cost recalcs
    true_cost = (metal_rate_per_g * req.weight_g) + (making_charge_per_g * req.weight_g) + gemstone_cost + 45.00
    true_cost = round(true_cost, 2)
    
    proposed_price = req.budget
    if not proposed_price or proposed_price <= 0:
        proposed_price = round(true_cost * 1.22, 2)
        log_audit(f"Sales Agent: No customer budget provided. Proposed standard pricing of ${proposed_price:.2f} formulated (+22% markup).", "DRAFT")
    else:
        log_audit(f"Sales Agent: Formulating pricing based on customer budget: ${proposed_price:.2f}.", "DRAFT")

    # Step 2: Costing Agent feed checks
    if not state["spot"]["feed_online"]:
        log_audit("SYSTEM_EXCEPTION: External spot-rate feed is offline. Halting execution.", "COST_VALIDATED")
        
        # Route straight to human override
        pending_order = {
            "id": f"KAS-{1001 + len(state['ledger'])}",
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
            "proposed_price": proposed_price,
            "true_cost": true_cost,
            "net_margin": None,
            "deficit": None,
            "suggested_price": round(true_cost / 0.85, 2),
            "artisan": None,
            "estimated_days": None,
            "feasibility_note": "SYSTEM_EXCEPTION: Spot rate feed offline. Cost recalcs disabled.",
            "critical_override": True,
            "override_reason": "SYSTEM_EXCEPTION: Market rates feed offline.",
            "timestamp": datetime.now().isoformat(),
            "status": "PENDING_HUMAN"
        }
        state["pending"] = pending_order
        log_audit(f"Orchestrator: Routing Order {pending_order['id']} to Human Approval Gate (feed offline).", "PENDING_HUMAN")
        return {"status": "pending", "order_id": pending_order["id"], "reason": "feed_offline"}
        
    # Step 3: Compute margins and routing logic
    net_margin = (proposed_price - true_cost) / proposed_price
    log_audit(f"Costing Agent: Recalculated true cost as ${true_cost:.2f} (metal: ${metal_rate_per_g * req.weight_g:.2f}, making: ${making_charge_per_g * req.weight_g:.2f}, gem surcharge: ${gemstone_cost:.2f}, base prem: $45.00). Net Margin: {net_margin * 100:.2f}%.", "COST_VALIDATED")
    
    # Estimate timeline
    matching_artisan = get_matching_artisan(req.technique)
    base_fab = get_base_fabrication_days(req.complexity)
    total_days = matching_artisan["backlog_days"] + base_fab + 2
    feasible = total_days <= req.deadline_days
    feasibility_str = "Feasible" if feasible else "Unfeasible"
    feasibility_note = (
        f"Artisan {matching_artisan['name']} matches specialty. "
        f"Backlog: {matching_artisan['backlog_days']}d. Base fab: {base_fab}d. QC buffer: 2d. "
        f"Total: {total_days} days. Status: {feasibility_str} (Deadline: {req.deadline_days} days)."
    )
    
    log_audit(f"Production Agent: {feasibility_note}", "PRODUCTION_CHECKED")
    
    order_id = f"KAS-{1001 + len(state['ledger'])}"
    pending_details = {
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
        "proposed_price": proposed_price,
        "true_cost": true_cost,
        "net_margin": round(net_margin, 4),
        "suggested_price": round(true_cost / 0.85, 2),
        "artisan": matching_artisan["name"],
        "estimated_days": total_days,
        "feasibility_note": feasibility_note,
        "timestamp": datetime.now().isoformat(),
        "status": "PENDING_HUMAN"
    }

    # Evaluate Branching
    if net_margin >= 0.15:
        # Check all three trust scores
        t_sales = state["trust"]["sales"]
        t_costing = state["trust"]["costing"]
        t_production = state["trust"]["production"]
        
        if t_sales >= 0.85 and t_costing >= 0.85 and t_production >= 0.85:
            if feasible:
                # Auto-execute immediately
                log_audit(f"Orchestrator: Auto-executing Order {order_id}. All trust metrics clear (Sales: {t_sales:.2f}, Cost: {t_costing:.2f}, Prod: {t_production:.2f}).", "AUTO_CONFIRMED")
                
                ledger_entry = {
                    "order_id": order_id,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "customer_name": req.customer_name,
                    "details": f"{req.weight_g}g {req.karat_or_purity} {req.metal} ({req.complexity}) | Gem: {req.gemstone} | Size: {req.size} | Finish: {req.finish}",
                    "sales_quote": proposed_price,
                    "final_price": proposed_price,
                    "true_cost": true_cost,
                    "net_margin": round(net_margin * 100, 2),
                    "live_metal_rate": round(metal_rate_per_g, 2),
                    "inr_value": round(proposed_price * state["spot"]["usd_inr"], 2),
                    "trust_score_changes": "Sales +0.01, Cost +0.01, Prod +0.01",
                    "resolution_pathway": "Auto-Executed",
                    "approval_memo": "N/A - Autonomous execution",
                    "status": "AUTO_CONFIRMED"
                }
                
                # Apply trust score improvements
                state["trust"]["sales"] = min(1.0, round(t_sales + 0.01, 3))
                state["trust"]["costing"] = min(1.0, round(t_costing + 0.01, 3))
                state["trust"]["production"] = min(1.0, round(t_production + 0.01, 3))
                
                state["ledger"].append(ledger_entry)
                save_ledger()
                
                # Update artisan backlog (increment by base_fab)
                for art in state["artisans"]:
                    if art["name"] == matching_artisan["name"]:
                        art["backlog_days"] += base_fab
                        log_audit(f"Production Agent: Updated backlog for {art['name']} to {art['backlog_days']} days.", "AUTO_CONFIRMED")
                        break
                        
                return {"status": "auto_executed", "order_id": order_id}
            else:
                # Production unfeasible overrides auto-execution
                pending_details["critical_override"] = False
                pending_details["override_reason"] = "Production conflict: estimated days exceed deadline."
                pending_details["status"] = "PENDING_HUMAN"
                state["pending"] = pending_details
                log_audit(f"Orchestrator: Routing Order {order_id} to Human Approval Gate. Reason: Production conflict (estimated days exceed deadline).", "PENDING_HUMAN")
                return {"status": "pending", "order_id": order_id, "reason": "production_conflict"}
        else:
            # Route to human override because of low trust
            pending_details["critical_override"] = False
            pending_details["override_reason"] = "Trust score below 0.85 safety gate."
            pending_details["status"] = "PENDING_HUMAN"
            state["pending"] = pending_details
            log_audit(f"Orchestrator: Routing Order {order_id} to Human Approval Gate. Reason: Safety verification lock (trust below threshold).", "PENDING_HUMAN")
            return {"status": "pending", "order_id": order_id, "reason": "low_trust"}
            
    else: # net_margin < 0.15
        deficit = 0.15 - net_margin
        pending_details["deficit"] = round(deficit, 4)
        pending_details["status"] = "PENDING_HUMAN"
        
        if deficit > 0.05:
            # Deficit critical (margin below 10%)
            pending_details["critical_override"] = True
            pending_details["override_reason"] = f"CRITICAL: Margin deficit too high ({deficit*100:.2f}% deficit, net margin {net_margin*100:.2f}%)."
            state["pending"] = pending_details
            log_audit(f"Orchestrator: Routing Order {order_id} to Human Approval Gate. Reason: {pending_details['override_reason']}", "PENDING_HUMAN")
            return {"status": "pending", "order_id": order_id, "reason": "margin_deficit_critical"}
        else:
            # Deficit low (margin between 10% and 15%)
            pending_details["critical_override"] = False
            pending_details["override_reason"] = f"Low margin deficit ({deficit*100:.2f}% deficit, net margin {net_margin*100:.2f}%)."
            state["pending"] = pending_details
            log_audit(f"Orchestrator: Routing Order {order_id} to Human Approval Gate. Reason: {pending_details['override_reason']}", "PENDING_HUMAN")
            return {"status": "pending", "order_id": order_id, "reason": "margin_deficit_low"}

@app.post("/api/override")
def post_override(req: OverrideRequest):
    pending = state["pending"]
    if not pending:
        raise HTTPException(status_code=400, detail="No pending order to override.")
    decision = req.decision.strip().lower()
    memo_val = req.memo
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
        final_price = req.adjusted_price if req.adjusted_price is not None else proposed_price
        margin_final = (final_price - true_cost) / final_price if final_price > 0 else 0
        
        log_audit(f"Human Override: Order {order_id} APPROVED by operator. Final sales price: ${final_price:.2f}. Memo: {memo_summary}", "RESOLVED")
        
        # Attribute trust updates
        if req.adjusted_price is None or abs(req.adjusted_price - proposed_price) < 0.01:
            trust_changes = "Sales +0.01, Cost +0.01, Prod +0.01"
            state["trust"]["sales"] = min(1.0, round(t_sales + 0.01, 3))
            state["trust"]["costing"] = min(1.0, round(t_costing + 0.01, 3))
            state["trust"]["production"] = min(1.0, round(t_production + 0.01, 3))
        else:
            trust_changes = "Sales -0.03, Cost +0.01, Prod +0.01"
            state["trust"]["sales"] = max(0.0, round(t_sales - 0.03, 3))
            state["trust"]["costing"] = min(1.0, round(t_costing + 0.01, 3))
            state["trust"]["production"] = min(1.0, round(t_production + 0.01, 3))
            log_audit(f"Trust update: Sales Agent penalized (-0.03) for pricing override. Costing/Production validated (+0.01).", "RESOLVED")
            
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
            "status": "RESOLVED"
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
            "status": "RESOLVED"
        }
        state["ledger"].append(ledger_entry)
        save_ledger()

    # Clear pending order
    state["pending"] = None
    return {"status": "success", "resolved_id": order_id}

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
    handoff_id = f"KAS-HANDOFF-{1001 + len(state['ledger'])}"
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
        "status": "PENDING_HUMAN"
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
        "status": "RESOLVED"
    }
    
    state["ledger"].append(ledger_entry)
    save_ledger()
    return {"status": "handoff_outcome_completed", "handoff_id": req.handoff_id}

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

