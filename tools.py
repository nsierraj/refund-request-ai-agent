"""The agent's hands: every tool from Step 4 onward lives here.

Each function is a plain Python function. Ollama reads the type hints
and the docstring to describe it to the model, so the docstring is the
tool's instructions. Keep them accurate.

Rule of thumb: the model decides WHEN to call a tool. The tool decides
WHAT is allowed. Never trust the model to enforce business rules.
"""

import json
import sqlite3
import uuid
from datetime import date, datetime

from config import DB_PATH

# Business rules. Change these and watch the agent's behavior change.
RETURN_WINDOW_DAYS = 30     # days after delivery a refund is allowed
AUTO_REFUND_LIMIT = 500.00  # above this, a human must approve


def _get_order(order_id: str):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM orders WHERE order_id = ?", (order_id.strip().upper(),)
    ).fetchone()
    con.close()
    return dict(row) if row else None


def _eligibility(order: dict) -> dict:
    """The refund rules, in one place. Used by two tools."""
    if order["status"] == "refunded":
        return {"eligible": False, "reason": "This order was already refunded."}
    if order["status"] != "delivered" or not order["delivered_date"]:
        return {"eligible": False,
                "reason": f"Order hasn't been delivered yet (status: {order['status']})."}

    days = (date.today() - date.fromisoformat(order["delivered_date"])).days
    if days > RETURN_WINDOW_DAYS:
        return {"eligible": False,
                "reason": f"Delivered {days} days ago. The return window is {RETURN_WINDOW_DAYS} days."}

    if order["price"] > AUTO_REFUND_LIMIT:
        return {"eligible": True, "needs_human_approval": True,
                "reason": f"Eligible, but refunds over ${AUTO_REFUND_LIMIT:.0f} need a human to approve."}

    return {"eligible": True, "needs_human_approval": False,
            "reason": f"Delivered {days} days ago, within the {RETURN_WINDOW_DAYS}-day window."}


# --- Tools the model can call --------------------------------------------

def lookup_order(order_id: str) -> str:
    """Look up a customer's order by its order ID.

    Args:
        order_id: The order ID, for example 'A1001'

    Returns:
        The order details as JSON, or an error if no order has that ID.
    """
    order = _get_order(order_id)
    if order is None:
        return json.dumps({"error": f"No order found with ID {order_id}"})
    return json.dumps(order)


def check_refund_eligibility(order_id: str) -> str:
    """Check whether an order can be refunded under store policy.

    Always call this before issue_refund.

    Args:
        order_id: The order ID, for example 'A1001'

    Returns:
        JSON with eligible (true/false), needs_human_approval, and the reason.
    """
    order = _get_order(order_id)
    if order is None:
        return json.dumps({"error": f"No order found with ID {order_id}"})
    return json.dumps({"order_id": order["order_id"], **_eligibility(order)})


def issue_refund(order_id: str, reason: str) -> str:
    """Issue a refund for an order. Only call this after check_refund_eligibility
    says the order is eligible and does not need human approval, and only when
    the customer has asked for a refund.

    Args:
        order_id: The order ID, for example 'A1001'
        reason: Short reason in the customer's words, for example 'arrived broken'

    Returns:
        JSON with the refund confirmation, or an error saying why it was refused.
    """
    order = _get_order(order_id)
    if order is None:
        return json.dumps({"error": f"No order found with ID {order_id}"})

    # Re-check the rules here. The model may skip a step or be talked into
    # something; this function is the last line of defense.
    check = _eligibility(order)
    if not check["eligible"]:
        return json.dumps({"refunded": False, "error": check["reason"]})
    if check["needs_human_approval"]:
        return json.dumps({"refunded": False,
                           "error": "Needs human approval. Refund NOT issued. "
                                    "Tell the customer a team member will review it."})

    refund_id = "R-" + uuid.uuid4().hex[:6].upper()
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS refunds (
                       refund_id TEXT PRIMARY KEY, order_id TEXT, amount REAL,
                       reason TEXT, created_at TEXT)""")
    con.execute("INSERT INTO refunds VALUES (?, ?, ?, ?, ?)",
                (refund_id, order["order_id"], order["price"], reason,
                 datetime.now().isoformat(timespec="seconds")))
    con.execute("UPDATE orders SET status = 'refunded' WHERE order_id = ?",
                (order["order_id"],))
    con.commit()
    con.close()

    return json.dumps({"refunded": True, "refund_id": refund_id,
                       "amount": order["price"], "order_id": order["order_id"]})


# Name -> function, so the loop can run whatever the model asks for.
TOOLS = {f.__name__: f for f in (lookup_order, check_refund_eligibility, issue_refund)}
