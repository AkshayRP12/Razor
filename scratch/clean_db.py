import sqlite3
import json
from db import seed_or_update

def cleanup_and_fix_prices():
    conn = sqlite3.connect("aria.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Fix any products where price was double-multiplied by 100
    products = cursor.execute("SELECT id, name, price FROM products").fetchall()
    fixed_count = 0
    for p in products:
        # If a face wash, moisturizer, or keyboard has a price >= 4000000 (>= ₹40,000) but shouldn't, divide by 100
        name_lower = p["name"].lower()
        price = p["price"]
        if ("moisturizer" in name_lower or "face wash" in name_lower or "facewash" in name_lower or "cleanser" in name_lower or "keyboard" in name_lower or "mouse" in name_lower) and price >= 3000000:
            new_price = price // 100
            cursor.execute("UPDATE products SET price = ? WHERE id = ?", (new_price, p["id"]))
            print(f"Fixed price for '{p['name']}': {price} -> {new_price}")
            fixed_count += 1

    # 2. Delete duplicate CSV imports
    rows = cursor.execute("SELECT id, merchant_id, name, price, inventory FROM products").fetchall()
    seen = {}
    duplicates_to_delete = []

    for r in rows:
        key = (r["merchant_id"], r["name"].strip().lower())
        if key in seen:
            existing_id = seen[key]
            if r["id"].startswith("prod_csv_"):
                duplicates_to_delete.append(r["id"])
            elif existing_id.startswith("prod_csv_"):
                duplicates_to_delete.append(existing_id)
                seen[key] = r["id"]
            else:
                duplicates_to_delete.append(r["id"])
        else:
            seen[key] = r["id"]

    if duplicates_to_delete:
        cursor.executemany("DELETE FROM products WHERE id = ?", [(d,) for d in duplicates_to_delete])
        print(f"Deleted {len(duplicates_to_delete)} duplicate products.")

    conn.commit()
    seed_or_update(conn)
    conn.close()

if __name__ == "__main__":
    cleanup_and_fix_prices()
