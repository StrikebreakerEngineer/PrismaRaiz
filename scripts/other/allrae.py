import re
from pathlib import Path

from léxico.database import (
    PROJECT_ROOT,
    create_raw_word,
    create_raw_word_source,
    get_connection,
)

# Target the text file from your directory setup
TXT_FILE = (
    PROJECT_ROOT
    / "datos"
    / "sinProcesar"
    / "allwords.txt"
)


def expand_gender_pair(line: str) -> list[str]:
    """
    Expande las diferentes estructuras que utiliza RAE en allwords.txt.

    Ejemplos:

        tifo, fa
            -> ["tifo", "tifa"]

        tiliáceo, a
            -> ["tiliáceo", "tiliácea"]

        cefalo-, -céfalo, la
            -> ["cefalo-", "-céfalo", "-céfala"]

        fago-, ‒́fago, ga
            -> ["fago-", "‒́fago", "‒́faga"]

    Las entradas que no correspondan a una estructura conocida
    se conservan como una sola entrada.
    """

    line = line.strip()

    if not line:
        return []

    # ---------------------------------------------------------------
    # No commas = single entry
    # ---------------------------------------------------------------
    if "," not in line:
        return [line]

    parts = [part.strip() for part in line.split(",")]

    # Remove empty pieces defensively
    parts = [part for part in parts if part]

    if not parts:
        return []

    # ---------------------------------------------------------------
    # Two-part gender pair
    #
    # tifo, fa
    # tiliáceo, a
    #
    # -> masculine/base form + feminine form
    # ---------------------------------------------------------------
    if len(parts) == 2:
        first, second = parts

        # Standard abbreviated feminine ending:
        #
        # tifo, fa -> tifo, tifa
        # blanco, ca -> blanco, blanca
        #
        # The second part is an ending rather than a complete word.
        if (
            len(second) <= 3
            and second.endswith(("a", "as"))
            and first.endswith(("o", "e"))
        ):
            if first.endswith("o"):
                return [
                    first,
                    first[:-1] + "a",
                ]

            # For unusual cases ending in -e, preserve the supplied
            # second element rather than inventing a transformation.
            return [first, second]

        # If the second element is already a complete-looking form,
        # preserve both independently.
        return [first, second]

    # ---------------------------------------------------------------
    # Three-part RAE structural gender entry
    #
    # cefalo-, -céfalo, la
    # -> cefalo-
    # -> -céfalo
    # -> -céfala
    #
    # fago-, ‒́fago, ga
    # -> fago-
    # -> ‒́fago
    # -> ‒́faga
    #
    # The third component is an abbreviated gender ending that applies
    # to the SECOND structural form.
    # ---------------------------------------------------------------
    if len(parts) == 3:
        first, second, third = parts

        # A short final component such as:
        #
        # la
        # ga
        # fa
        # ma
        # ra
        # ta
        #
        # is an abbreviated gender ending.
        if len(third) <= 3:
            # Preserve the first structural entry.
            results = [first]

            # Preserve the second structural entry.
            results.append(second)

            # Construct the feminine counterpart of the second entry.
            #
            # -céfalo + "la" -> -céfala
            # ‒́fago + "ga" -> ‒́faga
            #
            # Usually the final character of the supplied ending is
            # the actual gender vowel.
            if third.endswith("a") and second.endswith("o"):
                results.append(second[:-1] + "a")
            elif third.endswith("a") and second.endswith("e"):
                results.append(second)
            elif third.endswith("a"):
                # If the structural form does not end in a standard
                # masculine vowel, preserve the second form rather
                # than producing a speculative transformation.
                results.append(second)
            else:
                # Defensive fallback: retain the supplied final form.
                results.append(third)

            return results

        # Unknown three-part structure:
        # preserve every component separately rather than combining
        # them into a single invalid database entry.
        return parts

    # ---------------------------------------------------------------
    # More than three components
    #
    # Keep each component separately. This is safer for RAE structural
    # data than joining them into one artificial "word".
    # ---------------------------------------------------------------
    return parts


def is_valid_spanish_entry(word: str) -> bool:
    """
    Valida si una entrada corresponde a un elemento estructural válido
    del listado de la RAE.

    Permite:

    - letras españolas
    - letras con diacríticos
    - espacios
    - guion ASCII -
    - guion U+2010 ‐
    - guion U+2011 -
    - figure dash U+2012 ‒
    - en dash U+2013 –
    - em dash U+2014 —
    - acento agudo combinante U+0301

    Esto es importante porque allwords.txt contiene entradas como:

        ‒́cola
        ‒́foba
        ‒́fobo
        ‒́fora
        ‒́foro
        ‒́gena
        ‒́gono

    que son entradas reales del RAE.
    """

    pattern = (
        r"^[a-záéíóúüñ"
        r"\s"
        r"\-"
        r"\u2010"
        r"\u2011"
        r"\u2012"
        r"\u2013"
        r"\u2014"
        r"\u0301"
        r"]+$"
    )

    return bool(re.fullmatch(pattern, word))


def load_words_from_txt(txt_file: Path) -> list[str]:
    """
    Lee allwords.txt línea por línea y expande las estructuras
    morfológicas/género utilizadas por la RAE.
    """

    print(f"Cargando y expandiendo palabras desde {txt_file.name}...")

    expanded_words = []

    with open(txt_file, "r", encoding="utf-8") as file:
        for line in file:
            line_words = expand_gender_pair(line)

            for word in line_words:
                cleaned = word.strip().lower()

                if cleaned:
                    expanded_words.append(cleaned)

    print(
        f"Se han cargado y expandido "
        f"{len(expanded_words):,} variaciones!"
    )
    print()

    return expanded_words


def import_new_words(words: list[str], source: str) -> None:
    """
    Importa las palabras y sus fuentes utilizando el pipeline de
    léxico.database.

    Acepta:

    - palabras normales
    - locuciones
    - prefijos
    - sufijos
    - extranjerismos
    - elementos compositivos
    - formas con guiones tipográficos de la RAE

    Los elementos que no pasan la validación se muestran al final.
    """

    connection = get_connection()

    processed = 0
    added = 0
    existing = 0
    discarded = 0

    discarded_items = []

    try:
        for index, word in enumerate(words, start=1):
            processed += 1

            # -------------------------------------------------------
            # Validate entry
            # -------------------------------------------------------
            if not is_valid_spanish_entry(word):
                discarded += 1
                discarded_items.append(word)
                continue

            # -------------------------------------------------------
            # Insert into t01a_raw_words
            # -------------------------------------------------------
            word_id, was_created = create_raw_word(
                connection,
                word,
                commit_index=-1,
            )

            if word_id is not None:

                if was_created:
                    added += 1
                else:
                    existing += 1

                # ---------------------------------------------------
                # Register source + original rank in t01b
                # ---------------------------------------------------
                create_raw_word_source(
                    connection,
                    word_id,
                    index,
                    source,
                    commit_index=-1,
                )

            # -------------------------------------------------------
            # Progress
            # -------------------------------------------------------
            if index % 2000 == 0:
                connection.commit()

                print(
                    f"Procesadas: {index:,} | "
                    f"Añadidas: {added:,} | "
                    f"Ya existían: {existing:,} | "
                    f"Descartadas: {discarded:,}"
                )

        # -----------------------------------------------------------
        # Final commit
        # -----------------------------------------------------------
        connection.commit()

        print()
        print("✓ Importación terminada")
        print(f"  Palabras procesadas:  {processed:,}")
        print(f"  Palabras añadidas:    {added:,}")
        print(f"  Palabras ya existían: {existing:,}")
        print(f"  Palabras descartadas: {discarded:,}")
        print()

        # -----------------------------------------------------------
        # Discarded entries
        # -----------------------------------------------------------
        if discarded_items:
            unique_discarded = sorted(set(discarded_items))

            print(
                "--- ELEMENTOS REALMENTE DESCARTADOS "
                "(Fallo RegEx) ---"
            )

            for item in unique_discarded:
                print(f"  - {item}")

            print(
                f"Total de elementos únicos descartados: "
                f"{len(unique_discarded):,}"
            )

        else:
            print("¡Perfecto! No se descartó ningún elemento.")

    finally:
        connection.close()


def main():
    words = load_words_from_txt(TXT_FILE)

    import_new_words(
        words,
        source=TXT_FILE.name,
    )

    connection = get_connection()
    word_id, was_created = create_raw_word(connection, "ampère")
    create_raw_word_source(
                        connection,
                        word_id,
                        676767,
                        source=TXT_FILE.name
                    )


if __name__ == "__main__":
    main()