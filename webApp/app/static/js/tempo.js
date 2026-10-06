function getSelectedSensors() {
  const select = document.getElementById('sensorSelect');
  return Array.from(select.selectedOptions).map(opt => opt.value);
}

async function calcularLden() {
  const end = document.getElementById('endDate').value;
  const sensors = getSelectedSensors();
  if (!end || sensors.length !== 1) return;

  const sensor = sensors[0];
  // Dia anterior à data final, em hora local (o backend interpreta a data como dia de Lisboa)
  const startDate = new Date(end);
  startDate.setDate(startDate.getDate() - 1);

  const diasSemana = ['Domingo','Segunda','Terça','Quarta','Quinta','Sexta','Sábado'];
  const nomeDia = diasSemana[startDate.getDay()];
  const dia = String(startDate.getDate()).padStart(2, '0');
  const mes = String(startDate.getMonth() + 1).padStart(2, '0');
  const ano = startDate.getFullYear();
  document.getElementById('diaAnterior').textContent = `${nomeDia}, ${dia}/${mes}/${ano}`;

  fetch(`/api/lden?start=${ano}-${mes}-${dia}&sensor_id=${sensor}`)
    .then(resp => resp.json())
    .then(d => {
      const fmt = v => v !== null && v !== undefined ? v.toFixed(1) + ' dB' : '—';
      // Turnos hospitalares
      document.getElementById('laeqNight').textContent   = fmt(d.turno1);
      document.getElementById('laeqDay').textContent     = fmt(d.turno2);
      document.getElementById('laeqEvening').textContent = fmt(d.turno3);
      // Períodos Lden (legislação)
      document.getElementById('tempoLd').textContent = fmt(d.ld);
      document.getElementById('tempoLe').textContent = fmt(d.le);
      document.getElementById('tempoLn').textContent = fmt(d.ln);
      document.getElementById('lden').textContent    = fmt(d.lden);
    })
    .catch(() => {
      ['laeqNight','laeqDay','laeqEvening','tempoLd','tempoLe','tempoLn','lden']
        .forEach(id => { document.getElementById(id).textContent = '—'; });
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
    document.getElementById('Eventos').src      = buildGrafanaURL(13, from, to, sp, familiaGrafanaParam());
    calcularEstatisticas();
    calcularLden();
  }
}

// ── Download CSV com barra de progresso ─────────────────────────────────────
// O servidor envia o CSV em streaming, por ordem cronológica. O progresso é calculado
// a partir do TimeStamp (1.ª coluna) da última linha recebida face ao intervalo pedido.

const DOWNLOAD_MAX_HORAS = 24;
let downloadCtrl = null;

function setDownloadProgresso(pct, info) {
  const barra = document.getElementById('downloadBarra');
  const p = Math.max(0, Math.min(100, pct));
  barra.style.width = `${p}%`;
  barra.textContent = `${p.toFixed(0)}%`;
  if (info) document.getElementById('downloadInfo').textContent = info;
}

function mostrarDownloadProgresso(on) {
  document.getElementById('downloadProgresso').classList.toggle('d-none', !on);
  document.getElementById('btnDownload').disabled = on;
}

function cancelarDownload() {
  if (downloadCtrl) downloadCtrl.abort();
}

async function downloadCSV() {
  const start = document.getElementById('startDate').value;
  const end   = document.getElementById('endDate').value;
  const sensors = getSelectedSensors();
  if (!start || !end || sensors.length !== 1) {
    alert('Por favor seleciona um único sensor e datas válidas.');
    return;
  }
  const startD = new Date(start), endD = new Date(end);
  if (endD <= startD) { alert('A data de fim tem de ser posterior à de início.'); return; }
  if ((endD - startD) / 3600000 > DOWNLOAD_MAX_HORAS) {
    alert(`O intervalo máximo para download é de ${DOWNLOAD_MAX_HORAS} horas.`);
    return;
  }
  if (downloadCtrl) return;  // já há um download em curso

  const url = `/api/download?start=${startD.toISOString()}&end=${endD.toISOString()}&sensor_id=${encodeURIComponent(sensors[0])}`;
  const t0 = startD.getTime() / 1000, t1 = endD.getTime() / 1000;

  downloadCtrl = new AbortController();
  mostrarDownloadProgresso(true);
  setDownloadProgresso(0, 'A preparar...');

  try {
    const res = await fetch(url, { signal: downloadCtrl.signal });
    if (!res.ok) {
      const erro = await res.json().catch(() => ({}));
      throw new Error(erro.error || `Erro HTTP ${res.status}`);
    }

    const disp = res.headers.get('Content-Disposition') || '';
    const nome = (disp.match(/filename=([^;]+)/) || [])[1] || `SoundData_${sensors[0]}.csv`;

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    const partes  = [];
    let recebidos = 0, resto = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      partes.push(value);
      recebidos += value.length;

      const texto = resto + decoder.decode(value, { stream: true });
      if (texto.includes('# ERRO')) {
        throw new Error(texto.slice(texto.indexOf('# ERRO') + 2).split('\n')[0]);
      }
      const fim = texto.lastIndexOf('\n');
      if (fim < 0) { resto = texto; continue; }
      const ultima = texto.slice(texto.lastIndexOf('\n', fim - 1) + 1, fim);
      resto = texto.slice(fim + 1);

      const ts = parseFloat(ultima);
      const mb = (recebidos / 1048576).toFixed(1);
      if (!isNaN(ts)) setDownloadProgresso((ts - t0) / (t1 - t0) * 100, `${mb} MB recebidos`);
      else document.getElementById('downloadInfo').textContent = `${mb} MB recebidos`;
    }

    setDownloadProgresso(100, 'Concluído');
    const blob = new Blob(partes, { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  } catch (err) {
    if (err.name === 'AbortError') {
      document.getElementById('downloadInfo').textContent = 'Download cancelado.';
    } else {
      console.error('Erro no download:', err);
      alert(`Não foi possível descarregar o CSV: ${err.message}`);
    }
  } finally {
    downloadCtrl = null;
    setTimeout(() => { if (!downloadCtrl) mostrarDownloadProgresso(false); }, 2500);
  }
}

window.onload = () => {
  renderFamiliaToggle('familiaToggle', () => atualizarFamiliaIframe('Eventos'));
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
