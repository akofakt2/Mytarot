"""
Samostatná inštancia: jeden jazyk z .env (`TAROT_LOCALE`), slugy z `name` v `cards.<locale>.json`.

Všetky URL segmenty podľa mutácie sú v `LOCALE_ROUTES` (karty + informačné stránky).
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, render_template, request, url_for

from domain.cards import Card, validate_cards
from domain.deck import Deck
from domain.llm import call_llm

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data" / "i18n"

def _load_locale_routes() -> dict[str, dict[str, str]]:
    """
    Načíta route segmenty z `app/data/i18n/routes.json`, aby pridanie jazyka nevyžadovalo zmenu kódu.
    """
    path = DATA_DIR / "routes.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"Chýba {path}. Pridaj routes.json (napr. sk/en) alebo oprav cestu DATA_DIR."
        )

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("routes.json must be an object {locale: {route_key: segment}}")

    out: dict[str, dict[str, str]] = {}
    for loc, mapping in raw.items():
        if not isinstance(loc, str) or not loc:
            raise ValueError("routes.json: locale keys must be non-empty strings")
        if not isinstance(mapping, dict):
            raise ValueError(f"routes.json: locale {loc!r} must map to an object")

        m2: dict[str, str] = {}
        for k, v in mapping.items():
            if not isinstance(k, str) or not k:
                raise ValueError(f"routes.json: invalid route key for locale {loc!r}")
            if not isinstance(v, str) or not v:
                raise ValueError(f"routes.json: invalid segment for {loc!r}.{k!r}")
            m2[k] = v.strip().strip("/")

        # Minimálne kľúče, ktoré appka používa.
        required = ("cards_list", "card", "about_app", "about_tarot")
        missing = [k for k in required if k not in m2]
        if missing:
            raise ValueError(f"routes.json: locale {loc!r} missing keys: {missing}")

        out[loc.strip().lower()] = m2

    return out


def _load_locale_prompts() -> dict[str, dict[str, str]]:
    """
    Načíta prompt šablóny z `app/data/i18n/prompts.json` podľa locale.

    Očakáva JSON tvar:
      { "<locale>": { "reading_prompt": "<template with {question}/{past_block}...>" }, ... }
    """
    path = DATA_DIR / "prompts.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"Chýba {path}. Pridaj prompts.json (napr. sk/en) alebo oprav cestu DATA_DIR."
        )

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("prompts.json must be an object {locale: {prompt_key: template}}")

    out: dict[str, dict[str, str]] = {}
    for loc, mapping in raw.items():
        if not isinstance(loc, str) or not loc:
            raise ValueError("prompts.json: locale keys must be non-empty strings")
        if not isinstance(mapping, dict):
            raise ValueError(f"prompts.json: locale {loc!r} must map to an object")

        m2: dict[str, str] = {}
        for k, v in mapping.items():
            if not isinstance(k, str) or not k:
                raise ValueError(f"prompts.json: invalid prompt key for locale {loc!r}")
            if not isinstance(v, str) or not v.strip():
                raise ValueError(f"prompts.json: invalid template for {loc!r}.{k!r}")
            m2[k] = v

        if "reading_prompt" not in m2:
            raise ValueError(f"prompts.json: locale {loc!r} missing key 'reading_prompt'")

        out[loc.strip().lower()] = m2

    return out


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _card_index_rows(cards: tuple[Card, ...]) -> list[dict[str, Any]]:
    """Zoznam pre /cards: po každej karte, kde nasledujúca mení arkánu alebo sút, sep_after."""
    rows: list[dict[str, Any]] = []
    n = len(cards)
    for i, c in enumerate(cards):
        nxt = cards[i + 1] if i + 1 < n else None
        sep_after = bool(
            nxt is not None and (c.arcana != nxt.arcana or c.suit != nxt.suit)
        )
        rows.append(
            {
                "slug": slugify(c.name),
                "name": c.name,
                "id": c.id,
                "sep_after": sep_after,
            }
        )
    return rows


def _card_nav_rows(cards: tuple[Card, ...], current_slug: str) -> list[dict[str, Any]]:
    """Zoznam pre detail karty: ako index, plus is_current pre zvýraznenie aktuálnej karty."""
    rows = _card_index_rows(cards)
    for r in rows:
        r["is_current"] = r["slug"] == current_slug
    return rows


def _load_cards(locale: str) -> list[Card]:
    path = DATA_DIR / f"cards.{locale}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Chýba {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("cards")
    if not isinstance(raw, list):
        raise ValueError("cards: očakávam pole 'cards'")
    cards = [Card.from_dict(c) for c in raw]
    validate_cards(cards)
    return cards


def _load_ui_strings() -> dict[str, dict[str, str]]:
    """
    Načíta UI stringy z `app/data/i18n/ui.json` podľa locale.

    Formát:
      { "<locale>": { "<key>": "<string>", ... }, ... }
    """
    path = DATA_DIR / "ui.json"
    if not path.is_file():
        raise FileNotFoundError(f"Chýba {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("ui.json must be an object {locale: {key: string}}")
    out: dict[str, dict[str, str]] = {}
    for loc, mapping in raw.items():
        if not isinstance(loc, str) or not loc.strip():
            raise ValueError("ui.json: locale keys must be non-empty strings")
        if not isinstance(mapping, dict):
            raise ValueError(f"ui.json: locale {loc!r} must map to an object")
        filtered: dict[str, str] = {}
        for k, v in mapping.items():
            if isinstance(k, str) and k.strip() and isinstance(v, str):
                filtered[k] = v
        out[loc] = filtered
    return out


def _build_slug_index(cards: list[Card]) -> dict[str, Card]:
    out: dict[str, Card] = {}
    for c in cards:
        s = slugify(c.name)
        if s in out:
            raise ValueError(f"Duplicitný slug '{s}': {c.name!r} vs {out[s].name!r}")
        out[s] = c
    return out


def create_tarot_app() -> Flask:
    if load_dotenv is not None:
        load_dotenv()

    locale_routes = _load_locale_routes()
    locale_prompts = _load_locale_prompts()
    ui_strings = _load_ui_strings()
    supported_locales = frozenset(locale_routes.keys())
    supported_prompt_locales = frozenset(locale_prompts.keys())
    supported_ui_locales = frozenset(ui_strings.keys())

    locale = (os.getenv("TAROT_LOCALE") or "sk").strip().lower()
    if locale not in supported_locales:
        raise ValueError(
            f"TAROT_LOCALE musí byť jeden z {sorted(supported_locales)} "
            f"(doplň app/data/i18n/routes.json + cards.<locale>.json)"
        )
    if locale not in supported_prompt_locales:
        raise ValueError(
            f"TAROT_LOCALE={locale!r} nemá prompt v app/data/i18n/prompts.json. "
            f"Dostupné: {sorted(supported_prompt_locales)}"
        )
    if locale not in supported_ui_locales:
        raise ValueError(
            f"TAROT_LOCALE={locale!r} nemá UI stringy v app/data/i18n/ui.json. "
            f"Dostupné: {sorted(supported_ui_locales)}"
        )

    try:
        cards_list = sorted(_load_cards(locale), key=lambda c: c.id)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Vestenie: pre TAROT_LOCALE={locale!r} chýba súbor cards.{locale}.json. {e}"
        ) from e

    slug_to_card = _build_slug_index(cards_list)
    cards = tuple(cards_list)

    card_set = (os.getenv("TAROT_CARD_SET") or "default").strip()
    img_base = (os.getenv("TAROT_CARD_IMAGES_BASE_DIR") or "cards").strip().strip("/")
    card_images_dir = f"{img_base}/{card_set}"

    # Prefix pre všetky cesty (napr. ak je appka nasadená pod /tarot).
    # Odvodené z "script path" (env), bez trailing slash.
    script_path = (os.getenv("TAROT_SCRIPT_PATH") or "").strip()
    if script_path and not script_path.startswith("/"):
        script_path = f"/{script_path}"
    script_path = script_path.rstrip("/")

    def _p(suffix: str) -> str:
        """Zloží cestu: <script_path> + /<suffix> (bez dvojitých lomiek)."""
        if not suffix:
            suffix = "/"
        if not suffix.startswith("/"):
            suffix = f"/{suffix}"
        if suffix == "/":
            return f"{script_path}/" if script_path else "/"
        return f"{script_path}{suffix}" if script_path else suffix

    routes = locale_routes[locale]
    ui = ui_strings[locale]
    ctx: dict[str, Any] = {
        "locale": locale,
        "routes": routes,
        "ui": ui,
        "ui_i18n_json": json.dumps(ui, ensure_ascii=False),
    }
    reading_prompt_template = locale_prompts[locale]["reading_prompt"]
    # Jednotné definície ciest (vždy cez script_path prefix).
    index_path = _p("/")  # home page
    api_draw_path = _p("api/draw")  # JSON: 3 náhodné karty pre úvodnú stránku
    api_reading_path = _p("api/reading")  # JSON: question + 3 cards (past/present/future)
    cards_list_path = _p(routes["cards_list"])  # zoznam všetkých kariet
    card_detail_rule = _p(f"{routes['card']}/<slug>")  # detail jednej karty
    about_app_path = _p(routes["about_app"])  # info: aplikácia
    about_tarot_path = _p(routes["about_tarot"])  # info: tarot

    app = Flask(
        __name__,
        template_folder=str(APP_DIR / "templates"),
        static_folder=str(APP_DIR / "static"),
    )
    app.config["TAROT_LOCALE"] = locale
    app.config["CARD_IMAGES_DIR"] = card_images_dir

    @app.get(index_path)
    def index() -> str:
        return render_template(
            "index.html",
            back_image_url=url_for("static", filename=f"{card_images_dir}/back.png"),
            **ctx,
        )

    @app.get(api_draw_path)
    def api_draw() -> Response:
        """
        Vráti 3 náhodné karty pre úvodnú stránku.

        Dôležité: používa aktuálny balík (`card_images_dir`) a rovnaké modely `Card` + `Deck`.
        """
        images_dir = Path(app.static_folder) / card_images_dir
        deck = Deck(back="back.png", images_dir=images_dir)
        deck.init([c.id for c in cards])
        deck.shuffle()

        drawn = deck.draw(3)
        by_id = {c.id: c for c in cards}
        payload = []
        for card_id, orientation in drawn:
            c = by_id.get(card_id)
            if c is None:
                continue
            meaning = c.meaning_reversed if orientation == "reversed" else c.meaning_upright
            payload.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "meaning": meaning,
                    "rev": 1 if orientation == "reversed" else 0,
                    "image_url": url_for("static", filename=f"{card_images_dir}/{c.image_path}"),
                }
            )

        return app.response_class(
            response=json.dumps(payload, ensure_ascii=False),
            status=200,
            mimetype="application/json",
            headers={
                "Cache-Control": "no-store",
            },
        )

    @app.post(api_reading_path)
    def api_reading() -> Response:
        """
        Endpoint pre tarot reading (aktuálne: pripraví prompt).

        Poznámka: základné UX validácie (napr. prázdna otázka) robíme v prehliadači.
        Na serveri nechávame len minimálne parsovanie vstupu a error handling pre prípad LLM zlyhania.
        """
        raw = request.get_json(silent=True) or {}
        if not isinstance(raw, dict):
            return app.response_class(
                response=json.dumps({"ok": False, "error": "Bad request"}, ensure_ascii=False),
                status=400,
                mimetype="application/json",
            )

        try:
            question = str(raw.get("question") or "").strip()
            past_id = int(raw["past_id"])
            present_id = int(raw["present_id"])
            future_id = int(raw["future_id"])
            past_rev = int(raw.get("past_rev", 0))
            present_rev = int(raw.get("present_rev", 0))
            future_rev = int(raw.get("future_rev", 0))
        except Exception:
            return app.response_class(
                response=json.dumps({"ok": False, "error": "Bad request"}, ensure_ascii=False),
                status=400,
                mimetype="application/json",
            )

        by_id = {c.id: c for c in cards}

        def _card_block(label: str, card_id: int, rev: int) -> str:
            c = by_id.get(card_id)
            if c is None:
                return f"{label}: [unknown card id {card_id}]"
            orientation = "reversed" if rev == 1 else "upright"
            meaning = c.meaning_reversed if rev == 1 else c.meaning_upright
            keywords = ", ".join(c.keywords) if c.keywords else "—"
            archetype = c.archetype or "—"
            desc = c.description or "—"
            return (
                f"{label}:\n"
                f"- id: {c.id}\n"
                f"- name: {c.name}\n"
                f"- orientation: {orientation}\n"
                f"- keywords: {keywords}\n"
                f"- archetype: {archetype}\n"
                f"- description: {desc}\n"
                f"- meaning: {meaning}\n"
            )

        prompt = reading_prompt_template.format(
            question=question.strip(),
            past_block=_card_block("Minulosť", past_id, past_rev),
            present_block=_card_block("Prítomnosť", present_id, present_rev),
            future_block=_card_block("Budúcnosť", future_id, future_rev),
        )

        try:
            api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
            model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
            reading_text = call_llm(prompt, api_key=api_key, model=model)
        except Exception as e:
            return app.response_class(
                response=json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
                status=502,
                mimetype="application/json",
                headers={"Cache-Control": "no-store"},
            )

        return app.response_class(
            response=json.dumps(
                {
                    "ok": True,
                    "question": question.strip(),
                    "past_id": past_id,
                    "present_id": present_id,
                    "future_id": future_id,
                    "past_rev": past_rev,
                    "present_rev": present_rev,
                    "future_rev": future_rev,
                    "reading": reading_text,
                    "llm_response": reading_text,
                },
                ensure_ascii=False,
            ),
            status=200,
            mimetype="application/json",
            headers={"Cache-Control": "no-store"},
        )

    @app.get(about_app_path)
    def about_app() -> str:
        return render_template("pages/about_app.html", **ctx)

    @app.get(about_tarot_path)
    def about_tarot() -> str:
        return render_template("pages/about_tarot.html", **ctx)

    @app.get(cards_list_path)
    def cards_index() -> str:
        return render_template(
            "cards_index.html",
            card_index_rows=_card_index_rows(cards),
            **ctx,
        )

    @app.get(card_detail_rule)
    def card_page(slug: str) -> str:
        card = slug_to_card.get(slug)
        if card is None:
            abort(404)

        prev_c = cards[card.id - 1] if card.id > 0 else None
        next_c = cards[card.id + 1] if card.id < 77 else None
        nav_rows = _card_nav_rows(cards, slug)

        prev_slug = slugify(prev_c.name) if prev_c else None
        next_slug = slugify(next_c.name) if next_c else None

        return render_template(
            "template.html",
            card=card,
            slug=slug,
            prev_card=prev_c,
            next_card=next_c,
            prev_slug=prev_slug,
            next_slug=next_slug,
            nav_rows=nav_rows,
            card_images_dir=card_images_dir,
            **ctx,
        )

    return app
