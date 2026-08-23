# ARIA — Autonomous Revenue Intelligence Agent
## Razorpay Buildathon 2025 | Track 01: AI Growth & Agentic Commerce

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      ARIA Platform                           │
├──────────────────────┬──────────────────────────────────────┤
│    MERCHANT SIDE     │           BUYER SIDE                  │
│                      │                                       │
│  🏪 Merchant Agent  │    🤖 AI Buyer Agent                  │
│  ─────────────────  │    ─────────────────────              │
│  • Catalog Manager  │    • Natural language intent          │
│  • Upsell Engine    │    • Budget-bounded purchasing         │
│  • Campaign Orch.   │    • x402/ACP-style protocol          │
│  • Revenue Analyst  │    • Graceful failure handling        │
│                      │                                       │
├──────────────────────┴──────────────────────────────────────┤
│              Razorpay Test Mode APIs                         │
│   Orders | Payment Links | Subscriptions | Webhooks          │
├─────────────────────────────────────────────────────────────┤
│              Audit Trail & Explainability Layer              │
│   Every action: WHY • WHAT • BOUNDED BY • OUTCOME           │
└─────────────────────────────────────────────────────────────┘
```

### System Component Workflow Diagram

```mermaid
flowchart TB
    subgraph BuyerFlow ["🤖 AI Buyer Agent Workflow"]
        A["User Intent & Budget Input"] --> B["GET /api/catalog (x402 Headers)"]
        B --> C["Gemini 3.6 Flash Reasoning Loop"]
        C --> D{"Budget Guard Pre & Post Check"}
        D -- "Within Budget" --> E["Evaluate Products & Build Cart"]
        D -- "Exceeds Budget" --> F["PURCHASE_BLOCKED (Graceful Stop)"]
        E --> G["POST /api/orders (Razorpay Order API)"]
        G --> H["Order Created (order_xxx)"]
    end

    subgraph MerchantFlow ["🏪 Merchant Agent Workflow"]
        M1["Cart Event / Low Stock Scan"] --> M2["Gemini Upsell / Campaign Generator"]
        M2 --> M3["Generate Campaign Strategy"]
        M3 --> M4["POST /api/payment-links (Razorpay API)"]
        M4 --> M5["Payment Link Active (plink_xxx)"]
    end

    subgraph AuditLayer ["🔍 Audit & Explainability Layer"]
        B -. Log .-> AUD["In-Memory Audit Store (logAction)"]
        F -. Log .-> AUD
        H -. Log .-> AUD
        M5 -. Log .-> AUD
        AUD --> DISP["Audit Trail UI Dashboard (/audit)"]
    end
```

### Execution Sequence Workflow Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User as User / AI Buyer
    participant BuyerAgent as 🤖 Buyer Agent Engine
    participant Catalog as 📦 Catalog API (x402)
    participant Gemini as 🧠 Gemini 3.6 Flash LLM
    participant Razorpay as 💳 Razorpay Test APIs
    participant MerchantAgent as 🏪 Merchant Revenue Agent
    participant Audit as 🔍 Audit Trail Store

    User->>BuyerAgent: Send Intent ("Home office setup") + Budget Bound (₹20,000)
    BuyerAgent->>Audit: Log AGENT_REASONING (INFO)
    BuyerAgent->>Catalog: GET /api/catalog (x402/ACP headers)
    Catalog-->>BuyerAgent: Return Machine-Readable Catalog JSON + Headers
    
    BuyerAgent->>Gemini: Prompt Intent + Budget + Catalog JSON
    Gemini-->>BuyerAgent: Return Selected Products + Reasoning JSON
    
    alt Budget Exceeded (Hard Guard)
        BuyerAgent->>Audit: Log PURCHASE_BLOCKED (BLOCKED) with bound "budget_limit=₹20,000"
        BuyerAgent-->>User: Halt execution gracefully (Show explainable block reason)
    else Within Budget
        BuyerAgent->>Razorpay: POST /api/orders (createOrder)
        Razorpay-->>BuyerAgent: Return Order Object (order_id)
        BuyerAgent->>Audit: Log ORDER_CREATE (SUCCESS) + Razorpay Ref
        BuyerAgent-->>User: Present Order & Checkout Complete
    end

    Note over MerchantAgent, Razorpay: Upsell & Campaign Orchestration
    MerchantAgent->>Gemini: Analyze Cart / Low Stock Inventory
    Gemini-->>MerchantAgent: Return Targeted Upsells & Campaign Strategy
    MerchantAgent->>Razorpay: POST /api/payment-links (createPaymentLink)
    Razorpay-->>MerchantAgent: Return Short URL (plink_id)
    MerchantAgent->>Audit: Log CAMPAIGN_ACTIVATED (SUCCESS) + Payment Link Ref
```

### Component Breakdown

1. **Agent-Readable Catalog** — Structured product data with machine-readable pricing, inventory, and negotiation rules. Exposed via x402-inspired headers.

2. **Merchant Revenue Agent** — LLM-powered upsell/cross-sell running at checkout. Analyzes cart, suggests bundles, generates campaign payment links.

3. **AI Buyer Agent** — Simulates an autonomous AI buyer with budget constraints, decision logging, and x402-style payment authorization flow.

4. **Campaign Orchestrator** — Agent that auto-creates targeted payment link campaigns based on inventory and revenue goals.

5. **Explainability Dashboard** — Live audit trail with every action annotated: agent_id, action_type, bound, razorpay_ref, outcome, timestamp.

