async function atualizarTabelaClasses() {
  try {
    const sensorSelect = document.getElementById('sensorSelect');
    const sensoresSelecionados = Array.from(sensorSelect.selectedOptions).map(opt => opt.value);
    const sensor = sensoresSelecionados.length > 0 ? sensoresSelecionados[0] : null;
    if (!sensor) return;

    const res = await fetch(`/api/classes?sensor_id=${sensor}`);
    const data = await res.json();

    const rowDiv = document.getElementById('classesRow');
    rowDiv.innerHTML = '';
    data.forEach(row => {
      const span = document.createElement('span');
      span.innerHTML = `<strong>${row.ClassName}</strong> | ${row.ClassScore.toFixed(2)}`;
      rowDiv.appendChild(span);
    });
  } catch (err) {
    console.error('Erro ao buscar classes:', err);
  }
}

function atualizarGrafico() {
  const intervalo = document.querySelector('input[name="intervalo"]:checked').value;
  const from = `now-${intervalo}`;
  const to = 'now';

  const sensorSelect = document.getElementById('sensorSelect');
  const sensoresSelecionados = Array.from(sensorSelect.selectedOptions).map(opt => opt.value);
  const sensoresParams = sensoresSelecionados.map(s => `var-sensorName=${s}`).join('&');
  const isMulti = sensoresSelecionados.length > 1;

  document.getElementById('graficoLAEA_box').style.display   = isMulti ? 'none' : 'block';
  document.getElementById('NvlFreq_box').style.display       = isMulti ? 'none' : 'block';
  document.getElementById('Eventos_box').style.display       = isMulti ? 'none' : 'block';
  document.getElementById('Spectogram_box').style.display    = isMulti ? 'none' : 'block';
  document.getElementById('graficoMulti_box').classList.toggle('d-none', !isMulti);
  document.getElementById('paramSelect').style.display       = isMulti ? 'block' : 'none';

  if (!isMulti) {
    document.getElementById('graficoLAEA').src  = buildGrafanaURL(1,  from, to, sensoresParams);
    document.getElementById('NvlFreq').src      = buildGrafanaURL(7,  from, to, sensoresParams);
    document.getElementById('Spectogram').src   = buildGrafanaURL(16, from, to, sensoresParams);
    document.getElementById('Eventos').src      = buildGrafanaURL(13, from, to, sensoresParams);
    document.getElementById('Gauges').src       = buildGrafanaURL(14, from, to, sensoresParams);
  } else {
    const param = document.getElementById('paramSelect').value;
    document.getElementById('graficoMulti').src = buildGrafanaURL(12, from, to, sensoresParams, `&var-param=${param}`);
  }
}

window.onload = () => {
  carregarSensores('sensorSelect', atualizarGrafico);
  setInterval(atualizarTabelaClasses, 2000);
};
