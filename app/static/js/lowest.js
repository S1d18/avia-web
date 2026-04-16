/* Минимум за месяц — historical lowest price per day */

const MONTHS_LOW = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
];
const WEEKDAYS_LOW = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

let lowOrigin = '';
let lowDest = '';
let lowYear = 0;
let lowMonth = 0;

document.addEventListener('DOMContentLoaded', () => {
    const page = document.querySelector('.lowest-page');
    if (!page) return;

    lowOrigin = page.dataset.origin;
    lowDest = page.dataset.destination;

    const now = new Date();
    lowYear = now.getFullYear();
    lowMonth = now.getMonth() + 1;

    document.getElementById('prevMonth').addEventListener('click', () => {
        lowMonth--;
        if (lowMonth < 1) { lowMonth = 12; lowYear--; }
        loadLowest();
    });
    document.getElementById('nextMonth').addEventListener('click', () => {
        lowMonth++;
        if (lowMonth > 12) { lowMonth = 1; lowYear++; }
        loadLowest();
    });

    loadLowest();
});

function lowMonthKey() {
    return `${lowYear}-${String(lowMonth).padStart(2, '0')}`;
}

async function loadLowest() {
    document.getElementById('monthLabel').textContent = `${MONTHS_LOW[lowMonth - 1]} ${lowYear}`;

    const grid = document.getElementById('calendarGrid');
    grid.innerHTML = '<div class="calendar-loading">Загрузка...</div>';

    try {
        const resp = await fetch(`/api/lowest/${lowOrigin}/${lowDest}?month=${lowMonthKey()}`);
        const data = await resp.json();
        renderLowest(data);

        const upd = document.getElementById('lastUpdate');
        if (data.last_update) {
            const d = new Date(data.last_update);
            upd.textContent = `Обновлено: ${d.toLocaleTimeString('ru-RU')}`;
        } else {
            upd.textContent = 'Ожидание обновления...';
        }
    } catch (err) {
        grid.innerHTML = '<div class="calendar-loading">Ошибка загрузки</div>';
        console.error(err);
    }
}

function renderLowest(data) {
    const grid = document.getElementById('calendarGrid');
    grid.innerHTML = '';

    WEEKDAYS_LOW.forEach(wd => {
        const el = document.createElement('div');
        el.className = 'cal-weekday';
        el.textContent = wd;
        grid.appendChild(el);
    });

    const firstDay = new Date(lowYear, lowMonth - 1, 1);
    let startDow = firstDay.getDay();
    startDow = startDow === 0 ? 6 : startDow - 1;

    const daysInMonth = new Date(lowYear, lowMonth, 0).getDate();
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const { days, price_range } = data;
    const pMin = price_range.min || 0;
    const pMax = price_range.max || 0;
    const pRange = pMax - pMin;

    for (let i = 0; i < startDow; i++) {
        const el = document.createElement('div');
        el.className = 'cal-cell cal-cell--empty';
        grid.appendChild(el);
    }

    for (let d = 1; d <= daysInMonth; d++) {
        const dateKey = `${lowYear}-${String(lowMonth).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        const cellDate = new Date(lowYear, lowMonth - 1, d);
        const dayData = days[dateKey];
        const isPast = cellDate < today;

        const cell = document.createElement('div');
        cell.className = 'cal-cell';
        if (isPast) cell.classList.add('cal-cell--past');

        const dayEl = document.createElement('div');
        dayEl.className = 'cal-cell__day';
        dayEl.textContent = d;
        cell.appendChild(dayEl);

        if (dayData) {
            const tier = lowTier(dayData.min_price, pMin, pRange);
            cell.classList.add(`cal-cell--${tier}`);

            const priceEl = document.createElement('div');
            priceEl.className = `cal-cell__price cal-cell__price--${tier}`;
            priceEl.textContent = lowFormatPrice(dayData.min_price);
            cell.appendChild(priceEl);

            const meta = document.createElement('div');
            meta.className = 'cal-cell__hist-meta';
            const obs = lowFormatDate(dayData.observed_at);
            const air = dayData.airline_name || dayData.airline || '';
            meta.textContent = `от ${obs} • ${air}`;
            meta.title = `${air} ${dayData.flight_number || ''}\nМинимум зафиксирован: ${lowFormatDateTime(dayData.observed_at)}`;
            cell.appendChild(meta);
        } else {
            const noData = document.createElement('div');
            noData.className = 'cal-cell__price';
            noData.style.color = 'var(--text-muted)';
            noData.textContent = '—';
            cell.appendChild(noData);
        }

        grid.appendChild(cell);
    }
}

function lowTier(price, pMin, pRange) {
    if (pRange === 0) return 'low';
    const ratio = (price - pMin) / pRange;
    if (ratio < 0.33) return 'low';
    if (ratio < 0.66) return 'mid';
    return 'high';
}

function lowFormatPrice(p) {
    return p.toLocaleString('ru-RU') + ' \u20BD';
}

function lowFormatDate(isoStr) {
    if (!isoStr) return '—';
    try {
        const d = new Date(isoStr);
        const dd = String(d.getDate()).padStart(2, '0');
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        return `${dd}.${mm}`;
    } catch { return '—'; }
}

function lowFormatDateTime(isoStr) {
    if (!isoStr) return '—';
    try {
        const d = new Date(isoStr);
        return d.toLocaleString('ru-RU', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    } catch { return isoStr; }
}
