import asyncio
import os
import json
from io import BytesIO
from math import gcd
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv
load_dotenv()
api_key = (os.getenv("GEMINI_API_KEY") or "").strip()


# --- FIXNÝ PROMPT A KONFIGURÁCIA ---
JSON_PATH = "./data/i18n/cards.en.json"
STYLE_PROMPT = "Redraw picture in a clean minimalist semi-cubism with clearly defined, non-overlapping shapes" 
INPUT_DIR = "./static/cards/default"     
OUTPUT_DIR = "./static/cards/modern"

MODEL_ID = "gemini-3.1-flash-image-preview"
SEMAPHORE_LIMIT = 3 # Znížené na 3 pre stabilnejší batching pri väčších rozlíšeniach

client = genai.Client(api_key=api_key)

with open(JSON_PATH, "r", encoding="utf-8") as f:
    json_card_data = json.load(f)

# --- GENERÁTOR PROMPTU PODĽA JSON DÁT ---
def build_prompt_from_json(target_image_path: str, json_data: dict) -> str:
    
    card_data = None
    for card in json_data["cards"]:
        if card["image_path"] == target_image_path:
            card_data = card
            break
    
    """ Vytvorí prísny prompt na základe atribútov z JSONu. """
    card_name = card_data["name"]
    arcana = card_data["arcana"]
    
    # Ak je to Malá arkána ("minor"), vynútime presný počet
    if arcana == "minor":
        number = card_data["number"]
        suit = card_data["suit"] # napr. "wands", "cups"
        
        # Ošetrenie pre dvorné karty (Page, Knight, Queen, King nemajú číselné objekty na spočítanie)
        rank = card_data["rank"]
        if rank in ["page", "knight", "queen", "king"]:
            return f"A tarot card depicting {card_name}. The central figure is the {rank.upper()} of {suit.upper()}, {STYLE_PROMPT}"
        
        # Prísna inštrukcia pre číselné karty (Ace až 10)
        return (
            f"A tarot card depicting the '{card_name}'. It is absolutely critical that the image "
            f"features EXACTLY {number} DISTINCT {suit.upper()} symbols arranged in a structured, clear composition. "
            f"Do not depict any extra, hidden, or partial elements. Every single one of the {number} {suit.upper()} "
            f"must be clearly separated and individually defined as a fragmented geometric form, {STYLE_PROMPT}"
        )
    else:
        # Pre Veľkú arkánu ("major") neposielame žiadne počty, iba názov a štýl
        return f"A tarot card depicting '{card_name}', {STYLE_PROMPT}"

def get_aspect_ratio_string(width: int, height: int) -> str:
    """Vypočíta pomer strán obrázka a vráti ho vo formáte reťazca (napr. '16:9')."""
    divisor = gcd(width, height)
    w_ratio = width // divisor
    h_ratio = height // divisor
    
    # Nano Banana podporuje špecifické štandardné pomery. Ak vyjde neštandardný,
    # zaokrúhlime ho na najbližší podporovaný, aby sme zachovali proporcie čo najbližšie.
    supported_ratios = [(1,1), (3,2), (2,3), (4,3), (3,4), (16,9), (9,16), (4,5), (5,4)]
    current_ratio = w_ratio / h_ratio
    
    best_match = (1, 1)
    min_diff = float('inf')
    
    for w, h in supported_ratios:
        diff = abs(current_ratio - (w / h))
        if diff < min_diff:
            min_diff = diff
            best_match = (w, h)
            
    return f"{best_match[0]}:{best_match[1]}"

async def process_single_image(image_path: str, output_path: str, semaphore: asyncio.Semaphore):
    """Spracuje jeden obrázok s ohľadom na jeho pôvodný pomer strán."""
    # KONTROLA PREDCHÁDZANIA PÁDOM: Ak súbor už existuje, preskočíme ho
    if os.path.exists(output_path):
        print(f"⏭️ Preskakujem (už existuje): {os.path.basename(output_path)}")
        return

    async with semaphore:
        try:
            print(f"🚀 Spúšťam úpravu: {os.path.basename(image_path)}")
            
            with Image.open(image_path) as img:
                if img.mode in ('RGBA', 'LA'):
                    img = img.convert('RGB')
                
                prompt = build_prompt_from_json(os.path.basename(image_path),json_card_data)
                                
                
                # Zistenie rozmerov a výpočet správneho pomeru strán
                width, height = img.size
                detected_ratio = get_aspect_ratio_string(width, height)
                                
                # Volanie API s dynamickým aspect_ratio
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=MODEL_ID,
                    contents=[img, prompt],
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                        image_config=types.ImageConfig(
                            aspect_ratio=detected_ratio
                        )
                    )
                )

            # Uloženie upraveného obrázka
            image_saved = False
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    generated_img = Image.open(BytesIO(part.inline_data.data))
                    generated_img.save(output_path)
                    print(f"✅ Uložené: {os.path.basename(output_path)}")
                    image_saved = True
                    break
            
            if not image_saved:
                print(f"⚠️ API nevrátilo dáta pre {os.path.basename(image_path)} (Možný filter obsahu).")

        except Exception as e:
            print(f"❌ Chyba pri spracovaní {os.path.basename(image_path)}: {e}")

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
    valid_extensions = ('.png', '.jpg', '.jpeg', '.webp')
    
    tasks = []
    for filename in os.listdir(INPUT_DIR):
        if filename.lower().endswith(valid_extensions):
            input_path = os.path.join(INPUT_DIR, filename)
            # Výstupný súbor bude mať rovnaký názov ako pôvodný, ale bude v cieľovom priečinku
            output_path = os.path.join(OUTPUT_DIR, filename)
            
            tasks.append(process_single_image(input_path, output_path, semaphore))
            
    if not tasks:
        print(f"V priečinku '{INPUT_DIR}' sa nenašli žiadne obrázky.")
        return

    print(f"Spúšťam batch spracovanie pre {len(tasks)} obrázkov...")
    await asyncio.gather(*tasks)
    print("🎉 Hotovo! Ak niektoré obrázky chýbajú kvôli chybe, spusti skript znova. Spracuje len tie chýbajúce.")

if __name__ == "__main__":
    asyncio.run(main())