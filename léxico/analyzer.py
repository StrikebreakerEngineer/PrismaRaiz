import unicodedata

import spacy
import stanza
from simplemma import lemmatize

from léxico.models import WordAnalysis

_nlp_stanza = None
_nlp_spacy = None


def remove_accents(text: str):
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


# --- STANZA CORES ---
def load_stanza_model():
    global _nlp_stanza
    if _nlp_stanza is None:
        print("Cargando modelo de Stanza...")
        _nlp_stanza = stanza.Pipeline(
            lang="es",
            processors="tokenize,pos,lemma",
            tokenize_pretokenized=True,
            use_gpu=True,
            verbose=False,
        )
        print("Modelo cargado.")
    return _nlp_stanza


def stanza_analyze_words_batch(word_rows, chunk_size=10000):
    nlp = load_stanza_model()
    analyzed_results = []
    total_words = len(word_rows)
    
    print(f"Iniciando análisis (Stanza CPU) de {total_words} palabras en lotes de {chunk_size}...")

    for i in range(0, total_words, chunk_size):
        chunk = word_rows[i:i + chunk_size]
        stanza_in = [[row["word"]] for row in chunk]
        doc = nlp(stanza_in)
        
        for idx, row in enumerate(chunk):
            if idx < len(doc.sentences) and doc.sentences[idx].words:
                word_obj = doc.sentences[idx].words[0]
                lemma = word_obj.lemma.strip() if word_obj.lemma else row["word"].strip()
                pos = word_obj.upos if word_obj.upos else "X"
            else:
                lemma = row["word"].strip()
                pos = "X"
                
            analyzed_results.append({
                "id": row["id"],
                "lemma": lemma,
                "part_of_speech": pos
            })
            
        current_progress = min(i + len(chunk), total_words)
        print(f"→ Neuronal Stanza: [{current_progress}/{total_words}] palabras lematizadas.")
        
    return analyzed_results


# --- SPACY CORES ---
def load_spacy_model():
    """Initializes spaCy using the fast CPU-optimized Spanish engine."""
    global _nlp_spacy
    if _nlp_spacy is None:
        print("Cargando modelo de spaCy...")
        # Disabling parser and named entity recognition maximizes execution speed
        _nlp_spacy = spacy.load("es_core_news_sm", disable=["parser", "ner"])
        print("Modelo de spaCy cargado exitosamente.")
    return _nlp_spacy

def spacy_analyze_words_batch(word_rows, chunk_size=30000):
    """
    Processes word rows using fast multi-core CPU parsing via spaCy.
    Outputs identical dictionary formats for seamless database swapping.
    """
    nlp = load_spacy_model()
    analyzed_results = []
    total_words = len(word_rows)
    
    # Extract only the plain text strings for spaCy's optimized internal pipeline loop
    words_only = [row["word"] for row in word_rows]
    
    # n_process=-1 splits the text across all available CPU threads automatically
    for idx, doc in enumerate(nlp.pipe(words_only, batch_size=chunk_size, n_process=-1)):
        row = word_rows[idx]
        
        # FIX: Check if the doc has tokens, then extract attributes from the first token (index 0)
        if len(doc) > 0:
            token = doc[0] 
            lemma = token.lemma_.strip() if token.lemma_ else row["word"].strip()
            pos = token.pos_ if token.pos_ else "X"
        else:
            lemma = row["word"].strip()
            pos = "X"
            
        analyzed_results.append({
            "id": row["id"],
            "lemma": lemma,
            "part_of_speech": pos
        })
            
    return analyzed_results


# --- SIMPLEMMA CORES ---
def dictionary_lemmatizer(word: str) -> WordAnalysis:
    lemma = lemmatize(word, lang='es')

    return WordAnalysis(
        lemma=lemma,
        part_of_speech="Unknown"
    )


def main():
    print(stanza_analyze_words_batch("solo"))

if __name__ == "__main__":
    main()