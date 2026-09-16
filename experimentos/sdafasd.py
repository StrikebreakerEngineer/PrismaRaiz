import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "datos" / "baseDeDatos"
MASTER_DB_PATH = DB_DIR / "master.db"

# Ensure master database directory exists
DB_DIR.mkdir(parents=True, exist_ok=True)

# Sources to merge: (db_filename, table_name)
sources = [
    (DB_DIR / "test_b.db", "rae_test_b"),
    (DB_DIR / "test_w.db", "rae_test_w"),
    # Add future letters here as you finish them:
    # (DB_DIR / "test_a.db", "rae_test_a"),
]

master_conn = sqlite3.connect(MASTER_DB_PATH)
master_conn.execute("PRAGMA journal_mode=WAL")

try:
    for src_path, table_name in sources:
        if not src_path.exists():
            print(f"Skipping {src_path.name} (not found)")
            continue
        
        print(f"Merging {table_name} from {src_path.name}...")
        
        # Attach the source database
        master_conn.execute(f"ATTACH DATABASE ? AS src;", (str(src_path),))
        
        # Create table in master if it doesn't exist and copy data
        master_conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} AS 
            SELECT * FROM src.{table_name};
        """)
        
        # Optional: Handle duplicate insertions if copying into an existing table
        master_conn.execute(f"""
            INSERT OR IGNORE INTO main.{table_name} 
            SELECT * FROM src.{table_name};
        """)
        
        master_conn.commit()
        master_conn.execute("DETACH DATABASE src;")
        print(f"Successfully merged {table_name}.")

    print(f"\nAll specified tables successfully consolidated into: {MASTER_DB_PATH}")

finally:
    master_conn.close()