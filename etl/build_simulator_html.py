"""
Treasury simulator — standalone web page builder.

Injects the baseline quarters from the database into
dashboard/simulator_template.html and writes reports/treasury_simulator.html,
a single self-contained file (no server, no external libraries) that can be
opened in any browser or published as a shareable page.

Usage:
    python etl/build_simulator_html.py
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulator_engine import DEFAULT_ASSUMPTIONS, PRESETS, load_baselines  # noqa: E402

DB_PATH = "db/mavi_treasury.db"
TEMPLATE = "dashboard/simulator_template.html"
OUT_PATH = "reports/treasury_simulator.html"
PAGES_PATH = "docs/index.html"   # served by GitHub Pages (Settings > Pages > main /docs)
MARKER = "/*__DATA__*/null"


def main():
    baselines, asof = load_baselines(DB_PATH)
    if not baselines:
        sys.exit("No complete baseline quarter in the database; run the pipeline first.")
    data = {
        "baselines": baselines,
        "presets": [{"name": n, "scenario": s} for n, s in PRESETS],
        "assumptions": DEFAULT_ASSUMPTIONS,
        "asof": asof,
        "built": date.today().isoformat(),
    }
    html = Path(TEMPLATE).read_text(encoding="utf-8")
    if MARKER not in html:
        sys.exit(f"Template marker {MARKER} not found in {TEMPLATE}.")
    page = html.replace(MARKER, json.dumps(data))
    Path(OUT_PATH).write_text(page, encoding="utf-8")
    Path(PAGES_PATH).parent.mkdir(exist_ok=True)
    Path(PAGES_PATH).write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_PATH} and {PAGES_PATH}: {len(baselines)} baseline quarter(s), FX data to {asof}.")


if __name__ == "__main__":
    main()
