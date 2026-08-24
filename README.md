# Mavi Giyim (BIST: MAVI) Treasury Simulation

Long-term, monthly-maintained treasury analyst project. Free public data only:
KAP (kap.org.tr), Mavi Investor Relations, TCMB EVDS, TÜİK.

## Folder structure

```
mavi-treasury/
  db/
    schema.sql          -- SQLite schema, single source of truth for table structure
    init_db.py           -- runs schema.sql, creates mavi_treasury.db
    mavi_treasury.db     -- created after you run init_db.py (not in version control)
  etl/
    evds_client.py        -- reusable function to call the EVDS API
    test_evds_connection.py -- Step 1 check: confirms your API key + DB write path work
    load_fx_rates.py       -- Step 3: pulls USD/TRY, EUR/TRY daily series into fx_rates
    load_financials.py     -- Step 2: where you'll manually enter/parse KAP figures
  reports/                -- monthly output files land here (pdf/xlsx/pptx)
  notebooks/              -- scratch analysis, ratio calcs, backtest work
  .env.example            -- copy to .env, fill in your EVDS key, never commit .env
  requirements.txt
  README.md
```

## Step 1 — Set up the environment (do this first, today)

```bash
cd mavi-treasury
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then paste your EVDS key into .env
python db/init_db.py            # builds the empty database from schema.sql
python etl/test_evds_connection.py   # confirms EVDS tap works end to end
```

If `test_evds_connection.py` prints a small table of USD/TRY and EUR/TRY rates
for the last 10 days, your infrastructure is live. Nothing else should be
built until this passes.

## Why SQLite (not Postgres/MySQL)

- Zero server setup, single file (`mavi_treasury.db`), trivially portable —
  you can attach it to a job application or push it to GitHub (schema only,
  not the .db file if it has data you don't want public).
- SQL skills transfer 1:1 to Postgres/MySQL later; the syntax you're learning
  on DataCamp is standard SQL, not SQLite-specific, with a couple of minor
  exceptions (noted in schema.sql comments).
- Swappable later: if you want Postgres for the CV signal, the schema.sql
  is close to portable — flag it if you want that later, it's a ~1 hour swap.

## Design principle carried through every step

Raw pulled data (KAP line items, EVDS rates) is stored **as extracted**, with
a source reference and retrieval timestamp. Every derived number (DIO, DSO,
CCC, hedge P&L) is calculated in Python from that raw data, never hand-typed
into the database. This is what makes the project traceable — you can always
answer "where did this number come from" by following raw table -> calculation
script -> derived table.
