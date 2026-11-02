"""Step 8: the review queue, shared by the agent and the human reviewer.

A review is a row in orders.db with a status: pending -> approved or rejected.
The agent can open a review and check on one. Only review.py, run by a
person, can decide one. That split is the point: the agent can ask, it
can't approve.
"""

import json
import sqlite3
import uuid
from datetime import datetime

from config import DB_PATH
from fraud import assess
from tools import _eligibility, _get_order, record_refund


def _db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS reviews (
        review_id         TEXT PRIMARY KEY,
        order_id          TEXT,
        amount            REAL,
        customer_reason   TEXT,
        why_review        TEXT,
        risk_score        REAL,
        signals           TEXT,
        status            TEXT,     -- pending, approved, rejected
        customer_message  TEXT,     -- the reviewer's note, shown to the customer
        refund_id         TEXT,
        created_at        TEXT,
        decided_at        TEXT,
        customer_notified INTEGER DEFAULT 0)""")
    return con


def now():
    return datetime.now().isoformat(timespec="seconds")


def why_review_needed(order: dict, reason: str):
    """Why this refund needs a person, or None if it doesn't. Also returns the risk result."""
    try:
        risk = assess(order["order_id"], reason)
    except Exception as e:  # no model, missing table...: fail closed
        return f"automatic check unavailable ({e})", None
    reasons = []
    if _eligibility(order).get("needs_human_approval"):
        reasons.append("over the auto-refund limit")
    if risk and risk["risk_level"] == "high":
        reasons.append("high risk score")
    return (" and ".join(reasons) or None), risk


def open_review(order_id: str, reason: str, why: str = None) -> dict:
    """Create a pending review, or return the one already open for this order."""
    order = _get_order(order_id)
    if order is None:
        return {"error": f"No order found with ID {order_id}"}
    con = _db()
    existing = con.execute("SELECT * FROM reviews WHERE order_id = ? AND status = 'pending'",
                           (order["order_id"],)).fetchone()
    if existing:
        con.close()
        return {"review_id": existing["review_id"], "status": "pending", "already_open": True}

    auto_why, risk = why_review_needed(order, reason)
    review_id = "REV-" + uuid.uuid4().hex[:5].upper()
    con.execute("""INSERT INTO reviews (review_id, order_id, amount, customer_reason, why_review,
                   risk_score, signals, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (review_id, order["order_id"], order["price"], reason,
                 why or auto_why or "agent asked for a human",
                 risk["risk_score"] if risk else None,
                 "; ".join(risk["signals"]) if risk else None, now()))
    con.commit()
    con.close()
    return {"review_id": review_id, "status": "pending"}


def get_review(review_id: str):
    con = _db()
    row = con.execute("SELECT * FROM reviews WHERE review_id = ?", (review_id.strip().upper(),)).fetchone()
    con.close()
    return dict(row) if row else None


def pending_reviews():
    con = _db()
    rows = [dict(r) for r in con.execute("SELECT * FROM reviews WHERE status = 'pending' ORDER BY created_at")]
    con.close()
    return rows


def decide(review_id: str, approve: bool, customer_message: str = "") -> dict:
    """A person's decision. Approving issues the refund, skipping the agent's checks:
    the human is the check. It still won't refund an order twice."""
    review = get_review(review_id)
    if review is None or review["status"] != "pending":
        return {"error": f"{review_id} is not a pending review"}
    refund_id = None
    if approve:
        order = _get_order(review["order_id"])
        if order["status"] == "refunded":
            return {"error": f"{order['order_id']} is already refunded"}
        refund_id = record_refund(order, review["customer_reason"])["refund_id"]
    con = _db()
    con.execute("""UPDATE reviews SET status = ?, customer_message = ?, refund_id = ?, decided_at = ?
                   WHERE review_id = ?""",
                ("approved" if approve else "rejected", customer_message, refund_id, now(), review_id))
    con.commit()
    con.close()
    return get_review(review_id)


def customer_view(review: dict) -> dict:
    """What the agent (and so the customer) may see. No risk score, no signals."""
    keys = ("review_id", "order_id", "status", "amount", "refund_id", "customer_message", "decided_at")
    return {k: review[k] for k in keys}


def updates_since(started_at: str) -> list:
    """Decided reviews opened in this session that the customer hasn't heard about yet."""
    con = _db()
    rows = [dict(r) for r in con.execute(
        """SELECT * FROM reviews WHERE status != 'pending' AND customer_notified = 0
           AND created_at >= ? ORDER BY decided_at""", (started_at,))]
    con.executemany("UPDATE reviews SET customer_notified = 1 WHERE review_id = ?",
                    [(r["review_id"],) for r in rows])
    con.commit()
    con.close()
    return rows


# --- Tools the agent gets ---------------------------------------------------

def request_human_review(order_id: str, reason: str) -> str:
    """Send a refund request to a human reviewer. Use this when check_refund_eligibility
    says needs_human_approval, when score_refund_risk says high, or when issue_refund
    is refused for review. Give the customer the review ID it returns.

    Args:
        order_id: The order ID, for example 'A1005'
        reason: Why the customer wants a refund, in their words

    Returns:
        JSON with the review_id and status.
    """
    return json.dumps(open_review(order_id, reason))


def check_review_status(review_id: str) -> str:
    """Check whether a human reviewer has decided a refund review yet.

    Args:
        review_id: The review ID, for example 'REV-1A2B3'

    Returns:
        JSON with the status (pending, approved, rejected), the refund ID and amount
        if approved, and any message the reviewer left for the customer.
    """
    review = get_review(review_id)
    if review is None:
        return json.dumps({"error": f"No review found with ID {review_id}"})
    return json.dumps(customer_view(review))
