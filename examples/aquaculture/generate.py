"""Generate synthetic aquaculture data for one pond over two days.

All values are invented. The files imitate problems real farm data have:
sensors on different schedules, a temperature probe reporting in Fahrenheit,
sensor faults, a communication gap, duplicate records, and a hand-kept
feeding log.

Run: python examples/aquaculture/generate.py
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "data"
START = datetime(2026, 6, 1, 0, 0)
END = START + timedelta(days=2)
rng = random.Random(7)


def daily_cycle(t: datetime, peak_hour: float = 15.0) -> float:
    hours = t.hour + t.minute / 60
    return math.cos((hours - peak_hour) / 24 * 2 * math.pi)


def write(name: str, header: list[str], rows: list[list]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(header)
        w.writerows(rows)


def main() -> None:
    # Dissolved oxygen, every minute (mg/L). Daily swing from photosynthesis.
    do_rows = []
    t = START
    gap = (START + timedelta(hours=30), START + timedelta(hours=31, minutes=30))
    while t < END:
        if not (gap[0] <= t < gap[1]):  # communication outage
            value = 7.0 + 2.2 * daily_cycle(t) + rng.gauss(0, 0.15)
            do_rows.append([t.isoformat(), "P1", round(value, 3)])
        t += timedelta(minutes=1)
    for i in rng.sample(range(len(do_rows)), 6):  # sensor faults
        do_rows[i][2] = 45.0
    do_rows.insert(500, list(do_rows[499]))  # duplicate record
    write("do_sensor.csv", ["timestamp", "pond_id", "do_mg_l"], do_rows)

    # pH, every 5 minutes, with a two-hour gap and one fault.
    ph_rows = []
    t = START
    while t < END:
        if not (START + timedelta(hours=12) <= t < START + timedelta(hours=14)):
            ph_rows.append([t.isoformat(), "P1", round(7.9 + 0.25 * daily_cycle(t) + rng.gauss(0, 0.03), 3)])
        t += timedelta(minutes=5)
    ph_rows[100][2] = 14.6
    write("ph_sensor.csv", ["timestamp", "pond_id", "ph"], ph_rows)

    # Water temperature, every 10 minutes, reported in Fahrenheit.
    temp_rows = []
    t = START
    while t < END:
        c = 26.0 + 1.8 * daily_cycle(t, 16) + rng.gauss(0, 0.1)
        temp_rows.append([t.strftime("%m/%d/%Y %H:%M"), "P1", round(c * 9 / 5 + 32, 2)])
        t += timedelta(minutes=10)
    temp_rows[42][0] = "not recorded"  # unparseable timestamp
    write("water_temp.csv", ["reading_time", "pond", "temp_f"], temp_rows)

    # Weather, hourly, for the whole farm (no pond column).
    weather_rows = []
    t = START
    while t < END:
        weather_rows.append([t.isoformat(), round(29 + 4 * daily_cycle(t, 14) + rng.gauss(0, 0.4), 1),
                             round(max(0.0, rng.gauss(-0.6, 1.0)), 1)])
        t += timedelta(hours=1)
    write("weather.csv", ["timestamp", "air_temp_c", "rain_mm"], weather_rows)

    # Feeding log, kept by hand: irregular times, one duplicate entry.
    feed_rows = []
    for day in range(2):
        for hour, kg in ((6, 12.5), (11, 9.0), (17, 14.0)):
            t = START + timedelta(days=day, hours=hour, minutes=rng.randint(0, 40))
            feed_rows.append([t.isoformat(timespec="minutes"), "P1", kg])
    feed_rows.append(list(feed_rows[2]))
    write("feeding_log.csv", ["fed_at", "pond_id", "feed_kg"], feed_rows)
    print(f"wrote synthetic aquaculture data to {OUT}")


if __name__ == "__main__":
    main()
