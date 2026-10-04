import json
import os
import time
from google import genai

from dotenv import load_dotenv

load_dotenv()
# Načítanie API kľúča z prostredia
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("Chýba GEMINI_API_KEY v premenných prostredia!")

client = genai.Client(api_key=api_key)

# Cesty k súborom
INPUT_FILE = "data/i18n/cards.pl.json"
OUTPUT_FILE = "data/i18n/cards_en.pl.json"
TARGET_LANGUAGE = "poľština"  # Nastavte požadovaný jazyk ("čeština", "slovenčina", "angličtina")

def generate_description(card_data, language):
    """Odošle údaje karty do Gemini a vráti podrobný opis."""
    prompt = f"""
Napiš detailní a poutavý popis pro tarotovou kartu v jazyce: {language}.

Informace o kartě:
- Název: {card_data.get('name')}
- Arkána: {card_data.get('arcana')}
- Suit/Aritmetika: {card_data.get('suit')} ({card_data.get('rank')})
- Klíčová slova: {', '.join(card_data.get('keywords', []))}
- Význam (přípřímost): {card_data.get('meaning_upright')}
- Význam (obráceně): {card_data.get('meaning_reversed')}

Požadavky na popis (description):
1. Délka textu musí být přibližně 100 až 120 slov.
2. Text musí fungovat jako ucelený, plynulý rozbor karty pro návštěvníka tarotového webu.
3. Vysvětli v něm symboliku, energii karty vo vseobecnej rovine.
4. Pouzi jednoduchy jazyk strednej vrstvy, pouzi ustalene frazy, vyhybaj sa cudzim slovam a archaizmom.
5. Nepoužívej nadpisy, seznamy ani odrážky – napiš čistý text v 1 až 2 odstavcích.
6. Vrať POUZE samotný text popisu bez jakéhokoliv dalšího úvodu nebo komentáře.
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
    )
    return response.text.strip()

def process_cards():
    # Načítanie vstupného JSONu
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    cards = data['cards']
    
    print(f"Načítaných {len(cards)} kariet. Začínam generovanie pre jazyk: {TARGET_LANGUAGE}...")

    for index, card in enumerate(cards):
        # Ak karta už opis má, preskočíme ju (vhodné pri prerušení a opätovnom spustení)

        print(f"[{index+1}/{len(cards)}] Generujem popis pre: {card['name']}...")
        try:
            
            desc = generate_description(card, TARGET_LANGUAGE)
            card["description"] = desc
                        
            # Priebežné uloženie do výsledného súboru
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(cards, f, ensure_ascii=False, indent=2)
                
            # Krátka pauza kvôli šetreniu API limitov
            
            time.sleep(1)
        except Exception as e:
            print(f"Chyba pri karte {card['name']}: {e}")

    print(f"\nHotovo! Výsledný JSON bol uložený do '{OUTPUT_FILE}'.")

if __name__ == "__main__":
    process_cards()