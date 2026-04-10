/* Выгодные билеты — round-trip deal finder */

const AIRPORT_TZ_DEALS = { LED: 3, CEK: 5 };
const MONTHS_RU_SHORT = [
    'янв', 'фев', 'мар', 'апр', 'мая', 'июн',
    'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'
];
const WEEKDAYS_SHORT = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

document.addEventListener('DOMContentLoaded', () => {
    // Set default month to current
    const now = new Date();
    const monthInput = document.getElementById('filterMonth');
    monthInput.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

    // Set default dates
    const dateFrom = document.getElementById('filterDateFrom');
    const dateTo = document.getElementById('filterDateTo');
    dateFrom.value = now.toISOString().slice(0, 10);
    const nextMonth = new Date(now);
    nextMonth.setMonth(nextMonth.getMonth() + 1);
    dateTo.value = nextMonth.toISOString().slice(0, 10);

    // Tab switching
    document.getElementById('tabMonth').addEventListener('click', () => switchMode('month'));
    document.getElementById('tabDates').addEventListener('click', () => switchMode('dates'));

    // Search
    document.getElementById('searchBtn').addEventListener('click', searchDeals);
});

function switchMode(mode) {
    document.getElementById('tabMonth').classList.toggle('filter-tab--active', mode === 'month');
    document.getElementById('tabDates').classList.toggle('filter-tab--active', mode === 'dates');
    document.getElementById('monthGroup').style.display = mode === 'month' ? '' : 'none';
    document.getElementById('datesGroup').style.display = mode === 'dates' ? '' : 'none';
}

function currentMode() {
    return document.getElementById('tabMonth').classList.contains('filter-tab--active') ? 'month' : 'dates';
}

async function searchDeals() {
    const origin = document.getElementById('filterOrigin').value;
    const minDays = document.getElementById('filterMinDays').value;
    const maxDays = document.getElementById('filterMaxDays').value;

    let params = `origin=${origin}&min_days=${minDays}&max_days=${maxDays}`;

    if (currentMode() === 'month') {
        const month = document.getElementById('filterMonth').value;
        params += `&month=${month}`;
    } else {
        const df = document.getElementById('filterDateFrom').value;
        const dt = document.getElementById('filterDateTo').value;
        params += `&date_from=${df}&date_to=${dt}`;
    }

    const container = document.getElementById('dealsResults');
    container.innerHTML = '<div class="deals-placeholder">Поиск...</div>';

    try {
        const resp = await fetch(`/api/deals?${params}`);
        const data = await resp.json();
        renderDeals(data, origin);

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

function renderDeals(data, origin) {
    const container = document.getElementById('dealsResults');
    container.innerHTML = '';

    if (!data.deals || data.deals.length === 0) {
        container.innerHTML = '<div class="deals-placeholder">Ничего не найдено. Попробуйте изменить параметры.</div>';
        return;
    }

    const dest = origin === 'LED' ? 'CEK' : 'LED';
    const heading = document.createElement('div');
    heading.className = 'deals-count';
    heading.textContent = `Найдено ${data.count} вариант${pluralSuffix(data.count)}`;
    container.appendChild(heading);

    data.deals.forEach((deal, idx) => {
        const card = document.createElement('div');
        card.className = 'deal-card';

        // Rank badge
        const rank = document.createElement('div');
        rank.className = 'deal-rank';
        rank.textContent = `#${idx + 1}`;
        card.appendChild(rank);

        // Total price
        const total = document.createElement('div');
        total.className = 'deal-total';
        total.innerHTML = `<span class="deal-total__sum">${formatPrice(deal.total)}</span>
            <span class="deal-total__days">${deal.days} дн.</span>`;
        card.appendChild(total);

        // Flights row
        const flights = document.createElement('div');
        flights.className = 'deal-flights';

        flights.appendChild(buildFlightSegment(deal.outbound, origin, dest, 'Туда'));
        flights.appendChild(buildFlightSegment(deal['return'], dest, origin, 'Обратно'));

        card.appendChild(flights);
        container.appendChild(card);
    });
}

function buildFlightSegment(f, from, to, label) {
    const seg = document.createElement('div');
    seg.className = 'deal-segment';

    const d = new Date(f.date + 'T00:00:00');
    const dayName = WEEKDAYS_SHORT[d.getDay()];
    const dateStr = `${d.getDate()} ${MONTHS_RU_SHORT[d.getMonth()]}`;
    const time = formatTimeDeal(f.departure_at, from);
    const dur = formatDurationDeal(f.duration);

    let seatsBadge = '';
    if (f.seats_available != null && f.seats_available <= 5) {
        const cls = f.seats_available <= 3 ? 'seats-badge--urgent' : 'seats-badge--warning';
        seatsBadge = `<span class="seats-badge ${cls}">Осталось ${f.seats_available}</span>`;
    }

    seg.innerHTML = `
        <div class="deal-segment__label">${label}</div>
        <div class="deal-segment__main">
            <img src="${f.airline_logo}" alt="${f.airline}" class="deal-segment__logo">
            <div class="deal-segment__info">
                <div class="deal-segment__route">${from} &rarr; ${to}</div>
                <div class="deal-segment__date">${dateStr}, ${dayName}${time ? ' &bull; ' + time : ''}${dur ? ' &bull; ' + dur : ''}</div>
                <div class="deal-segment__meta">${f.airline_name} ${f.flight_number}${f.equipment ? ' &bull; ' + f.equipment : ''} ${seatsBadge}</div>
            </div>
            <div class="deal-segment__right">
                <div class="deal-segment__price">${formatPrice(f.price)}</div>
                ${f.booking_url ? `<a href="${f.booking_url}" target="_blank" rel="noopener" class="deal-segment__buy">Купить</a>` : ''}
            </div>
        </div>
    `;
    return seg;
}

function formatPrice(p) {
    return p.toLocaleString('ru-RU') + ' \u20BD';
}

function formatTimeDeal(isoStr, airportCode) {
    if (!isoStr) return '';
    try {
        const d = new Date(isoStr);
        const offset = AIRPORT_TZ_DEALS[airportCode] || 3;
        const local = new Date(d.getTime() + offset * 3600000);
        const hh = String(local.getUTCHours()).padStart(2, '0');
        const mm = String(local.getUTCMinutes()).padStart(2, '0');
        return `${hh}:${mm}`;
    } catch {
        return '';
    }
}

function formatDurationDeal(minutes) {
    if (!minutes) return '';
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}\u0447 ${m}\u043c`;
}

function pluralSuffix(n) {
    const abs = Math.abs(n) % 100;
    const last = abs % 10;
    if (abs >= 11 && abs <= 19) return 'ов';
    if (last === 1) return '';
    if (last >= 2 && last <= 4) return 'а';
    return 'ов';
}
