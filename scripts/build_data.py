#!/usr/bin/env python3
"""
Build compact chart data for the "Where We Are Today" section (Act 1).

Reads the raw sources in data/raw/ and writes a single small file,
data/processed/charts-data.js, that assigns window.CHART_DATA. It is loaded
via a plain <script src> tag so the artifact keeps working on a bare
double-click (file://), where fetch() of local files is blocked.

Sources
  1. Epoch AI, "AI Benchmarking Hub" (ECI). epoch.ai — capabilities index.
  2. IEA, "Energy and AI" (2025). Data annex + two published Base Case charts
     (data-centre CO2 emissions; sources of electricity generation).
     NOTE: the annex has no emissions or supply-mix series, so the energy
     numbers below are DIGITISED / ESTIMATED from the two published IEA
     Base Case charts (data/raw/*.png) and are approximate.
  3. McGregor, S. (2021). AI Incident Database. incidentdatabase.ai
"""

import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "charts-data.js"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def dec_year(iso: str) -> float:
    """ISO date -> decimal year, e.g. 2024-07-01 -> 2024.50."""
    y, m, d = (int(x) for x in iso[:10].split("-"))
    start = date(y, 1, 1)
    span = (date(y + 1, 1, 1) - start).days
    return round(y + (date(y, m, d) - start).days / span, 3)


def clean(text: str, limit: int = 175) -> str:
    """Collapse whitespace and trim to a clean length at a word boundary."""
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    cut = t[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:") + "…"


# --------------------------------------------------------------------------
# 1. Epoch capabilities index -> dots + rising frontier
# --------------------------------------------------------------------------
def build_capability():
    dots = []
    for r in csv.DictReader(open(RAW / "epoch_capabilities_index.csv")):
        ds, ss = r.get("Release date", ""), r.get("ECI Score", "")
        if not ds or not ss:
            continue
        try:
            x, s = dec_year(ds), round(float(ss), 1)
        except ValueError:
            continue
        dots.append({
            "x": x,
            "s": s,
            "n": (r.get("Display name") or r.get("Model name") or "").strip(),
            "o": (r.get("Organization") or "").strip(),
        })
    dots.sort(key=lambda d: d["x"])

    # rising frontier = running max; keep a point only when the record improves
    frontier, best = [], -1e9
    for d in dots:
        if d["s"] > best + 1e-9:
            best = d["s"]
            frontier.append({"x": d["x"], "s": d["s"], "n": d["n"], "o": d["o"]})
    # anchor the final point so the line reaches the latest date
    if dots and frontier and dots[-1]["x"] > frontier[-1]["x"]:
        frontier.append({"x": dots[-1]["x"], "s": best,
                         "n": frontier[-1]["n"], "o": frontier[-1]["o"]})

    return {
        "dots": dots,
        "frontier": frontier,
        "summary": {
            "start_year": dots[0]["x"], "start_eci": frontier[0]["s"],
            "end_year": dots[-1]["x"], "end_eci": best,
        },
    }


# --------------------------------------------------------------------------
# 2. IEA energy: demand split (renewables / nuclear / fossil) + emissions line
#    Values digitised/estimated from the two published IEA Base Case charts.
#    Demand total and the emissions curve are read off the charts; the
#    renewables/nuclear/fossil split is estimated so fossil generation tracks
#    the published emissions curve. Approximate — for illustration.
# --------------------------------------------------------------------------
def build_energy():
    years = list(range(2020, 2036))
    # data-centre electricity demand, TWh (stack total on the IEA sources chart)
    demand = [310, 335, 365, 410, 465, 560, 660, 765, 870, 960,
              1050, 1130, 1195, 1250, 1295, 1335]
    # data-centre CO2 emissions, Mt (IEA emissions chart: rises, peaks ~2030)
    emissions = [122, 140, 150, 165, 185, 205, 230, 262, 292, 310,
                 322, 321, 318, 314, 309, 305]

    series = []
    n = len(years)
    for i, yr in enumerate(years):
        t = i / (n - 1)
        # fossil carbon intensity drifts down slightly (coal->gas + cleaner grid)
        intensity = 0.64 + (0.60 - 0.64) * t          # tCO2 / MWh
        fossil = emissions[i] / intensity              # Mt / (t/MWh) = TWh
        nonfossil = max(demand[i] - fossil, 0)
        nuke_frac = 0.22 + (0.20 - 0.22) * t
        nuclear = nonfossil * nuke_frac
        renew = nonfossil - nuclear
        series.append({
            "y": yr,
            "renew": round(renew),
            "nuclear": round(nuclear),
            "fossil": round(fossil),
            "demand": demand[i],
            "co2": emissions[i],
        })

    return {
        "series": series,
        "hist_through": 2024,        # solid up to here; dashed projection after
        "emissions_peak_year": 2030,
        "approximate": True,
    }


# --------------------------------------------------------------------------
# 3. AI incidents: per-year counts + curated notable markers
# --------------------------------------------------------------------------
CURATED = [
    # id, short label (shown on-chart only when callout=True), callout
    (1,   "First logged",      True),
    (6,   "Tay chatbot",       False),
    (4,   "First AV death",    False),
    (374, "Exam algorithm",    False),
    (694, "AI political ad",   True),
    (826, "Companion-AI harm", False),
    (940, "Self-driving crash", True),
]


def build_incidents():
    rows = list(csv.DictReader(open(RAW / "incidents.csv")))
    by_id = {r["incident_id"]: r for r in rows}

    counts = {}
    for r in rows:
        d = (r.get("date") or "").strip()
        if len(d) >= 4 and d[:4].isdigit():
            y = int(d[:4])
            if 2015 <= y <= 2026:
                counts[y] = counts.get(y, 0) + 1

    per_year = [{"y": y, "n": counts.get(y, 0)} for y in range(2015, 2027)]

    notable = []
    for iid, label, callout in CURATED:
        r = by_id.get(str(iid))
        if not r:
            continue
        notable.append({
            "id": iid,
            "date": r.get("date", ""),
            "x": dec_year(r["date"]),
            "label": label,
            "callout": callout,
            "title": clean(r.get("title", ""), 120),
            "desc": clean(r.get("description", ""), 180),
        })
    notable.sort(key=lambda m: m["x"])

    return {
        "per_year": per_year,
        "notable": notable,
        "partial_year": 2026,        # year-to-date, under-counted
        "total": sum(counts.values()),
    }


# --------------------------------------------------------------------------
def main():
    data = {
        "capability": build_capability(),
        "energy": build_energy(),
        "incidents": build_incidents(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(
        "/* Auto-generated by scripts/build_data.py — do not edit by hand. */\n"
        "window.CHART_DATA = " + payload + ";\n",
        encoding="utf-8",
    )
    kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT.relative_to(ROOT)}  ({kb:.1f} KB)")
    print(f"  capability: {len(data['capability']['dots'])} dots, "
          f"{len(data['capability']['frontier'])} frontier pts")
    print(f"  energy:     {len(data['energy']['series'])} years")
    print(f"  incidents:  {len(data['incidents']['per_year'])} years, "
          f"{len(data['incidents']['notable'])} notable")


if __name__ == "__main__":
    main()
