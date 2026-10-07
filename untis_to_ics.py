#!/usr/bin/env python3
"""Holt den öffentlichen WebUntis-Stundenplan und schreibt ihn als .ics."""
import base64, hashlib, json, urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HOST = "https://tha.webuntis.com"
SCHOOL = "tha"
ELEMENT_TYPE = 1        # 1 = Klasse
ELEMENT_ID = 9816
WEEKS_BACK, WEEKS_AHEAD = 1, 12
OUT = "stundenplan.ics"
TZ = ZoneInfo("Europe/Berlin")


def fetch_week(day: date) -> dict:
    url = (f"{HOST}/WebUntis/api/public/timetable/weekly/data"
           f"?elementType={ELEMENT_TYPE}&elementId={ELEMENT_ID}"
           f"&date={day.isoformat()}&formatId=1")
    cookie = "schoolname=_" + base64.b64encode(SCHOOL.encode()).decode()
    req = urllib.request.Request(url, headers={"Cookie": cookie, "User-Agent": "untis-ics/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]["result"]["data"]


def utc(d: int, t: int) -> str:
    dt = datetime(d // 10000, d // 100 % 100, d % 100, t // 100, t % 100, tzinfo=TZ)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def main():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    events = {}
    for w in range(-WEEKS_BACK, WEEKS_AHEAD + 1):
        data = fetch_week(monday + timedelta(weeks=w))
        names = {(e["type"], e["id"]): e for e in data.get("elements", [])}
        for p in data.get("elementPeriods", {}).get(str(ELEMENT_ID), []):
            by_type = {}
            for el in p.get("elements", []):
                info = names.get((el["type"], el["id"]), {})
                by_type.setdefault(el["type"], []).append(info.get("name", "?"))
            subject = ", ".join(by_type.get(3, [])) or p.get("lessonText") or "Unterricht"
            teachers = ", ".join(by_type.get(2, []))
            rooms = ", ".join(by_type.get(4, []))
            cancelled = p.get("cellState") == "CANCEL"
            desc = "; ".join(x for x in [teachers, p.get("lessonText"), p.get("substText"), p.get("periodText")] if x)
            uid = hashlib.sha1(f"{p['id']}-{p['date']}-{p['startTime']}".encode()).hexdigest() + "@untis-ics"
            events[uid] = [
                "BEGIN:VEVENT", f"UID:{uid}",
                f"DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
                f"DTSTART:{utc(p['date'], p['startTime'])}",
                f"DTEND:{utc(p['date'], p['endTime'])}",
                f"SUMMARY:{esc(('ENTFÄLLT: ' if cancelled else '') + subject)}",
                f"LOCATION:{esc(rooms)}", f"DESCRIPTION:{esc(desc)}",
                f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}", "END:VEVENT",
            ]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//untis-ics//DE",
             "CALSCALE:GREGORIAN", "X-WR-CALNAME:Stundenplan THA",
             "X-WR-TIMEZONE:Europe/Berlin", "REFRESH-INTERVAL;VALUE=DURATION:PT6H"]
    for ev in events.values():
        lines += ev
    lines.append("END:VCALENDAR")
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(lines) + "\r\n")
    print(f"{len(events)} Termine geschrieben")


if __name__ == "__main__":
    main()
