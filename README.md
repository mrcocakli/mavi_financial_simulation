# Mavi Giyim Treasury Simulation

A simulated corporate treasury function for Mavi Giyim Sanayi ve Ticaret A.Ş. (BIST: MAVI), built entirely from free, publicly available data. No paid terminals, no insider access — every figure traces back to a public filing or a public government data series.

**Status:** Active, refreshed monthly | **License:** MIT

## Why this exists

This project simulates the day-to-day work of a treasury/FP&A/trade finance analyst: tracking cash conversion cycles, mapping FX exposure, backtesting hedging strategies against real market data, and comparing trade financing structures — all built as a recurring, maintained system rather than a one-time exercise.

## Data Sources

| Source | Data | Access |
|---|---|---|
| [KAP](https://www.kap.org.tr) | Quarterly/annual consolidated financials | Manual extraction from filed PDFs, source-traced |
| Mavi Investor Relations | Same filings; FX risk disclosure notes | Manual extraction, direct PDF links |
| [TCMB EVDS](https://evds2.tcmb.gov.tr) | Daily FX rates, deposit rates, loan rates | Automated via Python (`tcmb` package) |
| Market benchmarks | LC commission rate assumption | Documented, sourced, flagged as an assumption |

## Project Phases

- [x] **1. Data infrastructure** — SQLite + Python ETL pipeline
- [x] **2. Financial baseline** — cash conversion cycle (DIO/DSO/DPO/CCC) as a time series
- [x] **3. FX exposure mapping** — validated against Mavi's own disclosed sensitivities
- [x] **4. Hedging policy backtest** — forward (CIRP-derived) vs. options collar vs. unhedged
- [x] **5. Financing structure comparison** — factoring vs. LC vs. supply chain finance
- [x] **6. Monthly treasury report** — auto-generated in Markdown, HTML, and Excel
- [x] **7. Pipeline automation** — full refresh via a single command
- [ ] **8. Ongoing publishing** — recurring public write-ups

## Key Findings

- Mavi's FX exposure is driven primarily by USD-denominated cash and debt balances, not trade receivables — most trade payables are TRY-denominated domestic transactions.
- A forward-hedge proxy (derived via covered interest rate parity, since no free TRY forward-quote data exists) outperformed remaining unhedged in most settled quarters — driven by TRY consistently depreciating less than the interest rate differential implied.
- Factoring receivables was found to be *more* expensive than plain commercial borrowing in Mavi's current rate environment — the opposite of the common assumption that factoring is cheap working capital.
- An initial LC-vs-SCF cost comparison was identified as methodologically flawed (comparing a flat fee against a full-balance financing cost) and was deliberately not shipped as a "winner" — both are reported independently with a note explaining why.

Full methodology, all assumptions, and complete results tables are in [`mavi_treasury_project_report.docx`](./mavi_treasury_project_report.docx) (or see `reports/` for the latest monthly output).

## Project Structure

mavi-treasury/
├── data/ # Manually curated source CSVs (financials, FX exposure)
│ ├── financials_template.csv
│ └── fx_exposure_template.csv
├── db/
│ ├── schema.sql # Full database schema
│ └── init_db.py
├── etl/ # All pipeline scripts
│ ├── load_fx_rates.py
│ ├── load_interest_rates.py
│ ├── load_financing_rates.py
│ ├── load_financials.py
│ ├── calculate_ratios.py
│ ├── load_fx_exposure.py
│ ├── calculate_fx_sensitivity.py
│ ├── calculate_hedging_backtest.py
│ ├── calculate_options_collar.py
│ ├── calculate_financing_scenarios.py
│ ├── generate_monthly_report.py
│ ├── generate_monthly_report_xlsx.py
│ └── run_pipeline.py # Runs everything, in order, in one command
├── reports/ # Generated monthly reports
├── verify_data.py # Data integrity checks
├── .env.example
├── requirements.txt
└── README.md

## Getting Started

```bash
git clone https://github.com/mrcocakli/mavi_financial_simulation.git
cd mavi_financial_simulation
pip install -r requirements.txt --break-system-packages

# Get a free EVDS API key: evds2.tcmb.gov.tr → register → Profilim → API Key
cp .env.example .env
# then edit .env and paste your key

python db/init_db.py
python etl/run_pipeline.py
```

New quarterly filing available? Manually add the relevant line items to `data/financials_template.csv` and `data/fx_exposure_template.csv` (see inline comments/format in each file), then rerun `python etl/run_pipeline.py`.

## Methodology Notes

Several inputs have no free public data source and are handled as explicitly documented proxies/assumptions rather than hidden estimates:

- **Forward rates**: derived via covered interest rate parity (CIRP), not observed from an actual forward market (none exists free for TRY).
- **Options collar**: constructed synthetically from realized historical volatility, tested at three collar widths (k = 0.5 / 0.75 / 1.0) for sensitivity, since no free TRY options market data exists.
- **Factoring rate**: proxied using TCMB's BRSA-regulated "financing companies" rate series, which bundles factoring, leasing, and consumer finance together — no factoring-only public series exists.
- **LC commission**: a documented market-benchmark assumption (~6% annualized), sourced from published Turkish trade-finance advisory material, not a live rate.

## Limitations

- Small sample size (currently 4 quarters) — patterns observed are directional, not statistically robust yet.
- Working-capital cost uses quarter-end balances, not period averages (a stated simplification).
- LC and SCF costs are intentionally *not* netted against each other, since they serve different treasury functions (risk mitigation vs. liquidity) and aren't directly comparable on the current model.

## Disclaimer

This is an independent educational project, not investment research or a comment on Mavi Giyim's actual treasury decisions. All figures are derived exclusively from Mavi's own public disclosures and TCMB's public data. This project is not affiliated with, endorsed by, or reviewed by Mavi Giyim Sanayi ve Ticaret A.Ş.

## Author

**Altay Marco Ocaklı** — B.Sc. Management, Bilkent University (expected June 2028)
Open to feedback from anyone in treasury, FP&A, or trade finance.

## License

MIT — see [LICENSE](./LICENSE).
