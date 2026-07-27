from dataclasses import dataclass


@dataclass
class WordAnalysis:
    lemma: str
    part_of_speech: str