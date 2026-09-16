import unicodedata

word1 = "éuskara"  # Copy this directly from your crash log
word2 = "éuskara"  # Copy this out of your database viewer/table

print(f"Word 1 length: {len(word1)} | Bytes: {word1.encode('utf-8')}")
print(f"Word 2 length: {len(word2)} | Bytes: {word2.encode('utf-8')}")

# Clean them using Normalization Form C (NFC)
clean_word1 = unicodedata.normalize('NFC', word1).strip()
clean_word2 = unicodedata.normalize('NFC', word2).strip()

print(f"Do they match now? {clean_word1 == clean_word2}")
