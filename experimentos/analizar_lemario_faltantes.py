import csv
import sqlite3
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DB_PATH = PROJECT_ROOT / "datos" / "basededatos" / "crawler.db"
LEMARIO_PATH = PROJECT_ROOT / "datos" / "sinProcesar" / "lemario.csv"

OUTPUT_DIR = (
    PROJECT_ROOT
    / "datos"
    / "procesado"
    / "comparacion_lemario_claves"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def normalizar_clave_lemario(header):
    """
    Convierte un header del lemario en la clave de búsqueda.

    Ejemplos:
        "-aco, ca"      -> "-aco"
        "abacalero, ra" -> "abacalero"
        "a-"            -> "a-"
        "a"             -> "a"
    """
    header = header.strip()

    if "," in header:
        header = header.split(",", 1)[0]

    return header.strip()


def cargar_lemario():
    entradas = []

    with LEMARIO_PATH.open(
        "r",
        encoding="utf-8",
        newline=""
    ) as f:
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
        query = f'SELECT key FROM "{table_name}"'

        for (key,) in conn.execute(query):
            claves.add(key)

    return claves


def clasificar_clave(clave):
    """
    Clasifica una clave faltante en una categoría útil.
    """

    if clave == "":
        return "vacía"

    # Formas que empiezan con guion
    if clave.startswith("-") and not clave.endswith("-"):
        return "empieza_con_guion"

    # Formas que terminan con guion
    if clave.endswith("-") and not clave.startswith("-"):
        return "termina_con_guion"

    # Forma "-algo-"
    if clave.startswith("-") and clave.endswith("-"):
        return "guiones_ambos_lados"

    # Un solo carácter
    if len(clave) == 1:
        return "un_solo_caracter"

    # Todo mayúsculas
    if clave.upper() == clave and any(c.isalpha() for c in clave):
        return "mayusculas"

    # Contiene espacios
    if any(c.isspace() for c in clave):
        return "contiene_espacios"

    # Contiene números
    if any(c.isdigit() for c in clave):
        return "contiene_numeros"

    # Empieza con mayúscula
    if clave[0].isupper():
        return "empieza_con_mayuscula"

    # Empieza con minúscula
    if clave[0].islower():
        return "minuscula"

    return "otro"


def guardar_csv(path, rows, fieldnames):
    with path.open(
        "w",
        encoding="utf-8",
        newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():

    print("Cargando lemario...")
    lemario = cargar_lemario()

    print("Abriendo crawler.db...")
    conn = sqlite3.connect(DB_PATH)

    print("Cargando claves del crawler...")
    crawler_keys = cargar_claves_crawler(conn)

    conn.close()

    # ---------------------------------------------------------
    # Obtener las claves únicas del lemario
    # ---------------------------------------------------------

    lemario_por_clave = {}

    for entrada in lemario:
        clave = entrada["clave"]

        if clave not in lemario_por_clave:
            lemario_por_clave[clave] = []

        lemario_por_clave[clave].append(entrada)

    lemario_keys = set(lemario_por_clave)

    faltantes = sorted(
        lemario_keys - crawler_keys,
        key=lambda x: (x.lower(), x)
    )

    # ---------------------------------------------------------
    # Clasificación
    # ---------------------------------------------------------

    categorias = {}

    for clave in faltantes:
        categoria = clasificar_clave(clave)

        categorias.setdefault(categoria, []).append(clave)

    # ---------------------------------------------------------
    # Resumen
    # ---------------------------------------------------------

    print()
    print("=" * 60)
    print("ANÁLISIS DE CLAVES DEL LEMARIO QUE FALTAN")
    print("=" * 60)

    print()
    print(f"Claves únicas lemario:       {len(lemario_keys):,}")
    print(f"Claves crawler:               {len(crawler_keys):,}")
    print(f"Claves faltantes:             {len(faltantes):,}")

    print()
    print("CATEGORÍAS")
    print("-" * 60)

    for categoria, claves in sorted(
        categorias.items(),
        key=lambda item: (-len(item[1]), item[0])
    ):
        print(f"{categoria:30} {len(claves):>6,}")

    # ---------------------------------------------------------
    # Mostrar cada categoría
    # ---------------------------------------------------------

    for categoria, claves in sorted(
        categorias.items(),
        key=lambda item: (-len(item[1]), item[0])
    ):
        print()
        print("=" * 60)
        print(f"{categoria.upper()} ({len(claves)})")
        print("=" * 60)

        for clave in claves:
            print(clave)

    # ---------------------------------------------------------
    # Guardar CSV general
    # ---------------------------------------------------------

    rows = []

    for clave in faltantes:
        categoria = clasificar_clave(clave)

        for entrada in lemario_por_clave[clave]:
            rows.append({
                "categoria": categoria,
                "clave": clave,
                "header": entrada["header"],
                "rae_id": entrada["rae_id"],
            })

    guardar_csv(
        OUTPUT_DIR / "05_lemario_faltantes_analizados.csv",
        rows,
        [
            "categoria",
            "clave",
            "header",
            "rae_id",
        ],
    )

    # ---------------------------------------------------------
    # Guardar un CSV por categoría
    # ---------------------------------------------------------

    for categoria, claves in categorias.items():

        category_rows = []

        for clave in claves:
            for entrada in lemario_por_clave[clave]:
                category_rows.append({
                    "clave": clave,
                    "header": entrada["header"],
                    "rae_id": entrada["rae_id"],
                })

        guardar_csv(
            OUTPUT_DIR / f"faltantes_{categoria}.csv",
            category_rows,
            [
                "clave",
                "header",
                "rae_id",
            ],
        )

    # ---------------------------------------------------------
    # Casos especiales
    # ---------------------------------------------------------

    print()
    print("=" * 60)
    print("CASOS ESPECIALES")
    print("=" * 60)

    for clave in ["a", "-a", "a-"]:
        entradas = lemario_por_clave.get(clave, [])

        print()
        print(f"CLAVE: {clave!r}")

        if not entradas:
            print("  No está en el lemario.")
        else:
            for entrada in entradas:
                print(
                    f"  header={entrada['header']!r}"
                    f"  rae_id={entrada['rae_id']}"
                )

        if clave in crawler_keys:
            print("  Crawler: SÍ")
        else:
            print("  Crawler: NO")

    # ---------------------------------------------------------
    # Estadística adicional:
    # ¿cuántas filas del lemario corresponden a claves faltantes?
    # ---------------------------------------------------------

    filas_faltantes = sum(
        len(lemario_por_clave[clave])
        for clave in faltantes
    )

    print()
    print("=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)

    print(f"Claves faltantes únicas:      {len(faltantes):,}")
    print(f"Filas del lemario afectadas:  {filas_faltantes:,}")

    print()
    print("Archivos guardados en:")
    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()