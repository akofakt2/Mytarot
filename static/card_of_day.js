function loadI18nStrings() {
    try {
        const el = document.getElementById('ui-i18n');
        const raw = el?.textContent || 'null';
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
        return {};
    }
}

function bootCardOfDay() {
    const ui = loadI18nStrings();
    const host = document.getElementById('card-of-day-today');
    if (!host) return;

    const prefix = typeof ui.card_of_day_today_label === 'string' ? ui.card_of_day_today_label : 'Card of the day for';
    const lang = document.documentElement.lang || 'en';
    const today = new Date();
    const formatted = new Intl.DateTimeFormat(lang, { dateStyle: 'full' }).format(today);
    host.textContent = `${prefix} ${formatted}`;
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootCardOfDay);
} else {
    bootCardOfDay();
}

