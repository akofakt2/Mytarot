import os
from PIL import Image, ImageFilter, ImageDraw, ImageFont

# --- NASTAVENIA ---
INPUT_FOLDER = "static/cards/default"  # Priečinok, kde máte 78 pôvodných kariet
OUTPUT_FOLDER = "tmp"  # Kam sa uložia hotové obrázky
CANVAS_WIDTH = 1200
CANVAS_HEIGHT = 630
CARD_TARGET_HEIGHT = 580  # Výška karty na plátne (necháme 25px okraj hore/dole)
OVERLAY_COLOR = (0, 0, 0, 120)  # Čierna s priehľadnosťou (stmavenie pozadia)

# Vytvorenie priečinka pre výstup, ak neexistuje
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

def spracuj_kartu(filename):
    # 1. Otvorenie karty
    img = Image.open(os.path.join(INPUT_FOLDER, filename)).convert("RGBA")
    
    # 2. Vytvorenie pozadia (rozmazanie)
    # Roztiahneme kartu na celé plátno a rozmažeme
    bg = img.resize((CANVAS_WIDTH, int(CANVAS_WIDTH * (img.height / img.width))), Image.LANCZOS)
    bg = bg.crop((0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)) # Orezať na stred
    bg = bg.filter(ImageFilter.GaussianBlur(radius=15))
    
    # Stmavenie pozadia
    overlay = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), OVERLAY_COLOR)
    bg = Image.alpha_composite(bg, overlay)

    # 3. Príprava hlavnej karty (ostrej)
    aspect_ratio = img.width / img.height
    new_width = int(CARD_TARGET_HEIGHT * aspect_ratio)
    card_front = img.resize((new_width, CARD_TARGET_HEIGHT), Image.LANCZOS)

    # 4. Vloženie karty do stredu pozadia
    offset = ((CANVAS_WIDTH - new_width) // 2, (CANVAS_HEIGHT - CARD_TARGET_HEIGHT) // 2)
    bg.paste(card_front, offset, card_front)

    # 6. Uloženie
    output_filename = f"share_{filename}"
    bg.convert("RGB").save(os.path.join(OUTPUT_FOLDER, output_filename), "JPEG", quality=90)
    print(f"Hotovo: {output_filename}")


# Spustenie pre všetky súbory v priečinku
for file in os.listdir(INPUT_FOLDER):
    if file.endswith((".jpg", ".png", ".jpeg")):
        spracuj_kartu(file)

#spracuj_kartu("1.png")

