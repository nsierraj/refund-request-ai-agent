"""Create orders.db, a fake store database the agent will look things up in.

Run it again any time to reset the data. Dates are relative to today,
so the "delivered 3 days ago" order is always 3 days ago.
"""

import sqlite3
from datetime import date, timedelta

from config import DB_PATH


def days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


# Each order is a different situation you'll want the agent to handle later.
ORDERS = [
    # order_id, customer, email, item, price, ordered, delivered, status
    ("A1001", "Maria Lopez", "maria@example.com", "Ceramic table lamp", 89.00, days_ago(8), days_ago(3), "delivered"),
    ("A1002", "James Carter", "james@example.com", "Wool throw blanket", 64.50, days_ago(50), days_ago(45), "delivered"),
    ("A1003", "Priya Shah", "priya@example.com", "Cast iron skillet", 42.00, days_ago(2), None, "processing"),
    ("A1004", "Tom Becker", "tom@example.com", "Bamboo bath mat", 29.99, days_ago(20), days_ago(16), "refunded"),
    ("A1005", "Lena Fischer", "lena@example.com", "Leather lounge chair", 1249.00, days_ago(12), days_ago(6), "delivered"),
    ("A1006", "Sam Okafor", "sam@example.com", "Glass storage jars (set of 6)", 38.00, days_ago(5), None, "shipped"),
    ("A1007", "Maria Lopez", "maria@example.com", "Linen napkins (set of 4)", 24.00, days_ago(30), days_ago(27), "delivered"),
    ("A1008", "Kevin Wu", "kevin@example.com", "Espresso machine", 499.00, days_ago(10), days_ago(4), "delivered"),
]


def main():
    DB_PATH.unlink(missing_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE orders (
            order_id       TEXT PRIMARY KEY,
            customer_name  TEXT,
            email          TEXT,
            item           TEXT,
            price          REAL,
            order_date     TEXT,
            delivered_date TEXT,
            status         TEXT
        )"""
    )
    con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ORDERS)
    con.commit()
    con.close()
    print(f"Created {DB_PATH.name} with {len(ORDERS)} orders.")
    for o in ORDERS:
        print(f"  {o[0]}  {o[7]:<10}  ${o[4]:>8.2f}  {o[3]}")


if __name__ == "__main__":
    main()
