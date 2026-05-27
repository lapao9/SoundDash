function atualizarGrafico() {
  const sensor = document.getElementById('sensorSelect').value;
  const sp = `var-sensorName=${sensor}`;
  document.getElementById('graficoLAEA').src = buildGrafanaURL(1,  'now-6m', 'now-1m', sp);
  document.getElementById('NvlFreq').src     = buildGrafanaURL(13, 'now-6m', 'now-1m', sp);
  document.getElementById('Spectogram').src  = buildGrafanaURL(16, 'now-6m', 'now-1m', sp);
  document.getElementById('gaugePanel').src  = buildGrafanaURL(14, 'now-6m', 'now-1m', sp);
}

async function atualizarClasses() {
  try {
    const sensor = document.getElementById('sensorSelect').value;
    const res = await fetch(`/api/classes?sensor_id=${sensor}`);
    const data = await res.json();
    const container = document.getElementById('classesContainer');
    container.innerHTML = '';
    data.forEach(row => {
      const p = document.createElement('p');
      p.className = 'classes-line';
      p.innerHTML = `<strong>${row.ClassName}</strong> | ${row.ClassScore.toFixed(2)}`;
      container.appendChild(p);
    });
  } catch (err) {
    console.error('Erro ao buscar classes:', err);
  }
}

window.onload = () => {
  carregarSensores('sensorSelect', atualizarGrafico);
  atualizarClasses();
  setInterval(atualizarClasses, 5000);
};
