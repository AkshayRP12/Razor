import sqlite3
import csv
import json
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aria.db")
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "products_catalog.csv")

def export_db_to_csv():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT 
            p.id as product_id,
            m.name as merchant_name,
            m.slug as merchant_slug,
            p.name as product_name,
            p.category,
            p.price / 100.0 as price_inr,
            CASE WHEN p.original_price IS NOT NULL THEN p.original_price / 100.0 ELSE NULL END as original_price_inr,
            p.inventory,
            p.tags,
            p.ai_specs,
            p.description
        FROM products p
        JOIN merchants m ON p.merchant_id = m.id
        ORDER BY m.name, p.category, p.price DESC
    """

    rows = cursor.execute(query).fetchall()
    conn.close()

    headers = [
        "Product ID",
        "Merchant Store",
        "Merchant Slug",
        "Product Name",
        "Category",
        "Price (INR)",
        "Original Price (INR)",
        "Stock Inventory",
        "Tags",
        "Technical AI Specs",
        "Full Description"
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for r in rows:
            tags_list = ", ".join(json.loads(r["tags"] or "[]"))
            specs_dict = json.loads(r["ai_specs"] or "{}")
            specs_str = " | ".join([f"{k}: {v}" for k, v in specs_dict.items()]) if specs_dict else ""

            writer.writerow([
                r["product_id"],
                r["merchant_name"],
                r["merchant_slug"],
                r["product_name"],
                r["category"],
                f"₹{r['price_inr']:,.2f}",
                f"₹{r['original_price_inr']:,.2f}" if r["original_price_inr"] else "",
                r["inventory"],
                tags_list,
                specs_str,
                r["description"]
            ])

    print(f"Successfully exported {len(rows)} products to {OUTPUT_CSV}")

if __name__ == "__main__":
    export_db_to_csv()
