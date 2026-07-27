import stanza

nlp = stanza.Pipeline(
    lang="es",
    processors="tokenize,pos,lemma",
    tokenize_pretokenized=True,
    verbose=False,
)

words = [
    "hablar",
    "hablo",
    "hablábamos",
    "cantábamos",
    "estábamos",
    "íbamos",
    "comíamos",
    "vivíamos",
    "niños",
    "casas",
    "fui",
    "vino",
]

for word in words:
    doc = nlp([[word]])
    token = doc.sentences[0].words[0]

    print(f"{word:12} -> {token.lemma:12} | {token.upos}")