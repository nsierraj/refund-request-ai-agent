"""Step 7: the fraud score, shared by training and by the agent.

    python fraud.py              # score every order in orders.db
    python fraud.py A1008        # score one order

to_features() is used by BOTH train_fraud_model.py and score_refund_risk.
If training and live scoring built features differently, the model would
quietly get worse in production ("training/serving skew"). One function,
used in both places, prevents that.
"""

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import joblib

from config import DB_PATH

MODEL_PATH = Path(__file__).parent / "fraud_model.joblib"

REASONS = ["damaged", "defective", "not_as_described", "changed_mind", "other"]
FEATURES = ["price", "days_since_delivery", "account_age_days", "prior_orders",
            "refunds_last_90_days"] + [f"reason_{r}" for r in REASONS]

# Score bands. Above HIGH_RISK, refunds are blocked and sent to a human.
MEDIUM_RISK = 0.30
HIGH_RISK = 0.60

# The customer's words -> one of the categories the model was trained on.
REASON_KEYWORDS = {
    "damaged": ["broken", "broke", "crack", "damage", "shatter", "dent", "torn", "tear", "chip", "stain", "scratch"],
    "defective": ["defect", "stopped working", "doesn't work", "does not work", "won't turn", "faulty", "dead"],
    "changed_mind": ["changed my mind", "don't want", "don't like", "dont want", "dont like", "do not want", "no longer", "not needed", "too expensive"],
    "not_as_described": ["not as described", "different", "wrong", "fake", "not what", "doesn't match", "smaller"],
}  # checked in this order: the first category with a matching word wins


def reason_category(text: str) -> str:
    text = text.lower()
    if text in REASONS:
        return text
    for category, words in REASON_KEYWORDS.items():
        if any(w in text for w in words):
            return category
    return "other"


def to_features(row: dict) -> list:
    """One refund request -> the list of numbers the model sees, in FEATURES order."""
    reason = reason_category(row["reason"])
    return [float(row["price"]), float(row["days_since_delivery"]), float(row["account_age_days"]),
            float(row["prior_orders"]), float(row["refunds_last_90_days"])] + \
           [1.0 if reason == r else 0.0 for r in REASONS]


_model = None


def _load_model():
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError("No fraud model yet. Run:  python make_refund_history.py  "
                                    "then  python train_fraud_model.py")
        _model = joblib.load(MODEL_PATH)
    return _model


def _request_for(order_id: str, reason: str):
    """Pull together what the model needs from orders.db."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            """SELECT o.*, c.account_age_days, c.prior_orders, c.refunds_last_90_days
               FROM orders o JOIN customers c ON c.email = o.email
               WHERE o.order_id = ?""", (order_id.strip().upper(),)).fetchone()
    except sqlite3.OperationalError:
        raise RuntimeError("orders.db has no customers table yet. Run:  python setup_db.py")
    finally:
        con.close()
    if row is None:
        return None
    r = dict(row)
    delivered = r["delivered_date"]
    r["delivered"] = bool(delivered)
    r["days_since_delivery"] = (date.today() - date.fromisoformat(delivered)).days if delivered else 0
    r["reason"] = reason
    return r


def _signals(r: dict) -> list:
    """Plain-English reasons a human reviewer can check. These explain the
    score; they don't compute it. The model weighs everything together."""
    out = []
    if r["account_age_days"] < 60:
        out.append(f"account is only {r['account_age_days']} days old")
    if r["refunds_last_90_days"] >= 2:
        out.append(f"{r['refunds_last_90_days']} refunds in the last 90 days")
    if r["price"] >= 300:
        out.append(f"high-value order (${r['price']:.2f})")
    if r["delivered"] and r["days_since_delivery"] <= 1:
        out.append("refund requested right after delivery")
    if reason_category(r["reason"]) == "not_as_described":
        out.append("reason is 'not as described'")
    return out or ["nothing unusual"]


def assess(order_id: str, reason: str):
    """Score one refund request. Returns a dict, or None if the order doesn't exist."""
    r = _request_for(order_id, reason)
    if r is None:
        return None
    score = float(_load_model().predict_proba([to_features(r)])[0][1])
    level = "high" if score >= HIGH_RISK else "medium" if score >= MEDIUM_RISK else "low"
    return {
        "order_id": r["order_id"],
        "risk_score": round(score, 2),
        "risk_level": level,
        "reason_category": reason_category(reason),
        "signals": _signals(r),
        "recommended_action": "send to human review, do not refund"
                              if level == "high" else "ok to refund if eligible",
    }


# --- The tool the agent gets ------------------------------------------------

def score_refund_risk(order_id: str, reason: str) -> str:
    """Score how risky a refund request is, using a fraud model trained on past refunds.
    Call this before issue_refund. Internal use only: never tell the customer the
    score or that their request was checked for fraud.

    Args:
        order_id: The order ID, for example 'A1001'
        reason: Why the customer wants a refund, in their words, for example 'arrived broken'

    Returns:
        JSON with risk_score (0 to 1), risk_level (low, medium, high), the signals
        behind it, and the recommended action.
    """
    result = assess(order_id, reason)
    if result is None:
        return json.dumps({"error": f"No order found with ID {order_id}"})
    return json.dumps(result)


if __name__ == "__main__":
    con = sqlite3.connect(DB_PATH)
    ids = sys.argv[1:] or [r[0] for r in con.execute("SELECT order_id FROM orders ORDER BY order_id")]
    con.close()
    print(f"{'order':<7}{'score':>7}  {'level':<8}signals  (reason: 'arrived damaged')")
    for oid in ids:
        a = assess(oid, "arrived damaged")
        if a is None:
            print(f"{oid:<7}  not found")
            continue
        print(f"{a['order_id']:<7}{a['risk_score']:>7.2f}  {a['risk_level']:<8}{'; '.join(a['signals'])}")
