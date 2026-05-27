const MESES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
               'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
const DIAS_PT = ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'];

function dbToColor(value) {
  if (value === null || value === undefined) return null;
  const min = 40, max = 70;
  const ratio = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const hue = (1 - ratio) * 120;
  const sat = 70 + ratio * 10;
  const lig = 38 - ratio * 6;
  return `hsl(${hue.toFixed(0)}, ${sat.toFixed(0)}%, ${lig.toFixed(0)}%)`;
}

function formatWeekLabel(startDate, endDate) {
  const fmt = d => `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}`;
  return `${fmt(startDate)} – ${fmt(endDate)}`;
}

function renderCalendar(dias, param) {
  const body  = document.getElementById('calBody');
  const empty = document.getElementById('emptyMsg');
  body.innerHTML = '';

  const byDate = {};
  dias.forEach(d => { byDate[d.date] = d; });

  const hasAny = dias.some(d => d.has_data);
  if (!hasAny) { empty.classList.remove('d-none'); return; }
  empty.classList.add('d-none');

  // Find the Sunday of the week containing the first day
  const firstDay = new Date(dias[0].date + 'T00:00:00');
  const lastDay  = new Date(dias[dias.length - 1].date + 'T00:00:00');

  const weekStart = new Date(firstDay);
  weekStart.setDate(firstDay.getDate() - firstDay.getDay()); // go back to Sunday

  const current = new Date(weekStart);

  while (current <= lastDay) {
    const tr = document.createElement('tr');

    // Week label (Sun – Sat)
    const weekEnd = new Date(current);
    weekEnd.setDate(current.getDate() + 6);
    const tdLabel = document.createElement('td');
    tdLabel.className = 'week-label';
    tdLabel.textContent = formatWeekLabel(current, weekEnd);
    tr.appendChild(tdLabel);

    for (let d = 0; d < 7; d++) {
      const date = new Date(current);
      date.setDate(current.getDate() + d);
      const dateStr = date.toISOString().split('T')[0];
      const td = document.createElement('td');
      td.className = 'cal-cell';

      const info = byDate[dateStr];
      if (info && info.has_data && info[param] !== null) {
        const val = info[param];
        td.textContent = val.toFixed(1);
        td.style.backgroundColor = dbToColor(val);
        td.title = `${dateStr}: ${val.toFixed(1)} dB`;
      } else if (!info || date < firstDay || date > lastDay) {
        td.classList.add('other-month');
      } else {
        td.classList.add('no-data');
        td.textContent = '—';
      }

      tr.appendChild(td);
    }

    body.appendChild(tr);
    current.setDate(current.getDate() + 7);
  }
}

function atualizarResumo(dias, param) {
  const box = document.getElementById('resumoBox');
  const vals = dias.filter(d => d.has_data && d[param] !== null).map(d => ({date: d.date, val: d[param]}));

  if (!vals.length) { box.classList.add('d-none'); return; }
  box.classList.remove('d-none');

  const values = vals.map(v => v.val);
  const mean10 = values.reduce((s, v) => s + Math.pow(10, v / 10), 0) / values.length;
  const media  = (10 * Math.log10(mean10)).toFixed(1);

  const maxItem = vals.reduce((a, b) => b.val > a.val ? b : a);
  const minItem = vals.reduce((a, b) => b.val < a.val ? b : a);

  document.getElementById('resumoMedia').textContent = `${media} dB`;
  document.getElementById('resumoMax').textContent   = `${maxItem.date.slice(5).replace('-','/')} (${maxItem.val} dB)`;
  document.getElementById('resumoMin').textContent   = `${minItem.date.slice(5).replace('-','/')} (${minItem.val} dB)`;
  document.getElementById('resumoDias').textContent  = `${vals.length} / ${dias.length}`;
}

async function atualizarCalendario() {
  const sensor = document.getElementById('sensorSelect').value;
  const mes    = parseInt(document.getElementById('mesSelect').value);
  const ano    = parseInt(document.getElementById('anoSelect').value);
  const param  = document.getElementById('paramSelect').value;

  if (!sensor || isNaN(mes) || isNaN(ano)) return;

  const start = `${ano}-${String(mes).padStart(2,'0')}-01`;
  const daysInMonth = new Date(ano, mes, 0).getDate();
  const end   = `${ano}-${String(mes).padStart(2,'0')}-${String(daysInMonth).padStart(2,'0')}`;

  document.getElementById('loadingMsg').classList.remove('d-none');
  document.getElementById('calendarWrap').style.opacity = '0.4';

  try {
    const res  = await fetch(`/api/calendario?start=${start}&end=${end}&sensor_id=${sensor}`);
    const data = await res.json();

    document.getElementById('calendarTitle').textContent =
      `${MESES[mes - 1]} ${ano} — ${document.getElementById('paramSelect').selectedOptions[0].text}`;

    renderCalendar(data.dias, param);
    atualizarResumo(data.dias, param);
  } catch (err) {
    console.error('Erro ao carregar calendário:', err);
  } finally {
    document.getElementById('loadingMsg').classList.add('d-none');
    document.getElementById('calendarWrap').style.opacity = '1';
  }
}

function inicializarSeletores() {
  const now = new Date();
  const mesEl = document.getElementById('mesSelect');
  const anoEl = document.getElementById('anoSelect');

  MESES.forEach((m, i) => {
    const opt = document.createElement('option');
    opt.value = i + 1;
    opt.textContent = m;
    if (i + 1 === now.getMonth() + 1) opt.selected = true;
    mesEl.appendChild(opt);
  });

  for (let y = now.getFullYear(); y >= now.getFullYear() - 3; y--) {
    const opt = document.createElement('option');
    opt.value = y;
    opt.textContent = y;
    if (y === now.getFullYear()) opt.selected = true;
    anoEl.appendChild(opt);
  }
}

window.onload = () => {
  inicializarSeletores();
  carregarSensores('sensorSelect', atualizarCalendario);
};
