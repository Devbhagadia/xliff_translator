from googletrans import LANGUAGES

# Print all supported languages
for code, name in LANGUAGES.items():
    print(f"{code}: {name}")