import stanza

nlp = stanza.Pipeline(
    lang="es",
    processors="tokenize,pos,lemma",
    tokenize_pretokenized=True,
    verbose=False,
)

words = [
    "quito"
]

for word in words:
    doc = nlp([[word]])
    token = doc.sentences[0].words[0]

    print(f"{word:12} -> {token.lemma:12} | {token.upos}")

"""
SUCCESS:
->
hablar       -> hablar       | VERB
hablo        -> hablar       | VERB
hablábamos   -> hablar       | VERB
cantábamos   -> cantar       | VERB
estábamos    -> estar        | AUX
íbamos       -> ir           | VERB
comíamos     -> comer        | VERB
vivíamos     -> vivir        | VERB
niños        -> niño         | NOUN
casas        -> casa         | NOUN
fui          -> ser          | VERB
vino         -> vino         | NOUN
"""