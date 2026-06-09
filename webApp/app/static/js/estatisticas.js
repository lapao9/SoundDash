const MESES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
               'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
const DIAS_PT = ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'];

let vistaAtual      = 'mensal';
let semanalCache    = null;
let showEventos     = false;
let graficoChart = null;

// ── Color helpers ──────────────────────────────────────────────────────────

function dbToColor(value) {
  if (value === null || value === undefined) return null;
  const min = 40, max = 55;
  const ratio = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const hue = (1 - ratio) * 120;
  const sat = 70 + ratio * 10;
  const lig = 38 - ratio * 6;
  return `hsl(${hue.toFixed(0)}, ${sat.toFixed(0)}%, ${lig.toFixed(0)}%)`;
}

// ── Vista toggle ───────────────────────────────────────────────────────────

function setVista(vista) {
  vistaAtual = vista;

  const isMensal = vista === 'mensal';

  document.getElementById('periodoMensal').classList.toggle('d-none', !isMensal);
  document.getElementById('periodoSemanal').classList.toggle('d-none', isMensal);
  document.getElementById('calendarWrap').classList.toggle('d-none', !isMensal);
  document.getElementById('semanalWrap').classList.toggle('d-none', isMensal);
  document.getElementById('resumoBox').classList.toggle('d-none', true);

  document.getElementById('btnMensal').className  = isMensal ? 'btn btn-primary btn-sm'         : 'btn btn-outline-primary btn-sm';
  document.getElementById('btnSemanal').className = isMensal ? 'btn btn-outline-primary btn-sm' : 'btn btn-primary btn-sm';
}

// ── Loading state ──────────────────────────────────────────────────────────

function setLoading(on) {
  document.getElementById('loadingMsg').classList.toggle('d-none', !on);
  const wrap = vistaAtual === 'mensal'
    ? document.getElementById('calendarWrap')
    : document.getElementById('semanalWrap');
  wrap.style.opacity = on ? '0.4' : '1';
}

// ── Monthly calendar ───────────────────────────────────────────────────────

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

  const firstDay = new Date(dias[0].date + 'T00:00:00');
  const lastDay  = new Date(dias[dias.length - 1].date + 'T00:00:00');

  const weekStart = new Date(firstDay);
  weekStart.setDate(firstDay.getDate() - firstDay.getDay());

  const current = new Date(weekStart);

  while (current <= lastDay) {
    const tr = document.createElement('tr');

    const weekEnd = new Date(current);
    weekEnd.setDate(current.getDate() + 6);
    const tdLabel = document.createElement('td');
    tdLabel.className = 'week-label';
    tdLabel.textContent = formatWeekLabel(current, weekEnd);
    tr.appendChild(tdLabel);

    for (let d = 0; d < 7; d++) {
      const date = new Date(current);
      date.setDate(current.getDate() + d);
      const dateStr = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
      const td = document.createElement('td');
      td.className = 'cal-cell';

      const info = byDate[dateStr];
      const isTurno = ['turno1','turno2','turno3'].includes(param);

      if (info && info.has_data && info[param] !== null) {
        if (isTurno) {
          td.classList.add('turno-cell');
          td.style.backgroundColor = dbToColor(info[param]);
          const labels = ['T1 (00-08h)','T2 (08-16h)','T3 (16-00h)'];
          const keys   = ['turno1','turno2','turno3'];
          td.innerHTML = '<div class="turno-cell-inner">' + keys.map((k, i) => {
            const v = info[k];
            const bold = k === param ? ' style="font-weight:900"' : '';
            return `<span class="turno-row"${bold}>${labels[i]} ${v !== null ? v.toFixed(1) : '—'}</span>`;
          }).join('') + '</div>';
          td.title = `${dateStr} — T1: ${info.turno1??'—'} / T2: ${info.turno2??'—'} / T3: ${info.turno3??'—'} dB`;
        } else {
          const val = info[param];
          td.textContent = val.toFixed(1);
          td.style.backgroundColor = dbToColor(val);
          td.title = `${dateStr}: ${val.toFixed(1)} dB`;
        }
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

function atualizarTurnos(dias) {
  const box = document.getElementById('turnosBox');
  const withData = dias.filter(d => d.has_data);
  if (!withData.length) { box.classList.add('d-none'); return; }

  function energyAvg(vals) {
    if (!vals.length) return null;
    return 10 * Math.log10(vals.reduce((s, v) => s + Math.pow(10, v / 10), 0) / vals.length);
  }

  const t1 = energyAvg(withData.filter(d => d.turno1 !== null).map(d => d.turno1));
  const t2 = energyAvg(withData.filter(d => d.turno2 !== null).map(d => d.turno2));
  const t3 = energyAvg(withData.filter(d => d.turno3 !== null).map(d => d.turno3));

  const fmt = v => v !== null ? v.toFixed(1) + ' dB' : '—';
  document.getElementById('turnoT1').textContent = fmt(t1);
  document.getElementById('turnoT2').textContent = fmt(t2);
  document.getElementById('turnoT3').textContent = fmt(t3);
  box.classList.remove('d-none');
}

function atualizarLden(dias) {
  const box = document.getElementById('ldenBox');
  const withData = dias.filter(d => d.has_data);
  if (!withData.length) { box.classList.add('d-none'); return; }

  function energyAvg(vals) {
    if (!vals.length) return null;
    const sum = vals.reduce((s, v) => s + Math.pow(10, v / 10), 0);
    return 10 * Math.log10(sum / vals.length);
  }

  // Use official Ld/Le/Ln fields from backend (07-19h, 19-23h, 23-07h)
  const ldVals = withData.filter(d => d.ld !== null && d.ld !== undefined).map(d => d.ld);
  const leVals = withData.filter(d => d.le !== null && d.le !== undefined).map(d => d.le);
  const lnVals = withData.filter(d => d.ln !== null && d.ln !== undefined).map(d => d.ln);

  const Ld = energyAvg(ldVals);
  const Le = energyAvg(leVals);
  const Ln = energyAvg(lnVals);

  let Lden = null;
  if (Ld !== null && Le !== null && Ln !== null) {
    // Official EU formula: 12h day + 4h evening (+5dB) + 8h night (+10dB)
    Lden = 10 * Math.log10(
      (12 * Math.pow(10, Ld / 10) + 4 * Math.pow(10, (Le + 5) / 10) + 8 * Math.pow(10, (Ln + 10) / 10)) / 24
    );
  }

  document.getElementById('ldenLd').textContent   = Ld   !== null ? Ld.toFixed(1)   + ' dB' : '—';
  document.getElementById('ldenLe').textContent   = Le   !== null ? Le.toFixed(1)   + ' dB' : '—';
  document.getElementById('ldenLn').textContent   = Ln   !== null ? Ln.toFixed(1)   + ' dB' : '—';
  document.getElementById('ldenLden').textContent = Lden !== null ? Lden.toFixed(1) + ' dB' : '—';
  box.classList.remove('d-none');
}

function renderGrafico(dias) {
  const wrap = document.getElementById('graficoWrap');
  const withData = dias.filter(d => d.has_data && d.laeq !== null);
  if (!withData.length) { wrap.classList.add('d-none'); return; }
  wrap.classList.remove('d-none');

  const labels   = withData.map(d => d.date.slice(5).replace('-', '/'));
  const laeqData = withData.map(d => d.laeq);
  const lcData   = withData.map(d => d.lcpeak);

  if (graficoChart) { graficoChart.destroy(); graficoChart = null; }

  const datasets = [
    {
      type: 'bar', label: 'LAeq (dB)', data: laeqData,
      backgroundColor: 'rgba(41,128,185,0.75)', borderRadius: 3, yAxisID: 'y'
    },
    {
      type: 'bar', label: 'LCpeak (dB)', data: lcData,
      backgroundColor: 'rgba(231,76,60,0.75)', borderRadius: 3, yAxisID: 'y'
    }
  ];

  const ctx = document.getElementById('graficoCanvas').getContext('2d');
  graficoChart = new Chart(ctx, {
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top', labels: { font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y !== null ? ctx.parsed.y.toFixed(1) + ' dB' : '—'}`
          }
        }
      },
      scales: {
        y: { title: { display: true, text: 'dB', font: { size: 11 } }, beginAtZero: false }
      }
    }
  });
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
  document.getElementById('resumoMax').textContent   = `${maxItem.date.slice(5).replace('-','/')} (${maxItem.val.toFixed(1)} dB)`;
  document.getElementById('resumoMin').textContent   = `${minItem.date.slice(5).replace('-','/')} (${minItem.val.toFixed(1)} dB)`;
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

  setLoading(true);

  try {
    const res  = await fetch(`/api/calendario?start=${start}&end=${end}&sensor_id=${sensor}`);
    const data = await res.json();

    document.getElementById('calendarTitle').textContent =
      `${MESES[mes - 1]} ${ano} — ${document.getElementById('paramSelect').selectedOptions[0].text}`;

    renderCalendar(data.dias, param);
    atualizarResumo(data.dias, param);
    atualizarTurnos(data.dias);
    atualizarLden(data.dias);
    renderGrafico(data.dias);
  } catch (err) {
    console.error('Erro ao carregar calendário:', err);
  } finally {
    setLoading(false);
  }
}

// ── Weekly tables ──────────────────────────────────────────────────────────

function buildDayHeaders(days, headId) {
  const tr = document.getElementById(headId);
  // Remove all th except the first (row label)
  while (tr.children.length > 1) tr.removeChild(tr.lastChild);

  days.forEach(dateStr => {
    const date = new Date(dateStr + 'T00:00:00');
    const th = document.createElement('th');
    th.innerHTML = `<span class="day-name">${DIAS_PT[date.getDay()]}</span><br><span class="day-date">${String(date.getDate()).padStart(2,'0')}/${String(date.getMonth()+1).padStart(2,'0')}</span>`;
    tr.appendChild(th);
  });
}

function makeCell(cellData) {
  const td = document.createElement('td');
  td.className = 'cal-cell semanal-cell';

  if (!cellData || cellData.laeq === null) {
    td.classList.add('no-data');
    td.innerHTML = '<span class="cell-laeq">—</span>';
    return td;
  }

  const color = dbToColor(cellData.laeq);
  if (color) td.style.backgroundColor = color;

  const lcText = cellData.lcpeak !== null ? cellData.lcpeak.toFixed(1) : '—';
  const evCount = cellData.events ?? 0;

  let evHtml = '';
  if (showEventos) {
    td.classList.add('with-events');
    evHtml = `<div class="cell-divider"></div><div class="cell-events">${evCount > 0 ? evCount + ' ev' : '—'}</div>`;
  }

  td.innerHTML = `<div class="cell-inner"><div class="cell-half">${cellData.laeq.toFixed(1)}</div><div class="cell-divider"></div><div class="cell-half">${lcText}</div>${evHtml}</div>`;
  td.title = `LAeq: ${cellData.laeq.toFixed(1)} dB  |  LCpeak: ${lcText} dB  |  Eventos: ${evCount}`;
  return td;
}

function renderWeeklyHoras(data) {
  buildDayHeaders(data.days, 'headHoras');

  const body = document.getElementById('bodyHoras');
  body.innerHTML = '';

  data.horas.forEach(row => {
    const tr = document.createElement('tr');
    const tdLabel = document.createElement('td');
    tdLabel.className = 'row-label';
    tdLabel.textContent = row.label;
    tr.appendChild(tdLabel);

    data.days.forEach(dateStr => {
      tr.appendChild(makeCell(row.data[dateStr] || null));
    });

    body.appendChild(tr);
  });
}

function renderWeeklyTurnos(data) {
  buildDayHeaders(data.days, 'headTurnos');

  const body = document.getElementById('bodyTurnos');
  body.innerHTML = '';

  data.turnos.forEach(row => {
    const tr = document.createElement('tr');
    const tdLabel = document.createElement('td');
    tdLabel.className = 'row-label';
    tdLabel.textContent = row.label;
    tr.appendChild(tdLabel);

    data.days.forEach(dateStr => {
      tr.appendChild(makeCell(row.data[dateStr] || null));
    });

    body.appendChild(tr);
  });
}

async function atualizarSemanal() {
  const sensor  = document.getElementById('sensorSelect').value;
  const dateVal = document.getElementById('weekDateInput').value;

  if (!sensor || !dateVal) return;

  const empty = document.getElementById('emptySemanal');
  empty.classList.add('d-none');
  setLoading(true);

  try {
    const res  = await fetch(`/api/semanal?start=${dateVal}&sensor_id=${sensor}`);
    const data = await res.json();

    semanalCache = data;

    const fmt = d => `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}`;
    const ws = new Date(data.week_start + 'T00:00:00');
    const we = new Date(data.week_end   + 'T00:00:00');
    document.getElementById('semanalTitle').textContent =
      `Semana ${fmt(ws)} – ${fmt(we)}`;

    const hasAny = data.horas.some(h => Object.values(h.data).some(c => c && c.laeq !== null));
    if (!hasAny) {
      empty.classList.remove('d-none');
    } else {
      renderWeeklyHoras(data);
      renderWeeklyTurnos(data);
    }
  } catch (err) {
    console.error('Erro ao carregar semanal:', err);
  } finally {
    setLoading(false);
  }
}

function toggleEventos() {
  showEventos = document.getElementById('checkEventos').checked;
  if (semanalCache) {
    renderWeeklyHoras(semanalCache);
    renderWeeklyTurnos(semanalCache);
  }
}

// ── Init ───────────────────────────────────────────────────────────────────

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

  // Pre-fill week date picker with today
  const pad = n => String(n).padStart(2, '0');
  document.getElementById('weekDateInput').value =
    `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}`;
}

window.onload = () => {
  inicializarSeletores();
  carregarSensores('sensorSelect', atualizarCalendario);
};
