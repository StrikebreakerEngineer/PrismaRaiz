import stanza
from léxico.models import WordAnalysis
import unicodedata

_nlp = None


def load_model():
    global _nlp

    if _nlp is None:
        print("Cargando modelo de Stanza...")

        _nlp = stanza.Pipeline(
            lang="es",
            processors="tokenize,pos,lemma",
            tokenize_pretokenized=True,
            verbose=False,
        )

        print("Modelo cargado.")

    return _nlp


def remove_accents(text: str):
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def analyze_word(word: str) -> WordAnalysis:
    nlp = load_model()

    doc = nlp([[word]])

    token = doc.sentences[0].words[0]

    return WordAnalysis(
        lemma=token.lemma,
        part_of_speech=token.upos,
    )

def main():
    print(analyze_word("solo"))

if __name__ == "__main__":
    main()