import csv
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DB_PATH = PROJECT_ROOT / "datos" / "basededatos" / "crawler.db"
LEMARIO_PATH = PROJECT_ROOT / "datos" / "sinProcesar" / "lemario.csv"

OUTPUT_DIR = PROJECT_ROOT / "datos" / "procesado" / "comparacion_lemario_claves"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def normalizar_clave_lemario(header):
    """
    Convierte un header del lemario en la clave que probablemente
    se usaría para /data/search.

    Ejemplos:
        "-aco, ca"       -> "-aco"
        "acarreado, da"  -> "acarreado"
        "ser"            -> "ser"
        "a-"             -> "a-"
    """
    header = header.strip()

    # Quitar coma + información de género/variantes.
    if "," in header:
        header = header.split(",", 1)[0]

    return header.strip()


def cargar_lemario():
    entradas = []

    with LEMARIO_PATH.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)

        for row in reader:
            if len(row) < 2:
                continue

            header = row[0].strip().strip('"')
            rae_id = row[1].strip().strip('"')

            if not header:
                continue

            clave = normalizar_clave_lemario(header)

            entradas.append({
                "header": header,
                "clave": clave,
                "rae_id": rae_id,
            })

    return entradas


def cargar_claves_crawler(conn):
    tablas = []

    rows = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name LIKE 'rae_keys_%'
        ORDER BY name
    """).fetchall()

    for (table_name,) in rows:
        tablas.append(table_name)

    claves = set()

    for table_name in tablas:
        # El nombre de la tabla viene de sqlite_master, no del usuario.
        query = f'SELECT key FROM "{table_name}"'

        for (key,) in conn.execute(query):
            claves.add(key)

    return claves, tablas


def guardar_csv(path, rows, fieldnames):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    print("Cargando lemario...")
    lemario = cargar_lemario()

    print("Abriendo crawler.db...")
    conn = sqlite3.connect(DB_PATH)

    print("Cargando claves del crawler...")
    crawler_keys, tables = cargar_claves_crawler(conn)

    conn.close()

    print()
    print(f"Tablas del crawler:       {len(tables):,}")
    print(f"Entradas del lemario:     {len(lemario):,}")
    print(f"Claves únicas crawler:   {len(crawler_keys):,}")

    # ---------------------------------------------------------
    # 1. Casos especiales que nos interesan directamente
    # ---------------------------------------------------------

    print()
    print("CLAVES ESPECIALES")
    print("-" * 50)

    for key in ["a", "-a", "a-"]:
        print(f"{key!r:8} -> {'SÍ' if key in crawler_keys else 'NO'}")

    # ---------------------------------------------------------
    # 2. Comparación por clave normalizada
    # ---------------------------------------------------------

    lemario_keys = {x["clave"] for x in lemario}

    both = lemario_keys & crawler_keys
    lemario_only_keys = lemario_keys - crawler_keys
    crawler_only_keys = crawler_keys - lemario_keys

    print()
    print("COMPARACIÓN POR CLAVE")
    print("-" * 50)
    print(f"Claves únicas lemario:       {len(lemario_keys):,}")
    print(f"Claves únicas crawler:       {len(crawler_keys):,}")
    print(f"Presentes en ambos:          {len(both):,}")
    print(f"Solo lemario:                 {len(lemario_only_keys):,}")
    print(f"Solo crawler:                 {len(crawler_only_keys):,}")

    # ---------------------------------------------------------
    # 3. Headers del lemario cuya clave YA existe
    # ---------------------------------------------------------

    richer_headers = [
        x for x in lemario
        if x["clave"] in crawler_keys
    ]

    missing_headers = [
        x for x in lemario
        if x["clave"] not in crawler_keys
    ]

    # ---------------------------------------------------------
    # 4. Guardar resultados
    # ---------------------------------------------------------

    guardar_csv(
        OUTPUT_DIR / "01_lemario_clave_ya_existe.csv",
        richer_headers,
        ["header", "clave", "rae_id"],
    )

    guardar_csv(
        OUTPUT_DIR / "02_lemario_clave_falta.csv",
        missing_headers,
        ["header", "clave", "rae_id"],
    )

    guardar_csv(
        OUTPUT_DIR / "03_lemario_claves_faltantes.csv",
        [{"clave": x} for x in sorted(lemario_only_keys)],
        ["clave"],
    )

    guardar_csv(
        OUTPUT_DIR / "04_crawler_claves_extra.csv",
        [{"clave": x} for x in sorted(crawler_only_keys)],
        ["clave"],
    )

    # ---------------------------------------------------------
    # 5. Mostrar ejemplos
    # ---------------------------------------------------------

    print()
    print("EJEMPLOS DE CLAVES DEL LEMARIO QUE FALTAN")
    print("-" * 50)

    for key in sorted(lemario_only_keys)[:100]:
        print(key)

    print()
    print("EJEMPLOS DE HEADERS DEL LEMARIO CUYA CLAVE YA EXISTE")
    print("-" * 50)

    count = 0

    for x in lemario:
        if x["clave"] in crawler_keys:
            print(
                f"{x['header']!r:35} -> {x['clave']!r}"
            )
            count += 1

            if count >= 30:
                break

    print()
    print("Archivos guardados en:")
    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()