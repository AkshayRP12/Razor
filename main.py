import os
import uuid
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from db import (
    init_db, get_merchants, get_products, get_merchant_by_id,
    get_orders_by_merchant, get_campaigns_by_merchant, create_order,
    create_campaign, log_audit, get_audit_logs, get_audit_stats,
    get_product_by_id, format_price
)
from razorpay_service import create_razorpay_order, create_razorpay_payment_link
from buyer_agent import run_buyer_agent_reasoning
from merchant_agent import run_merchant_upsell_agent, generate_campaign_idea
from csv_parser import parse_and_import_csv

# Initialize database schema & seed data on server startup
init_db()

app = FastAPI(
    title="ARIA — Autonomous Revenue Intelligence Agent (100% Python)",
    description="100% Pure Python FastAPI platform servicing multi-merchant agentic commerce and Razorpay APIs.",
    version="2.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files & Jinja2 HTML templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ── Pydantic Request Models ───────────────────

class BuyerAgentRequest(BaseModel):
    intent: str
    budgetPaise: int
    currentCartPaise: int = 0
    previousSteps: List[str] = []
    agentId: Optional[str] = None

class MerchantAgentRequest(BaseModel):
    action: str  # 'upsell' or 'campaign'
    merchantId: str
    cart: List[Dict[str, Any]] = []
    revenueGoal: int = 5000000

class CreateOrderRequest(BaseModel):
    merchantId: str
    amount: int
    buyerAgentId: Optional[str] = None
    productIds: List[str] = []

class CreatePaymentLinkRequest(BaseModel):
    merchantId: str
    amount: int
    description: str
    campaignName: Optional[str] = None
    targetAudience: Optional[str] = None
    discountPercent: Optional[int] = None

class CsvImportRequest(BaseModel):
    csvText: str
    merchantId: str

# ── HTML Template Page Routes ─────────────────

@app.get("/")
def page_launchpad(request: Request):
    merchants = get_merchants()
    enriched = []
    for m in merchants:
        orders = get_orders_by_merchant(m["id"])
        products = get_products(m["id"])
        m_copy = dict(m)
        m_copy["stats"] = {
            "productCount": len(products),
            "totalOrders": len(orders),
        }
        enriched.append(m_copy)

    stats = get_audit_stats()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "active_page": "launchpad",
        "merchants": enriched,
        "audit_total": stats["total"]
    })

@app.get("/buyer")
def page_buyer(request: Request):
    return templates.TemplateResponse("buyer.html", {
        "request": request,
        "active_page": "buyer"
    })

@app.get("/merchant")
def page_merchant(request: Request):
    merchants = get_merchants()
    return templates.TemplateResponse("merchant.html", {
        "request": request,
        "active_page": "merchant",
        "merchants": merchants
    })

@app.get("/audit")
def page_audit(request: Request):
    merchants = get_merchants()
    return templates.TemplateResponse("audit.html", {
        "request": request,
        "active_page": "audit",
        "merchants": merchants
    })

@app.get("/catalog")
def page_catalog(request: Request):
    merchants = get_merchants()
    return templates.TemplateResponse("catalog.html", {
        "request": request,
        "active_page": "catalog",
        "merchants": merchants
    })

# ── REST API Endpoints ────────────────────────

@app.get("/api/info")
def api_info():
    return {
        "status": "online",
        "service": "ARIA Python Backend",
        "version": "2.0.0",
        "docs": "http://localhost:8000/docs"
    }

@app.get("/api/merchants")
def list_merchants():
    """GET /api/merchants — List all 5 merchants with revenue & stock statistics."""
    merchants = get_merchants()
    enriched = []
    for m in merchants:
        orders = get_orders_by_merchant(m["id"])
        campaigns = get_campaigns_by_merchant(m["id"])
        products = get_products(m["id"])
        revenue = sum(o["amount_paise"] for o in orders if o["status"] in ["created", "paid"])
        low_stock = len([p for p in products if p["inventory"] <= 20])
        
        m_copy = dict(m)
        m_copy["stats"] = {
            "productCount": len(products),
            "totalOrders": len(orders),
            "activeCampaigns": len([c for c in campaigns if c["status"] == "ACTIVE"]),
            "revenuePaise": revenue,
            "lowStock": low_stock
        }
        enriched.append(m_copy)
    return {"merchants": enriched}

@app.get("/api/catalog")
def open_catalog(response: Response, merchant_id: Optional[str] = Query(None)):
    """GET /api/catalog — Open x402 Agent Catalog Standard with protocol headers."""
    products = get_products(merchant_id)
    
    # Emit x402 Agent Headers
    response.headers["X-Agent-Readable"] = "true"
    response.headers["X-Catalog-Schema"] = "aria/v2"
    response.headers["X-Payment-Required"] = "razorpay"
    response.headers["X-ACP-Compatible"] = "true"
    
    formatted = []
    for p in products:
        m = get_merchant_by_id(p["merchant_id"])
        formatted.append({
            "id": p["id"],
            "merchantId": p["merchant_id"],
            "name": p["name"],
            "description": p["description"],
            "category": p["category"],
            "price": p["price"],
            "originalPrice": p["original_price"],
            "inventory": p["inventory"],
            "tags": p["tags"],
            "image": p["image"],
            "upsellIds": p["upsell_ids"],
            "crossSellIds": p["cross_sell_ids"],
            "aiReadable": {
                "specs": p["ai_specs"],
                "negotiable": bool(p["negotiable"]),
                "minQuantity": p["min_quantity"],
                "maxQuantity": p["max_quantity"]
            },
            "merchantName": m["name"] if m else p["merchant_id"],
            "merchantColor": m["color"] if m else "#71717a",
            "merchantLogo": m["logo"] if m else ""
        })
        
    return {
        "version": "aria/v2",
        "totalProducts": len(formatted),
        "products": formatted
    }

@app.post("/api/buyer-agent")
def buyer_agent_step(req: BuyerAgentRequest):
    """POST /api/buyer-agent — Run one step of AI Buyer Agent reasoning loop."""
    agent_id = req.agentId or f"buyer_{uuid.uuid4().hex[:8]}"

    if req.currentCartPaise >= req.budgetPaise:
        log_audit(
            agent_id=agent_id,
            agent_type="BUYER",
            action_type="PURCHASE_BLOCKED",
            status="BLOCKED",
            bound=f"budget_limit={format_price(req.budgetPaise)}",
            reasoning=f"Budget limit of {format_price(req.budgetPaise)} reached. Agent stopping autonomously.",
            amount_paise=req.currentCartPaise
        )
        return {
            "agentId": agent_id,
            "status": "BLOCKED",
            "reason": "budget_exhausted",
            "message": f"Budget limit of {format_price(req.budgetPaise)} reached.",
            "selectedProductIds": [],
            "reasoning": f"Budget limit of {format_price(req.budgetPaise)} reached. Stopping.",
            "shouldStop": True,
            "auditBound": f"budget_limit={format_price(req.budgetPaise)}"
        }

    log_audit(
        agent_id=agent_id,
        agent_type="BUYER",
        action_type="AGENT_REASONING",
        status="INFO",
        bound=f"budget_limit={format_price(req.budgetPaise)}",
        reasoning=f"Buyer agent reasoning in Python. Intent: \"{req.intent}\". Remaining: {format_price(req.budgetPaise - req.currentCartPaise)}.",
        amount_paise=req.budgetPaise - req.currentCartPaise
    )

    result = run_buyer_agent_reasoning(
        intent=req.intent,
        budget_paise=req.budgetPaise,
        current_cart_paise=req.currentCartPaise,
        previous_steps=req.previousSteps
    )

    selected_ids = result.get("selectedProductIds", [])
    selected_products = [get_product_by_id(pid) for pid in selected_ids if get_product_by_id(pid)]

    # Enrich selected products
    enriched = []
    for p in selected_products:
        m = get_merchant_by_id(p["merchant_id"])
        enriched.append({
            "id": p["id"],
            "merchantId": p["merchant_id"],
            "name": p["name"],
            "description": p["description"],
            "category": p["category"],
            "price": p["price"],
            "originalPrice": p["original_price"],
            "inventory": p["inventory"],
            "tags": p["tags"],
            "merchantName": m["name"] if m else "Merchant",
            "merchantColor": m["color"] if m else "#71717a",
            "merchantLogo": m["logo"] if m else ""
        })

    for p in selected_products:
        m = get_merchant_by_id(p["merchant_id"])
        log_audit(
            agent_id=agent_id,
            agent_type="BUYER",
            action_type="PRODUCT_EVALUATE",
            status="SUCCESS",
            merchant_id=p["merchant_id"],
            reasoning=f"Adding {p['name']} ({format_price(p['price'])}) from {m['name'] if m else p['merchant_id']} to cart.",
            amount_paise=p["price"],
            payload={"productId": p["id"], "merchantId": p["merchant_id"]}
        )

    return {
        "agentId": agent_id,
        "status": "COMPLETE" if result.get("shouldStop") else "SHOPPING",
        "thoughts": result.get("thoughts", ""),
        "selectedProductIds": selected_ids,
        "selectedProducts": enriched,
        "upsellProducts": result.get("upsellProducts", []),
        "reasoning": result.get("reasoning", ""),
        "shouldStop": result.get("shouldStop", False),
        "budgetRemaining": req.budgetPaise - req.currentCartPaise - sum(p["price"] for p in selected_products),
        "auditBound": f"budget_limit={format_price(req.budgetPaise)}"
    }

@app.post("/api/merchant-agent")
def merchant_agent_action(req: MerchantAgentRequest):
    """POST /api/merchant-agent — Run Merchant Agent upsell or campaign strategy."""
    if req.action == "upsell":
        suggestions = run_merchant_upsell_agent(req.cart, req.merchantId)
        log_audit(
            merchant_id=req.merchantId,
            agent_id=f"merchant_agent_{req.merchantId}",
            agent_type="MERCHANT",
            action_type="UPSELL_TRIGGER",
            status="SUCCESS",
            reasoning=f"Generated {len(suggestions)} upsell recommendations in Python backend."
        )
        return {"merchantId": req.merchantId, "suggestions": suggestions}
    elif req.action == "campaign":
        campaign = generate_campaign_idea(req.merchantId, req.revenueGoal)
        log_audit(
            merchant_id=req.merchantId,
            agent_id=f"merchant_orchestrator_{req.merchantId}",
            agent_type="MERCHANT",
            action_type="CAMPAIGN_CREATE",
            status="SUCCESS",
            reasoning=f"Orchestrated campaign: \"{campaign['name']}\" in Python backend."
        )
        return {"merchantId": req.merchantId, "campaign": campaign}
    else:
        raise HTTPException(status_code=400, detail="Invalid action type")

@app.post("/api/orders")
def create_order_endpoint(req: CreateOrderRequest):
    """POST /api/orders — Create Razorpay order in test mode & log audit entry."""
    rzp_order = create_razorpay_order(
        amount_paise=req.amount,
        receipt=f"rcpt_{uuid.uuid4().hex[:8]}",
        notes={"merchantId": req.merchantId, "agentId": req.buyerAgentId or "buyer_agent"}
    )

    db_order = create_order(
        merchant_id=req.merchantId,
        amount_paise=req.amount,
        razorpay_order_id=rzp_order["id"],
        buyer_agent_id=req.buyerAgentId,
        receipt=rzp_order.get("receipt")
    )

    log_audit(
        merchant_id=req.merchantId,
        agent_id=req.buyerAgentId or "buyer_agent",
        agent_type="BUYER",
        action_type="ORDER_SUCCESS",
        status="SUCCESS",
        razorpay_ref=rzp_order["id"],
        amount_paise=req.amount,
        reasoning=f"Razorpay order created: {rzp_order['id']} for {format_price(req.amount)} via Python backend.",
        payload={"orderId": db_order["id"], "razorpayOrderId": rzp_order["id"], "productIds": req.productIds}
    )

    return {"order": rzp_order, "dbOrder": db_order}

@app.post("/api/payment-links")
def create_payment_link_endpoint(req: CreatePaymentLinkRequest):
    """POST /api/payment-links — Create Razorpay Payment Link for campaigns."""
    rzp_link = create_razorpay_payment_link(
        amount_paise=req.amount,
        description=req.description,
        notes={"merchantId": req.merchantId, "campaignName": req.campaignName or "Campaign"}
    )

    db_campaign = create_campaign(
        merchant_id=req.merchantId,
        name=req.campaignName or "Campaign Link",
        description=req.description,
        amount_paise=req.amount,
        target_audience=req.targetAudience or "Customers",
        discount_percent=req.discountPercent,
        payment_link_id=rzp_link["id"],
        payment_link_url=rzp_link.get("short_url")
    )

    log_audit(
        merchant_id=req.merchantId,
        agent_id=f"merchant_{req.merchantId}",
        agent_type="MERCHANT",
        action_type="CAMPAIGN_ACTIVATED",
        status="SUCCESS",
        razorpay_ref=rzp_link["id"],
        amount_paise=req.amount,
        reasoning=f"Razorpay payment link activated: {rzp_link.get('short_url')} via Python backend."
    )

    return {"link": rzp_link, "campaign": db_campaign}

@app.post("/api/csv-import")
def csv_import_endpoint(req: CsvImportRequest):
    """POST /api/csv-import — Import CSV product catalog into merchant store."""
    res = parse_and_import_csv(req.csvText, req.merchantId)
    return res

@app.get("/api/audit")
def audit_endpoint(
    merchantId: Optional[str] = Query(None),
    agentType: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100)
):
    """GET /api/audit — Query cross-merchant compliance logs & platform statistics."""
    entries = get_audit_logs(merchant_id=merchantId, agent_type=agentType, status=status, limit=limit)
    stats = get_audit_stats(merchant_id=merchantId)
    return {
        "entries": entries,
        "total": stats["total"],
        "stats": stats
    }

@app.post("/api/webhooks")
def razorpay_webhook_endpoint(payload: Dict[str, Any]):
    """POST /api/webhooks — Razorpay webhook event handler."""
    event = payload.get("event", "unknown")
    log_audit(
        agent_id="razorpay_webhook",
        agent_type="BUYER",
        action_type="WEBHOOK_RECEIVED",
        status="INFO",
        reasoning=f"Webhook received: {event}",
        payload={"event": event}
    )

    if event == "payment.captured":
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        if payment:
            log_audit(
                agent_id="razorpay_webhook",
                agent_type="BUYER",
                action_type="PAYMENT_CAPTURE",
                status="SUCCESS",
                reasoning=f"Payment captured: {payment.get('id')}. Amount: {payment.get('amount')}. Method: {payment.get('method')}.",
                razorpay_ref=payment.get("id"),
                amount_paise=payment.get("amount"),
                payload={"orderId": payment.get("order_id"), "method": payment.get("method")}
            )
    elif event == "payment.failed":
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        log_audit(
            agent_id="razorpay_webhook",
            agent_type="BUYER",
            action_type="PAYMENT_FAILED",
            status="FAILED",
            reasoning=f"Payment failed: {payment.get('id')}. Error: {payment.get('error_description', 'unknown')}.",
            razorpay_ref=payment.get("id"),
            amount_paise=payment.get("amount")
        )

    return {"received": True, "event": event}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
