from google import genai  # type: ignore[import-not-found]
client = genai.Client(api_key="AIzaSyDrjBOK3WhQVVyWRUTjJW2AzEu6Zf8lUFI")


# 3. Načítaj pôvodný JSON súbor
input_filename = 'data/i18n/cards.en.json'
output_filename = 'data/i18n/cards.pl.json'

try:
    with open(input_filename, 'r', encoding='utf-8') as f:
        json_content = f.read()
except FileNotFoundError:
    print(f"Chyba: Súbor {input_filename} sa nenašiel.")
    exit()

# 4. Priprav prompt s inštrukciami pre Gemini
prompt = f"""
Prelož nasledujúci JSON súbor do poľštiny.
Dodržuj tieto prísne pravidlá:
1. Ponechaj celú štruktúru JSON a technické kľúče (ako "id", "arcana", "suit", "rank", "image_path" atď.) úplne bez zmeny.
2. Prelož IBA hodnoty určené na čítanie, teda hodnoty pre kľúče: "name", "keywords", "meaning_upright", "meaning_reversed", "archetype" a "description".
3. Zmeň hodnotu "locale" z "en" na "pl".
4. Vráť mi iba čistý JSON kód, bez akéhokoľvek ďalšieho textu (nepridávaj markdown formátovanie ako ```json na začiatok a koniec, chcem len čisté dáta).

Tu je JSON na preklad:
{json_content}
"""


print("Odosielam dáta na Gemini API. Prosím, čakaj...")

# 5. Zavolaj API
try:
    response = client.models.generate_content(model="gemini-2.5-flash-lite", contents=prompt)
    
    # 6. Ulož výsledok do nového súboru
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(response.text)
        
    print(f"Úspech! Preložený súbor bol uložený ako: {output_filename}")
    
except Exception as e:
    print(f"Naskytla sa chyba pri volaní API: {e}")


try:
    with open(input_filename, 'r', encoding='utf-8') as f:
        json_content = f.read()
except FileNotFoundError:
    print(f"Chyba: Súbor {input_filename} sa nenašiel.")
    exit()


print("Odosielam dáta na Gemini API. Prosím, čakaj...")

