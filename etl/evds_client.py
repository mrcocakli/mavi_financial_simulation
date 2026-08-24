"""
Thin wrapper around the `tcmb` package (PyPI: tcmb), which talks to TCMB's
EVDS3 Web Service.

WHY A THIRD-PARTY PACKAGE HERE, WHEN THE REST OF THIS PROJECT AVOIDS THEM:
As of August 2026, TCMB has migrated EVDS from
  evds2.tcmb.gov.tr/service/evds/
to a new backend at
  evds3.tcmb.gov.tr/igmevdsms-dis/
which also uses a non-standard URL construction (query parameters are
appended directly to the path, with NO leading "?"). Hand-rolling this is
fragile against TCMB changing things again, and easy to get subtly wrong.
The `tcmb` package (MIT license, github.com/kaymal/tcmb-py) already tracks
this correctly and is small enough to read end to end in a few minutes.
Depending on a small, inspectable, actively maintained wrapper for a moving
government API is a defensible engineering call worth being able to explain
if asked in an interview — the earlier version of this file hand-rolled the
request against the OLD (now-dead) evds2 endpoint, which is exactly the kind
of breakage this kind of dependency choice avoids.

get_evds_series() returns a pandas DataFrame:
  - index: DatetimeIndex (one row per date)
  - columns: one per series code, with dots replaced by underscores
    e.g. 'TP.DK.USD.A.YTL' -> column 'TP_DK_USD_A_YTL'
"""
import os
import tcmb
from dotenv import load_dotenv

load_dotenv()


def get_evds_series(series_codes: list[str], start_date: str, end_date: str,
                     api_key: str | None = None):
    """
    Pull one or more EVDS series for a date range.

    Args:
        series_codes: list of EVDS series codes, e.g. ['TP.DK.USD.A.YTL']
        start_date: 'YYYY-MM-DD' (or 'DD-MM-YYYY', both accepted)
        end_date:   'YYYY-MM-DD' (or 'DD-MM-YYYY', both accepted)
        api_key: defaults to EVDS_API_KEY from .env

    Returns:
        pandas.DataFrame as described above.

    Raises:
        tcmb.errors.ApiKeyError if the key is invalid.
        Various requests errors on network failure.
    """
    api_key = api_key or os.getenv("EVDS_API_KEY")
    if not api_key:
        raise ValueError("No EVDS_API_KEY found. Check your .env file.")

    return tcmb.read(series_codes, start=start_date, end=end_date, api_key=api_key)
