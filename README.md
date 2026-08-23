# ARIA — Autonomous Revenue Intelligence Agent 🤖🐍



ARIA is a **100% Pure Python** full-stack agentic commerce ecosystem built using **FastAPI, SQLite, Google Gemini 3.6 Flash**.

It enables autonomous AI agents to discover, evaluate, and purchase across multi-merchant networks with strict budget bounds, while giving merchants AI-powered upsells, automated payment link campaigns, and CSV catalog onboarding.

---

## 🎯 Why ARIA Wins

Every requirement from the Razorpay problem statement, fully delivered in Python:

| Problem Statement Requirement | ARIA Implementation |
|---|---|
| **Conversational Agentic Commerce** | ✅ Conversational AI Buyer Chatbot (`/buyer`) with step-by-step reasoning |
| **Multi-Merchant Network** | ✅ 5 distinct merchant stores (ByteForge, HomeChef Co., DeskCraft, GlowLab, SonicWave) |
| **Agent-Readable Catalog** | ✅ x402/ACP-compatible open catalog standard (`/catalog`) with machine headers |
| **Merchant Upsell & Cross-sell** | ✅ Gemini-powered real-time upsell engine in `merchant_agent.py` |
| **Automated Campaign Orchestrator** | ✅ Auto-generates Razorpay Payment Links for low-inventory stock |
| **CSV Catalog Import** | ✅ AI-powered CSV parser (`csv_parser.py`) for merchant onboarding |
| **Every money action explainable** | ✅ Complete audit log: Timestamp • Agent ID • Action • Bound • LLM Reasoning • Razorpay Ref |
| **Bounded & Gated (Safety)** | ✅ Hard budget limits (e.g. ₹2,00,000) — agent cannot exceed budget |
| **Graceful Failure Handling** | ✅ Budget bounds, stock shortages, payment errors handled and logged |

---

## 🏗️ 100% Python Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      ARIA Ecosystem                          │
├─────────────────────────────────────────────────────────────┤
│         FastAPI HTML5 / CSS3 Templates (Port 8000)          │
│   Launchpad | Buyer Chat | Merchant OS | Audit Explorer     │
├─────────────────────────────────────────────────────────────┤
│                 Python FastAPI Core (main.py)               │
├──────────────────────┬──────────────────────────────────────┤
│    MERCHANT AGENT    │            BUYER AGENT               │
│                      │                                       │
│  🏪 merchant_agent.py│    🤖 buyer_agent.py                 │
│  • Upsell Engine     │    • Natural language intent parser   │
│  • Campaign Orch.    │    • Budget limit guard (HARD BOUND)  │
│  • CSV Parser        │    • Semantic keyword matcher         │
│  • Inventory Sync    │    • Multi-merchant cart builder      │
├──────────────────────┴──────────────────────────────────────┤
│              Razorpay Test Mode APIs (Python SDK)           │
│   razorpay_service.py — Orders | Payment Links               │
├─────────────────────────────────────────────────────────────┤
│         Google Gemini 3.6 Flash — Reasoning Layer           │
│   Buyer reasoning | Upsell recommendations | Campaigns       │
├─────────────────────────────────────────────────────────────┤
│         SQLite Database & Audit Trail (db.py)                │
│   5 Merchants | 20 Products | Orders | Audit Logs            │
└─────────────────────────────────────────────────────────────┘
```

---

## 💻 Tech Stack

- **Language**: 100% Python 3.13
- **Web Framework**: FastAPI + Uvicorn + Jinja2 Templates
- **Database**: SQLite (`aria.db`) using Python's native `sqlite3` module
- **AI Intelligence**: Google Gemini 3.6 Flash (`google-generativeai`)
- **Payments**: Razorpay Test Mode Python SDK (`razorpay`)
- **Styling**: Vanilla CSS ("Quiet Dark" Linear-inspired theme)

---

## 🚀 Quick Start (One Single Command)

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start Application (Port 8000)

```bash
python main.py
```

Open **[http://localhost:8000](http://localhost:8000)** in your browser!

> Interactive FastAPI Swagger API Docs available at **[http://localhost:8000/docs](http://localhost:8000/docs)**

---

## 📁 Repository Structure

```
z:\razor\
├── main.py                  # FastAPI server, HTML template routes & REST endpoints
├── db.py                    # SQLite database engine, 5 merchants & 20 products
├── buyer_agent.py           # Buyer AI Agent reasoning & keyword matcher
├── merchant_agent.py        # Merchant AI Agent upsells & campaign orchestrator
├── razorpay_service.py      # Official Razorpay Python SDK integration
├── csv_parser.py            # AI CSV catalog import parser
├── requirements.txt         # Python dependencies
├── static/                  # Static CSS styles (Quiet Dark design system)
├── templates/               # HTML5 Jinja2 Templates (base, index, buyer, merchant, audit, catalog)
└── aria.db                  # SQLite database file
```

---

