import json
import os, time

# --- KONFIGURÁCIA ---
SOURCE_FILE = 'data/i18n/cards.en.json'
TARGET_FILE = 'cards_prelozene.json'
from google import genai  # type: ignore[import-not-found]
client = genai.Client(api_key="AIzaSyDdLAERsacTOKwNauypNCtkzYcl4H9gM5Y")

def dummy_api_call(card_json):
    """
    Simulácia volania API. Tu je vložený tvoj špeciálny prompt.
    """
    
    from google import genai  # type: ignore[import-not-found]
    
    
    # Tento prompt sa posiela ako inštrukcia k správe (role: user alebo system)
    prompt = f"""
 Review and refine this Tarot card JSON for a global audience. 
    Target Audience: International users (ESL friendly - English as a Second Language).

    Rules for Refinement:
    1. Language Style: Use "Plain English". Keep sentences short and direct. 
    2. No Idioms: Avoid complex metaphors or culturally specific phrases (e.g., no "beat around the bush").
    3. Clarity over Flair: Use common, high-frequency words. Ensure the meaning is accessible to non-native speakers.
    4. Consistency: 
       - Keep Suit names as: Wands, Cups, Swords, Pentacles.
       - Keep Ranks as: Ace, Page, Knight, Queen, King.
    5. Tone: Helpful, grounded, and neutral. Avoid overly mystical or "dark" language.
    6. Output: Return ONLY the raw JSON. Do not change the JSON structure or keys.

    JSON TO REFINE:
    {json.dumps(card_json, indent=2, ensure_ascii=False)}
    """
    
    # Simulácia úspešného prekladu (v realite tu bude return response.json())
    # Pre demo účely len vrátime pôvodné dáta (v tvojom skripte to nahradíš volaním modelu)
    
    try:
        response = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt) 
        raw_text = response.text
        clean_json_text = raw_text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json_text)
                
    except Exception as e:
        print(f"Naskytla sa chyba pri volaní API: {e}")
        return card_json
    

def save_progress(translated_cards):
    """Priebežne ukladá zoznam preložených kariet do súboru."""
    output_data = {
        "version": 2,
        "locale": "pl",
        "cards": translated_cards
    }
    with open(TARGET_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

def main():
    # 1. Načítanie pôvodných dát
    if not os.path.exists(SOURCE_FILE):
        print(f"Zdrojový súbor {SOURCE_FILE} neexistuje.")
        return

    with open(SOURCE_FILE, 'r', encoding='utf-8') as f:
        source_data = json.load(f)
    
    all_cards = source_data.get('cards', [])
    
    # 2. Kontrola, či už niečo máme preložené (aby sme nezačínali od nuly)
    translated_cards = []
    if os.path.exists(TARGET_FILE):
        with open(TARGET_FILE, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
            translated_cards = existing_data.get('cards', [])
    
    # OPRAVA: Množina IDčiek (čísel), nie celých objektov
    translated_ids = {c.get('id') for c in translated_cards if c.get('id') is not None}

    print(f"Začínam preklad. Celkovo: {len(all_cards)}. Už hotovo: {len(translated_ids)}.")

    print(f"Začínam preklad. Celkovo kariet: {len(all_cards)}. Už preložených: {len(translated_ids)}.")

    # 3. Iterácia a preklad
    try:
        for card in all_cards:
            c_id = card.get('id')
            
            if c_id is None:
                print("Varovanie: Našiel som kartu bez ID, preskakujem.")
                continue
            
            if c_id in translated_ids:
                continue  # Preskoč, ak už kartu máme
            
            print(f"Prekladám kartu ID: {card['id']} ({card.get('name')})...")
            
            #print(card)
            
            # VOLANIE API (v tvojom prípade dummy s promptom)
            translated_card = dummy_api_call(card)
                                    
            translated_cards.append(translated_card)
            
            # PRIEBEŽNÉ UKLADANIE
            save_progress(translated_cards)
            time.sleep(2)
            
        print(f"Hotovo! Preklady sú v súbore: {TARGET_FILE}")

    except KeyboardInterrupt:
        print("\nPreklad prerušený užívateľom. Progres bol uložený.")

if __name__ == "__main__":
    main()