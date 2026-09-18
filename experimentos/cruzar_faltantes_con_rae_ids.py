import csv
import sqlite3
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DB_PATH = PROJECT_ROOT / "datos" / "basededatos" / "crawler.db"
LEMARIO_PATH = PROJECT_ROOT / "datos" / "sinProcesar" / "lemario.csv"

INPUT_PATH = (
    PROJECT_ROOT
    / "datos"
    / "procesado"
    / "comparacion_lemario_claves"
    / "05_lemario_faltantes_analizados.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "datos"
    / "procesado"
    / "comparacion_lemario_claves"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def cargar_faltantes():
    """
    Carga las claves del lemario que no aparecen en rae_keys_*.
    """

    faltantes = []

    with INPUT_PATH.open(
        "r",
        encoding="utf-8",
        newline=""
    ) as f:
        reader = csv.DictReader(f)

        for row in reader:
            faltantes.append({
                "categoria": row["categoria"],
                "clave": row["clave"],
                "header": row["header"],
                "rae_id": row["rae_id"],
            })

    return faltantes


def cargar_rae_ids(conn):
    """
    Carga toda la información de rae_ids agrupada por RAE ID.
    """

    por_rae_id = defaultdict(list)

    rows = conn.execute("""
        SELECT
            id,
            feed_id,
            header,
            rae_id,
            method,
            time,
            grp
        FROM rae_ids
        ORDER BY id
    """).fetchall()

    for row in rows:
        (
            local_id,
            feed_id,
            header,
            rae_id,
            method,
            time,
            grp,
        ) = row

        por_rae_id[rae_id].append({
            "id": local_id,
            "feed_id": feed_id,
            "header": header,
            "rae_id": rae_id,
            "method": method,
            "time": time,
            "grp": grp,
        })

    return por_rae_id


def cargar_rae_ids_por_header(conn):
    """
    También crea un índice por header.
    """

    por_header = defaultdict(list)

    rows = conn.execute("""
        SELECT
            id,
            feed_id,
            header,
            rae_id,
            method,
            time,
            grp
        FROM rae_ids
        ORDER BY id
    """).fetchall()

    for row in rows:
        (
            local_id,
            feed_id,
            header,
            rae_id,
            method,
            time,
            grp,
        ) = row

        if header is None:
            continue

        por_header[header].append({
            "id": local_id,
            "feed_id": feed_id,
            "header": header,
            "rae_id": rae_id,
            "method": method,
            "time": time,
            "grp": grp,
        })

    return por_header


def main():

    print("Cargando claves faltantes...")
    faltantes = cargar_faltantes()

    print("Abriendo crawler.db...")
    conn = sqlite3.connect(DB_PATH)

    print("Cargando rae_ids...")
    por_rae_id = cargar_rae_ids(conn)

    print("Creando índice por header...")
    por_header = cargar_rae_ids_por_header(conn)

    conn.close()

    print()
    print("=" * 70)
    print("CRUCE DE FALTANTES CON rae_ids")
    print("=" * 70)

    print()
    print(f"Filas faltantes cargadas:       {len(faltantes):,}")
    print(f"RAE IDs únicos en rae_ids:      {len(por_rae_id):,}")
    print(f"Headers indexados:               {len(por_header):,}")

    # ---------------------------------------------------------
    # Clasificar
    # ---------------------------------------------------------

    resultados = []

    contadores = defaultdict(int)

    for item in faltantes:

        old_rae_id = item["rae_id"]
        old_header = item["header"]
        clave = item["clave"]

        id_match = old_rae_id in por_rae_id

        header_match = old_header in por_header

        if id_match and header_match:
            estado = "ID_Y_HEADER_EXISTEN"

        elif id_match:
            estado = "ID_EXISTE_HEADER_NO"

        elif header_match:
            estado = "ID_NO_HEADER_EXISTE"

        else:
            estado = "NINGUNO"

        contadores[estado] += 1

        # Información de IDs actuales encontrados
        current_ids = []

        if header_match:
            current_ids = sorted({
                x["rae_id"]
                for x in por_header[old_header]
            })

        # Información del ID antiguo
        current_headers_for_old_id = []

        if id_match:
            current_headers_for_old_id = sorted({
                x["header"]
                for x in por_rae_id[old_rae_id]
                if x["header"] is not None
            })

        resultados.append({
            "categoria": item["categoria"],
            "clave": clave,
            "old_header": old_header,
            "old_rae_id": old_rae_id,
            "estado": estado,
            "current_ids_by_header": "; ".join(current_ids),
            "current_headers_by_old_id": "; ".join(
                current_headers_for_old_id
            ),
        })

    # ---------------------------------------------------------
    # Mostrar resumen
    # ---------------------------------------------------------

    print()
    print("ESTADOS")
    print("-" * 70)

    for estado, cantidad in sorted(
        contadores.items(),
        key=lambda x: (-x[1], x[0])
    ):
        print(f"{estado:35} {cantidad:>6,}")

    # ---------------------------------------------------------
    # Mostrar ejemplos
    # ---------------------------------------------------------

    for estado in [
        "ID_Y_HEADER_EXISTEN",
        "ID_EXISTE_HEADER_NO",
        "ID_NO_HEADER_EXISTE",
        "NINGUNO",
    ]:

        rows = [
            x for x in resultados
            if x["estado"] == estado
        ]

        print()
        print("=" * 70)
        print(f"{estado} ({len(rows)})")
        print("=" * 70)

        for row in rows[:50]:
            print(
                f"{row['clave']!r:25} "
                f"old_id={row['old_rae_id']:<10} "
                f"header={row['old_header']!r}"
            )

            if row["current_ids_by_header"]:
                print(
                    f"    IDs por header: "
                    f"{row['current_ids_by_header']}"
                )

            if row["current_headers_by_old_id"]:
                print(
                    f"    Headers por ID: "
                    f"{row['current_headers_by_old_id']}"
                )

    # ---------------------------------------------------------
    # Guardar resultado completo
    # ---------------------------------------------------------

    output_path = OUTPUT_DIR / "06_cruce_faltantes_rae_ids.csv"

    with output_path.open(
        "w",
        encoding="utf-8",
        newline=""
    ) as f:

        fieldnames = [
            "categoria",
            "clave",
            "old_header",
            "old_rae_id",
            "estado",
            "current_ids_by_header",
            "current_headers_by_old_id",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(resultados)

    # ---------------------------------------------------------
    # Guardar cada estado separado
    # ---------------------------------------------------------

    for estado in contadores:

        rows = [
            x for x in resultados
            if x["estado"] == estado
        ]

        path = (
            OUTPUT_DIR
            / f"06_{estado.lower()}.csv"
        )

        with path.open(
            "w",
            encoding="utf-8",
            newline=""
        ) as f:

            fieldnames = [
                "categoria",
                "clave",
                "old_header",
                "old_rae_id",
                "estado",
                "current_ids_by_header",
                "current_headers_by_old_id",
            ]

            writer = csv.DictWriter(
                f,
                fieldnames=fieldnames
            )

            writer.writeheader()
            writer.writerows(rows)

    print()
    print("=" * 70)
    print("ARCHIVOS")
    print("=" * 70)

    print(output_path)

    print()
    print("No se hicieron solicitudes a RAE.")
    print("No se modificó crawler.db.")


if __name__ == "__main__":
    main()