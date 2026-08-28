import os
import json
import re
import google.generativeai as genai
from typing import List, Dict, Any, Optional
from db import get_products, get_product_by_id, format_price, get_merchant_by_id, log_audit, get_top_co_purchased_products

# ── Merchant-Side Configurable Constants ──────────────────────────
UPSELL_PRICE_MULTIPLE_CAP = 3.0   # Max upsell-to-base price ratio for non-tagged upgrades
LOW_STOCK_THRESHOLD = 5            # Below this inventory count → eligible for low-stock campaign
MAX_DISCOUNT_PERCENT = 30          # Hard cap on auto-generated campaign discount percentage
MIN_CO_PURCHASE_SAMPLE = 3         # Min times a pair must be bought together before co-purchase data overrides curated fallback
MIN_PERCENTAGE_SAMPLE = 5          # Min total base product orders required before displaying percentage claims


def is_gemini_configured() -> bool:
    key = os.getenv("GEMINI_API_KEY", "")
    return bool(key) and key != "REPLACE_ME"


def _max_cart_price(cart: List[Dict[str, Any]]) -> int:
    """Return the highest single-item price in the cart (paise)."""
    prices = [item.get("product", {}).get("price", 0) for item in cart]
    return max(prices) if prices else 0


def _cart_tagged_ids(cart: List[Dict[str, Any]]) -> set:
    """Collect all explicitly tagged upsell_ids and cross_sell_ids from the cart items."""
    ids = set()
    for item in cart:
        prod = item.get("product", {})
        ids.update(prod.get("upsell_ids", []))
        ids.update(prod.get("cross_sell_ids", []))
    return ids


def _validate_upsell_candidate(
    product: Dict[str, Any],
    merchant_id: str,
    max_price_paise: int,
    cart_product_ids: set,
    cart_product_names: set,
    agent_id: str,
) -> Optional[str]:
    """
    Validate a single upsell candidate against bounded/gated rules.
    Returns None if valid, or a rejection reason string if invalid.
    """
    # Gate 0: Already in cart or duplicate name
    if product.get("id") in cart_product_ids or product.get("name", "").lower().strip() in cart_product_names:
        return f"Product '{product['name']}' is already in the cart"

    # Gate 1: Out of stock
    if product.get("inventory", 0) <= 0:
        return f"Product '{product['name']}' is out of stock (inventory=0)"

    # Gate 2: Cross-merchant (product belongs to a different merchant)
    if product.get("merchant_id") != merchant_id:
        return f"Product '{product['name']}' belongs to merchant '{product.get('merchant_id')}', not '{merchant_id}'"

    # Gate 3: Unconditional 3.0x Price-Multiple Cap (Strict Hard Cap for ALL recommendations)
    if max_price_paise > 0:
        ratio = product["price"] / max_price_paise
        if ratio > UPSELL_PRICE_MULTIPLE_CAP:
            return (
                f"Product '{product['name']}' ({format_price(product['price'])}) exceeds "
                f"{UPSELL_PRICE_MULTIPLE_CAP}x price cap of base cart item "
                f"({format_price(max_price_paise)}), ratio={ratio:.1f}x"
            )

    return None  # Valid


def run_merchant_upsell_agent(
    cart: List[Dict[str, Any]],
    merchant_id: str,
    simulate_gemini_failure: bool = False,
) -> List[Dict[str, Any]]:
    """
    Analyzes cart items and generates AI upsell suggestions for the specified merchant.
    Enforces bounded/gated rules and logs every recommendation and rejection to audit_logs.
    """
    agent_id = f"merchant_agent_{merchant_id}"

    if not cart:
        return []

    cart_ids = {item["product"]["id"] for item in cart if "product" in item}
    cart_names = {item["product"]["name"].lower().strip() for item in cart if "product" in item}
    all_products = get_products(merchant_id)
    candidates = [p for p in all_products if p["id"] not in cart_ids and p["name"].lower().strip() not in cart_names and p["inventory"] > 0]

    if not candidates:
        return []

    max_price = _max_cart_price(cart)

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

    suggestions_raw = []
    used_fallback = False

    if simulate_gemini_failure:
        log_audit(
            agent_id=agent_id,
            agent_type="MERCHANT",
            action_type="upsell_llm_error",
            status="FAILED",
            merchant_id=merchant_id,
            reasoning="Simulated Gemini API failure — falling back to keyword-matching upsell logic.",
        )
        return _validated_mock_suggestions(cart, candidates, merchant_id, max_price, cart_ids, cart_names, agent_id)

    return _validated_mock_suggestions(cart, candidates, merchant_id, max_price, cart_ids, cart_names, agent_id)

    try:
        model = genai.GenerativeModel("models/gemini-3.6-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()

        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            raise ValueError("No JSON array found in Gemini response")

        suggestions_raw = json.loads(match.group(0))
    except Exception as e:
        print(f"[Merchant Upsell Fallback]: {e}")
        log_audit(
            agent_id=agent_id,
            agent_type="MERCHANT",
            action_type="upsell_llm_error",
            status="FAILED",
            merchant_id=merchant_id,
            reasoning=f"Gemini API error: {str(e)[:200]} — falling back to keyword-matching upsell logic.",
        )
        return _validated_mock_suggestions(cart, candidates, merchant_id, max_price, cart_ids, cart_names, agent_id)

    # Post-Gemini validation: re-check every product ID returned by the LLM
    results = []
    for s in suggestions_raw[:3]:
        validated_prods = []
        for pid in s.get("productIds", []):
            prod = get_product_by_id(pid)
            if not prod:
                continue

            rejection = _validate_upsell_candidate(prod, merchant_id, max_price, cart_ids, cart_names, agent_id)
            if rejection:
                log_audit(
                    agent_id=agent_id,
                    agent_type="MERCHANT",
                    action_type="UPSELL_REJECTED",
                    status="BLOCKED",
                    merchant_id=merchant_id,
                    reasoning=rejection,
                    amount_paise=prod["price"],
                    payload={"rejectedProductId": pid, "baseCartIds": list(cart_ids)},
                )
                continue

            validated_prods.append(prod)

        if validated_prods:
            potential_rev = sum(p["price"] for p in validated_prods)
            suggestion = {
                "type": s.get("type", "UPSELL"),
                "products": validated_prods,
                "reasoning": s.get("reasoning", "Recommended add-on item."),
                "potentialRevenuePaise": potential_rev,
            }
            results.append(suggestion)

            # Log each accepted recommendation
            log_audit(
                agent_id=agent_id,
                agent_type="MERCHANT",
                action_type="UPSELL_RECOMMENDED",
                status="SUCCESS",
                merchant_id=merchant_id,
                reasoning=suggestion["reasoning"],
                amount_paise=potential_rev,
                payload={
                    "recommendedProductIds": [p["id"] for p in validated_prods],
                    "baseCartIds": list(cart_ids),
                    "type": suggestion["type"],
                },
            )

    return results


def _validated_mock_suggestions(
    cart: List[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    merchant_id: str,
    max_price: int,
    cart_ids: set,
    cart_names: set,
    agent_id: str,
) -> List[Dict[str, Any]]:
    """
    PART B & C: Generate upsell suggestions using real co-purchase data first,
    falling back to curated cross_sell_ids/upsell_ids.
    Applies identical safety gates and logs exact source tracking.
    """
    suggestions = []

    for item in cart:
        prod = item.get("product", {})
        base_id = prod.get("id")
        prod_db = get_product_by_id(base_id) if base_id else prod
        if prod_db:
            base_name = prod_db.get("name", "this product")
            upsell_ids = prod_db.get("upsell_ids", [])
            cross_ids = prod_db.get("cross_sell_ids", [])
        else:
            base_name = prod.get("name", "this product")
            upsell_ids = prod.get("upsell_ids", [])
            cross_ids = prod.get("cross_sell_ids", [])

        found_co_purchase = False

        # ── Step 1: PRIMARY — Try Real Co-Purchase Data First (PART B & D & Fix 2) ────────
        try:
            if base_id:
                co_candidates = get_top_co_purchased_products(base_id, merchant_id, min_times=MIN_CO_PURCHASE_SAMPLE)
                for co_item in co_candidates:
                    co_prod = co_item["product"]
                    times = co_item["times_bought_together"]
                    pct = co_item["co_occurrence_pct"]

                    rejection = _validate_upsell_candidate(co_prod, merchant_id, max_price, cart_ids, cart_names, agent_id)
                    if rejection:
                        log_audit(
                            agent_id=agent_id,
                            agent_type="MERCHANT",
                            action_type="UPSELL_REJECTED",
                            status="BLOCKED",
                            merchant_id=merchant_id,
                            reasoning=f"{rejection} [Source: co_purchase_data]",
                            amount_paise=co_prod["price"],
                            payload={"rejectedProductId": co_prod["id"], "baseProductId": base_id, "source": "co_purchase_data"},
                            source="co_purchase_data",
                        )
                        continue

                    # Found valid co-purchase candidate passing all safety gates
                    if pct is not None:
                        reasoning = f"Buyers who purchased {base_name} also purchased {co_prod['name']} in {pct}% of cases ({times} co-purchases)."
                    else:
                        reasoning = f"Buyers who purchased {base_name} also frequently purchased {co_prod['name']} ({times} co-purchases)."

                    suggestions.append({
                        "type": "CROSS_SELL",
                        "products": [co_prod],
                        "reasoning": reasoning,
                        "potentialRevenuePaise": co_prod["price"],
                        "source": "co_purchase_data",
                        "times_bought_together": times,
                        "co_occurrence_pct": pct,
                    })

                    log_audit(
                        agent_id=agent_id,
                        agent_type="MERCHANT",
                        action_type="UPSELL_RECOMMENDED",
                        status="SUCCESS",
                        merchant_id=merchant_id,
                        reasoning=reasoning,
                        amount_paise=co_prod["price"],
                        payload={
                            "recommendedProductIds": [co_prod["id"]],
                            "type": "CROSS_SELL",
                            "source": "co_purchase_data",
                            "times_bought_together": times,
                            "co_occurrence_pct": pct,
                        },
                        source="co_purchase_data",
                    )
                    found_co_purchase = True
                    break
        except Exception as e:
            print(f"[Co-Purchase Lookup Fallback]: {e}")
            found_co_purchase = False

        if found_co_purchase:
            continue

        # ── Step 2: COLD-START FALLBACK — Curated Catalog Graph ──────────
        # Check upsells
        for uid in upsell_ids:
            if uid in cart_ids:
                continue
            up_prod = get_product_by_id(uid)
            if not up_prod:
                continue

            rejection = _validate_upsell_candidate(up_prod, merchant_id, max_price, cart_ids, cart_names, agent_id)
            if rejection:
                log_audit(
                    agent_id=agent_id,
                    agent_type="MERCHANT",
                    action_type="UPSELL_REJECTED",
                    status="BLOCKED",
                    merchant_id=merchant_id,
                    reasoning=f"{rejection} [Source: curated_fallback]",
                    amount_paise=up_prod["price"],
                    payload={"rejectedProductId": uid, "baseProductId": base_id, "source": "curated_fallback"},
                    source="curated_fallback",
                )
                continue

            reasoning = f"Customers buying {base_name} often upgrade to {up_prod['name']}."
            suggestions.append({
                "type": "UPSELL",
                "products": [up_prod],
                "reasoning": reasoning,
                "potentialRevenuePaise": up_prod["price"],
                "source": "curated_fallback",
            })
            log_audit(
                agent_id=agent_id,
                agent_type="MERCHANT",
                action_type="UPSELL_RECOMMENDED",
                status="SUCCESS",
                merchant_id=merchant_id,
                reasoning=reasoning,
                amount_paise=up_prod["price"],
                payload={"recommendedProductIds": [up_prod["id"]], "type": "UPSELL", "source": "curated_fallback"},
                source="curated_fallback",
            )
        # Check cross-sells
        for cid in cross_ids:
            if cid in cart_ids:
                continue
            cross_prod = get_product_by_id(cid)
            if not cross_prod:
                continue

            rejection = _validate_upsell_candidate(cross_prod, merchant_id, max_price, cart_ids, cart_names, agent_id)
            if rejection:
                log_audit(
                    agent_id=agent_id,
                    agent_type="MERCHANT",
                    action_type="UPSELL_REJECTED",
                    status="BLOCKED",
                    merchant_id=merchant_id,
                    reasoning=f"{rejection} [Source: curated_fallback]",
                    amount_paise=cross_prod["price"],
                    payload={"rejectedProductId": cid, "baseProductId": base_id, "source": "curated_fallback"},
                    source="curated_fallback",
                )
                continue

            reasoning = f"{cross_prod['name']} complements {base_name} perfectly."
            suggestions.append({
                "type": "CROSS_SELL",
                "products": [cross_prod],
                "reasoning": reasoning,
                "potentialRevenuePaise": cross_prod["price"],
                "source": "curated_fallback",
            })
            log_audit(
                agent_id=agent_id,
                agent_type="MERCHANT",
                action_type="UPSELL_RECOMMENDED",
                status="SUCCESS",
                merchant_id=merchant_id,
                reasoning=reasoning,
                amount_paise=cross_prod["price"],
                payload={"recommendedProductIds": [cid], "baseProductId": base_id, "type": "CROSS_SELL", "source": "curated_fallback"},
                source="curated_fallback",
            )

        if len(suggestions) >= 3:
            break

    # Fallback: pick a generic candidate if no relationship-based suggestions
    if not suggestions and candidates:
        for c in candidates:
            rejection = _validate_upsell_candidate(c, merchant_id, max_price, cart_ids, cart_names, agent_id)
            if rejection:
                log_audit(
                    agent_id=agent_id,
                    agent_type="MERCHANT",
                    action_type="UPSELL_REJECTED",
                    status="BLOCKED",
                    merchant_id=merchant_id,
                    reasoning=f"{rejection} [Source: curated_fallback]",
                    amount_paise=c["price"],
                    payload={"rejectedProductId": c["id"], "source": "curated_fallback"},
                    source="curated_fallback",
                )
                continue
            reasoning = f"{c['name']} is a popular choice for this store."
            suggestions.append({
                "type": "CROSS_SELL",
                "products": [c],
                "reasoning": reasoning,
                "potentialRevenuePaise": c["price"],
                "source": "curated_fallback",
            })
            log_audit(
                agent_id=agent_id,
                agent_type="MERCHANT",
                action_type="UPSELL_RECOMMENDED",
                status="SUCCESS",
                merchant_id=merchant_id,
                reasoning=reasoning,
                amount_paise=c["price"],
                payload={"recommendedProductIds": [c["id"]], "type": "CROSS_SELL", "source": "curated_fallback"},
                source="curated_fallback",
            )
            break

    return suggestions[:3]


def generate_campaign_idea(merchant_id: str, revenue_goal_paise: int = 5000000, product_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Scans low-stock inventory for a merchant and generates a promotional campaign strategy.
    Enforces LOW_STOCK_THRESHOLD, separates out-of-stock from low-stock, and caps discount.
    """
    merchant = get_merchant_by_id(merchant_id)
    merchant_name = merchant["name"] if merchant else "Merchant Store"

    all_prods = get_products(merchant_id)

    # If a specific product is requested, use it; otherwise find low-stock products
    if product_id:
        target = get_product_by_id(product_id)
        if target:
            low_stock = [target] if 0 < target["inventory"] <= LOW_STOCK_THRESHOLD else []
            is_oos = target["inventory"] <= 0
        else:
            low_stock = []
            is_oos = False
    else:
        low_stock = [p for p in all_prods if 0 < p["inventory"] <= LOW_STOCK_THRESHOLD]
        is_oos = False

    if not low_stock:
        # If no genuine low-stock, pick first 2 products as sample (for general campaign)
        low_stock = [p for p in all_prods if p["inventory"] > 0][:2]

    if not low_stock:
        low_stock = all_prods[:2] if all_prods else []

    primary_prod = low_stock[0] if low_stock else None
    primary_name = primary_prod["name"] if primary_prod else "Promotional Item"

    if not is_gemini_configured():
        campaign = {
            "name": f"Flash Sale: {primary_name}",
            "description": f"Limited time offer on {primary_name} from {merchant_name}. Stock running low ({primary_prod['inventory']} left)!",
            "targetAudience": "Productivity & setup enthusiasts",
            "discountPercent": 15,
        }
    else:
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

            campaign = json.loads(match.group(0))
        except Exception as e:
            print(f"[Campaign Generator Fallback]: {e}")
            campaign = {
                "name": f"Flash Sale: {low_stock[0]['name']}" if low_stock else "Flash Sale",
                "description": f"Limited time offer on {product_names} from {merchant_name}.",
                "targetAudience": "Productivity & setup enthusiasts",
                "discountPercent": 15,
            }

    # Enforce MAX_DISCOUNT_PERCENT hard cap
    original_discount = campaign.get("discountPercent", 15)
    if original_discount > MAX_DISCOUNT_PERCENT:
        campaign["discountPercent"] = MAX_DISCOUNT_PERCENT
        campaign["discountCapped"] = True
        campaign["originalDiscountPercent"] = original_discount
    else:
        campaign["discountCapped"] = False

    # Attach metadata for the caller
    campaign["lowStockProducts"] = [{"id": p["id"], "name": p["name"], "inventory": p["inventory"], "price": p["price"]} for p in low_stock[:3]]
    campaign["primaryPricePaise"] = low_stock[0]["price"] if low_stock else 44900

    return campaign
