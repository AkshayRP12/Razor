import sqlite3

def test_sql_analytics():
    conn = sqlite3.connect("aria.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    merchants = ["ALL", "merchant_byteforge", "merchant_homechef", "merchant_deskcraft", "merchant_glowlab", "merchant_sonicwave"]

    for m in merchants:
        m_filter = "" if m == "ALL" else f"AND merchant_id = '{m}'"
        m_where = "" if m == "ALL" else f"WHERE merchant_id = '{m}'"

        total_orders = c.execute(f"SELECT COUNT(*) FROM orders WHERE status IN ('created', 'completed') {m_filter}").fetchone()[0]
        total_rev = c.execute(f"SELECT COALESCE(SUM(amount_paise), 0) FROM orders WHERE status IN ('created', 'completed') {m_filter}").fetchone()[0]
        upsell_orders = c.execute(f"SELECT COUNT(*) FROM orders WHERE (buyer_agent_id = 'buyer_upsell' OR buyer_agent_id LIKE '%upsell%') AND status IN ('created', 'completed') {m_filter}").fetchone()[0]
        upsell_rev = c.execute(f"SELECT COALESCE(SUM(amount_paise), 0) FROM orders WHERE (buyer_agent_id = 'buyer_upsell' OR buyer_agent_id LIKE '%upsell%') AND status IN ('created', 'completed') {m_filter}").fetchone()[0]
        attach_rate = round((upsell_orders / total_orders * 100.0), 1) if total_orders > 0 else 0.0
        campaign_count = c.execute(f"SELECT COUNT(*) FROM campaigns {m_where}").fetchone()[0]
        discount_val = c.execute(f"SELECT COALESCE(SUM((amount_paise * COALESCE(discount_percent, 0)) / 100), 0) FROM campaigns {m_where}").fetchone()[0]

        print(f"=== MERCHANT: {m} ===")
        print(f"  1. Total Orders: {total_orders}")
        print(f"  2. Total Revenue: INR {total_rev/100:,.2f}")
        print(f"  3. Upsell Orders: {upsell_orders}")
        print(f"  4. Upsell Revenue: INR {upsell_rev/100:,.2f}")
        print(f"  5. Attach Rate: {attach_rate}%")
        print(f"  6. Campaigns Created: {campaign_count}")
        print(f"  7. Total Discount Value Offered: INR {discount_val/100:,.2f}\n")

if __name__ == "__main__":
    test_sql_analytics()
