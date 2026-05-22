function getSelectedSensors() {
  const select = document.getElementById('sensorSelect');
  return Array.from(select.selectedOptions).map(opt => opt.value);
}

async function calcularLden() {
  const end = document.getElementById('endDate').value;
  const sensors = getSelectedSensors();
  if (!end || sensors.length !== 1) return;

  const sensor = sensors[0];
  const endDate = new Date(end);
  const startDate = new Date(endDate);
  startDate.setUTCDate(endDate.getDate() - 1);
  startDate.setUTCHours(0, 0, 0, 0);
  const finishDate = new Date(endDate);
  finishDate.setUTCDate(endDate.getDate() - 1);
  finishDate.setUTCHours(23, 59, 59, 999);

  const diasSemana = ['Domingo','Segunda','Terça','Quarta','Quinta','Sexta','Sábado'];
  const nomeDia = diasSemana[startDate.getDay()];
  const dia = String(startDate.getDate()).padStart(2, '0');
  const mes = String(startDate.getMonth() + 1).padStart(2, '0');
  const ano = startDate.getFullYear();
  document.getElementById('diaAnterior').textContent = `${nomeDia}, ${dia}/${mes}/${ano}`;

  fetch(`/api/lden?start=${startDate.toISOString()}&end=${finishDate.toISOString()}&sensor_id=${sensor}`)
    .then(resp => resp.json())
    .then(ldens => {
      const Lday = ldens.laeq_day;
      const Levening = ldens.laeq_evening;
      const Lnight = ldens.laeq_night;

      document.getElementById('laeqDay').textContent     = Lday     ? Lday.toFixed(1)     + ' dB' : '- dB';
      document.getElementById('laeqEvening').textContent = Levening ? Levening.toFixed(1) + ' dB' : '- dB';
      document.getElementById('laeqNight').textContent   = Lnight   ? Lnight.toFixed(1)   + ' dB' : '- dB';

      if (Lday && Levening && Lnight) {
        const Lden = 10 * Math.log10(
          (1 / 24) * (
            12 * Math.pow(10, Lday / 10) +
             4 * Math.pow(10, (Levening + 5) / 10) +
             8 * Math.pow(10, (Lnight + 10) / 10)
          )
        );
        document.getElementById('lden').textContent = Lden.toFixed(1) + ' dB';
      } else {
        document.getElementById('lden').textContent = '- dB';
      }
    });
}

function calcularEstatisticas() {
  const start = document.getElementById('startDate').value;
  const end   = document.getElementById('endDate').value;
  const sensors = getSelectedSensors();
  if (!start || !end || sensors.length !== 1) return;

  const isoStart = new Date(start).toISOString();
  const isoEnd   = new Date(end).toISOString();
  const sensor   = sensors[0];

  const setEmptyStats = () => {
    ['laeq','lcpeak','lafmax','lafmin','la50','la95'].forEach(id => {
      document.getElementById(id).textContent = '- dB';
    });
    Plotly.purge('kdeChart');
  };

  fetch(`/api/stats?start=${isoStart}&end=${isoEnd}&sensor_id=${sensor}`)
    .then(res => res.json())
    .then(data => {
      const laeaValues  = (data.laea   || []).map(e => e.value).filter(v => typeof v === 'number');
      const lcpeakValues= (data.lcpeak || []).map(e => e.value).filter(v => typeof v === 'number');
      const lafmaxValues= (data.lafmax || []).map(e => e.value).filter(v => typeof v === 'number');
      const lafminValues= (data.lafmin || []).map(e => e.value).filter(v => typeof v === 'number');

      if (!laeaValues.length) return setEmptyStats();

      const max = arr => Math.max(...arr);
      const min = arr => Math.min(...arr);
      const percentile = (arr, p) => {
        const sorted = [...arr].sort((a, b) => a - b);
        const i = (p / 100) * (sorted.length - 1);
        const lower = Math.floor(i), upper = Math.ceil(i);
        return sorted[lower] * (1 - (i - lower)) + sorted[upper] * (i - lower);
      };

      const laeq = 10 * Math.log10(
        laeaValues.reduce((sum, v) => sum + Math.pow(10, v / 10), 0) / laeaValues.length
      );
      document.getElementById('laeq').textContent   = laeq.toFixed(1) + ' dB';
      document.getElementById('lcpeak').textContent = lcpeakValues.length ? max(lcpeakValues).toFixed(1) + ' dB' : '- dB';
      document.getElementById('lafmax').textContent = lafmaxValues.length ? max(lafmaxValues).toFixed(1) + ' dB' : '- dB';
      document.getElementById('lafmin').textContent = lafminValues.length ? min(lafminValues).toFixed(1) + ' dB' : '- dB';
      document.getElementById('la50').textContent   = percentile(laeaValues, 50).toFixed(1) + ' dB';
      document.getElementById('la95').textContent   = percentile(laeaValues, 10).toFixed(1) + ' dB';
      atualizarKDE(laeaValues);
    })
    .catch(err => { console.error('Erro ao buscar estatísticas:', err); setEmptyStats(); });
}

function atualizarKDE(data) {
  if (!data.length) { Plotly.purge('kdeChart'); return; }

  function kde(xs, bandwidth, points) {
    const mn = Math.min(...xs), mx = Math.max(...xs);
    const step = (mx - mn) / points;
    const kernel = x => v => (1 / Math.sqrt(2 * Math.PI)) * Math.exp(-0.5 * Math.pow((x - v) / bandwidth, 2));
    const density = [];
    for (let i = 0; i <= points; i++) {
      const x = mn + i * step;
      const sum = xs.map(kernel(x)).reduce((a, b) => a + b, 0);
      density.push({ x, y: sum / (xs.length * bandwidth) });
    }
    return density;
  }

  const kdeData = kde(data, 1.0, 100);
  Plotly.newPlot('kdeChart', [{
    x: kdeData.map(d => d.x),
    y: kdeData.map(d => d.y),
    type: 'scatter', mode: 'lines',
    name: 'Densidade (KDE)',
    line: { color: '#e74c3c', width: 3 }
  }], {
    margin: { t: 30, r: 20, b: 40, l: 50 },
    xaxis: { title: 'LAF (dB)', color: '#fff', showgrid: false, zeroline: false },
    yaxis: { title: 'Densidade', color: '#fff', showgrid: false, zeroline: false },
    plot_bgcolor: '#111217', paper_bgcolor: '#111217',
    font: { color: '#fff' }, showlegend: true
  }, { responsive: true });
}

function atualizarGrafico() {
  const start = document.getElementById('startDate').value;
  const end   = document.getElementById('endDate').value;
  const from  = start ? new Date(start).getTime() : 'now-5m';
  const to    = end   ? new Date(end).getTime()   : 'now';
  const sensors = getSelectedSensors();
  const showComparativo = sensors.length > 1;

  document.getElementById('graficoContainer').style.display   = showComparativo ? 'none'  : 'block';
  document.getElementById('multiSensorGrafico').style.display = showComparativo ? 'block' : 'none';
  document.getElementById('parametroBox').classList.toggle('d-none', !showComparativo);
  document.getElementById('statsBox').classList.toggle('d-none', sensors.length !== 1);

  if (showComparativo) {
    const parametro = document.getElementById('parametroSelect').value;
    const sensorParams = sensors.map(s => `var-sensorName=${encodeURIComponent(s)}`).join('&');
    document.getElementById('graficoComparativo').src = buildGrafanaURL(12, from, to, sensorParams, `&var-param=${parametro}`);
    Plotly.purge('kdeChart');
    ['laeq','lcpeak','lafmax','lafmin','la50','la95'].forEach(id => {
      document.getElementById(id).textContent = '- dB';
    });
  } else {
    const sp = `var-sensorName=${sensors[0]}`;
    document.getElementById('graficoLAEA').src  = buildGrafanaURL(1,  from, to, sp);
    document.getElementById('NvlFreq').src      = buildGrafanaURL(15, from, to, sp);
    document.getElementById('Espectogram').src  = buildGrafanaURL(16, from, to, sp);
    document.getElementById('Eventos').src      = buildGrafanaURL(13, from, to, sp);
    calcularEstatisticas();
    calcularLden();
  }
}

function downloadCSV() {
  const start = document.getElementById('startDate').value;
  const end   = document.getElementById('endDate').value;
  const sensors = getSelectedSensors();
  if (!start || !end || sensors.length !== 1) {
    alert('Por favor seleciona um único sensor e datas válidas.');
    return;
  }
  window.location.href = `/api/download?start=${new Date(start).toISOString()}&end=${new Date(end).toISOString()}&sensor_id=${sensors[0]}`;
}

window.onload = () => {
  carregarSensores('sensorSelect', atualizarGrafico);
  const now = new Date();
  const fiveMinAgo = new Date(now.getTime() - 5 * 60 * 1000);
  document.getElementById('endDate').value   = formatDatetimeLocal(now);
  document.getElementById('startDate').value = formatDatetimeLocal(fiveMinAgo);

  document.getElementById('parametroSelect').addEventListener('change', atualizarGrafico);
  document.getElementById('sensorSelect').addEventListener('change', atualizarGrafico);
  document.getElementById('startDate').addEventListener('change', atualizarGrafico);
  document.getElementById('endDate').addEventListener('change', () => { atualizarGrafico(); calcularEstatisticas(); });
};
