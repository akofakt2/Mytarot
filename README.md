# Tarot Mentor

Webová Flask aplikácia na interaktívny trojkartový rozklad (minulosť / prítomnosť / budúcnosť) s textovým výkladom generovaným cez **Google Gemini** API. Jedna bežiaca inštancia obsluhuje **jeden jazyk** podľa premennej `TAROT_LOCALE`; texty rozhrania, URL segmenty a dáta kariet sú v `data/i18n/`.

## Čo aplikácia robí

- **Domovská stránka** – miešanie balíčka, lízanie troch kariet (náhodná orientácia), zvukové efekty, pole na otázku a vyžiadanie výkladu.
- **API** – `GET …/api/draw` vráti tri náhodné karty (JSON); `POST …/api/reading` pošle otázku a ID kariet do LLM a vráti text výkladu.
- **Katalóg** – zoznam všetkých 78 kariet a detail každej karty (slug z normalizovaného názvu).
- **Informačné stránky** – o aplikácii a o tarote (šablóny v `templates/pages/`).

## Technológie

- Python 3 (odporúčané 3.12+)
- [Flask](https://flask.palletsprojects.com/) 3.x
- [google-genai](https://github.com/googleapis/python-genai) (Gemini)
- [python-dotenv](https://pypi.org/project/python-dotenv/) (voliteľné načítanie `.env`)
- [Gunicorn](https://gunicorn.org/) na produkčné nasadenie

Frontend: vanilla HTML/CSS/JS (`templates/`, `static/`).

## Štruktúra repozitára

| Cesta | Účel |
|--------|------|
| `tarot_app.py` | Factory `create_tarot_app()`, routy, načítanie i18n |
| `domain/cards.py` | Model `Card`, validácia 78 kariet (ID 0–77) |
| `domain/deck.py` | Balíček: miešanie, orientácia, ťahanie |
| `domain/llm.py` | Volanie Gemini (`call_llm`) |
| `data/i18n/routes.json` | URL segmenty podľa locale (napr. `karty` / `cards`) |
| `data/i18n/ui.json` | Texty UI podľa locale |
| `data/i18n/prompts.json` | Šablóna promptu pre výklad (`reading_prompt`) |
| `data/i18n/cards.<locale>.json` | Definície kariet (názvy, významy, obrázky, …) |
| `templates/` | Jinja šablóny |
| `static/` | CSS, JS, zvuky; obrázky kariet pod `static/<TAROT_CARD_IMAGES_BASE_DIR>/…` |

## Inštalácia

```bash
cd /path/to/tarotdeploy
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Konfigurácia (premenné prostredia)

Vytvor súbor `.env` v koreni projektu (nie je v git-e) alebo exportuj premenné v shelli.

| Premenná | Povinná | Predvolená hodnota | Popis |
|----------|---------|-------------------|--------|
| `GEMINI_API_KEY` | áno pre výklady | — | Kľúč pre Google AI / Gemini |
| `GEMINI_MODEL` | nie | `gemini-2.5-flash` | Model pre `generate_content` |
| `TAROT_LOCALE` | nie | `sk` | Jazyk inštancie: musí existovať v `routes.json`, `prompts.json`, `ui.json` a súbore `cards.<locale>.json` |
| `TAROT_CARD_SET` | nie | `default` | Podadresár s obrázkami: `…/<TAROT_CARD_IMAGES_BASE_DIR>/<TAROT_CARD_SET>/` |
| `TAROT_CARD_IMAGES_BASE_DIR` | nie | `cards` | Relatívna cesta pod `static/` k priečinku s balíčkami |
| `TAROT_SCRIPT_PATH` | nie | prázdne | Voliteľný prefix URL (napr. `/tarot`), ak je aplikácia za reverzným proxy pod podscestou |

**Obrázky kariet:** očakáva sa adresár `static/<TAROT_CARD_IMAGES_BASE_DIR>/<TAROT_CARD_SET>/` so súbormi podľa `image_path` v JSON kariet a so súborom **`back.png`** (rub karty). Repozitár obsahuje `static/cards/` ako miesto pre assety; bez obrázkov môže aplikácia pri miešaní/ťahaní zlyhať na chýbajúcom `back.png`.

## Spustenie

**Vývoj (Flask dev server):**

```bash
source venv/bin/activate
flask --app tarot_app:create_tarot_app run
```

**Produkcia (Gunicorn):**

```bash
gunicorn "tarot_app:create_tarot_app()" -b 0.0.0.0:8000
```

Aplikácia sa vytvára cez factory `create_tarot_app()` – pri štarte sa validujú locale súbory a konzistencia dát kariet.

## API (skrátene)

- **`GET /api/draw`** (relatívne k `TAROT_SCRIPT_PATH`) – vráti pole troch objektov: `id`, `name`, `meaning`, `rev`, `image_url`. Bez cache (`no-store`).
- **`POST /api/reading`** – JSON telo: `question`, `past_id`, `present_id`, `future_id`, voliteľne `past_rev`, `present_rev`, `future_rev` (0/1). Úspech: `{ "ok": true, "reading": "…", … }`. Chyba validácie: 400; zlyhanie LLM: 502.

Presné cesty k stránkam závisia od `routes.json` (napr. pre `sk`: `/karty`, `/karta/<slug>`, `/o-aplikacii`, `/o-tarote`).

## Pridanie jazyka alebo úprava rout

1. Pridaj kľúč locale do `data/i18n/routes.json` so všetkými požadovanými kľúčmi: `cards_list`, `card`, `about_app`, `about_tarot`.
2. Doplň rovnaký locale do `prompts.json` (aspoň `reading_prompt` s placeholdermi `{question}`, `{past_block}`, `{present_block}`, `{future_block}`).
3. Pridaj `cards.<locale>.json` (78 kariet, rovnaká štruktúra ako existujúce locale).
4. Doplň `ui.json` pre daný locale.
5. Nastav `TAROT_LOCALE` na nový kód a reštartuj proces.

## Test LLM z CLI

```bash
python domain/llm.py "Krátky test promptu"
```

Načíta `GEMINI_API_KEY` a `GEMINI_MODEL` z prostredia (prípadne z `.env` cez dotenv).

## Licencia

V repozitári nie je uvedená licencia; pred šírením ju doplň podľa potreby.
