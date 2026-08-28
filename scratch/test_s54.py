import requests
import sqlite3
import datetime

def test_s54():
    conn = sqlite3.connect("aria.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    t_start = datetime.datetime.now(datetime.timezone.utc).isoformat()

    c.execute(
        "INSERT OR REPLACE INTO product_pair_stats (product_a_id, product_b_id, merchant_id, times_bought_together, last_updated) VALUES ('prod_bf_001', 'prod_bf_phone_02', 'merchant_byteforge', 10, '2026-08-27T06:00:00')"
    )
    conn.commit()

    upsell_body = {
        "action": "upsell",
        "merchantId": "merchant_byteforge",
        "cart": [{"product": {"id": "prod_bf_001", "name": "Vortex Mechanical Keyboard", "price": 549900}, "quantity": 1}]
    }
    res = requests.post("http://localhost:8000/api/merchant-agent", json=upsell_body).json()

    rejected_logs = c.execute(
        "SELECT * FROM audit_logs WHERE status = 'BLOCKED' AND action_type = 'UPSELL_REJECTED' AND merchant_id = 'merchant_byteforge' AND source = 'co_purchase_data' AND timestamp > ?",
        (t_start,)
    ).fetchall()

    print("Suggestions returned:", res)
    print("Rejected logs count:", len(rejected_logs))
    for r in rejected_logs:
        print("  -", dict(r))

if __name__ == "__main__":
    test_s54()
