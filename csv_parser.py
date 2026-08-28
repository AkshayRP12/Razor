import os
import json
import re
import csv
import io
import google.generativeai as genai
from typing import List, Dict, Any
from db import insert_product, upsert_product_from_csv, get_merchant_by_id, get_merchants, log_audit

# ── CSV Import Configurable Constants ─────────────────────────────
MAX_CSV_ROWS = 5000  # Max rows accepted in a single CSV import


def is_gemini_configured() -> bool:
    key = os.getenv("GEMINI_API_KEY", "")
    return bool(key) and key != "REPLACE_ME"


def parse_and_import_csv(csv_text: str, merchant_id: str) -> Dict[str, Any]:
    """
    Parses arbitrary CSV product text using Gemini AI or fallback, mapping headers to standard schema.
    Validates each row before insertion. Rejects invalid rows without crashing.
    Inserts valid products into SQLite database and logs audit entry with summary counts.
    """
    merchant = get_merchant_by_id(merchant_id)
    if not merchant:
        raise ValueError(f"Merchant with ID '{merchant_id}' not found.")

    # ── Clean BOM & Normalize Line Endings ─────────────────────────
    csv_text = (csv_text or "").strip("\ufeff\ufffe \t\r\n").replace("\r\n", "\n").replace("\r", "\n")

    if not csv_text:
        log_audit(
            agent_id="csv_import_python",
            agent_type="MERCHANT",
            action_type="csv_import_error",
            status="FAILED",
            merchant_id=merchant_id,
            reasoning="CSV import failed: uploaded file is empty.",
        )
        return {
            "error": True,
            "message": "This file is empty — please upload a CSV file with product data.",
            "imported": 0,
            "rejected": 0,
            "total": 0,
            "rejectedReasons": [],
            "merchantName": merchant["name"],
        }

    # Auto-detect delimiter (comma, semicolon, or tab)
    delimiter = ","
    lines_raw = csv_text.splitlines()
    first_line = lines_raw[0] if lines_raw else ""
    if ";" in first_line and "," not in first_line:
        delimiter = ";"
    elif "\t" in first_line and "," not in first_line:
        delimiter = "\t"

    # ── Robust CSV row extraction ──────────────────────────────────
    try:
        f_test = io.StringIO(csv_text)
        reader_test = csv.reader(f_test, delimiter=delimiter)
        rows_test = [row for row in reader_test if any(str(cell).strip() for cell in row)]
    except Exception:
        rows_test = [
            [cell.strip() for cell in line.split(delimiter)]
            for line in csv_text.splitlines()
            if line.strip()
        ]

    if len(rows_test) < 2:
        log_audit(
            agent_id="csv_import_python",
            agent_type="MERCHANT",
            action_type="csv_import_error",
            status="FAILED",
            merchant_id=merchant_id,
            reasoning="CSV import failed: file has fewer than 2 rows (need at least a header + 1 data row).",
        )
        return {
            "error": True,
            "message": "This file could not be read as a CSV — please check the format and try again. A CSV file needs at least a header row and one data row.",
            "imported": 0,
            "rejected": 0,
            "total": 0,
            "rejectedReasons": [],
            "merchantName": merchant["name"],
        }

    # Check max row cap
    data_row_count = len(rows_test) - 1  # exclude header
    if data_row_count > MAX_CSV_ROWS:
        log_audit(
            agent_id="csv_import_python",
            agent_type="MERCHANT",
            action_type="csv_import_error",
            status="FAILED",
            merchant_id=merchant_id,
            reasoning=f"CSV import rejected: file contains {data_row_count} data rows, exceeding the maximum of {MAX_CSV_ROWS}.",
        )
        return {
            "error": True,
            "message": f"This CSV file has {data_row_count} rows, which exceeds the maximum of {MAX_CSV_ROWS} rows per import. Please split the file and try again.",
            "imported": 0,
            "rejected": 0,
            "total": data_row_count,
            "rejectedReasons": [],
            "merchantName": merchant["name"],
        }

    # ── Parse CSV into product dicts ──────────────────────────────
    products_data: List[Dict[str, Any]] = []

    if is_gemini_configured():
        prompt = f"""You are a product data parser for the store "{merchant['name']}" ({merchant['category']}).

Parse the following CSV text into a JSON array of products. The CSV may have non-standard headers — map them intelligently.

CSV DATA:
{csv_text}

Return ONLY a valid JSON array where each object has:
{{
  "merchantName": "Store Name", // optional merchant or store name if present in CSV
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

    # ── Row-level validation and insertion ─────────────────────────
    imported_count = 0
    rejected_count = 0
    rejected_reasons: List[str] = []

    for idx, item in enumerate(products_data, start=1):
        # Validate required fields
        name = item.get("name", "").strip() if item.get("name") else ""
        if not name:
            rejected_reasons.append(f"row {idx}: missing required field 'name'")
            rejected_count += 1
            continue

        # Validate price — ensure price is accurately stored in integer PAISE (1 INR = 100 PAISE)
        raw_p = item.get("price", 0)
        try:
            val = float(re.sub(r"[^\d.\-]", "", str(raw_p)))
            if val <= 0:
                rejected_reasons.append(f"row {idx}: negative or zero price ({val})")
                rejected_count += 1
                continue

            # If input is in Rupees (e.g. 449, 699, 2499, 27999), multiply by 100 to get paise.
            # If input is ALREADY in Paise (e.g. 44900, 69900, 249900), keep as is without double multiplying.
            if val < 200000 and not (val >= 10000 and val % 100 == 0):
                price = int(round(val * 100))
            else:
                price = int(round(val))
        except (ValueError, TypeError):
            rejected_reasons.append(f"row {idx}: invalid price value '{raw_p}'")
            rejected_count += 1
            continue

        # Validate inventory
        inventory = item.get("inventory", 50)
        try:
            inventory = int(inventory)
        except (ValueError, TypeError):
            rejected_reasons.append(f"row {idx}: invalid inventory value '{item.get('inventory')}'")
            rejected_count += 1
            continue

        if inventory < 0:
            rejected_reasons.append(f"row {idx}: negative inventory ({inventory})")
            rejected_count += 1
            continue

        # Determine target merchant ID (use row merchant if provided, else default selected merchant)
        target_merchant_id = merchant_id
        raw_m = item.get("merchantName") or item.get("merchant") or item.get("store") or item.get("merchantStore") or item.get("merchant_store")
        if raw_m and str(raw_m).strip():
            raw_m_lower = str(raw_m).strip().lower()
            all_merchants = get_merchants()
            for m in all_merchants:
                if m["id"].lower() == raw_m_lower or m["name"].lower() == raw_m_lower or m["name"].lower() in raw_m_lower or raw_m_lower in m["name"].lower():
                    target_merchant_id = m["id"]
                    break

        if not get_merchant_by_id(target_merchant_id):
            target_merchant_id = merchant_id

        # All validations passed — insert/upsert
        try:
            upsert_product_from_csv(
                merchant_id=target_merchant_id,
                name=name,
                description=item.get("description", ""),
                category=item.get("category", merchant["category"]),
                price=price,
                original_price=item.get("originalPrice"),
                inventory=inventory,
                tags=item.get("tags", []),
            )
            imported_count += 1
        except Exception as err:
            rejected_reasons.append(f"row {idx}: database insertion error — {str(err)[:100]}")
            rejected_count += 1

    # ── Audit log with summary counts ──────────────────────────────
    summary_reasoning = (
        f"CSV import for {merchant['name']}: "
        f"{imported_count} rows imported, {rejected_count} rows rejected "
        f"out of {len(products_data)} total parsed rows."
    )
    if rejected_reasons:
        summary_reasoning += f" Rejections: {'; '.join(rejected_reasons[:10])}"

    log_audit(
        agent_id="csv_import_python",
        agent_type="MERCHANT",
        action_type="CSV_IMPORT",
        status="SUCCESS" if imported_count > 0 else "FAILED",
        merchant_id=merchant_id,
        reasoning=summary_reasoning,
        payload={
            "imported": imported_count,
            "rejected": rejected_count,
            "total": len(products_data),
            "rejectedReasons": rejected_reasons[:20],
        },
    )

    return {
        "imported": imported_count,
        "rejected": rejected_count,
        "total": len(products_data),
        "rejectedReasons": rejected_reasons,
        "merchantName": merchant["name"],
    }


def fallback_csv_parse(csv_text: str) -> List[Dict[str, Any]]:
    """Fallback manual CSV parser if Gemini AI parsing is disabled or fails."""
    results = []
    csv_text = (csv_text or "").strip("\ufeff\ufffe \t\r\n").replace("\r\n", "\n").replace("\r", "\n")
    if not csv_text:
        return results

    lines_raw = csv_text.splitlines()
    first_line = lines_raw[0] if lines_raw else ""
    delimiter = ";" if ";" in first_line and "," not in first_line else ("\t" if "\t" in first_line and "," not in first_line else ",")

    f = io.StringIO(csv_text)
    reader = csv.reader(f, delimiter=delimiter)
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
    merchant_idx = find_idx(["merchant", "store", "vendor", "shop"])

    for row in rows[1:]:
        if not row or len(row) < 1:
            continue

        def get_col(idx: int, default_val: str = "") -> str:
            if idx >= 0 and idx < len(row):
                return row[idx].strip()
            return default_val

        name = get_col(name_idx, row[0] if len(row) > 0 else "")
        merchant_val = get_col(merchant_idx, "")

        # Parse price — keep raw value, validation happens in parse_and_import_csv
        price_str = get_col(price_idx, "999")
        try:
            val = float(re.sub(r"[^\d.\-]", "", price_str))
            price_paise = int(val * 100)
        except ValueError:
            price_paise = 0  # Will be caught by validation

        category = get_col(cat_idx, "General") or "General"

        # Parse stock
        stock_str = get_col(stock_idx, "50")
        try:
            inventory = int(re.sub(r"[^\d\-]", "", stock_str))
        except ValueError:
            inventory = -1  # Will be caught by validation

        description = get_col(desc_idx, "")

        results.append({
            "name": name,
            "merchantName": merchant_val,
            "description": description,
            "category": category,
            "price": price_paise,
            "inventory": inventory,
            "tags": [category.lower()],
        })

    return results
