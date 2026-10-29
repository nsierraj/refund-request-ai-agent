"""Step 7, part 1: create fake refund history to learn from.

    python make_refund_history.py

Writes refund_history.csv: 6,000 past refund requests, each labeled
was_fraud = 1 or 0. Open it in a spreadsheet and look around before
training anything. Real teams spend most of their time at this stage.

How the fake data is made: two kinds of customers, honest and
fraudsters, with overlapping habits. Fraudsters tend to have new
accounts, pricier orders, many recent refunds, and ask for refunds
fast. Tend to, not always. Some honest customers look suspicious and
some fraudsters look normal, so no single rule catches them cleanly.
That overlap is why a learned model is worth having.
"""

import csv
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent / "refund_history.csv"
ROWS = 6000
FRAUD_RATE = 0.07
REASONS = ["damaged", "defective", "not_as_described", "changed_mind", "other"]

rng = np.random.default_rng(42)  # fixed seed: same "random" data every run


def honest():
    age = int(rng.choice([rng.integers(1, 90), rng.integers(90, 2500)], p=[0.15, 0.85]))
    return {
        "price": round(float(np.clip(rng.lognormal(4.2, 0.9), 8, 2500)), 2),
        "days_since_delivery": int(rng.integers(0, 31)),
        "account_age_days": age,
        "prior_orders": int(1 + rng.poisson(age / 120)),
        "refunds_last_90_days": int(rng.poisson(0.25)),
        "reason": str(rng.choice(REASONS, p=[0.35, 0.2, 0.15, 0.25, 0.05])),
    }


def fraudster():
    age = int(rng.choice([rng.integers(1, 60), rng.integers(60, 1500)], p=[0.7, 0.3]))
    return {
        "price": round(float(np.clip(rng.lognormal(5.6, 0.7), 20, 2500)), 2),
        "days_since_delivery": int(rng.choice([rng.integers(0, 4), rng.integers(4, 31)], p=[0.6, 0.4])),
        "account_age_days": age,
        "prior_orders": int(1 + rng.poisson(age / 60)),
        "refunds_last_90_days": int(rng.poisson(2.2)),
        "reason": str(rng.choice(REASONS, p=[0.3, 0.15, 0.4, 0.05, 0.1])),
    }


def main():
    rows = []
    for _ in range(ROWS):
        is_fraud = rng.random() < FRAUD_RATE
        row = fraudster() if is_fraud else honest()
        # Labels are never perfect: investigators miss some and mislabel some.
        if rng.random() < 0.02:
            is_fraud = not is_fraud
        row["was_fraud"] = int(is_fraud)
        rows.append(row)

    with OUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    fraud = sum(r["was_fraud"] for r in rows)
    print(f"Wrote {len(rows)} refund requests to {OUT.name} ({fraud} labeled fraud, {fraud / len(rows):.1%}).")


if __name__ == "__main__":
    main()
