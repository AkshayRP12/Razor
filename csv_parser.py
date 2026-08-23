import os
import json
import re
import csv
import io
import google.generativeai as genai
from typing import List, Dict, Any
from db import insert_product, get_merchant_by_id, log_audit

def is_gemini_configured() -> bool:
    key = os.getenv("GEMINI_API_KEY", "")
    return bool(key) and key != "REPLACE_ME"

def parse_and_import_csv(csv_text: str, merchant_id: str) -> Dict[str, Any]:
    """
    Parses arbitrary CSV product text using Gemini AI or fallback, mapping headers to standard schema.
    Inserts products into SQLite database and logs audit entry.
    """
    merchant = get_merchant_by_id(merchant_id)
    if not merchant:
        raise ValueError(f"Merchant with ID '{merchant_id}' not found.")

    products_data: List[Dict[str, Any]] = []

    if is_gemini_configured():
        prompt = f"""You are a product data parser for the store "{merchant['name']}" ({merchant['category']}).

Parse the following CSV text into a JSON array of products. The CSV may have non-standard headers — map them intelligently.

CSV DATA:
{csv_text}

Return ONLY a valid JSON array where each object has:
{{
  "name": "Product Name",
  "description": "A brief description",
  "category": "Product category",
  "price": 99900,           // price in PAISE (INR x 100). If CSV gives price in rupees, multiply by 100.
  "originalPrice": null,     // optional, in paise
  "inventory": 50,           // stock count
  "tags": ["tag1", "tag2"],  // relevant tags
  "aiSpecs": {{"key": "value"}}
}}

IMPORTANT: price must be in PAISE (not rupees). If CSV says "2499", that means ₹2499 = 249900 paise.
Return ONLY the JSON array. No explanation."""

        try:
            model = genai.GenerativeModel("models/gemini-3.6-flash")
            response = model.generate_content(prompt)
            text = response.text.strip()

            match = re.search(r"\[[\s\S]*\]", text)
            if match:
                products_data = json.loads(match.group(0))
            else:
                products_data = fallback_csv_parse(csv_text)
        except Exception as e:
            print(f"[CSV Gemini Parsing Fallback]: {e}")
            products_data = fallback_csv_parse(csv_text)
    else:
        products_data = fallback_csv_parse(csv_text)

    imported_count = 0
    for item in products_data:
        try:
            insert_product(
                merchant_id=merchant_id,
                name=item.get("name", "Unnamed Product"),
                description=item.get("description", ""),
                category=item.get("category", merchant["category"]),
                price=item.get("price", 99900),
                original_price=item.get("originalPrice"),
                inventory=item.get("inventory", 50),
                tags=item.get("tags", []),
            )
            imported_count += 1
        except Exception as err:
            print(f"Failed to insert product: {item.get('name')} - {err}")

    log_audit(
        agent_id="csv_import_python",
        agent_type="MERCHANT",
        action_type="CATALOG_FETCH",
        status="SUCCESS" if imported_count > 0 else "FAILED",
        merchant_id=merchant_id,
        reasoning=f"CSV import: {imported_count} products added to {merchant['name']} catalog via Python backend."
    )

    return {
        "imported": imported_count,
        "total": len(products_data),
        "merchantName": merchant["name"]
    }

def fallback_csv_parse(csv_text: str) -> List[Dict[str, Any]]:
    """Fallback manual CSV parser if Gemini AI parsing is disabled or fails."""
    results = []
    f = io.StringIO(csv_text.strip())
    reader = csv.reader(f)
    rows = list(reader)
    if len(rows) < 2:
        return results

    headers = [h.strip().lower() for h in rows[0]]

    def find_idx(keywords: List[str]) -> int:
        for i, h in enumerate(headers):
            if any(k in h for k in keywords):
                return i
        return -1

    name_idx = find_idx(["name", "product", "title"])
    price_idx = find_idx(["price", "cost", "mrp", "rate"])
    cat_idx = find_idx(["category", "type", "group"])
    stock_idx = find_idx(["stock", "inventory", "qty", "count"])
    desc_idx = find_idx(["description", "desc", "detail"])

    for row in rows[1:]:
        if not row or len(row) < 2:
            continue

        name = row[name_idx] if name_idx >= 0 and name_idx < len(row) else row[0]
        
        # Parse price
        price_str = row[price_idx] if price_idx >= 0 and price_idx < len(row) else "999"
        try:
            val = float(re.sub(r"[^\d.]", "", price_str))
            price_paise = int(val * 100)
        except ValueError:
            price_paise = 99900

        category = row[cat_idx] if cat_idx >= 0 and cat_idx < len(row) else "General"
        
        # Parse stock
        stock_str = row[stock_idx] if stock_idx >= 0 and stock_idx < len(row) else "50"
        try:
            inventory = int(re.sub(r"\D", "", stock_str))
        except ValueError:
            inventory = 50

        description = row[desc_idx] if desc_idx >= 0 and desc_idx < len(row) else ""

        results.append({
            "name": name,
            "description": description,
            "category": category,
            "price": price_paise,
            "inventory": inventory,
            "tags": [category.lower()]
        })

    return results
