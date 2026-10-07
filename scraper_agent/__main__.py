import argparse
from datetime import datetime
from pathlib import Path

from .agent import run


def main() -> None:
    ap = argparse.ArgumentParser(prog="scraper_agent", description=__doc__)
    ap.add_argument("direction", help='where to look, e.g. "trade publications and associations in the plastics industry"')
    ap.add_argument("question", help='what to extract, e.g. "trade shows near me this year that customer XYZ will likely attend"')
    ap.add_argument("--location", default="unspecified", help='your location, e.g. "Cleveland, OH"')
    ap.add_argument("--out", help="output .xlsx or .csv (default: output/<timestamp>.xlsx)")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--max-turns", type=int, default=60)
    ap.add_argument("-q", "--quiet", action="store_true")
    a = ap.parse_args()

    rs = run(a.direction, a.question, a.location, a.max_turns, a.effort, not a.quiet)
    out = Path(a.out) if a.out else Path("output") / f"{datetime.now():%Y%m%d-%H%M%S}.xlsx"
    rs.save(out)
    print(f"\n{len(rs.rows)} rows -> {out}\n\n{rs.notes}")


if __name__ == "__main__":
    main()
