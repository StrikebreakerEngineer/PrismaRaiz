import sqlite3
from pathlib import Path

DB_PATH = Path("datos/baseDeDatos/crawler.db")


def main():
    connection = sqlite3.connect(DB_PATH)

    try:
        cursor = connection.cursor()

        # Find all rae_keys_* tables
        cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name LIKE 'rae_keys_%'
            ORDER BY name
        """)

        tables = [row[0] for row in cursor.fetchall()]

        print(f"Encontradas {len(tables)} tablas.")
        print()

        # Migrate each letter/special-character table
        for table in tables:
            print(f"Migrando: {table}")

            temp_table = f"__temp_{table}"

            # Create new structure
            cursor.execute(f'''
                CREATE TABLE "{temp_table}" (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    method TEXT NOT NULL,
                    time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Copy existing data.
            # Explicitly copy the original timestamp.
            cursor.execute(f'''
                INSERT INTO "{temp_table}" (id, key, method, time)
                SELECT id, key, method, time
                FROM "{table}"
            ''')

            # Remove old table
            cursor.execute(f'DROP TABLE "{table}"')

            # Rename temporary table
            cursor.execute(
                f'ALTER TABLE "{temp_table}" RENAME TO "{table}"'
            )

            print("  ✓ listo")

        # Create the new RAE IDs table
        print()
        print("Creando: rae_ids")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rae_ids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                header TEXT,
                rae_id TEXT NOT NULL,
                method TEXT NOT NULL,
                time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(key, rae_id)
            )
        """)

        connection.commit()

        print()
        print("Migración completada.")
        print(f"Tablas migradas: {len(tables)}")
        print("Tabla creada: rae_ids")

    except Exception:
        connection.rollback()
        print()
        print("ERROR: se revirtieron los cambios.")
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    main()