function mostrarSensor(sensorId) {
  const wrap = document.getElementById('mapaIframeWrap');
  if (!sensorId) return;
  const url = buildGrafanaURL(14, 'now-5m', 'now', `var-sensorName=${sensorId}`);
  wrap.innerHTML = `<iframe src="${url}" width="100%" height="100%" style="border:none;" allowfullscreen></iframe>`;
}

window.addEventListener('load', () => {
  carregarSensores('mapaSelectSensor', () => {
    const select = document.getElementById('mapaSelectSensor');
    mostrarSensor(select.value);
  });

  document.getElementById('mapaSelectSensor').addEventListener('change', e => {
    mostrarSensor(e.target.value);
  });
});
