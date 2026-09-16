from léxico.analyzer import spacy_analyze_words_batch
from léxico.database import (
    create_lemma,
    create_lemma_raw_relation,
    get_connection,
    get_lemmas,
    get_unprocessed_raw_words,
)

LEMMATIZER = "spaCy_sm"


def main():
    print(f"Iniciando Paso 02B: Lematización de flujo con {LEMMATIZER}...")

    connection = get_connection()

    # Automatically retrieves words where lemmatizer = 'spaCy' hasn't run yet
    raw_words = get_unprocessed_raw_words(
        connection,
        LEMMATIZER,
    )

    total = len(raw_words)

    print(
        f"Se encontraron {total} palabras crudas pendientes "
        f"para {LEMMATIZER}."
    )

    if total == 0:
        print(f"✓ El procesamiento con {LEMMATIZER} ya está al día.")
        connection.close()
        return

    lemma_cache = get_lemmas(connection)

    print(
        f"✓ Caché de lemas inicializado con "
        f"{len(lemma_cache)} registros."
    )

    print(f"\n--- PASO MIXTO: Procesamiento y Guardado Constante ({LEMMATIZER}) ---")
    
    CHUNK_SIZE = 10000
    COMMIT_INTERVAL = 50000
    words_processed = 0

    for i in range(0, total, CHUNK_SIZE):
        chunk = raw_words[i:i + CHUNK_SIZE]
        
        # Process the 10k chunk lightning-fast via spaCy's CPU threads
        analyzed_chunk = spacy_analyze_words_batch(chunk, chunk_size=len(chunk))

        # Perform lookups, cache validation, and execution inserts
        for analysis in analyzed_chunk:
            word_id = analysis["id"]
            lemma_text = analysis["lemma"]
            pos = analysis["part_of_speech"]

            lemma_key = lemma_text.lower()

            if lemma_key in lemma_cache:
                lemma_id = lemma_cache[lemma_key]
            else:
                lemma_id = create_lemma(
                    connection,
                    (
                        lemma_text,
                        pos,
                    ),
                    commit_index=-1,
                )
                lemma_cache[lemma_key] = lemma_id

            create_lemma_raw_relation(
                connection,
                (
                    word_id,
                    lemma_id,
                    LEMMATIZER,
                ),
                commit_index=-1,
            )
            
            words_processed += 1

            # Commit to disk every 50k processed words to preserve state safely
            if words_processed % COMMIT_INTERVAL == 0:
                connection.commit()
                print(
                    f"💾 [CHECKPOINT] Guardado seguro parcial {LEMMATIZER}: "
                    f"[{words_processed}/{total}] registros confirmados en base de datos."
                )

    # Final commit for the remaining rows
    print("\nVolcando lote de cierre final...")
    connection.commit()

    print("\n" + "=" * 50)
    print("¡Paso 02B completado exitosamente!")
    print(f"✓ Procesamiento completo con {LEMMATIZER}.")
    print("=" * 50)

    connection.close()


if __name__ == "__main__":
    main()