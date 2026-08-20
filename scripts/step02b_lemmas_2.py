from léxico.analyzer import dictionary_lemmatizer
from léxico.database import (
    create_lemma,
    create_lemma_raw_relation,
    get_connection,
    get_lemmas,
    get_raw_words,
)


def main():
    print("Iniciando Paso 02: Lematización masiva corregida sin pérdidas...")
    
    connection = get_connection()
    raw_words = get_raw_words(connection)
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
        
        analysis = dictionary_lemmatizer(word_text)
        lemma_str = analysis.lemma.strip().lower()
        print(f"Lemma: {word_text} -> {lemma_str}")
        # Búsqueda en caché O(1) basada exclusivamente en el lema de texto
        if lemma_str in lemma_cache:
            lemma_id = lemma_cache[lemma_str]
        else:
            # Si el texto es nuevo, se delega al comando defensivo usando INSERT OR IGNORE
            lemma_id = create_lemma(
                connection, 
                (analysis.lemma, analysis.part_of_speech),
                source="simplemma",
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


"""
sqlite3 your_database.db ".output backup_tables.sql" "SELECT sql FROM sqlite_master WHERE type='table' AND name IN ('t01_raw_words', 't02_lemmas', 't03_word_lemmas', 't04_rae_entries');" ".dump t01_raw_words t02_lemmas t03_word_lemmas t04_rae_entries"
```[sqlite3]

### Option 2: Using Python (Recommended & Safe)
If you prefer a programmatic backup that you can run right before starting your script, use Python's built-in [sqlite3 backup API](https://python.org) to copy the entire active database into a safe `.bak` file:

```python
import sqlite3

def backup_database(source_db_path="lexico.db", backup_db_path="lexico_backup.bak"):
    src_conn = sqlite3.connect(source_db_path)
    dst_conn = sqlite3.connect(backup_db_path)
    
    with dst_conn:
        src_conn.backup(dst_conn)
        
    src_conn.close()
    dst_conn.close()
    print(f"✓ Backup successfully created at {backup_db_path}")

if __name__ == "__main__":
    backup_database()
```

<FollowUp>
If you'd like, I can show you how to integrate this **Python backup function** directly at the very beginning of your `main()` script so it automatically backups up before running any modifications.
</FollowUp>

"""