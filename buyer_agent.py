import os
import json
import re
import google.generativeai as genai
from typing import List, Dict, Any, Tuple
from db import get_products, get_merchant_by_id, get_active_campaigns, format_price

# Configure Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY and GEMINI_API_KEY != "REPLACE_ME":
    genai.configure(api_key=GEMINI_API_KEY)

def is_gemini_configured() -> bool:
    key = os.getenv("GEMINI_API_KEY", "")
    return bool(key) and key != "REPLACE_ME"

def run_buyer_agent_reasoning(intent: str, budget_paise: int, current_cart_paise: int, previous_steps: List[str]) -> Dict[str, Any]:
    """
    Runs one step of the ARIA Buyer AI Reasoning loop.
    Evaluates multi-merchant products against intent & remaining budget limit.
    """
    remaining_budget = budget_paise - current_cart_paise
    all_products = get_products()
    
    # Filter products within remaining budget & in stock
    affordable = [p for p in all_products if p["price"] <= remaining_budget and p["inventory"] > 0]
    
    # Enrich with merchant names
    for p in affordable:
        m = get_merchant_by_id(p["merchant_id"])
        p["merchantName"] = m["name"] if m else p["merchant_id"]
        
    catalog_summary = "\n".join([
        f"- [{p['id']}] {p['name']} | {format_price(p['price'])} | Merchant: {p['merchantName']} | Category: {p['category']} | Specs: {json.dumps(p.get('ai_specs', {}))} | Description: {p['description']}"
        for p in affordable
    ])
    
    active_campaigns = get_active_campaigns()
    campaign_info = ""
    if active_campaigns:
        camp_lines = []
        for c in active_campaigns:
            m = get_merchant_by_id(c["merchant_id"])
            m_name = m["name"] if m else "Merchant"
            disc = f"{c['discount_percent']}% off" if c.get("discount_percent") else "Special offer"
            camp_lines.append(f"- {m_name}: \"{c['name']}\" ({disc})")
        campaign_info = "\nACTIVE CAMPAIGNS (inform user if waiting gets a better discount):\n" + "\n".join(camp_lines)

    prompt = f"""You are ARIA's Buyer Agent — an autonomous AI shopping agent operating across a 5-MERCHANT network (ByteForge, HomeChef Co., DeskCraft, GlowLab, SonicWave).

MISSION: "{intent}"

BUDGET CONSTRAINTS:
- Total budget limit: {format_price(budget_paise)} (HARD BOUND)
- Already spent: {format_price(current_cart_paise)}
- Remaining budget: {format_price(remaining_budget)}

AVAILABLE PRODUCTS FROM ALL MERCHANTS (within budget):
{catalog_summary if catalog_summary else 'No products fit within remaining budget.'}
{campaign_info}

PREVIOUS STEPS:
{chr(10).join(previous_steps[-5:]) if previous_steps else 'None yet.'}

RULES:
1. You MUST NOT exceed the budget.
2. For each product, highlight key technical specifications (processor, camera, display, VRAM, audio drivers) and explain WHY it fits the user's intent.
3. You may select products from DIFFERENT merchants in a single step.
4. If a product has an active campaign/discount coming, tell the user they might want to wait.
5. If budget is exhausted or mission is complete, set shouldStop=true.
6. Be concise, highly intelligent, and technical.

Respond in this EXACT JSON format:
{{
  "thoughts": "Your internal monologue analyzing technical specifications and budget",
  "selectedProductIds": ["prod_XXX"],
  "reasoning": "Detailed technical explanation highlighting processor, camera, display, or audio specs with merchant attribution",
  "shouldStop": false
}}"""

    if not is_gemini_configured():
        return get_mock_buyer_reasoning(intent, remaining_budget, affordable)

    try:
        model = genai.GenerativeModel("models/gemini-3.6-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("No JSON object in Gemini response")
            
        result = json.loads(match.group(0))
        return result
    except Exception as e:
        print(f"[Buyer Agent Gemini Fallback]: {e}")
        return get_mock_buyer_reasoning(intent, remaining_budget, affordable)

def get_mock_buyer_reasoning(intent: str, remaining_budget: int, affordable_products: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Intelligent keyword-matching fallback engine for Python Buyer Agent.
    Scores products against prompt keywords and handles technical specs (e.g. 'camera', 'processor', 'snapdragon', 'iphone').
    """
    intent_lower = intent.lower()
    stop_words = {"i", "want", "need", "buy", "get", "for", "the", "a", "an", "and", "with", "some", "by", "tomorrow", "today", "please", "me", "to", "or", "setup", "good", "him", "her", "exceptional"}
    
    clean_text = re.sub(r"[^\w\s]", " ", intent_lower)
    keywords = [w for w in clean_text.split() if len(w) >= 2 and w not in stop_words]

    def word_matches(target: str, kw: str) -> bool:
        if kw in target:
            return True
        if kw.endswith("s") and len(kw) > 3 and kw[:-1] in target:
            return True
        if kw.endswith("es") and len(kw) > 4 and kw[:-2] in target:
            return True
        return False

    # Domain-agnostic category synonym mapping
    synonyms = {
        "phone": ["smartphone", "mobile"],
        "cellphone": ["smartphone", "mobile"],
        "gpu": ["graphics", "vram", "display"],
        "speaker": ["speakers", "soundbar", "audio"],
        "speakers": ["speaker", "soundbar", "audio"],
        "headphones": ["earphones", "headset", "audio"],
        "desk": ["standing-desk", "workspace", "table"],
        "knife": ["knives", "cutlery", "chef"],
        "wash": ["cleanser", "face-wash", "facewash"]
    }

    expanded_keywords = set(keywords)
    for kw in keywords:
        if kw in synonyms:
            expanded_keywords.update(synonyms[kw])

    scored_items: List[Tuple[Dict[str, Any], int]] = []
    for p in affordable_products:
        name_lower = p["name"].lower()
        cat_lower = p["category"].lower()
        desc_lower = p["description"].lower()
        tags_lower = " ".join(p.get("tags", [])).lower()
        specs_lower = json.dumps(p.get("ai_specs", {})).lower()

        score = 0
        for kw in keywords:
            # Dynamic exact word match in product name (e.g. user typed "samsung", "pixel", "dell", etc.)
            if kw in name_lower.split() or kw in tags_lower:
                score += 30
            elif kw in name_lower:
                score += 15
            elif kw in specs_lower:
                score += 10
            elif kw in desc_lower:
                score += 5

        # Secondary score for expanded synonyms (e.g. "phone" -> "smartphone")
        for kw in expanded_keywords:
            if word_matches(name_lower, kw):
                score += 5
            elif word_matches(tags_lower, kw):
                score += 3
        
        if score > 0:
            scored_items.append((p, score))

    # Sort by highest relevance score
    scored_items.sort(key=lambda x: x[1], reverse=True)

    selected_products: List[Dict[str, Any]] = []
    selected_ids = set()
    current_sum = 0

    if scored_items:
        for p, score in scored_items:
            if p["id"] not in selected_ids and current_sum + p["price"] <= remaining_budget:
                selected_products.append(p)
                selected_ids.add(p["id"])
                current_sum += p["price"]
                if len(selected_products) >= 2:
                    break
    elif keywords:
        return {
            "thoughts": f"Analyzing mission: \"{intent}\". Parsed keywords: [{', '.join(keywords)}]. Matched 0 products across 5 merchants.",
            "selectedProductIds": [],
            "reasoning": f"No products found matching \"{intent}\" across our 5 merchant stores.",
            "shouldStop": True,
        }
    else:
        # General store browsing
        sorted_by_price = sorted(affordable_products, key=lambda x: x["price"], reverse=True)
        for p in sorted_by_price:
            if p["id"] not in selected_ids and current_sum + p["price"] <= remaining_budget:
                selected_products.append(p)
                selected_ids.add(p["id"])
                current_sum += p["price"]
                if len(selected_products) >= 2:
                    break

    item_descs = []
    for p in selected_products:
        m = get_merchant_by_id(p["merchant_id"])
        m_name = m["name"] if m else "Merchant"
        specs = p.get("ai_specs", {})
        spec_summary = ", ".join([f"{v}" for k, v in list(specs.items())[:2]]) if specs else ""
        spec_text = f" ({spec_summary})" if spec_summary else ""
        item_descs.append(f"**{p['name']}** from {m_name} ({format_price(p['price'])}){spec_text}:\n  └ *Key Specs & Description*: {p['description']}")

    # Check for Merchant AI Upsell recommendations for selected products
    from merchant_agent import run_merchant_upsell_agent
    upsell_products = []
    upsell_notes = []

    for p in selected_products:
        merchant_id = p["merchant_id"]
        m = get_merchant_by_id(merchant_id)
        m_name = m["name"] if m else "Merchant"
        
        cart_sim = [{"product": p, "quantity": 1}]
        suggestions = run_merchant_upsell_agent(cart_sim, merchant_id)
        
        for s in suggestions:
            for up in s.get("products", []):
                if up["id"] not in selected_ids and up["price"] + current_sum <= remaining_budget:
                    upsell_products.append({
                        "id": up["id"],
                        "name": up["name"],
                        "price": up["price"],
                        "merchantId": merchant_id,
                        "merchantName": m_name,
                        "reasoning": s["reasoning"]
                    })
                    upsell_notes.append(f"💡 {m_name} AI Suggestion: Add {up['name']} ({format_price(up['price'])}) — \"{s['reasoning']}\"")
                    break

    reasoning = (
        f"Selected the following optimal product(s):\n\n" + "\n\n".join(item_descs)
        if selected_products
        else f"No products found matching \"{intent}\" within your remaining budget of {format_price(remaining_budget)}."
    )

    return {
        "thoughts": f"Analyzing mission: \"{intent}\". Parsed keywords: [{', '.join(keywords)}]. Matched {len(selected_products)} products across 5 merchants.",
        "selectedProductIds": [p["id"] for p in selected_products],
        "upsellProducts": upsell_products,
        "reasoning": reasoning,
        "shouldStop": current_sum >= remaining_budget * 0.85 or len(selected_products) == 0,
    }
