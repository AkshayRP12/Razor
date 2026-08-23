# ARIA — AI Assistant Project Instructions

## Stack & Architecture
- **Language**: 100% Pure Python (FastAPI + SQLite + Uvicorn + Jinja2)
- **AI Engine**: Google Gemini 3.6 Flash (`google-generativeai`)
- **Payments**: Razorpay Python SDK (`razorpay`)

## Commands
- **Run Application**: `python main.py` (App starts on `http://localhost:8000`)
- **Install Dependencies**: `pip install -r requirements.txt`

## Design & UI
- **Styles**: `static/css/style.css` (Quiet Dark theme)
- **Templates**: `templates/` (Jinja2 HTML templates: `index.html`, `buyer.html`, `merchant.html`, `audit.html`, `catalog.html`)
