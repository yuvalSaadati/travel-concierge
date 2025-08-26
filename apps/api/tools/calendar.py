from ics import Calendar, Event
from datetime import datetime, timedelta
import os

def make_ics(plan_md: str, city: str, start_date: str, days: int, out_dir: str = "exports"):
    os.makedirs(out_dir, exist_ok=True)
    cal = Calendar()
    # very naive: split plan by "Day N:" headings
    blocks = []
    cur = []
    for line in plan_md.splitlines():
        if line.strip().lower().startswith("day ") and ":" in line:
            if cur:
                blocks.append("\n".join(cur))
                cur = [line]
            else:
                cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))

    d0 = datetime.fromisoformat(start_date)
    for i, block in enumerate(blocks[:days]):
        ev = Event()
        ev.name = f"{city} — Day {i+1}"
        ev.begin = d0 + timedelta(days=i, hours=9)
        ev.duration = timedelta(hours=8)
        ev.description = block
        cal.events.add(ev)

    path = os.path.join(out_dir, f"{city.lower().replace(' ','_')}_{start_date}.ics")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(cal)
    return path
