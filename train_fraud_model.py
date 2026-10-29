"""Step 7, part 2: train the fraud model.

    python train_fraud_model.py

1. Load refund_history.csv and turn each row into numbers (fraud.to_features).
2. Hold back 25% of the rows. The model never sees them during training,
   so they give an honest test, like a final exam with new questions.
3. Train a random forest: a few hundred small decision trees, each one a
   flowchart of yes/no questions learned from the data, that vote.
4. Compare it against a hand-written rule, the way you'd write it without ML.
5. Save the model to fraud_model.joblib for the agent to use.
"""

import csv
import sys
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

from fraud import FEATURES, HIGH_RISK, MODEL_PATH, to_features

DATA = Path(__file__).parent / "refund_history.csv"


def hand_written_rule(row):
    """What you might write without ML: lots of recent refunds on a pricey order."""
    return int(int(row["refunds_last_90_days"]) >= 2 and float(row["price"]) >= 200)


def report(name, y_true, y_pred):
    caught = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    missed = sum(1 for t, p in zip(y_true, y_pred) if t and not p)
    false_alarms = sum(1 for t, p in zip(y_true, y_pred) if p and not t)
    print(f"  {name:<20} caught {caught:>3}  missed {missed:>3}  false alarms {false_alarms:>3}   "
          f"precision {precision_score(y_true, y_pred, zero_division=0):.0%}  "
          f"recall {recall_score(y_true, y_pred):.0%}")


def main():
    if not DATA.exists():
        print("refund_history.csv not found. Run:  python make_refund_history.py")
        sys.exit(1)

    rows = list(csv.DictReader(DATA.open()))
    X = [to_features(r) for r in rows]
    y = [int(r["was_fraud"]) for r in rows]

    X_train, X_test, y_train, y_test, _, rows_test = train_test_split(
        X, y, rows, test_size=0.25, random_state=42, stratify=y)
    print(f"Training on {len(X_train)} past requests, testing on {len(X_test)} it has never seen.\n")

    model = RandomForestClassifier(n_estimators=300, max_depth=8, min_samples_leaf=5, random_state=42)
    model.fit(X_train, y_train)

    scores = model.predict_proba(X_test)[:, 1]
    print(f"Results on the {len(X_test)} test requests ({sum(y_test)} of them really were fraud):")
    report("Hand-written rule", y_test, [hand_written_rule(r) for r in rows_test])
    report(f"Model (score >= {HIGH_RISK})", y_test, [int(s >= HIGH_RISK) for s in scores])
    report("Model (score >= 0.30)", y_test, [int(s >= 0.30) for s in scores])
    print(f"\n  AUC {roc_auc_score(y_test, scores):.3f}  (1.0 = perfect ranking, 0.5 = coin flip)")

    print("\nWhat the model leans on most:")
    for name, weight in sorted(zip(FEATURES, model.feature_importances_), key=lambda x: -x[1]):
        print(f"  {name:<24}{'#' * round(weight * 60):<30}{weight:.2f}")

    joblib.dump(model, MODEL_PATH)
    print(f"\nSaved {MODEL_PATH.name}. Try:  python fraud.py")


if __name__ == "__main__":
    main()
