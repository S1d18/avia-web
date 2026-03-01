/* Flight Price Tracker — Calendar & Auto-refresh */

const MONTHS_RU = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
];

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

// Airport timezone offsets (UTC+N hours) for local time display
const AIRPORT_TZ = {
    'LED': 3,  // St. Petersburg — MSK (UTC+3)
    'CEK': 5,  // Chelyabinsk — YEKT (UTC+5)
};

let currentOrigin = '';
let currentDest = '';
let currentYear = 0;
let currentMonth = 0;
let lastUpdateTs = null;
let refreshTimer = null;

function initCalendar() {
    const page = document.querySelector('.calendar-page');
    if (!page) return;

    currentOrigin = page.dataset.origin;
    currentDest = page.dataset.destination;

    const now = new Date();
    currentYear = now.getFullYear();
    currentMonth = now.getMonth() + 1;

    document.getElementById('prevMonth').addEventListener('click', () => {
        currentMonth--;
        if (currentMonth < 1) { currentMonth = 12; currentYear--; }
        loadCalendar();
    });

    document.getElementById('nextMonth').addEventListener('click', () => {
        currentMonth++;
        if (currentMonth > 12) { currentMonth = 1; currentYear++; }
        loadCalendar();
    });

    // Modal close
    document.getElementById('modalClose').addEventListener('click', closeModal);
    document.getElementById('modalOverlay').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeModal();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });

    loadCalendar();
    startAutoRefresh();
}

function monthKey() {
    return `${currentYear}-${String(currentMonth).padStart(2, '0')}`;
}

async function loadCalendar() {
    const label = document.getElementById('monthLabel');
    label.textContent = `${MONTHS_RU[currentMonth - 1]} ${currentYear}`;

    const grid = document.getElementById('calendarGrid');
    grid.innerHTML = '<div class="calendar-loading">\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430...</div>';

    try {
        const resp = await fetch(`/api/calendar/${currentOrigin}/${currentDest}?month=${monthKey()}`);
        const data = await resp.json();
        renderCalendar(data);

        if (data.last_update) {
            lastUpdateTs = data.last_update;
            updateLastUpdateLabel(data.last_update);
        }
    } catch (err) {
        grid.innerHTML = '<div class="calendar-loading">\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438</div>';
        console.error(err);
    }
}

function renderCalendar(data) {
    const grid = document.getElementById('calendarGrid');
    grid.innerHTML = '';

    // Weekday headers
    WEEKDAYS.forEach(wd => {
        const el = document.createElement('div');
        el.className = 'cal-weekday';
        el.textContent = wd;
        grid.appendChild(el);
    });

    // First day of month
    const firstDay = new Date(currentYear, currentMonth - 1, 1);
    let startDow = firstDay.getDay(); // 0=Sun
    startDow = startDow === 0 ? 6 : startDow - 1; // Convert to Mon=0

    const daysInMonth = new Date(currentYear, currentMonth, 0).getDate();
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const { days, price_range } = data;
    const pMin = price_range.min || 0;
    const pMax = price_range.max || 0;
    const pRange = pMax - pMin;

    // Empty cells before first day
    for (let i = 0; i < startDow; i++) {
        const el = document.createElement('div');
        el.className = 'cal-cell cal-cell--empty';
        grid.appendChild(el);
    }

    for (let d = 1; d <= daysInMonth; d++) {
        const dateKey = `${currentYear}-${String(currentMonth).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        const cellDate = new Date(currentYear, currentMonth - 1, d);
        const dayData = days[dateKey];
        const isPast = cellDate < today || (dayData && dayData.all_past);

        const cell = document.createElement('div');
        cell.className = 'cal-cell';

        if (isPast) cell.classList.add('cal-cell--past');

        if (dayData && dayData.cheapest_price) {
            const price = dayData.cheapest_price;
            const tier = getPriceTier(price, pMin, pRange);
            cell.classList.add(`cal-cell--${tier}`);

            // Day number
            const dayEl = document.createElement('div');
            dayEl.className = 'cal-cell__day';
            dayEl.textContent = d;
            cell.appendChild(dayEl);

            // Price + optional change arrow
            const priceRow = document.createElement('div');
            priceRow.className = 'cal-cell__price-row';

            const priceEl = document.createElement('span');
            priceEl.className = `cal-cell__price cal-cell__price--${tier}`;
            priceEl.textContent = formatPrice(price);
            priceRow.appendChild(priceEl);

            const cheapest = dayData.flights.find(f => f.is_available) || dayData.flights[0];
            if (cheapest && cheapest.price_history && cheapest.price_history.length > 0) {
                const lastChange = cheapest.price_history[0];
                const arrow = document.createElement('span');
                arrow.className = 'price-arrow';
                if (lastChange.new < lastChange.old) {
                    arrow.classList.add('price-arrow--down');
                    arrow.textContent = '\u2193';
                } else {
                    arrow.classList.add('price-arrow--up');
                    arrow.textContent = '\u2191';
                }
                priceRow.appendChild(arrow);
            }

            cell.appendChild(priceRow);

            // Sold out badge if no available flights
            const hasAvailable = dayData.flights.some(f => f.is_available);
            if (!hasAvailable) {
                const soldOut = document.createElement('div');
                soldOut.className = 'cal-cell__sold-out';
                soldOut.textContent = 'Нет билетов';
                cell.appendChild(soldOut);
                cell.classList.add('cal-cell--sold-out');
            }

            // Flight count
            if (dayData.flight_count > 1) {
                const countEl = document.createElement('div');
                countEl.className = 'cal-cell__count';
                countEl.textContent = dayData.flight_count + ' \u0440\u0435\u0439\u0441.';
                cell.appendChild(countEl);
            }

            cell.addEventListener('click', () => openDayModal(dateKey, dayData));
        } else {
            const dayEl = document.createElement('div');
            dayEl.className = 'cal-cell__day';
            dayEl.textContent = d;
            cell.appendChild(dayEl);

            const noData = document.createElement('div');
            noData.className = 'cal-cell__price';
            noData.style.color = 'var(--text-muted)';
            noData.textContent = '\u2014';
            cell.appendChild(noData);
        }

        grid.appendChild(cell);
    }
}

function getPriceTier(price, pMin, pRange) {
    if (pRange === 0) return 'low';
    const ratio = (price - pMin) / pRange;
    if (ratio < 0.33) return 'low';
    if (ratio < 0.66) return 'mid';
    return 'high';
}

function formatPrice(p) {
    return p.toLocaleString('ru-RU') + ' \u20BD';
}

function formatDuration(minutes) {
    if (!minutes) return '';
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}\u0447 ${m}\u043c`;
}

function formatTime(isoStr, airportCode) {
    if (!isoStr) return '';
    try {
        const d = new Date(isoStr);
        const offset = AIRPORT_TZ[airportCode] || 3; // default MSK
        const local = new Date(d.getTime() + offset * 3600000);
        const hh = String(local.getUTCHours()).padStart(2, '0');
        const mm = String(local.getUTCMinutes()).padStart(2, '0');
        return `${hh}:${mm}`;
    } catch {
        const match = isoStr.match(/T(\d{2}:\d{2})/);
        return match ? match[1] : '';
    }
}

function formatDateTime(isoStr) {
    if (!isoStr) return '';
    try {
        const d = new Date(isoStr);
        return d.toLocaleDateString('ru-RU', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    } catch { return isoStr; }
}

function openDayModal(dateKey, dayData) {
    const overlay = document.getElementById('modalOverlay');
    const title = document.getElementById('modalTitle');
    const body = document.getElementById('modalBody');

    const d = new Date(dateKey + 'T00:00:00');
    const todayDate = new Date();
    todayDate.setHours(0, 0, 0, 0);
    const isPastDate = d < todayDate || (dayData && dayData.all_past);

    const dateStr = d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
    const archiveBadge = isPastDate ? ' <span class="modal-archive-badge">Архив</span>' : '';
    title.innerHTML = `${dateStr} \u2014 ${dayData.flight_count} \u0440\u0435\u0439\u0441${flightSuffix(dayData.flight_count)}${archiveBadge}`;

    body.innerHTML = '';

    // Read which history sections are open from localStorage
    const storageKey = `hist_open_${dateKey}`;
    let openSet;
    try {
        openSet = new Set(JSON.parse(localStorage.getItem(storageKey) || '[]'));
    } catch { openSet = new Set(); }

    dayData.flights.forEach((f, idx) => {
        const card = document.createElement('div');
        card.className = 'flight-card';

        const flightId = `${f.airline}_${f.flight_number || idx}`;

        // Main row: logo + airline + time + duration + price + buy
        const time = formatTime(f.departure_at, currentOrigin);
        const dur = formatDuration(f.duration);
        const metaParts = [];
        if (time) metaParts.push(time);
        if (dur) metaParts.push(dur);

        // Equipment & arrival time in meta
        if (f.equipment) metaParts.push(f.equipment);
        if (f.arrive_time_local) metaParts.push('приб. ' + f.arrive_time_local);

        // Seats available badge (show only when truly scarce — 5 or fewer)
        let seatsBadge = '';
        if (f.is_available && f.seats_available != null && f.seats_available <= 5) {
            const seatsCls = f.seats_available <= 3 ? 'seats-badge--urgent' : 'seats-badge--warning';
            seatsBadge = `<span class="seats-badge ${seatsCls}">Осталось ${f.seats_available} бил.</span>`;
        }

        const mainRow = document.createElement('div');
        mainRow.className = 'flight-card__main';
        mainRow.innerHTML = `
            <div class="flight-card__info">
                <img src="${f.airline_logo}" alt="${f.airline}" class="flight-card__logo">
                <div class="flight-card__details">
                    <span class="flight-card__name">${f.airline_name} ${seatsBadge}</span>
                    <span class="flight-card__meta">${f.airline} ${f.flight_number}${metaParts.length ? ' \u2022 ' + metaParts.join(' \u2022 ') : ''}</span>
                </div>
            </div>
            <div class="flight-card__right">
                <span class="flight-card__price${!f.is_available || isPastDate ? ' flight-card__price--unavailable' : ''}">${formatPrice(f.price)}</span>
                ${isPastDate ? '' : (!f.is_available ? '<span class="flight-card__sold-out">\u0411\u0438\u043b\u0435\u0442\u043e\u0432 \u043d\u0435\u0442</span>' : (f.booking_url ? `<a href="${f.booking_url}" target="_blank" rel="noopener" class="flight-card__buy" onclick="event.stopPropagation()">\u041a\u0443\u043f\u0438\u0442\u044c</a>` : ''))}
            </div>
        `;
        card.appendChild(mainRow);

        // History accordion (collapsible, all closed by default unless saved in localStorage)
        const hasHistory = f.price_history && f.price_history.length > 0;
        const histIsOpen = openSet.has(flightId);

        const histToggle = document.createElement('div');
        histToggle.className = 'flight-card__hist-toggle' + (histIsOpen ? ' flight-card__hist-toggle--open' : '');

        if (hasHistory) {
            histToggle.innerHTML = `<span class="flight-card__hist-arrow">\u25BC</span> \u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0446\u0435\u043d (${f.price_history.length})`;
        } else {
            histToggle.innerHTML = `<span class="flight-card__no-changes">\u0426\u0435\u043d\u0430 \u043d\u0435 \u043c\u0435\u043d\u044f\u043b\u0430\u0441\u044c</span>`;
        }
        card.appendChild(histToggle);

        if (hasHistory) {
            const histBody = document.createElement('div');
            histBody.className = 'flight-card__hist-body' + (histIsOpen ? ' flight-card__hist-body--open' : '');

            const table = document.createElement('table');
            table.className = 'history-table';
            table.innerHTML = '<thead><tr><th>\u0414\u0430\u0442\u0430</th><th>\u0411\u044b\u043b\u0430</th><th>\u0421\u0442\u0430\u043b\u0430</th><th>\u0418\u0437\u043c.</th></tr></thead>';
            const tbody = document.createElement('tbody');

            const VISIBLE_COUNT = 3;
            f.price_history.forEach((h, hIdx) => {
                const diff = h.new - h.old;
                const diffSign = diff < 0 ? '\u2193' : '\u2191';
                const diffClass = diff < 0 ? 'history-down' : 'history-up';
                const tr = document.createElement('tr');
                if (hIdx >= VISIBLE_COUNT) {
                    tr.classList.add('history-table__row--hidden');
                }
                tr.innerHTML = `
                    <td class="history-date">${formatDateTime(h.at)}</td>
                    <td>${formatPrice(h.old)}</td>
                    <td>${formatPrice(h.new)}</td>
                    <td class="${diffClass}">${diffSign} ${formatPrice(Math.abs(diff))}</td>
                `;
                tbody.appendChild(tr);
            });
            table.appendChild(tbody);
            histBody.appendChild(table);

            if (f.price_history.length > VISIBLE_COUNT) {
                const moreToggle = document.createElement('a');
                moreToggle.className = 'history-table__toggle';
                moreToggle.href = '#';
                moreToggle.textContent = `\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0432\u0441\u0435 (${f.price_history.length})`;
                let expanded = false;
                moreToggle.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    expanded = !expanded;
                    tbody.querySelectorAll('.history-table__row--hidden').forEach(row => {
                        row.classList.toggle('history-table__row--shown', expanded);
                    });
                    moreToggle.textContent = expanded
                        ? '\u0421\u043a\u0440\u044b\u0442\u044c'
                        : `\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0432\u0441\u0435 (${f.price_history.length})`;
                });
                histBody.appendChild(moreToggle);
            }

            card.appendChild(histBody);

            // Toggle history on click
            histToggle.addEventListener('click', () => {
                histBody.classList.toggle('flight-card__hist-body--open');
                histToggle.classList.toggle('flight-card__hist-toggle--open');
                // Save open state to localStorage
                if (histBody.classList.contains('flight-card__hist-body--open')) {
                    openSet.add(flightId);
                } else {
                    openSet.delete(flightId);
                }
                try { localStorage.setItem(storageKey, JSON.stringify([...openSet])); } catch {}
            });
        }

        body.appendChild(card);
    });

    overlay.classList.add('modal-overlay--open');
}

function closeModal() {
    document.getElementById('modalOverlay').classList.remove('modal-overlay--open');
}

function flightSuffix(n) {
    if (n === 1) return '';
    if (n >= 2 && n <= 4) return '\u0430';
    return '\u043e\u0432';
}

function updateLastUpdateLabel(isoStr) {
    const el = document.getElementById('lastUpdate');
    if (!el) return;
    if (!isoStr) {
        el.textContent = '\u041e\u0436\u0438\u0434\u0430\u043d\u0438\u0435 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f...';
        return;
    }
    try {
        const d = new Date(isoStr);
        el.textContent = `\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e: ${d.toLocaleTimeString('ru-RU')}`;
    } catch {
        el.textContent = `\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e: ${isoStr}`;
    }
}

function startAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(async () => {
        try {
            const resp = await fetch('/api/last_update');
            const data = await resp.json();
            if (data.last_update && data.last_update !== lastUpdateTs) {
                lastUpdateTs = data.last_update;
                loadCalendar();
            }
        } catch (err) {
            console.error('Auto-refresh error:', err);
        }
    }, 5000);
}
