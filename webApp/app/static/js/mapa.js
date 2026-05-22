async function carregarSensoresMapa() {
  try {
    const res = await fetch('/api/sensores');
    const sensores = await res.json();
    const lista = document.getElementById('sensoresLista');
    lista.innerHTML = '';
    sensores.forEach(s => {
      const nome = s.charAt(0).toUpperCase() + s.slice(1);
      lista.innerHTML += `
        <div class="sensor-card">
          <div class="sensor-header" onclick="toggleSensor('${s}')">${nome}</div>
          <div class="sensor-body" id="${s}-body"></div>
        </div>`;
    });
  } catch (err) {
    console.error('Erro ao carregar sensores:', err);
  }
}

function toggleSensor(sensorId) {
  const iframeURL = buildGrafanaURL(14, 'now-5m', 'now', `var-sensorName=${sensorId}`);
  const body = document.getElementById(sensorId + '-body');

  document.querySelectorAll('.sensor-body').forEach(div => {
    if (div.id !== sensorId + '-body') {
      div.classList.remove('show');
      div.innerHTML = '';
    }
  });

  if (body.classList.contains('show')) {
    body.classList.remove('show');
    body.innerHTML = '';
  } else {
    body.innerHTML = `<iframe src="${iframeURL}" allowfullscreen></iframe>`;
    body.classList.add('show');
  }
}

window.addEventListener('load', carregarSensoresMapa);
