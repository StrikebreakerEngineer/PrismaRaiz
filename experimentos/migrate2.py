import os
import sqlite3

# 1. Paths to your database
db_path = "datos/basededatos/crawler.db"
backup_path = "datos/basededatos/crawler_backup_before_migration.db"

# Safety backup check
if not os.path.exists(backup_path):
    print("Creating a safety backup of your database...")
    import shutil
    shutil.copy2(db_path, backup_path)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Turn on safety configurations
cursor.execute("PRAGMA foreign_keys = OFF;") # Off during restructuring

try:
    # --- STEP A: Create the new Registry Table ---
    print("Creating central feed registry...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feed_registry (
        registry_id INTEGER PRIMARY KEY AUTOINCREMENT
    );
    """)

    # --- STEP B: Find all your 29 alphabetical key tables ---
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'rae_keys_%';")
    key_tables = [row[0] for row in cursor.fetchall()]

    # We will temporarily hold a map of {'text_key': new_registry_id} to fix the master table later
    key_to_registry_id_map = {}

    # --- STEP C: Rebuild each key table to use the registry ---
    for table in key_tables:
        print(f"Migrating table: {table}...")
        
        # 1. Fetch all current data from this table
        cursor.execute(f"SELECT key, method, time FROM \"{table}\"")
        old_rows = cursor.fetchall()
        
        # 2. Drop the old table
        cursor.execute(f"DROP TABLE \"{table}\"")
        
        # 3. Re-create the table with the new FOREIGN KEY command matching the registry
        cursor.execute(f"""
        CREATE TABLE "{table}" (
            id INTEGER PRIMARY KEY,
            key TEXT NOT NULL UNIQUE,
            method TEXT NOT NULL,
            time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (id) REFERENCES feed_registry(registry_id) ON DELETE CASCADE
        );
        """)
        
        # 4. Loop through old data, register an ID, and insert it
        for key, method, time in old_rows:
            # Create a blank row in the master directory to generate a globally unique ID
            cursor.execute("INSERT INTO feed_registry DEFAULT VALUES;")
            new_id = cursor.lastrowid
            
            # Put the data into your specific key table using that exact ID
            cursor.execute(f"""
            INSERT INTO "{table}" (id, key, method, time)
            VALUES (?, ?, ?, ?);
            """, (new_id, key, method, time))
            
            # Keep track of this key's new ID for the master table migration next
            key_to_registry_id_map[key] = new_id

    # --- STEP D: Rebuild the master rae_ids table ---
    print("Migrating master table 'rae_ids'...")
    
    # 1. Get all data from current master table
    cursor.execute("SELECT key, header, rae_id, method, time, grp FROM rae_ids")
    old_master_rows = cursor.fetchall()
    
    # 2. Drop old master table
    cursor.execute("DROP TABLE rae_ids")
    
    # 3. Create new master table with the exact columns you asked for and the FOREIGN KEY command
    cursor.execute("""
    CREATE TABLE rae_ids (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        feed_id INTEGER,
        header TEXT,
        rae_id TEXT NOT NULL,
        method TEXT NOT NULL,
        time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, 
        grp INTEGER,
        UNIQUE(feed_id, rae_id),
        FOREIGN KEY (feed_id) REFERENCES feed_registry(registry_id) ON DELETE RESTRICT
    );
    """)
    
    # 4. Insert data back into master table using the new IDs instead of text keys
    for key, header, rae_id, method, time, grp in old_master_rows:
        # Look up the new number ID using the old text key
        feed_id = key_to_registry_id_map.get(key)
        
        if feed_id is not None:
            cursor.execute("""
            INSERT INTO rae_ids (feed_id, header, rae_id, method, time, grp)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (feed_id, header, rae_id, method, time, grp))
        else:
            # This handles cases where a master record exists but the key wasn't in any key table
            print(f"Warning: Key '{key}' in rae_ids did not match any entry in sub-tables. Skipped.")

    # Commit all changes to the database safely
    conn.commit()
    print("🎉 Success! Your database structure has been updated perfectly without data loss.")

except Exception as e:
    conn.rollback()
    print(f"❌ An error occurred! All changes rolled back. Your data is safe. Error: {e}")

finally:
    conn.close()