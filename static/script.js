/** Centrálne ID → jedno miesto na údržbu */
const EL = {
    question: 'question',
    deck: 'mainDeck',
    deckLabel: 'deckLabel',
    loading: 'loadingState',
    reading: 'finalReading',
    newReading: 'newReadingBtn',
    tarotJson: 'tarot-data',
    uiJson: 'ui-i18n',
    slot: (i) => `slot-${i}`,
    caption: (i) => `caption-${i}`,
};

const $ = (id) => document.getElementById(id);

/** Referencie na DOM po init (žiadne getElementById po kóde) */
const UI = {
    question: null,
    deck: null,
    deckLabel: null,
    loading: null,
    reading: null,
    newReading: null,
    tarotJson: null,
    uiJson: null,
    slots: [],
    i18n: {},
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

function loadI18nStrings() {
    try {
        const raw = UI.uiJson?.textContent || 'null';
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
        return {};
    }
}

function t(key, fallback = '') {
    const v = UI.i18n?.[key];
    return typeof v === 'string' ? v : fallback;
}

// --- ZVUKY (jedna inštancia na typ, bez ručného cloneNode) ---
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
        a.play().catch(() => {});
    }
    return { play };
})();

const HTML_ESC = new Map([
    ['&', '&amp;'],
    ['<', '&lt;'],
    ['>', '&gt;'],
    ['"', '&quot;'],
    ["'", '&#39;'],
]);

function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, (ch) => HTML_ESC.get(ch) ?? ch);
}

function renderMarkdownSafe(md) {
    let out = escapeHtml(md ?? '');
    out = out.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
    out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong class="md-strong">$1</strong>');
    out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    const blocks = out
        .split(/\n{2,}/g)
        .map((b) => b.trim())
        .filter(Boolean);
    return blocks
        .map((b) => {
            const m = b.match(/^###\s*(.+)$/);
            if (m) return `<h3 class="md-h3">${m[1]}</h3>`;
            return `<p>${b.replaceAll('\n', '<br>')}</p>`;
        })
        .join('');
}

// --- API ---
async function apiFetchDraw() {
    const res = await fetch('api/draw', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

async function apiPostReading(payload) {
    const res = await fetch('api/reading', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
        body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => null);
    return { ok: res.ok, status: res.status, data };
}

async function fetchDealtCardsSafe() {
    try {
        const data = await apiFetchDraw();
        return Array.isArray(data) ? data : [];
    } catch (e) {
        console.log(t('log_draw_failed', 'Failed to load new cards:'), e);
        return [];
    }
}

function loadTarotData() {
    try {
        const raw = UI.tarotJson?.textContent || '[]';
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}

let tarotData = [];

function normalizeDealtCards(arr) {
    if (!Array.isArray(arr)) return [];
    return arr.map((c) => {
        const rev =
            typeof c?.rev === 'number' ? c.rev : (c?.orientation === 'reversed' ? 1 : 0);
        return { ...c, rev };
    });
}

let deckState = 'ready_to_shuffle';
let flippedCount = 0;
let currentDealtCards = [];
let pendingLoadingTimeoutId = null;

function setLoadingActive(on) {
    UI.loading?.classList.toggle('active', on);
}

function setNewReadingVisible(on) {
    if (!UI.newReading) return;
    UI.newReading.classList.toggle('visible', on);
    UI.newReading.setAttribute('aria-hidden', on ? 'false' : 'true');
}

function clearReadingUi() {
    if (UI.reading) {
        UI.reading.classList.remove('visible');
        UI.reading.innerHTML = '';
    }
    setNewReadingVisible(false);
}

function startLLMLoading() {
    setLoadingActive(true);
}

function scheduleReadingAfterThirdFlip() {
    sendReadingRequest();
    pendingLoadingTimeoutId = setTimeout(startLLMLoading, 1000);
}

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

        if (!ok) {
            setLoadingActive(false);
            const serverMsg =
                data && typeof data.error === 'string' && data.error.trim()
                    ? data.error.trim()
                    : null;
            const msg =
                serverMsg ||
                (status === 502
                    ? t('error_llm_unavailable', 'LLM unavailable. Please try again later.')
                    : t('error_reading_failed', 'Reading failed. Please try again.'));
            if (UI.reading) {
                UI.reading.innerHTML = `<p>${escapeHtml(msg)}</p>`;
                UI.reading.classList.add('visible');
            }
            setNewReadingVisible(true);
            return;
        }

        setLoadingActive(false);
        const text =
            (data && typeof data.llm_response === 'string' && data.llm_response.trim())
                ? data.llm_response.trim()
                : (data && typeof data.reading === 'string' && data.reading.trim())
                    ? data.reading.trim()
                    : '';
        if (UI.reading) {
            UI.reading.innerHTML = renderMarkdownSafe(text);
            UI.reading.classList.add('visible');
        }
        setNewReadingVisible(true);
    } catch (e) {
        console.log('Reading request failed:', e);
    }
}

function applyCardFlipVisual(index, cardEl) {
    cardEl.classList.add('is-flipped');
    UI.captionEl(index)?.classList.add('visible');
}

function onAllThreeCardsFlipped() {
    scheduleReadingAfterThirdFlip();
}

function flipCard(index, element) {

    if (element.classList.contains('is-flipped')) return;

    SoundManager.play('flip');
    applyCardFlipVisual(index, element);
    flippedCount += 1;

    if (flippedCount === 3) onAllThreeCardsFlipped();
}

async function handleDeckInteraction() {
    const q = (UI.question?.value || '').trim();

    if (deckState === 'ready_to_shuffle') {
        if (!q) {
            if (UI.deckLabel) {
                UI.deckLabel.innerText = t('deck_label_need_question', 'Write your question first ↑');
                UI.deckLabel.style.opacity = '1';
                UI.deckLabel.style.fontStyle = 'italic';
            }
            UI.question?.focus();
            return;
        }
        deckState = 'shuffling';
        UI.deck?.classList.add('is-shuffling');
        if (UI.deckLabel) {
            UI.deckLabel.innerText = t('deck_label_focus', 'Focus on your question...');
            UI.deckLabel.style.opacity = '0.7';
            UI.deckLabel.style.fontStyle = 'italic';
        }

        SoundManager.play('shuffle');

        setTimeout(() => {
            UI.deck?.classList.remove('is-shuffling');
            deckState = 'ready_to_deal';
            if (UI.deckLabel) {
                UI.deckLabel.innerText = t('deck_label_deal', 'Deal the cards');
                UI.deckLabel.style.opacity = '1';
                UI.deckLabel.style.fontStyle = 'normal';
            }
            if (UI.deck) UI.deck.style.boxShadow = '0 0 20px rgba(197, 160, 89, 0.6)';
        }, 1500);
    } else if (deckState === 'ready_to_deal') {
        deckState = 'dealt';
        flippedCount = 0;
        if (UI.deck) {
            UI.deck.style.opacity = '0.2';
            UI.deck.style.cursor = 'default';
            UI.deck.style.boxShadow = 'none';
        }
        if (UI.deckLabel) UI.deckLabel.style.opacity = '0';

        const dealt = await fetchDealtCardsSafe();
        currentDealtCards = normalizeDealtCards(dealt.length ? dealt : tarotData).slice(0, 3);

        for (let i = 0; i < 3; i++) {
            setTimeout(() => {
                SoundManager.play('deal');

                const slot = UI.slots[i];
                if (!slot) return;

                const cardData = currentDealtCards[i] || { id: null, image_url: '', rev: 0, name: '', meaning: '' };
                const rotateStyle = cardData.rev === 1 ? 'transform: rotate(180deg);' : '';
                const title = escapeHtml(cardData.name);
                const meaning = escapeHtml(cardData.meaning);

                slot.innerHTML = `
                    <div class="card" onclick="flipCard(${i}, this)">
                        <div class="card-face card-back">✨</div>
                        <div class="card-face card-front">
                            ${cardData.image_url ? `<img src="${cardData.image_url}" alt="" loading="lazy" style="${rotateStyle}" />` : ''}
                        </div>
                    </div>
                    <div class="slot-caption" id="${EL.caption(i)}">
                        <div class="slot-title">${title}</div>
                        ${meaning ? `<div class="slot-meaning">${meaning}</div>` : ''}
                    </div>
                `;

                if (i === 2 && UI.deckLabel) {
                    UI.deckLabel.innerText = t('deck_label_flip', 'Flip a card');
                    UI.deckLabel.style.opacity = '1';
                    UI.deckLabel.style.fontStyle = 'normal';
                }
            }, i * 400);
        }
    }
}

function resetReading() {
    if (pendingLoadingTimeoutId != null) {
        clearTimeout(pendingLoadingTimeoutId);
        pendingLoadingTimeoutId = null;
    }

    deckState = 'ready_to_shuffle';
    flippedCount = 0;
    currentDealtCards = [];

    if (UI.question) {
        UI.question.value = '';
        UI.question.focus();
    }

    UI.deck?.classList.remove('is-shuffling');
    if (UI.deck) {
        UI.deck.style.opacity = '';
        UI.deck.style.cursor = 'pointer';
        UI.deck.style.boxShadow = '';
    }
    if (UI.deckLabel) {
        UI.deckLabel.innerText = t('deck_label_shuffle', 'Shuffle the cards');
        UI.deckLabel.style.opacity = '1';
        UI.deckLabel.style.fontStyle = 'normal';
    }

    for (const slot of UI.slots) {
        if (slot) slot.innerHTML = '';
    }

    setLoadingActive(false);
    clearReadingUi();
}

function boot() {
    UI.init();
    tarotData = loadTarotData();
    UI.newReading?.addEventListener('click', resetReading);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
} else {
    boot();
}

window.flipCard = flipCard;
window.handleDeckInteraction = handleDeckInteraction;
window.resetForNewReading = resetReading;
