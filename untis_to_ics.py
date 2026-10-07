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


def mins(t: int) -> int:
    return t // 100 * 60 + t % 100


MAX_GAP = 30  # Minuten Pause, bis zu der Stunden zu einem Termin zusammengefasst werden


def main():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    periods = {}
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
            desc = "; ".join(x for x in [teachers, p.get("lessonText"), p.get("substText"), p.get("periodText")] if x)
            periods[(p["id"], p["date"], p["startTime"])] = {
                "id": p["id"], "date": p["date"], "start": p["startTime"], "end": p["endTime"],
                "key": (p.get("lessonId"), subject, teachers, rooms, p.get("cellState") == "CANCEL", desc),
                "subject": subject, "rooms": rooms, "desc": desc,
                "cancelled": p.get("cellState") == "CANCEL",
            }

    # Aufeinanderfolgende Stunden desselben Unterrichts zusammenfassen
    merged = []
    for p in sorted(periods.values(), key=lambda x: (x["date"], x["start"])):
        last = merged[-1] if merged else None
        if (last and last["date"] == p["date"] and last["key"] == p["key"]
                and 0 <= mins(p["start"]) - mins(last["end"]) <= MAX_GAP):
            last["end"] = p["end"]
        else:
            merged.append(dict(p))

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//untis-ics//DE",
             "CALSCALE:GREGORIAN", "X-WR-CALNAME:Stundenplan THA",
             "X-WR-TIMEZONE:Europe/Berlin", "REFRESH-INTERVAL;VALUE=DURATION:PT6H"]
    for p in merged:
        uid = hashlib.sha1(f"{p['id']}-{p['date']}-{p['start']}".encode()).hexdigest() + "@untis-ics"
        lines += [
            "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}",
            f"DTSTART:{utc(p['date'], p['start'])}",
            f"DTEND:{utc(p['date'], p['end'])}",
            f"SUMMARY:{esc(('ENTFÄLLT: ' if p['cancelled'] else '') + p['subject'])}",
            f"LOCATION:{esc(p['rooms'])}", f"DESCRIPTION:{esc(p['desc'])}",
            f"STATUS:{'CANCELLED' if p['cancelled'] else 'CONFIRMED'}", "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(lines) + "\r\n")
    print(f"{len(merged)} Termine geschrieben ({len(periods)} Einzelstunden)")


if __name__ == "__main__":
    main()
