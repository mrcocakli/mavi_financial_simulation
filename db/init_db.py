"""
Run once (and again any time schema.sql changes) to (re)build the database.

Usage:
    python db/init_db.py
"""
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "db/mavi_treasury.db")
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    conn.commit()

    # sanity check: list tables created
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [row[0] for row in cur.fetchall()]
    conn.close()

    print(f"Database created/updated at: {DB_PATH}")
    print("Tables:")
    for t in tables:
        print(f"  - {t}")


if __name__ == "__main__":
    init_db()
