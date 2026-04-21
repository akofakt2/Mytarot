"""
Samostatná inštancia: jeden jazyk z .env (`TAROT_LOCALE`), slugy z `name` v `cards.<locale>.json`.

Všetky URL segmenty podľa mutácie sú v `LOCALE_ROUTES` (karty + informačné stránky).

`<title>` a SEO meta tagy sú v šablónach `templates/meta/<locale>/*.html` (pozri `META_PAGE_IDS`),
nie v `ui.json`.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import time
import unicodedata
from collections import defaultdict, deque
from datetime import date
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
TEMPLATES_DIR = APP_DIR / "templates"

# HTML partials for <title> and meta tags: templates/meta/<locale>/<page_id>.html
# — index.html → home; cards_index → cards_index; about_* → about_app / about_tarot;
#   template.html (card + card-of-day) → card_detail.
META_PAGE_IDS: tuple[str, ...] = (
    "home",
    "cards_index",
    "about_app",
    "about_tarot",
    "card_detail",
)


def _validate_meta_templates(templates_dir: Path, locales: frozenset[str]) -> None:
    """Every locale in routes.json must ship a matching meta partial for each page id."""
    root = templates_dir / "meta"
    missing: list[str] = []
    for loc in sorted(locales):
        for page_id in META_PAGE_IDS:
            p = root / loc / f"{page_id}.html"
            if not p.is_file():
                try:
                    missing.append(str(p.relative_to(APP_DIR)))
                except ValueError:
                    missing.append(str(p))
    if missing:
        raise FileNotFoundError(
            "Chýbajú jazykové meta šablóny (templates/meta/<locale>/<page_id>.html):\n"
            + "\n".join(missing)
        )


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
        required = ("cards_list", "card", "card_of_day", "about_app", "about_tarot")
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
        out[loc.strip().lower()] = filtered
    return out


def _load_card_of_day_explanations(locale: str) -> dict[str, Any]:
    """
    Loads card-of-day explanations from `data/i18n/card_of_day.<locale>.json`.

    Expected shape:
      {
        "topics": ["general", "money", "relationships", "plans"],
        "cards": {
          "0": { "general": ["..."], "money": ["..."], ... },
          ...
          "77": { ... }
        }
      }
    """
    path = DATA_DIR / f"card_of_day.{locale}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Chýba {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("card_of_day.<locale>.json must be an object")

    topics = raw.get("topics")
    if not isinstance(topics, list) or not topics or not all(isinstance(t, str) and t.strip() for t in topics):
        raise ValueError("card_of_day.<locale>.json: 'topics' must be a non-empty list[str]")
    topics = [t.strip() for t in topics]

    cards = raw.get("cards")
    if not isinstance(cards, dict):
        raise ValueError("card_of_day.<locale>.json: 'cards' must be an object {id: {topic: [texts...]}}")

    # Validate 0..77 and topic presence.
    for i in range(78):
        k = str(i)
        if k not in cards:
            raise ValueError(f"card_of_day.<locale>.json: missing card id {k}")
        entry = cards[k]
        if not isinstance(entry, dict):
            raise ValueError(f"card_of_day.<locale>.json: card {k} must be an object")
        for topic in topics:
            arr = entry.get(topic)
            if not isinstance(arr, list) or not arr or not all(isinstance(s, str) and s.strip() for s in arr):
                raise ValueError(f"card_of_day.<locale>.json: card {k} topic {topic!r} must be a non-empty list[str]")

    return {"topics": topics, "cards": cards}


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
        # Note: dotenv does NOT override already-exported env vars by default.
        # This is intentional: production environments (systemd/docker) can set TAROT_LOCALE etc.
        load_dotenv()

    locale_routes = _load_locale_routes()
    locale_prompts = _load_locale_prompts()
    ui_strings = _load_ui_strings()
    supported_locales = frozenset(locale_routes.keys())
    supported_prompt_locales = frozenset(locale_prompts.keys())
    supported_ui_locales = frozenset(ui_strings.keys())

    _validate_meta_templates(TEMPLATES_DIR, supported_locales)

    # Single-locale instance:
    # - we select ONE locale at startup (TAROT_LOCALE)
    # - all human-facing URL segments come from data/i18n/routes.json for that locale
    #   e.g. locale=en -> "/cards", locale=sk -> "/karty"
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

    # "Card of the day" explanations are treated as required content: we fail fast on startup
    # if any card/topic is missing so incomplete translations can't accidentally deploy.
    card_of_day_expl = _load_card_of_day_explanations(locale)

    try:
        cards_list = sorted(_load_cards(locale), key=lambda c: c.id)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Vestenie: pre TAROT_LOCALE={locale!r} chýba súbor cards.{locale}.json. {e}"
        ) from e

    slug_to_card = _build_slug_index(cards_list)
    cards = tuple(cards_list)
    cards_by_id = {c.id: c for c in cards}

    card_set = (os.getenv("TAROT_CARD_SET") or "default").strip()
    img_base = (os.getenv("TAROT_CARD_IMAGES_BASE_DIR") or "cards").strip().strip("/")
    card_images_dir = f"{img_base}/{card_set}"

    # Prefix pre všetky cesty (napr. ak je appka nasadená pod /tarot).
    # Keep it normalized to avoid double slashes and to make url rules deterministic.
    script_path = (os.getenv("TAROT_SCRIPT_PATH") or "").strip()
    if script_path and not script_path.startswith("/"):
        script_path = f"/{script_path}"
    script_path = script_path.rstrip("/")

    def _p(suffix: str) -> str:
        """
        Build a URL path with an optional deployment prefix.

        `TAROT_SCRIPT_PATH` lets you mount the whole app under a subpath behind a reverse proxy
        (e.g. https://example.com/tarot/). All rules are registered with this prefix so both
        URL generation (url_for) and request matching stay consistent.
        """
        if not suffix:
            suffix = "/"
        if not suffix.startswith("/"):
            suffix = f"/{suffix}"
        if suffix == "/":
            return f"{script_path}/" if script_path else "/"
        return f"{script_path}{suffix}" if script_path else suffix

    # Localized route segments for this locale.
    # Example:
    #   routes["cards_list"] == "cards" (en) or "karty" (sk)
    # These are segments (no leading/trailing slash) and are later combined with script_path via _p().
    routes = locale_routes[locale]
    ui = ui_strings[locale]
    required_ui_keys = (
        "cards_index_heading",
        "card_section_keywords",
        "card_section_upright",
        "card_section_reversed",
        "card_section_description",
        "card_pager_aria",
        "all_cards_aria",
        "all_cards_heading",
        "card_of_day_explanation_title",
        "card_of_day_reveal_label",
        "card_of_day_today_label",
        "reading_label_past",
        "reading_label_present",
        "reading_label_future",
        "nav_brand",
        "nav_aria_main",
        "nav_aria_menu",
        "nav_cards",
        "nav_reading",
        "nav_about_app",
        "nav_about_tarot",
        "nav_card_of_day",
    )
    missing_ui = [k for k in required_ui_keys if not isinstance(ui.get(k), str) or not ui.get(k, "").strip()]
    if missing_ui:
        raise ValueError(
            f"ui.json for locale {locale!r} is missing required keys: {missing_ui}. "
            "Add them to data/i18n/ui.json."
        )

    # Optional API protection for the LLM endpoint.
    # This is a "soft gate": the token is visible to the browser client (it is injected into HTML),
    # so it is NOT a secret and does not stop a determined attacker. It mainly blocks opportunistic scans.
    api_token = (os.getenv("TAROT_API_TOKEN") or "").strip()
    ctx: dict[str, Any] = {
        "locale": locale,
        "routes": routes,
        "ui": ui,
        "ui_i18n_json": json.dumps(ui, ensure_ascii=False),
        # Exposed to the frontend intentionally (soft-gate; not a secret).
        "tarot_api_token": api_token,
    }
    reading_prompt_template = locale_prompts[locale]["reading_prompt"]
    # Register paths once (always through _p() so script_path is applied everywhere).
    # Note: because this app is single-locale, these paths are locale-specific too.
    index_path = _p("/")  # home page
    api_draw_path = _p("api/draw")  # JSON: 3 náhodné karty pre úvodnú stránku
    api_reading_path = _p("api/reading")  # JSON: question + 3 cards (past/present/future)
    cards_list_path = _p(routes["cards_list"])  # zoznam všetkých kariet
    card_detail_rule = _p(f"{routes['card']}/<slug>")  # detail jednej karty
    card_of_day_path = _p(routes["card_of_day"])  # karta dňa
    about_app_path = _p(routes["about_app"])  # info: aplikácia
    about_tarot_path = _p(routes["about_tarot"])  # info: tarot

    app = Flask(
        __name__,
        template_folder=str(APP_DIR / "templates"),
        static_folder=str(APP_DIR / "static"),
    )
    app.config["TAROT_LOCALE"] = locale
    app.config["CARD_IMAGES_DIR"] = card_images_dir

    
    rate_limit_per_minute_raw = (os.getenv("TAROT_RATE_LIMIT_PER_MINUTE") or "").strip()
    try:
        rate_limit_per_minute = int(rate_limit_per_minute_raw) if rate_limit_per_minute_raw else 0
    except ValueError:
        raise ValueError("TAROT_RATE_LIMIT_PER_MINUTE must be an integer") from None
    if rate_limit_per_minute < 0:
        raise ValueError("TAROT_RATE_LIMIT_PER_MINUTE must be >= 0")

    # In-memory per-IP rate limit.
    # Trade-off: simple and dependency-free, but in multi-process setups (gunicorn workers)
    # each worker keeps its own counters, effectively multiplying the limit.
    _ip_calls: dict[str, deque[float]] = defaultdict(deque)

    def _client_ip() -> str:
        # Prefer reverse-proxy header if present; fall back to remote_addr.
        # Security note: only trust X-Forwarded-For if you control the proxy in front of the app.
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
        return (request.remote_addr or "unknown").strip()

    def _check_rate_limit() -> Response | None:
        if rate_limit_per_minute <= 0:
            return None
        now = time.monotonic()
        window = 60.0
        dq = _ip_calls[_client_ip()]
        while dq and (now - dq[0]) > window:
            dq.popleft()
        if len(dq) >= rate_limit_per_minute:
            return app.response_class(
                response=json.dumps({"ok": False, "error": "Rate limit exceeded"}, ensure_ascii=False),
                status=429,
                mimetype="application/json",
                headers={"Cache-Control": "no-store"},
            )
        dq.append(now)
        return None

    def _check_api_token() -> Response | None:
        if not api_token:
            return None
        hdr = (request.headers.get("X-API-Token") or "").strip()
        auth = (request.headers.get("Authorization") or "").strip()
        bearer = ""
        if auth.lower().startswith("bearer "):
            bearer = auth[7:].strip()
        if hdr != api_token and bearer != api_token:
            return app.response_class(
                response=json.dumps({"ok": False, "error": "Unauthorized"}, ensure_ascii=False),
                status=401,
                mimetype="application/json",
                headers={"Cache-Control": "no-store"},
            )
        return None

    @app.get(index_path)
    def index() -> str:
        """Home page (HTML). Card draw + reading happen via JS calling /api/*."""
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
        payload = []
        for card_id, orientation in drawn:
            c = cards_by_id.get(card_id)
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
        limited = _check_rate_limit()
        if limited is not None:
            return limited
        unauthorized = _check_api_token()
        if unauthorized is not None:
            return unauthorized

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

        if not question:
            return app.response_class(
                response=json.dumps({"ok": False, "error": "Question is required"}, ensure_ascii=False),
                status=400,
                mimetype="application/json",
            )
        if past_rev not in (0, 1) or present_rev not in (0, 1) or future_rev not in (0, 1):
            return app.response_class(
                response=json.dumps({"ok": False, "error": "Bad request"}, ensure_ascii=False),
                status=400,
                mimetype="application/json",
            )
        if past_id not in cards_by_id or present_id not in cards_by_id or future_id not in cards_by_id:
            return app.response_class(
                response=json.dumps({"ok": False, "error": "Bad request"}, ensure_ascii=False),
                status=400,
                mimetype="application/json",
            )

        label_past = ui["reading_label_past"]
        label_present = ui["reading_label_present"]
        label_future = ui["reading_label_future"]

        def _card_block(label: str, card_id: int, rev: int) -> str:
            c = cards_by_id.get(card_id)
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
            past_block=_card_block(label_past, past_id, past_rev),
            present_block=_card_block(label_present, present_id, present_rev),
            future_block=_card_block(label_future, future_id, future_rev),
        )

        try:
            api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
            model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
            reading_text = call_llm(prompt, api_key=api_key, model=model)
        except Exception as e:
            return app.response_class(
                response=json.dumps({"ok": False, "error": "LLM error"}, ensure_ascii=False),
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
                },
                ensure_ascii=False,
            ),
            status=200,
            mimetype="application/json",
            headers={"Cache-Control": "no-store"},
        )

    @app.get(about_app_path)
    def about_app() -> str:
        """Static info page (HTML)."""
        return render_template("pages/about_app.html", **ctx)

    @app.get(about_tarot_path)
    def about_tarot() -> str:
        """Static info page (HTML)."""
        return render_template("pages/about_tarot.html", **ctx)

    @app.get(cards_list_path)
    def cards_index() -> str:
        """Catalog page listing all 78 cards (HTML)."""
        return render_template(
            "cards_index.html",
            card_index_rows=_card_index_rows(cards),
            **ctx,
        )

    @app.get(card_of_day_path)
    def card_of_day() -> str:
        """
        Card of the day (HTML).

        The selected card is deterministic for a given calendar day, so reloading the page
        shows the same result (useful UX and easy caching). The explanation text is also
        deterministic per day+card+topic to avoid flicker.
        """
        # Deterministic "card of the day": same card for the same calendar day.
        today = date.today().isoformat()
        digest = hashlib.sha256(today.encode("utf-8")).digest()
        card_id = int.from_bytes(digest[:4], "big") % 78
        card = cards_by_id.get(card_id)
        if card is None:
            abort(500)

        topics: list[str] = card_of_day_expl["topics"]
        topic = (request.args.get("topic") or "general").strip().lower()
        if topic not in topics:
            topic = "general"

        # Pick a deterministic variant for the given day+card+topic.
        variants = card_of_day_expl["cards"][str(card_id)][topic]
        v_digest = hashlib.sha256(f"{today}:{card_id}:{topic}".encode("utf-8")).digest()
        v_idx = int.from_bytes(v_digest[:4], "big") % len(variants)
        card_of_day_explanation = variants[v_idx].strip()

        slug = slugify(card.name)
        prev_c = cards[card.id - 1] if card.id > 0 else None
        next_c = cards[card.id + 1] if card.id < 77 else None
        nav_rows = _card_nav_rows(cards, slug)

        prev_slug = slugify(prev_c.name) if prev_c else None
        next_slug = slugify(next_c.name) if next_c else None

        return render_template(
            "template.html",
            card=card,
            slug=slug,
            is_card_of_day=True,
            card_images_dir=card_images_dir,
            card_of_day_explanation=card_of_day_explanation,
            card_of_day_topic=topic,
            card_of_day_topics=topics,
            **ctx,
        )

    @app.get(card_detail_rule)
    def card_page(slug: str) -> str:
        """Card detail page (HTML) by slug; includes prev/next navigation and full list nav."""
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
