"""
Recalculates every .xlsx in reports/ with headless LibreOffice so formula
cells carry cached values (openpyxl writes formulas without results).

Runs in the scheduled GitHub Actions refresh, where nobody opens the files in
Excel. On a machine without LibreOffice it prints a note and exits cleanly;
opening and saving the file in Excel does the same job.

Usage:
    python etl/recalc_xlsx.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPORTS = Path("reports")


def main():
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    files = sorted(REPORTS.glob("*.xlsx"))
    if not soffice:
        print("LibreOffice not found - skipping. Open the .xlsx files in Excel and save once instead.")
        return
    failed = 0
    for f in files:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([soffice, "--headless", "--convert-to", "xlsx", "--outdir", tmp, str(f)],
                           check=False, capture_output=True, timeout=180)
            out = Path(tmp) / f.name
            if out.exists() and out.stat().st_size > 0:
                shutil.copyfile(out, f)
                print(f"Recalculated {f}")
            else:
                failed += 1
                print(f"FAILED to recalculate {f}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
