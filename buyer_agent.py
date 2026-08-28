import os
import json
import re
import google.generativeai as genai
from typing import List, Dict, Any, Tuple
from db import get_products, get_product_by_id, get_merchant_by_id, get_active_campaigns, format_price

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
    intent_lower = intent.lower()
    confirm_words = ["yes", "proceed", "confirm", "buy remaining", "buy all", "all available", "ok", "okay", "sure", "accept"]
    is_confirm = any(kw in intent_lower for kw in confirm_words)

    effective_intent = intent
    if is_confirm and previous_steps:
        for prev in reversed(previous_steps):
            prev_lower = prev.lower()
            if not any(kw in prev_lower for kw in confirm_words):
                effective_intent = prev
                break

    effective_intent_lower = effective_intent.lower()

    # Scenario 1.4 & 1.5 — Security: Authority Spoofing & Prompt Injection Defense
    spoof_terms = ["admin", "disable budget", "override limit", "unlimited spend", "ignore previous instructions", "disable limit", "bypass"]
    if any(t in intent_lower for t in spoof_terms):
        return {
            "thoughts": f"Security Alert: Prompt injection or authority spoofing detected in intent: \"{intent}\". Enforcing hard safety bounds.",
            "selectedProductIds": [],
            "productQuantities": {},
            "reasoning": f"Security Refusal: System safety policies prohibit overriding or disabling budget bounds. Hard limit of {format_price(budget_paise)} remains active and strictly enforced.",
            "shouldStop": True,
            "actionType": "budget_check_failed"
        }

    # Scenario 1.6 — Ambiguous Intent Defense
    ambiguous_terms = ["something nice for my office", "get me something nice", "something cool", "anything good", "surprise me", "something nice"]
    clean_prompt = intent_lower.strip()
    if not is_confirm and (clean_prompt in ambiguous_terms or "something nice for my office" in clean_prompt or (len(clean_prompt.split()) <= 6 and "nice" in clean_prompt and not any(p in clean_prompt for p in ["phone", "gpu", "desk", "chair", "speaker", "serum", "blender", "spoon", "keyboard", "mouse", "monitor", "samsung", "apple", "iphone", "nvidia", "rtx", "breville", "herman"]))):
        return {
            "thoughts": f"Ambiguous intent detected in prompt: \"{intent}\". Asking clarifying question before taking any purchase action.",
            "selectedProductIds": [],
            "productQuantities": {},
            "reasoning": "Could you please specify what office item you are looking for? (e.g. Ergonomic Office Chair, Standing Desk, Gas-Spring Monitor Arm, or LED Desk Lamp?)",
            "shouldStop": True,
            "actionType": "ambiguous_intent"
        }

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
        return get_mock_buyer_reasoning(effective_intent, budget_paise, remaining_budget, current_cart_paise, all_products, is_confirm=is_confirm)

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
        return get_mock_buyer_reasoning(effective_intent, budget_paise, remaining_budget, current_cart_paise, all_products, is_confirm=is_confirm)

def extract_requested_quantity(intent: str) -> int:
    """
    Extracts explicit quantity requested by user (e.g. '200 units', '100 BrightBoost', 'buy 10 bottles', '5 keyboards').
    Ignores specs & model numbers like '100W', '4090', '15 Pro', '200MP' unless explicitly formatted as a unit count.
    """
    intent_lower = intent.lower()

    # Pattern 1: Explicit quantity with units/multiplier (e.g. '200 units', '50 bottles', '10x', '5 pieces')
    unit_match = re.search(r"\b(\d{1,4})\s*(units|pieces|items|bottles|packs|x)\b", intent_lower)
    if unit_match:
        num = int(unit_match.group(1))
        if 1 <= num <= 10000:
            return num

    # Pattern 2: Action verb followed by number (e.g. 'buy 200', 'need 50')
    action_match = re.search(r"\b(need|buy|want|get|order)\s+(\d{1,4})\b", intent_lower)
    if action_match:
        num = int(action_match.group(2))
        if num not in [4090, 4080, 4070, 4060, 2026, 2024, 2025]:
            if 1 <= num <= 10000:
                return num

    # Pattern 3: Standalone number match with spec exclusion
    match = re.search(r"\b(\d{1,4})\b", intent_lower)
    if match:
        num = int(match.group(1))
        # Ignore numbers that look like specs or model numbers when standalone
        if num in [4090, 4080, 4070, 4060, 1000, 2026, 2024, 2025, 120, 165, 200, 48, 15, 24, 16, 8]:
            return 1
        if 1 <= num <= 10000:
            return num
    return 1

def get_mock_buyer_reasoning(intent: str, total_budget_paise: int, remaining_budget: int, current_cart_paise: int, all_products: List[Dict[str, Any]], is_confirm: bool = False) -> Dict[str, Any]:
    """
    Intelligent keyword-matching fallback engine for Python Buyer Agent.
    Handles exact quantities (e.g. '100 BrightBoost'), inventory caps, stock-outs, and budget bounds.
    """
    intent_lower = intent.lower()
    requested_qty = extract_requested_quantity(intent)
    
    stop_words = {"i", "want", "need", "buy", "get", "for", "the", "a", "an", "and", "with", "some", "by", "tomorrow", "today", "please", "me", "to", "or", "setup", "good", "him", "her", "exceptional"}
    
    clean_text = re.sub(r"[^\w\s]", " ", intent_lower)
    keywords = [w for w in clean_text.split() if len(w) >= 2 and w not in stop_words and not w.isdigit()]

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
        "wash": ["cleanser", "face-wash", "facewash", "cleansers", "face wash"],
        "facewash": ["cleanser", "face-wash", "wash", "cleansers", "skincare", "face wash"],
        "face": ["cleanser", "face-wash", "facewash", "cleansers", "skincare", "wash"],
        "cleanser": ["facewash", "face-wash", "wash", "skincare", "cleansers"],
        "serum": ["serums", "vitaminc", "brightboost"],
        "keyboard": ["keyboards", "mechanical", "deskcraft"],
        "keyboards": ["keyboard", "mechanical", "deskcraft"]
    }

    expanded_keywords = set(keywords)
    for kw in keywords:
        if kw in synonyms:
            expanded_keywords.update(synonyms[kw])

    scored_items: List[Tuple[Dict[str, Any], int]] = []
    for p in all_products:
        name_lower = p["name"].lower()
        cat_lower = p["category"].lower()
        desc_lower = p["description"].lower()
        tags_lower = " ".join(p.get("tags", [])).lower()
        specs_lower = json.dumps(p.get("ai_specs", {})).lower()

        name_flat = name_lower.replace(" ", "").replace("-", "")
        tags_flat = tags_lower.replace(" ", "").replace("-", "")
        cat_flat = cat_lower.replace(" ", "").replace("-", "")

        score = 0
        for kw in keywords:
            kw_flat = kw.replace(" ", "").replace("-", "")
            if kw in name_lower.split() or kw in tags_lower:
                score += 30
            elif kw in name_lower or (len(kw_flat) >= 4 and kw_flat in name_flat):
                score += 20
            elif kw_flat in cat_flat or kw_flat in tags_flat:
                score += 15
            elif kw in specs_lower:
                score += 10
            elif kw in desc_lower:
                if kw in ["gpu", "gaming", "pc", "desk", "chair"] and cat_lower in ["smartphones", "serums", "cleansers", "appliances"]:
                    continue
                score += 5

        for kw in expanded_keywords:
            kw_flat = kw.replace(" ", "").replace("-", "")
            if word_matches(name_lower, kw) or (len(kw_flat) >= 4 and kw_flat in name_flat):
                score += 10
            elif word_matches(tags_lower, kw) or (len(kw_flat) >= 4 and kw_flat in tags_flat):
                score += 5
            elif kw_flat in cat_flat:
                score += 5
        
        if score > 0:
            scored_items.append((p, score))

    # Sort by highest relevance score
    scored_items.sort(key=lambda x: x[1], reverse=True)

    # Check for Scenario 2.1 — Stock-Out Mid-Purchase on top matched item
    if scored_items:
        top_product, top_score = scored_items[0]
        if top_product.get("inventory", 0) <= 0:
            m_id = top_product["merchant_id"]
            alt_list = [p for p in all_products if p["merchant_id"] == m_id and p["inventory"] > 0 and p["id"] != top_product["id"]]
            alt_text = ""
            if alt_list:
                m_obj = get_merchant_by_id(m_id)
                m_name = m_obj["name"] if m_obj else "the merchant store"
                alt_text = f" We recommend checking **{alt_list[0]['name']}** from {m_name} which is currently in stock."
            
            return {
                "thoughts": f"Stock-Out Detected: Product {top_product['name']} has inventory 0. Order blocked.",
                "selectedProductIds": [],
                "productQuantities": {},
                "reasoning": f"This item ({top_product['name']}) just sold out before we could complete your order.{alt_text}",
                "shouldStop": True,
                "actionType": "stock_check_failed"
            }

    # Check for Scenario 1.1 / 2.3 — Budget Breach on requested quantities / cart total
    if scored_items:
        top_product, top_score = scored_items[0]
        req_cost = requested_qty * top_product["price"]
        total_projected_cart = current_cart_paise + req_cost
        
        if total_projected_cart > total_budget_paise:
            breach = total_projected_cart - total_budget_paise
            return {
                "thoughts": f"Budget Breach Detected: Cart total {format_price(total_projected_cart)} exceeds budget limit of {format_price(total_budget_paise)} by {format_price(breach)}.",
                "selectedProductIds": [],
                "productQuantities": {},
                "reasoning": f"This order totals {format_price(total_projected_cart)}, which exceeds your {format_price(total_budget_paise)} budget limit by {format_price(breach)}. Please remove an item or reduce quantity.",
                "shouldStop": True,
                "actionType": "budget_check_failed",
                "cartTotalPaise": total_projected_cart,
                "breachPaise": breach
            }

    # Stock Shortfall Clarification Guardrail: If requested_qty > available stock, ask user before purchasing partial stock
    if scored_items:
        top_product, top_score = scored_items[0]
        stock = top_product.get("inventory", 0)
        confirm_words = ["yes", "proceed", "confirm", "buy remaining", "buy all", "all available", "ok", "okay", "sure", "accept"]
        cancel_words = ["no", "cancel", "stop", "nevermind", "abort", "don't", "dont"]

        if any(kw in intent_lower for kw in cancel_words) and not is_confirm:
            return {
                "thoughts": f"User cancelled purchase for {top_product['name']} after inventory shortfall prompt.",
                "selectedProductIds": [],
                "productQuantities": {},
                "reasoning": f"Understood! Your purchase request for **{top_product['name']}** has been cancelled.",
                "shouldStop": True,
                "actionType": "shortfall_cancelled"
            }

        if 0 < stock < requested_qty and not is_confirm and not any(kw in intent_lower for kw in confirm_words):
            total_shortfall_cost = stock * top_product["price"]
            return {
                "thoughts": f"Inventory Shortfall: Requested {requested_qty} units of {top_product['name']}, but only {stock} units in stock. Asking user to confirm.",
                "selectedProductIds": [],
                "productQuantities": {},
                "reasoning": f"We currently have **{stock} units** of **{top_product['name']}** in stock (you requested {requested_qty} units). Would you like to proceed with purchasing all **{stock} remaining units** for **{format_price(total_shortfall_cost)}**?",
                "shouldStop": False,
                "actionType": "stock_shortfall_clarify"
            }

    selected_products: List[Dict[str, Any]] = []
    product_quantities: Dict[str, int] = {}
    selected_ids = set()
    current_sum = 0

    # Calculate exact requested target count
    if "," in intent:
        comma_segments = []
        for s in intent.split(","):
            s_clean = s.strip()
            # Ignore quantity-only segments like "210 units", "10x", "5 pieces"
            if re.search(r"^\d+\s*(units|pieces|items|bottles|packs|x)?$", s_clean.lower()):
                continue
            if len(s_clean) >= 2:
                comma_segments.append(s_clean)
        max_items = max(1, len(comma_segments))
    elif any(b in intent_lower for b in ["setup", "bundle", "routine", "combo", "kit", "pack", "multiple", "items", "products", "pc", "build"]) or " and " in intent_lower:
        max_items = 3
    else:
        max_items = 1

    if scored_items:
        high_rel_count = len([item for item in scored_items if item[1] >= 15])
        if high_rel_count > 0:
            max_items = min(max_items, high_rel_count)

        selected_categories = set()
        for p, score in scored_items:
            cat = p["category"]
            if cat not in selected_categories and p["id"] not in selected_ids and p["inventory"] > 0:
                stock = p.get("inventory", 50)
                qty = min(requested_qty, stock)
                
                # Check budget constraint
                while qty > 0 and (current_sum + (qty * p["price"]) > remaining_budget):
                    qty -= 1
                    
                if qty > 0:
                    selected_products.append(p)
                    selected_ids.add(p["id"])
                    selected_categories.add(cat)
                    product_quantities[p["id"]] = qty
                    current_sum += (qty * p["price"])
                    
                if len(selected_products) >= max_items:
                    break
    elif keywords:
        return {
            "thoughts": f"Analyzing mission: \"{intent}\". Parsed keywords: [{', '.join(keywords)}]. Matched 0 products across 5 merchants.",
            "selectedProductIds": [],
            "productQuantities": {},
            "reasoning": f"No products found matching \"{intent}\" across our 5 merchant stores.",
            "shouldStop": True,
        }
    else:
        # General store browsing
        sorted_by_price = sorted([p for p in all_products if p["inventory"] > 0], key=lambda x: x["price"], reverse=True)
        for p in sorted_by_price:
            if p["id"] not in selected_ids and current_sum + p["price"] <= remaining_budget:
                selected_products.append(p)
                selected_ids.add(p["id"])
                product_quantities[p["id"]] = 1
                current_sum += p["price"]
                if len(selected_products) >= 2:
                    break

    item_descs = []
    for p in selected_products:
        m = get_merchant_by_id(p["merchant_id"])
        m_name = m["name"] if m else "Merchant"
        qty = product_quantities.get(p["id"], 1)
        stock = p.get("inventory", 50)
        
        qty_str = f"**{qty}x** " if qty > 1 else ""
        total_price_str = format_price(qty * p["price"])
        unit_price_str = f" ({format_price(p['price'])} each)" if qty > 1 else ""
        
        cap_note = ""
        if requested_qty > stock and qty == stock:
            cap_note = f"\n  └ ⚠️ *Inventory Cap Notice*: Requested {requested_qty} units, but capped at maximum available store inventory of **{stock} units**."
        elif requested_qty > qty and qty < stock:
            cap_note = f"\n  └ ⚠️ *Budget Limit Cap*: Capped at **{qty} units** to stay strictly within your remaining budget of {format_price(remaining_budget)}."

        specs = p.get("ai_specs", {})
        spec_summary = ", ".join([f"{v}" for k, v in list(specs.items())[:2]]) if specs else ""
        spec_text = f" ({spec_summary})" if spec_summary else ""
        item_descs.append(f"{qty_str}**{p['name']}** from {m_name} — Total: **{total_price_str}**{unit_price_str}{spec_text}:{cap_note}\n  └ *Key Specs & Description*: {p['description']}")

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
        "productQuantities": product_quantities,
        "upsellProducts": upsell_products,
        "reasoning": reasoning,
        "shouldStop": current_sum >= remaining_budget * 0.85 or len(selected_products) == 0,
    }
