import os
import uuid
import razorpay
from typing import Dict, Any, Optional

# Load Razorpay test keys from env or fallback
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_TS1QcYdKLNTixJ")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "8TRD0eEyiNALjrTmHODZTEkb")

def get_razorpay_client():
    """Get initialized Razorpay Python SDK client."""
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

def create_razorpay_order(amount_paise: int, currency: str = "INR", receipt: Optional[str] = None, notes: Dict[str, Any] = None, simulate_failure: bool = False) -> Dict[str, Any]:
    """
    Create a Razorpay Order in test mode using official Python SDK.
    Supports SIMULATE_RAZORPAY_FAILURE env var or simulate_failure parameter for Scenario 2.2 demo.
    """
    env_sim = os.getenv("SIMULATE_RAZORPAY_FAILURE", "false").lower() in ("true", "1", "yes")
    if simulate_failure or env_sim:
        raise razorpay.errors.RazorpayError("Simulated Razorpay gateway timeout — no charge was made.")

    receipt_id = receipt or f"rcpt_{uuid.uuid4().hex[:8]}"
    notes_dict = notes or {}

    try:
        client = get_razorpay_client()
        order_data = {
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt_id,
            "notes": notes_dict,
        }
        order = client.order.create(data=order_data)
        return order
    except Exception as e:
        print(f"[Razorpay Python] Client API call fallback: {e}")
        return {
            "id": f"order_{uuid.uuid4().hex[:14]}",
            "entity": "order",
            "amount": amount_paise,
            "amount_paid": 0,
            "amount_due": amount_paise,
            "currency": currency,
            "receipt": receipt_id,
            "status": "created",
            "attempts": 0,
            "notes": notes_dict,
            "created_at": 1740000000,
        }

def create_razorpay_payment_link(amount_paise: int, description: str, customer_name: str = "Valued Customer", customer_email: str = "customer@example.com", notes: Dict[str, Any] = None, simulate_failure: bool = False) -> Dict[str, Any]:
    """
    Create a Razorpay Payment Link in test mode using official Python SDK.
    Supports SIMULATE_RAZORPAY_FAILURE env var or simulate_failure parameter.
    """
    env_sim = os.getenv("SIMULATE_RAZORPAY_FAILURE", "false").lower() in ("true", "1", "yes")
    if simulate_failure or env_sim:
        raise razorpay.errors.RazorpayError("Simulated Razorpay Payment Link creation timeout — no payment link generated.")

    notes_dict = notes or {}
    reference_id = f"plink_ref_{uuid.uuid4().hex[:8]}"

    try:
        client = get_razorpay_client()
        link_data = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": description,
            "customer": {
                "name": customer_name,
                "email": customer_email,
                "contact": "+919999999999"
            },
            "notify": {"sms": False, "email": False},
            "reminder_enable": True,
            "notes": notes_dict,
            "callback_url": "http://localhost:8000/merchant",
            "callback_method": "get"
        }
        link = client.payment_link.create(data=link_data)
        return link
    except Exception as e:
        print(f"[Razorpay Python Link] Fallback: {e}")
        mock_id = f"plink_{uuid.uuid4().hex[:10]}"
        return {
            "id": mock_id,
            "short_url": f"http://localhost:8000/buyer?plink={mock_id[:8]}",
            "amount": amount_paise,
            "currency": "INR",
            "description": description,
            "status": "created",
            "reference_id": reference_id
        }

