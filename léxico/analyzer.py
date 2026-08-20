import unicodedata

import stanza
from simplemma import lemmatize

from léxico.models import WordAnalysis

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


def stanza_analyze_word(word: str) -> WordAnalysis:
    nlp = load_model()

    doc = nlp([[word]])

    token = doc.sentences[0].words[0]

    return WordAnalysis(
        lemma=token.lemma,
        part_of_speech=token.upos,
    )


def dictionary_lemmatizer(word: str) -> WordAnalysis:
    lemma = lemmatize(word, lang='es')

    return WordAnalysis(
        lemma=lemma,
        part_of_speech="Unknown"
    )


def main():
    print(stanza_analyze_word("solo"))

if __name__ == "__main__":
    main()