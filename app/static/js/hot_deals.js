/* Горячие билеты — cheapest flights in the next 14 days */

const AIRPORT_TZ_HOT = { LED: 3, CEK: 5 };
const MONTHS_RU_HOT = [
    'янв', 'фев', 'мар', 'апр', 'мая', 'июн',
    'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'
];
const WEEKDAYS_HOT = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

document.addEventListener('DOMContentLoaded', loadHotDeals);

async function loadHotDeals() {
    const container = document.getElementById('hotList');

    try {
        const resp = await fetch('/api/hot-deals');
        const data = await resp.json();
        renderHotDeals(data);

        if (data.last_update) {
            const el = document.getElementById('lastUpdate');
            const d = new Date(data.last_update);
            el.textContent = `Обновлено: ${d.toLocaleTimeString('ru-RU')}`;
        }
    } catch (err) {
        container.innerHTML = '<div class="deals-placeholder">Ошибка загрузки</div>';
        console.error(err);
    }
}

function renderHotDeals(data) {
    const container = document.getElementById('hotList');
    container.innerHTML = '';

    if (!data.deals || data.deals.length === 0) {
        container.innerHTML = '<div class="deals-placeholder">Нет доступных рейсов в ближайшие 14 дней</div>';
        return;
    }

    data.deals.forEach((f, idx) => {
        const card = document.createElement('div');
        card.className = 'hot-card';

        const d = new Date(f.date + 'T00:00:00');
        const dayName = WEEKDAYS_HOT[d.getDay()];
        const dateStr = `${d.getDate()} ${MONTHS_RU_HOT[d.getMonth()]}`;
        const time = formatTimeHot(f.departure_at, f.origin);
        const dur = formatDurationHot(f.duration);

        // Days until departure
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const diff = Math.ceil((d - today) / 86400000);
        let daysLabel = '';
        if (diff === 0) daysLabel = 'Сегодня';
        else if (diff === 1) daysLabel = 'Завтра';
        else daysLabel = `Через ${diff} дн.`;

        let seatsBadge = '';
        if (f.seats_available != null && f.seats_available <= 5) {
            const cls = f.seats_available <= 3 ? 'seats-badge--urgent' : 'seats-badge--warning';
            seatsBadge = `<span class="seats-badge ${cls}">Осталось ${f.seats_available}</span>`;
        }

        card.innerHTML = `
            <div class="hot-card__rank">#${idx + 1}</div>
            <div class="hot-card__main">
                <img src="${f.airline_logo}" alt="${f.airline}" class="hot-card__logo">
                <div class="hot-card__info">
                    <div class="hot-card__route">${f.origin_name} &rarr; ${f.dest_name}</div>
                    <div class="hot-card__date">${dateStr}, ${dayName} &bull; ${daysLabel}${time ? ' &bull; ' + time : ''}${dur ? ' &bull; ' + dur : ''}</div>
                    <div class="hot-card__meta">${f.airline_name} ${f.flight_number}${f.equipment ? ' &bull; ' + f.equipment : ''} ${seatsBadge}</div>
                </div>
                <div class="hot-card__right">
                    <div class="hot-card__price">${formatPriceHot(f.price)}</div>
                    ${f.booking_url ? `<a href="${f.booking_url}" target="_blank" rel="noopener" class="hot-card__buy">Купить</a>` : ''}
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

function formatPriceHot(p) {
    return p.toLocaleString('ru-RU') + ' \u20BD';
}

function formatTimeHot(isoStr, airportCode) {
    if (!isoStr) return '';
    try {
        const d = new Date(isoStr);
        const offset = AIRPORT_TZ_HOT[airportCode] || 3;
        const local = new Date(d.getTime() + offset * 3600000);
        const hh = String(local.getUTCHours()).padStart(2, '0');
        const mm = String(local.getUTCMinutes()).padStart(2, '0');
        return `${hh}:${mm}`;
    } catch {
        return '';
    }
}

function formatDurationHot(minutes) {
    if (!minutes) return '';
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}\u0447 ${m}\u043c`;
}
