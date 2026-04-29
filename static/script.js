/** * KONFIGURÁCIA IDENTIFIKÁTOROV (IDs)
 * Centrálne miesto pre názvy ID elementov v HTML. 
 * Uľahčuje údržbu, ak sa zmení HTML štruktúra.
 */
const EL = {
    question: 'question',      // Textarea pre otázku
    deck: 'mainDeck',          // Element balíčka kariet
    deckLabel: 'deckLabel',    // Textový popis pod balíčkom
    loading: 'loadingState',   // Indikátor načítavania (spinner)
    reading: 'finalReading',   // Kontajner pre výslednú veštbu (text od AI)
    newReading: 'newReadingBtn', // Tlačidlo pre novú veštbu
    tarotJson: 'tarot-data',   // ID script tagu s dátami o kartách
    uiJson: 'ui-i18n',         // ID script tagu s prekladmi rozhrania
    slot: (i) => `slot-${i}`,  // Dynamické ID pre 3 miesta na karty
    caption: (i) => `caption-${i}`, // Dynamické ID pre popisky pod kartami
};

/** Skratka pre document.getElementById */
const $ = (id) => document.getElementById(id);

/** * OBJEKT UI (USER INTERFACE)
 * Obsahuje referencie na živé DOM elementy a inicializačnú logiku.
 * Zabraňuje opakovanému volaniu getElementById v priebehu behu programu.
 */
const UI = {
    question: null,
    deck: null,
    deckLabel: null,
    loading: null,
    reading: null,
    newReading: null,
    tarotJson: null,
    uiJson: null,
    slots: [],      // Pole pre 3 sloty kariet
    i18n: {},       // Objekt s načítanými prekladmi
    init() {
        this.question = $(EL.question);
        this.deck = $(EL.deck);
        this.deckLabel = $(EL.deckLabel);
        this.loading = $(EL.loading);
        this.reading = $(EL.reading);
        this.newReading = $(EL.newReading);
        this.tarotJson = $(EL.tarotJson);
        this.uiJson = $(EL.uiJson);
        this.slots = [0, 1, 2].map((i) => $(EL.slot(i)));
        this.i18n = loadI18nStrings();
    },
    captionEl(i) {
        return $(EL.caption(i));
    },
};

const LOCK_TIME = 24 * 60 * 60 * 1000; // 24 hodín v milisekundách

/** POMOCNÉ FUNKCIE PRE RESPONSIVITU A UX */

// Zisťuje, či je šírka okna menšia ako 768px (mobil)
function isMobileViewport() {
    return window.matchMedia && window.matchMedia('(max-width: 768px)').matches;
}

// Automaticky odroluje na element, ak je užívateľ na mobile
function scrollIntoViewIfMobile(el, block = 'center') {
    if (!el || !isMobileViewport()) return;
    requestAnimationFrame(() => {
        el.scrollIntoView({ behavior: 'smooth', block });
    });
}

// Nastaví focus na element bez neželaného skoku stránky (na mobile)
function focusElementIfMobile(el) {
    if (!el || !isMobileViewport()) return;
    try {
        el.focus({ preventScroll: true });
    } catch {
        try { el.focus(); } catch { /* ignore */ }
    }
}

// Zaostrí na pole s otázkou
function focusQuestionAndReveal() {
    if (!UI.question) return;
    UI.question.focus();
    scrollIntoViewIfMobile(UI.question, 'center');
}

/**
 * Kontroluje, či má používateľ právo na výklad.
 * @returns {boolean} true, ak je aktuálny čas väčší ako uložený limit (alebo limit neexistuje).
 */
function isAccessGranted() {
    const limitRaw = localStorage.getItem('last_reading');        
    // Ak v pamäti nič nie je, používateľ môže veštiť
    if (!limitRaw) return 'new';
    
    const limitDate = parseInt(limitRaw, 10);
    const now = Date.now();

    // Ak je aktuálny čas väčší ako zapísaný limit, prístup je povolený
    return now < limitDate ? 'ok' : 'nok';
}

/** INTERNACIONALIZÁCIA (i18n) */

// Načíta JSON string s prekladmi z HTML a vráti objekt
function loadI18nStrings() {
    try {
        const raw = UI.uiJson?.textContent || 'null';
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
        return {};
    }
}

// Vráti preložený reťazec podľa kľúča, inak vráti fallback
function t(key, fallback = '') {
    const v = UI.i18n?.[key];
    return typeof v === 'string' ? v : fallback;
}

/** * SOUND MANAGER
 * Riadi prehrávanie audio efektov (miešanie, otočenie, rozdanie karty).
 * Používa pool na znovupoužitie Audio inštancií.
 */
const SoundManager = (() => {
    const specs = {
        shuffle: { path: '/static/shuffle.mp3', volume: 0.4 },
        flip: { path: '/static/flip.mp3', volume: 1 },
        deal: { path: '/static/deal.mp3', volume: 1 },
    };
    const pool = {};
    function play(name) {
        const spec = specs[name];
        if (!spec) return;
        let a = pool[name];
        if (!a) {
            a = new Audio(spec.path);
            a.volume = spec.volume;
            pool[name] = a;
        }
        a.currentTime = 0;
        a.play().catch(() => { });
    }
    return { play };
})();

/** MARKDOWN A BEZPEČNOSŤ */

// Ošetrenie nebezpečných znakov pre prevenciu XSS útokov
function escapeHtml(s) {
    const HTML_ESC = new Map([['&', '&amp;'], ['<', '&lt;'], ['>', '&gt;'], ['"', '&quot;'], ["'", '&#39;']]);
    return String(s ?? '').replace(/[&<>"']/g, (ch) => HTML_ESC.get(ch) ?? ch);
}

// Zjednodušený parser Markdownu na HTML (podporuje ### nadpisy, tučné písmo, kurzívu a odseky)
function renderMarkdownSafe(md) {
    let out = escapeHtml(md ?? '');
    out = out.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
    out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong class="md-strong">$1</strong>');
    out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    out = out.replace(/^\s*###(?!#)\s*(.+?)\s*$/gm, '\n\n<h3 class="md-h3">$1</h3>\n\n');

    return out
        .split(/\n{2,}/g)
        .map((b) => b.trim())
        .filter(Boolean)
        .map((b) => {
            if (b.startsWith('<h3 class="md-h3">')) return b;
            return `<p>${b.replaceAll('\n', '<br>')}</p>`;
        })
        .join('');
}

/** API KOMUNIKÁCIA */

// Získa CSRF/API token z meta tagov pre autorizáciu požiadaviek
function getApiToken() {
    const meta = document.querySelector('meta[name="tarot-api-token"]');
    return meta?.getAttribute('content')?.trim() || null;
}

// Načíta náhodné karty z backendu
async function apiFetchDraw() {
    const res = await fetch('api/draw', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

// Odošle otázku a vybrané karty na backend pre vygenerovanie AI interpretácie
async function apiPostReading(payload) {
    const token = getApiToken();
    const res = await fetch('api/reading', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        cache: 'no-store',
        body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => null);
    return { ok: res.ok, status: res.status, data };
}

/** LOGIKA TAROTU */

let tarotData = [];          // Všetky dostupné karty (ako fallback)
let deckState = 'ready_to_shuffle'; // Stav hry: ready_to_shuffle -> shuffling -> ready_to_deal -> dealt
let flippedCount = 0;        // Počet otočených kariet
let currentDealtCards = [];  // Aktuálne rozdané 3 karty
let pendingLoadingTimeoutId = null; // ID pre oneskorené zobrazenie loading spinneru

/**
 * Bezpečne zavolá API na vytiahnutie kariet.
 * Ak server neodpovedá, vráti prázdne pole, aby aplikácia nezamrzla.
 */
async function fetchDealtCardsSafe() {
    try {
        // Použije vašu existujúcu funkciu apiFetchDraw na riadku 178
        const data = await apiFetchDraw();
        return Array.isArray(data) ? data : [];
    } catch (e) {
        console.error('Kritická chyba pri ťahaní kariet:', e);
        return [];
    }
}

// Zabezpečuje správne formátovanie dát o kartách (napr. otočenie karty)
function normalizeDealtCards(arr) {
    if (!Array.isArray(arr)) return [];
    return arr.map((c) => {
        const rev = typeof c?.rev === 'number' ? c.rev : (c?.orientation === 'reversed' ? 1 : 0);
        return { ...c, rev };
    });
}

// Zobrazí/skryje loading spinner
function setLoadingActive(on) {
    UI.loading?.classList.toggle('active', on);
}

// Zobrazí/skryje tlačidlo "Nová veštba"
function setNewReadingVisible(on) {
    if (!UI.newReading) return;
    UI.newReading.classList.toggle('visible', on);
    UI.newReading.setAttribute('aria-hidden', on ? 'false' : 'true');
}

// Vyčistí UI pred novou interpretáciou
function clearReadingUi() {
    if (UI.reading) {
        UI.reading.classList.remove('visible');
        UI.reading.innerHTML = '';
    }
    setNewReadingVisible(false);
}

// Hlavná funkcia na odoslanie dát na server a spracovanie AI odpovede
async function sendReadingRequest() {
    const q = (UI.question?.value || '').trim();
    if (!q) return;

    setLoadingActive(true);
    clearReadingUi();

    const [p0, p1, p2] = currentDealtCards;
    const payload = {
        question: q,
        past_id: p0?.id,
        present_id: p1?.id,
        future_id: p2?.id,
        past_rev: p0?.rev ?? 0,
        present_rev: p1?.rev ?? 0,
        future_rev: p2?.rev ?? 0,
    };

    try {
        const { ok, status, data } = await apiPostReading(payload);
        setLoadingActive(false);

        if (!ok) {
            // --- LOGIKA PRE CHYBU (vrátane 502) ---
            let errorMsg = "Spojenie s hviezdami sa prerušilo. Skús to o chvíľu znova.";

            if (status === 502) {
                errorMsg = "Hlas hviezd je momentálne príliš slabý (Chyba 502). Skús požiadať o výklad znova.";
            }

            if (UI.reading) {
                UI.reading.innerText = t('error_llm_unavailable');                
            }
            // Pri chybe NEZAPISOVAŤ čas do localStorage, aby mal používateľ ďalší pokus zadarmo
            UI.reading.classList.add('visible');
            setNewReadingVisible(true);
        } else {
            // --- ÚSPEŠNÁ VEŠTBA ---
            const text = data?.reading || '';
            if (UI.reading) {
                UI.reading.innerHTML = renderMarkdownSafe(text);
                UI.reading.classList.add('visible');

                // Zápis do localStorage len pri úspechu                                
                if(isAccessGranted() == 'new') {
                    const expirationDate = Date.now();
                    localStorage.setItem('last_reading', expirationDate.toString());
                    UI.reading.innerHTML += '<hr>';
                    UI.reading.innerHTML += UI.i18n?.['daily_limit'] || '';
                }
                //ak moze vestit
                else {
                    setNewReadingVisible(true);
                }
            }
        }        
        scrollIntoViewIfMobile(UI.reading, 'start');

    } catch (e) {
        console.error('Reading request failed:', e);
        setLoadingActive(false);
        if (UI.reading) {
            UI.reading.innerHTML = "<p>Magické sily sú momentálne vyčerpané. Skús to neskôr.</p>";
            UI.reading.classList.add('visible');
        }
    }
}
/** INTERAKCIE S KARTAMI */

// Funkcia volaná pri kliknutí na kartu (otočenie)
function flipCard(index, element) {
    if (element.classList.contains('is-flipped')) return;

    SoundManager.play('flip');
    element.classList.add('is-flipped');
    UI.captionEl(index)?.classList.add('visible');

    flippedCount += 1;

    // Po otočení karty zameria pozornosť na jej význam (na mobile)
    const caption = UI.captionEl(index);
    const meaningEl = caption?.querySelector('.slot-meaning') || caption?.querySelector('.slot-title');
    if (meaningEl) {
        scrollIntoViewIfMobile(meaningEl, 'center');
        focusElementIfMobile(meaningEl);
    }

    // Ak sú otočené všetky 3, požiadaj o výklad
    if (flippedCount === 3) {
        sendReadingRequest();
        pendingLoadingTimeoutId = setTimeout(() => setLoadingActive(true), 1000);
    }
}

// Hlavný riadiaci mechanizmus balíčka (miešanie -> rozdávanie)
async function handleDeckInteraction() {
    const q = (UI.question?.value || '').trim();
    const lastClick = localStorage.getItem('last_reading');
    const now = Date.now();


    // 1. FÁZA: MIEŠANIE
    if (deckState === 'ready_to_shuffle') {        
        // KONTROLA ČASOVÉHO ZÁMKU        
        if (isAccessGranted() == 'nok') {
            const remainingMs = LOCK_TIME - (now - lastClick);
            const remainingHours = Math.ceil(remainingMs / (1000 * 60 * 60));

            UI.deckLabel.innerHTML = UI.i18n?.['daily_limit'] || '';
            
            // Voliteľné: Presmerovanie na kávu po kliknutí v zámku
            //window.open('https://www.buymeacoffee.com/vas-profil', '_blank');
            return;
        }

        if (!q) {
            UI.deckLabel.innerText = t('deck_label_need_question');
            focusQuestionAndReveal();
            return;
        }
        deckState = 'shuffling';
        UI.deck?.classList.add('is-shuffling');
        SoundManager.play('shuffle');

        setTimeout(() => {
            UI.deck?.classList.remove('is-shuffling');
            deckState = 'ready_to_deal';
            UI.deckLabel.innerText = t('deck_label_deal');
        }, 1500);

        // 2. FÁZA: ROZDÁVANIE
    } else if (deckState === 'ready_to_deal') {
        deckState = 'dealt';
        UI.deck.style.opacity = '0.2';

        const dealt = await fetchDealtCardsSafe();
        currentDealtCards = normalizeDealtCards(dealt.length ? dealt : tarotData).slice(0, 3);

        // Postupné vykreslenie 3 kariet s animáciou
        for (let i = 0; i < 3; i++) {
            setTimeout(() => {
                SoundManager.play('deal');
                const slot = UI.slots[i];
                if (!slot) return;

                const cardData = currentDealtCards[i];
                const rotateStyle = cardData.rev === 1 ? 'transform: rotate(180deg);' : '';

                slot.innerHTML = `
                    <div class="card" onclick="flipCard(${i}, this)">
                        <div class="card-face card-back">✨</div>
                        <div class="card-face card-front">
                            ${cardData.image_url ? `<img src="${cardData.image_url}" alt="" loading="lazy" style="${rotateStyle}" />` : ''}
                        </div>
                    </div>
                    <div class="slot-caption" id="${EL.caption(i)}">
                        <div class="slot-title">${escapeHtml(cardData.name)}</div>
                        ${cardData.meaning ? `<div class="slot-meaning" tabindex="-1">${escapeHtml(cardData.meaning)}</div>` : ''}
                    </div>
                `;
            }, i * 400);
        }
    }
}

// Resetuje celú aplikáciu do pôvodného stavu pre novú otázku
function resetReading() {
    if (pendingLoadingTimeoutId) clearTimeout(pendingLoadingTimeoutId);
    deckState = 'ready_to_shuffle';
    flippedCount = 0;
    if (UI.question) UI.question.value = '';
    UI.deck.style.opacity = '';
    UI.deckLabel.innerText = t('deck_label_shuffle');
    UI.slots.forEach(s => s.innerHTML = '');
    setLoadingActive(false);
    clearReadingUi();
}

/** INICIALIZÁCIA */
function boot() {
    UI.init();
    // Načítanie základných dát o kartách z JSON skriptu v HTML
    try {
        const raw = UI.tarotJson?.textContent || '[]';
        tarotData = JSON.parse(raw);
    } catch { tarotData = []; }

    UI.newReading?.addEventListener('click', resetReading);
}

// Spustenie po načítaní DOM
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
} else {
    boot();
}

// Export funkcií pre globálny prístup z HTML (onclick atribúty)
window.flipCard = flipCard;
window.handleDeckInteraction = handleDeckInteraction;
window.resetForNewReading = resetReading;