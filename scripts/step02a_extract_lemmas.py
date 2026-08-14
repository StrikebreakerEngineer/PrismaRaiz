from léxico.analyzer import analyze_word
from léxico.database import (
    create_lemma,
    create_lemma_raw_relation,
    get_connection,
    get_lemmas,
    get_unprocessed_raw_words,
)


def main():
    print("Iniciando Paso 02: Lematización masiva corregida sin pérdidas...")
    
    connection = get_connection()
    raw_words = get_unprocessed_raw_words(connection)
    total = len(raw_words)
    
    print(f"Se encontraron {total} palabras crudas pendientes por analizar.")
    if total == 0:
        print("✓ El procesamiento de lemas ya está al día.")
        connection.close()
        return

    # Cargamos el caché estructurado únicamente por texto
    lemma_cache = get_lemmas(connection)
    print(f"✓ Caché de texto inicializado con {len(lemma_cache)} registros.")
    
    print("\nProcesando análisis morfológico e inyección de correspondencias...")
    for index, raw_row in enumerate(raw_words, start=1):
        word_id = raw_row["id"]
        word_text = raw_row["word"]
        
        analysis = analyze_word(word_text)
        lemma_str = analysis.lemma.strip().lower()
        
        # Búsqueda en caché O(1) basada exclusivamente en el lema de texto
        if lemma_str in lemma_cache:
            lemma_id = lemma_cache[lemma_str]
        else:
            # Si el texto es nuevo, se delega al comando defensivo usando INSERT OR IGNORE
            lemma_id = create_lemma(
                connection, 
                (analysis.lemma, analysis.part_of_speech),
                commit_index=-1
            )
            lemma_cache[lemma_str] = lemma_id
            
        create_lemma_raw_relation(connection, (word_id, lemma_id), commit_index=-1)

        # Volcado periódico en ráfagas transaccionales de 100 filas
        if index % 100 == 0: 
            connection.commit()
            print(f" Progreso: [{index}/{total}] relaciones guardadas...")

    # =====================================================================
    # VACIADO COMPLETO DEL LOTE REMANENTE (Evita la fuga de datos)
    # =====================================================================
    print("\nVolcando lote de cierre final...")
    connection.commit()

    print("\n" + "="*50)
    print("¡Paso 02 completado exitosamente!")
    print("✓ Se garantizó el mapeo íntegro en t03_word_lemmas.")
    print("="*50)
    
    connection.close()

if __name__ == "__main__":
    main()