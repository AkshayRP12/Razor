import os
import json
import re
import google.generativeai as genai
from typing import List, Dict, Any
from db import get_products, get_product_by_id, format_price, get_merchant_by_id

def is_gemini_configured() -> bool:
    key = os.getenv("GEMINI_API_KEY", "")
    return bool(key) and key != "REPLACE_ME"

def run_merchant_upsell_agent(cart: List[Dict[str, Any]], merchant_id: str) -> List[Dict[str, Any]]:
    """
    Analyzes cart items and generates AI upsell suggestions for the specified merchant.
    """
    if not cart:
        return []

    cart_ids = {item["product"]["id"] for item in cart if "product" in item}
    all_products = get_products(merchant_id)
    candidates = [p for p in all_products if p["id"] not in cart_ids and p["inventory"] > 0]

    if not candidates:
        return []

    cart_summary = "\n".join([
        f"- {item['product']['name']} (qty: {item.get('quantity', 1)}) | {format_price(item['product']['price'])}"
        for item in cart if "product" in item
    ])

    candidates_summary = "\n".join([
        f"[{p['id']}] {p['name']} | {format_price(p['price'])} | Tags: {', '.join(p['tags'])}"
        for p in candidates
    ])

    prompt = f"""You are ARIA's Merchant Revenue Agent. Suggest relevant upsells for the store.

CURRENT CART:
{cart_summary}

UPSELL/CROSS-SELL CANDIDATES:
{candidates_summary}

Generate 2-3 targeted suggestions in this EXACT JSON format:
[
  {{
    "type": "UPSELL",
    "productIds": ["prod_XXX"],
    "reasoning": "Why this fits the customer's cart",
    "confidence": 0.9
  }}
]"""

    if not is_gemini_configured():
        return get_mock_upsell_suggestions(cart, candidates)

    try:
        model = genai.GenerativeModel("models/gemini-3.6-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()

        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            raise ValueError("No JSON array found")

        suggestions_raw = json.loads(match.group(0))
        results = []
        for s in suggestions_raw[:3]:
            prods = [get_product_by_id(pid) for pid in s.get("productIds", []) if get_product_by_id(pid)]
            if prods:
                potential_rev = sum(p["price"] for p in prods)
                results.append({
                    "type": s.get("type", "UPSELL"),
                    "products": prods,
                    "reasoning": s.get("reasoning", "Recommended add-on item."),
                    "potentialRevenuePaise": potential_rev
                })
        return results
    except Exception as e:
        print(f"[Merchant Upsell Fallback]: {e}")
        return get_mock_upsell_suggestions(cart, candidates)

def get_mock_upsell_suggestions(cart: List[Dict[str, Any]], candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mock upsell recommendation logic based on product upsell_ids & cross_sell_ids."""
    suggestions = []
    cart_ids = {item["product"]["id"] for item in cart if "product" in item}

    for item in cart:
        prod = item.get("product", {})
        upsell_ids = prod.get("upsell_ids", [])
        cross_ids = prod.get("cross_sell_ids", [])

        # Check upsells
        upsell_prods = [get_product_by_id(uid) for uid in upsell_ids if uid not in cart_ids and get_product_by_id(uid)]
        if upsell_prods:
            suggestions.append({
                "type": "UPSELL",
                "products": upsell_prods,
                "reasoning": f"Customers buying {prod.get('name', 'this product')} often upgrade to {upsell_prods[0]['name']}.",
                "potentialRevenuePaise": sum(p["price"] for p in upsell_prods)
            })

        # Check cross-sells
        cross_prods = [get_product_by_id(cid) for cid in cross_ids if cid not in cart_ids and get_product_by_id(cid)]
        if cross_prods:
            suggestions.append({
                "type": "CROSS_SELL",
                "products": cross_prods[:1],
                "reasoning": f"{cross_prods[0]['name']} complements {prod.get('name', 'this product')} perfectly.",
                "potentialRevenuePaise": cross_prods[0]["price"]
            })

        if len(suggestions) >= 3:
            break

    # If no suggestions found from relationships, pick candidate items
    if not suggestions and candidates:
        suggestions.append({
            "type": "CROSS_SELL",
            "products": candidates[:1],
            "reasoning": f"{candidates[0]['name']} is a popular choice for this store.",
            "potentialRevenuePaise": candidates[0]["price"]
        })

    return suggestions[:3]

def generate_campaign_idea(merchant_id: str, revenue_goal_paise: int = 5000000) -> Dict[str, Any]:
    """
    Scans low-stock inventory for a merchant and generates a promotional campaign strategy.
    """
    merchant = get_merchant_by_id(merchant_id)
    merchant_name = merchant["name"] if merchant else "Merchant Store"

    all_prods = get_products(merchant_id)
    low_stock = [p for p in all_prods if p["inventory"] <= 25]
    if not low_stock:
        low_stock = all_prods[:2]

    product_names = ", ".join([p["name"] for p in low_stock[:3]])

    if not is_gemini_configured():
        return {
            "name": f"Flash Sale: {low_stock[0]['name']}",
            "description": f"Limited time offer on {product_names} from {merchant_name}. Stock running low!",
            "targetAudience": "Productivity & setup enthusiasts",
            "discountPercent": 15
        }

    prompt = f"""You are ARIA's Campaign Orchestrator for {merchant_name}. Create a compelling campaign strategy.

LOW INVENTORY PRODUCTS:
{chr(10).join([f"- {p['name']} | {format_price(p['price'])} | {p['inventory']} left" for p in low_stock[:3]])}

REVENUE GOAL: {format_price(revenue_goal_paise)}

Create a campaign in this EXACT JSON format:
{{
  "name": "Campaign name (5 words max)",
  "description": "2-sentence description",
  "targetAudience": "Who this target audience is",
  "discountPercent": 15
}}"""

    try:
        model = genai.GenerativeModel("models/gemini-3.6-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()

        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("No JSON object found")

        return json.loads(match.group(0))
    except Exception as e:
        print(f"[Campaign Generator Fallback]: {e}")
        return {
            "name": f"Flash Sale: {low_stock[0]['name']}",
            "description": f"Limited time offer on {product_names} from {merchant_name}.",
            "targetAudience": "Productivity & setup enthusiasts",
            "discountPercent": 15
        }
