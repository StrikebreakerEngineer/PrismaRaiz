from léxico.analyzer import stanza_analyze_words_batch
from léxico.database import (
    create_lemma,
    create_lemma_raw_relation,
    get_connection,
    get_lemmas,
    get_unprocessed_raw_words,
)

LEMMATIZER = "Stanza"


def main():
    print("Iniciando Paso 02A: Lematización con Stanza...")

    connection = get_connection()

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

    print("\n--- PASO MIXTO: Procesamiento y Guardado en Flujo Constante ---")
    
    CHUNK_SIZE = 10000
    COMMIT_INTERVAL = 50000
    words_processed = 0

    # Step through your database records 10,000 items at a time
    for i in range(0, total, CHUNK_SIZE):
        chunk = raw_words[i:i + CHUNK_SIZE]
        
        # 1. Lemmatize just this 10k chunk
        # Note: Set chunk_size inside the analyzer call equal to len(chunk) so it runs in one go
        analyzed_chunk = stanza_analyze_words_batch(chunk, chunk_size=len(chunk))

        # 2. Process database cache/lookups for just this 10k chunk
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

            # 3. Checkpoint commit every 50,000 words total across chunks
            if words_processed % COMMIT_INTERVAL == 0:
                connection.commit()
                print(
                    f"\n💾 [CHECKPOINT] Guardado seguro parcial: "
                    f"[{words_processed}/{total}] registros confirmados en disco.\n"
                )

    # Final wrap-up commit for any leftover records
    print("\nVolcando lote de cierre final...")
    connection.commit()

    print("\n" + "=" * 50)
    print("¡Paso 02A completado exitosamente!")
    print(f"✓ Procesamiento completo con {LEMMATIZER}.")
    print("=" * 50)

    connection.close()


if __name__ == "__main__":
    main()