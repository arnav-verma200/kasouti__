import os
import httpx
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Load env variables
load_dotenv()

SALES_NOTION_TOKEN = os.environ.get("SALES_NOTION_TOKEN")
SALES_DATABASE_ID = os.environ.get("SALES_DATABASE_ID")

COSTING_NOTION_TOKEN = os.environ.get("COSTING_NOTION_TOKEN")
COSTING_DATABASE_ID = os.environ.get("COSTING_DATABASE_ID")

PRODUCTION_NOTION_TOKEN = os.environ.get("PRODUCTION_NOTION_TOKEN")
PRODUCTION_DATABASE_ID = os.environ.get("PRODUCTION_DATABASE_ID")

ORCHESTRATOR_NOTION_TOKEN = os.environ.get("ORCHESTRATOR_NOTION_TOKEN")
ORCHESTRATOR_DATABASE_ID = os.environ.get("ORCHESTRATOR_DATABASE_ID")

NOTION_ENABLED = all([
    SALES_NOTION_TOKEN, SALES_DATABASE_ID,
    COSTING_NOTION_TOKEN, COSTING_DATABASE_ID,
    PRODUCTION_NOTION_TOKEN, PRODUCTION_DATABASE_ID,
    ORCHESTRATOR_NOTION_TOKEN, ORCHESTRATOR_DATABASE_ID
])

def log_notion_audit(text: str, status: str = "SYSTEM"):
    try:
        import main
        main.log_audit(text, status)
    except Exception:
        print(f"[{status}] {text}")

# Initialize warnings if Notion is disabled
if not NOTION_ENABLED:
    log_notion_audit("Notion Integration: Credentials incomplete or missing. Running in LOCAL fallback mode (Notion sync disabled).", "SYSTEM")

async def create_sales_row(order_id: str, pending_order: dict) -> str:
    if not NOTION_ENABLED:
        return ""
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {SALES_NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    # Standardize description for humans
    design_str = f"Metal: {pending_order['metal']} ({pending_order['karat_or_purity']}), Weight: {pending_order['weight_g']}g, Complexity: {pending_order['complexity']}, Technique: {pending_order['technique']}, Gemstone: {pending_order['gemstone']}"
    title = f"{order_id} — Sales Proposal"
    rationale = pending_order.get("workshop_notes") or "Standard sales intake proposal formulated."
    
    payload = {
        "parent": {"database_id": SALES_DATABASE_ID},
        "properties": {
            "Customer": {"title": [{"text": {"content": f"{order_id} — {pending_order['customer_name']}"}}]},
            "Design": {"rich_text": [{"text": {"content": design_str}}]},
            "Proposed Price": {"number": float(pending_order["proposed_price"])},
            "Rationale": {"rich_text": [{"text": {"content": rationale[:2000]}}]}
        }
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            return res.json().get("url", "")
        else:
            log_notion_audit(f"Notion Error (Sales): Failed to create page: {res.text}", "SYSTEM")
            return ""

async def create_costing_row(order_id: str, pending_order: dict) -> str:
    if not NOTION_ENABLED:
        return ""
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {COSTING_NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    true_cost = pending_order["true_cost"]
    proposed_price = pending_order["proposed_price"]
    net_margin = pending_order.get("net_margin")
    if net_margin is None:
        net_margin = (proposed_price - true_cost) / proposed_price if proposed_price > 0 else 0.0
    margin_pct = round(net_margin * 100, 2)
    margin_ok = net_margin >= 0.15
    pushback_needed = not margin_ok
    suggested_price = pending_order.get("suggested_price") or round(true_cost / 0.85, 2)
    
    title = f"{order_id} — Costing Audit (Margin: {margin_pct}%)"
    
    payload = {
        "parent": {"database_id": COSTING_DATABASE_ID},
        "properties": {
            "Order Ref": {"title": [{"text": {"content": title}}]},
            "True Cost": {"number": float(true_cost)},
            "Margin %": {"number": float(margin_pct)},
            "Pushback Issued": {"checkbox": pushback_needed},
            "Suggested Price": {"number": float(suggested_price)}
        }
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            return res.json().get("url", "")
        else:
            log_notion_audit(f"Notion Error (Costing): Failed to create page: {res.text}", "SYSTEM")
            return ""

async def create_production_row(order_id: str, pending_order: dict) -> str:
    if not NOTION_ENABLED:
        return ""
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {PRODUCTION_NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    artisan = pending_order.get("artisan") or "Unassigned"
    estimated_days = pending_order.get("estimated_days") or 0
    feasible = True
    if pending_order.get("deadline_days") and estimated_days:
        feasible = estimated_days <= pending_order["deadline_days"]
    
    title = f"{order_id} — Production Schedule (Est: {estimated_days}d)"
    
    payload = {
        "parent": {"database_id": PRODUCTION_DATABASE_ID},
        "properties": {
            "Order Ref": {"title": [{"text": {"content": title}}]},
            "Artisan": {"rich_text": [{"text": {"content": artisan}}]},
            "Backlog Days": {"number": float(pending_order.get("backlog_days") or 0)},
            "Feasible": {"checkbox": feasible},
            "Estimated Days": {"number": int(estimated_days)}
        }
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            return res.json().get("url", "")
        else:
            log_notion_audit(f"Notion Error (Production): Failed to create page: {res.text}", "SYSTEM")
            return ""

async def create_ledger_row(order_id: str, pending_order: dict, sales_url: str, costing_url: str, production_url: str):
    if not NOTION_ENABLED:
        return
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {ORCHESTRATOR_NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    status = "Pending Approval"
    pathway = "Pending Approval"
    decision = "Pending"
    
    if pending_order.get("status") == "AUTO_CONFIRMED":
        status = "Resolved"
        pathway = "Auto-Executed"
        decision = "Approved"
        
    try:
        import main
        t_sales = main.state["trust"]["sales"]
        t_costing = main.state["trust"]["costing"]
        t_production = main.state["trust"]["production"]
    except Exception:
        t_sales, t_costing, t_production = 0.85, 0.85, 0.85
        
    trust_snapshot = f"Sales {t_sales:.2f} · Costing {t_costing:.2f} · Production {t_production:.2f}"
    
    proposed_price = pending_order["proposed_price"]
    true_cost = pending_order["true_cost"]
    net_margin = pending_order.get("net_margin")
    if net_margin is None:
        net_margin = (proposed_price - true_cost) / proposed_price if proposed_price > 0 else 0.0
    margin_pct = round(net_margin * 100, 2)
    suggested_price = pending_order.get("suggested_price") or round(true_cost / 0.85, 2)
    
    summary = f"Sales proposed ${proposed_price:.2f} against true cost ${true_cost:.2f} (margin: {margin_pct}%). "
    if pending_order.get("is_custom"):
        summary += "Bespoke custom order flagged. "
    else:
        summary += "Standard catalog order evaluated. "
    summary += f"Assigned artisan: {pending_order.get('artisan') or 'None'} with {pending_order.get('estimated_days') or 0} days crafting timeline."
    
    payload = {
        "parent": {"database_id": ORCHESTRATOR_DATABASE_ID},
        "properties": {
            "Order ID": {"title": [{"text": {"content": order_id}}]},
            "Customer": {"rich_text": [{"text": {"content": pending_order["customer_name"]}}]},
            "Design": {"rich_text": [{"text": {"content": f"{pending_order['weight_g']}g {pending_order['karat_or_purity']} {pending_order['metal']}"}}]},
            "Order Type": {"select": {"name": "Custom" if pending_order.get("is_custom") else "Catalog"}},
            "Status": {"select": {"name": status}},
            "Sales Quote": {"number": float(proposed_price)},
            "True Cost": {"number": float(true_cost)},
            "Suggested Min Price": {"number": float(suggested_price)},
            "Margin %": {"number": float(margin_pct)},
            "Trust Snapshot": {"rich_text": [{"text": {"content": trust_snapshot}}]},
            "Resolution Pathway": {"select": {"name": pathway}},
            "Approval Decision": {"select": {"name": decision}},
            "Human Memo": {"rich_text": [{"text": {"content": pending_order.get("override_reason") or "Pending manual verification."}}]},
            "Negotiation Summary": {"rich_text": [{"text": {"content": summary[:2000]}}]},
            "Timestamp": {"date": {"start": datetime.now().isoformat()}}
        }
    }
    
    if sales_url:
        payload["properties"]["Sales Link"] = {"url": sales_url}
    if costing_url:
        payload["properties"]["Costing Link"] = {"url": costing_url}
    if production_url:
        payload["properties"]["Production Link"] = {"url": production_url}
        
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(url, headers=headers, json=payload)
        if res.status_code != 200:
            log_notion_audit(f"Notion Error (Ledger): Failed to create page: {res.text}", "SYSTEM")

async def sync_order_to_notion(order_id: str, pending_order: dict):
    if not NOTION_ENABLED:
        return
    try:
        log_notion_audit(f"Notion Sync: Writing agent outcomes for order {order_id} to databases...", "SYSTEM")
        sales_url = await create_sales_row(order_id, pending_order)
        costing_url = await create_costing_row(order_id, pending_order)
        production_url = await create_production_row(order_id, pending_order)
        await create_ledger_row(order_id, pending_order, sales_url, costing_url, production_url)
        log_notion_audit(f"Notion Sync: Order {order_id} successfully synced to Notion workspace.", "SYSTEM")
    except Exception as e:
        log_notion_audit(f"Notion Sync Error: Failed to write to databases: {str(e)}", "SYSTEM")

async def update_ledger_row_status_async(order_id: str, decision: str, memo: str):
    if not NOTION_ENABLED:
        return
    url_query = f"https://api.notion.com/v1/databases/{ORCHESTRATOR_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {ORCHESTRATOR_NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    payload = {
        "filter": {
            "property": "Order ID",
            "title": {"equals": order_id}
        }
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url_query, headers=headers, json=payload)
            if res.status_code != 200:
                return
            results = res.json().get("results", [])
            if not results:
                return
            page_id = results[0]["id"]
            
            url_update = f"https://api.notion.com/v1/pages/{page_id}"
            mapped_pathway = "Human-Approved" if decision.lower() == "approve" else "Human-Rejected"
            mapped_decision = "Approved" if decision.lower() == "approve" else "Rejected"
            
            update_payload = {
                "properties": {
                    "Status": {"select": {"name": "Resolved"}},
                    "Resolution Pathway": {"select": {"name": mapped_pathway}},
                    "Approval Decision": {"select": {"name": mapped_decision}},
                    "Human Memo": {"rich_text": [{"text": {"content": memo[:2000]}}]}
                }
            }
            await client.patch(url_update, headers=headers, json=update_payload)
            log_notion_audit(f"Notion Sync: Updated order {order_id} status to RESOLVED in Notion Ledger.", "SYSTEM")
    except Exception as e:
        log_notion_audit(f"Notion Sync Error (Status Update): {str(e)}", "SYSTEM")

async def start_notion_sync_loop():
    if not NOTION_ENABLED:
        return
        
    log_notion_audit("Notion Integration: Background sync polling loop started (10s cadence).", "SYSTEM")
    
    url = f"https://api.notion.com/v1/databases/{ORCHESTRATOR_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {ORCHESTRATOR_NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    payload = {
        "filter": {
            "and": [
                {
                    "property": "Status",
                    "select": {"equals": "Pending Approval"}
                }
            ]
        }
    }
    
    while True:
        try:
            await asyncio.sleep(10)
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code != 200:
                    continue
                data = res.json()
                for page in data.get("results", []):
                    properties = page.get("properties", {})
                    
                    # Extract Order ID
                    title_list = properties.get("Order ID", {}).get("title", [])
                    if not title_list:
                        continue
                    order_id = title_list[0].get("text", {}).get("content", "").strip()
                    
                    # Extract Approval Decision
                    decision_obj = properties.get("Approval Decision", {}).get("select")
                    decision = decision_obj.get("name") if decision_obj else None
                    
                    # Extract Human Memo
                    memo_list = properties.get("Human Memo", {}).get("rich_text", [])
                    memo = memo_list[0].get("text", {}).get("content", "") if memo_list else "Notion Operator Action"
                    
                    if decision in ["Approved", "Rejected"]:
                        # Double check order matches pending
                        import main
                        pending = main.state.get("pending")
                        if pending and pending.get("id") == order_id:
                            log_notion_audit(f"Notion Sync: Detected Notion {decision.upper()} for order {order_id}. Resolving locals.", "SYSTEM")
                            
                            mapped_decision = "approve" if decision == "Approved" else "reject"
                            main.execute_override(mapped_decision, adjusted_price=None, memo=memo)
                            
        except Exception as e:
            # Prevent loop from crashing on network exception
            pass

async def get_ledger_count() -> int:
    """Query the Orchestrator Ledger database and return the total number of rows."""
    if not NOTION_ENABLED:
        return 0
    url = f"https://api.notion.com/v1/databases/{ORCHESTRATOR_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {ORCHESTRATOR_NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, headers=headers, json={"page_size": 100})
            if res.status_code == 200:
                return len(res.json().get("results", []))
    except Exception:
        pass
    return 0

def get_ledger_count_sync() -> int:
    """Synchronous wrapper for get_ledger_count."""
    if not NOTION_ENABLED:
        return 0
    import httpx as httpx_sync
    url = f"https://api.notion.com/v1/databases/{ORCHESTRATOR_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {ORCHESTRATOR_NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    try:
        res = httpx_sync.post(url, headers=headers, json={"page_size": 100})
        if res.status_code == 200:
            return len(res.json().get("results", []))
    except Exception:
        pass
    return 0

def query_ledger_entry_sync(order_id: str) -> dict:
    """Query the Orchestrator Ledger for a specific order_id. Returns the page properties or None."""
    if not NOTION_ENABLED:
        return None
    url = f"https://api.notion.com/v1/databases/{ORCHESTRATOR_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {ORCHESTRATOR_NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    payload = {
        "filter": {
            "property": "Order ID",
            "title": {"equals": order_id}
        }
    }
    try:
        res = httpx.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            results = res.json().get("results", [])
            if results:
                return results[0]
    except Exception:
        pass
    return None

def query_all_ledger_entries_sync() -> list:
    """Query all rows from the Orchestrator Ledger. Returns list of Notion page objects."""
    if not NOTION_ENABLED:
        return []
    url = f"https://api.notion.com/v1/databases/{ORCHESTRATOR_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {ORCHESTRATOR_NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    try:
        res = httpx.post(url, headers=headers, json={"page_size": 100})
        if res.status_code == 200:
            return res.json().get("results", [])
    except Exception:
        pass
    return []
