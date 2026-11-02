"""Step 8: the human side. Run this in a second terminal.

    python review.py           # work through pending reviews
    python review.py --all     # list every review, decided ones too

You're the support team member. For each pending refund you see what the
agent and the checks found, then approve, reject, or skip. Your note goes
to the customer, so write it for them.
"""

import sys

from reviews import _db, decide, pending_reviews
from tools import _eligibility, _get_order


def show_all():
    con = _db()
    rows = con.execute("SELECT * FROM reviews ORDER BY created_at").fetchall()
    con.close()
    if not rows:
        print("No reviews yet.")
    for r in rows:
        print(f"{r['review_id']}  {r['order_id']}  ${r['amount']:>8.2f}  {r['status']:<9}"
              f"{r['refund_id'] or '':<10}{r['why_review']}")


def show(review):
    order = _get_order(review["order_id"])
    eligibility = _eligibility(order)
    print("\n" + "-" * 70)
    print(f"{review['review_id']}   opened {review['created_at']}")
    print(f"  Order       {order['order_id']}  {order['item']}  ${order['price']:.2f}  (status: {order['status']})")
    print(f"  Customer    {order['customer_name']} <{order['email']}>")
    print(f"  Their words \"{review['customer_reason']}\"")
    print(f"  Why here    {review['why_review']}")
    if review["risk_score"] is not None:
        print(f"  Risk score  {review['risk_score']:.2f}  ({review['signals']})")
    print(f"  Policy      {eligibility['reason']}")


def main():
    if "--all" in sys.argv:
        show_all()
        return

    queue = pending_reviews()
    if not queue:
        print("No pending reviews. Leave this running? Re-run it after the agent opens one.")
        return
    print(f"{len(queue)} pending review(s).")

    for review in queue:
        show(review)
        choice = ""
        while choice not in ("a", "r", "s"):
            choice = input("  [a]pprove, [r]eject, [s]kip? ").strip().lower()[:1]
        if choice == "s":
            continue
        note = input("  Note to the customer (optional): ").strip()
        result = decide(review["review_id"], approve=(choice == "a"), customer_message=note)
        if "error" in result:
            print(f"  Couldn't record that: {result['error']}")
        elif result["status"] == "approved":
            print(f"  Approved. Refund {result['refund_id']} issued for ${result['amount']:.2f}.")
        else:
            print("  Rejected. No refund issued.")
    print("\nDone. The agent will pass your decisions to the customer.")


if __name__ == "__main__":
    main()
