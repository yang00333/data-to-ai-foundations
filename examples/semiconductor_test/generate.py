"""Generate synthetic semiconductor-test planning data for 30 days.

All values are invented. The files imitate data a test-planning team
assembles from separate systems: material inventory, the test plan, tester
capacity, and a product master. They include a negative inventory entry, a
missing day, a plan line exported twice, and a product the master does not
know.

Run: python examples/semiconductor_test/generate.py
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "data"
START = date(2026, 5, 1)
DAYS = 30
PRODUCTS = {"PA-100": (3.5, 900), "PB-220": (5.0, 1200), "PC-310": (2.0, 600)}
rng = random.Random(11)


def write(name: str, header: list[str], rows: list[list]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(header)
        w.writerows(rows)


def main() -> None:
    inventory, plan, capacity = [], [], []
    for d in range(DAYS):
        day = START + timedelta(days=d)
        for pid, (_, units_per_lot) in PRODUCTS.items():
            if not (pid == "PB-220" and d == 12):  # missing day in inventory feed
                inventory.append([day.isoformat(), pid, rng.randint(6, 14) * units_per_lot])
            plan.append([day.isoformat(), pid, rng.randint(2, 9)])
            capacity.append([day.isoformat(), pid, rng.choice([16, 20, 24, 24, 32])])
    inventory[20][2] = -1500  # data-entry error
    plan.append([(START + timedelta(days=5)).isoformat(), "PX-999", 4])  # unknown product
    plan.insert(31, list(plan[30]))  # the same plan line exported twice
    write("inventory.csv", ["snapshot_date", "product_id", "units_on_hand"], inventory)
    write("test_plan.csv", ["plan_date", "product_id", "planned_lots"], plan)
    write("tester_capacity.csv", ["date", "product_id", "tester_hours"], capacity)

    master = [[pid, hours, units] for pid, (hours, units) in PRODUCTS.items()]
    write("product_master.csv", ["product_id", "test_hours_per_lot", "units_per_lot"], master)
    print(f"wrote synthetic semiconductor-test data to {OUT}")


if __name__ == "__main__":
    main()
