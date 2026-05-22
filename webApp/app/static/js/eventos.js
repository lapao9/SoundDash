let intervalosGlobais = [];

const nomesTipos = {
  EventType1: 'Alarme',   EventType2: 'Impacto',    EventType3: 'Música',
  EventType4: 'Gritos',   EventType5: 'Respiração',  EventType6: 'Conversas',
  EventType7: 'Telefone', EventType8: 'Líquidos',    EventType9: 'Rodas',
  EventType10: 'Assobios'
};

function agruparEventos(dados) {
  if (!dados.length) return [];
  const eventos = dados.map(d => ({ time: new Date(d.time), data: d }));
  let intervalos = [];
  let grupo = { inicio: eventos[0].time, fim: eventos[0].time, eventos: [eventos[0].data] };

  for (let i = 1; i < eventos.length; i++) {
    if ((eventos[i].time - eventos[i-1].time) / 1000 <= 5) {
      grupo.fim = eventos[i].time;
      grupo.eventos.push(eventos[i].data);
    } else {
      intervalos.push({ ...grupo });
      grupo = { inicio: eventos[i].time, fim: eventos[i].time, eventos: [eventos[i].data] };
    }
  }
  intervalos.push({ ...grupo });
  return intervalos;
}

function contarTiposEvento(eventos) {
  const contagem = {};
  eventos.forEach(reg => {
    for (let i = 1; i <= 10; i++) {
      const key = `EventType${i}`;
      contagem[key] = (contagem[key] || 0) + reg[key];
    }
  });
  return Object.entries(contagem).sort((a, b) => b[1] - a[1]).slice(0, 2);
}

function mostrarDetalhes(index) {
  const grupo = intervalosGlobais[index];
  const topTipos = contarTiposEvento(grupo.eventos);
  const div = document.getElementById(`detalhes-${index}`);
  if (div.innerHTML.trim() !== '') {
    div.innerHTML = '';
    return;
  }
  intervalosGlobais.forEach((_, i) => {
    if (i !== index) document.getElementById(`detalhes-${i}`).innerHTML = '';
  });
  let html = '<ul class="list-group mt-2">';
  if (!topTipos.length) {
    html += '<li class="list-group-item">Nenhum tipo de evento registado.</li>';
  } else {
    topTipos.forEach(([tipo]) => {
      html += `<li class="list-group-item">${nomesTipos[tipo] || tipo}</li>`;
    });
  }
  html += '</ul>';
  div.innerHTML = html;
}

async function carregarEventos() {
  const resultadoDiv = document.getElementById('resultado');
  const sensor = document.getElementById('sensorSelect').value;
  const start  = document.getElementById('startDate').value;
  const end    = document.getElementById('endDate').value;

  if (!sensor || !start || !end) {
    resultadoDiv.innerHTML = '<div class="alert alert-warning">Seleciona sensor e datas válidas.</div>';
    return;
  }

  resultadoDiv.innerHTML = '<div class="alert alert-info">A carregar...</div>';

  try {
    const ISOstart = new Date(start).toISOString().replace('Z','').replace(':00.000','');
    const ISOend   = new Date(end).toISOString().replace('Z','').replace(':00.000','');
    const res = await fetch(`/api/eventos?sensor=${sensor}&start=${ISOstart}&end=${ISOend}`);
    const dados = await res.json();

    if (!dados || !dados.length) {
      resultadoDiv.innerHTML = '<div class="alert alert-success">Nenhum evento detetado.</div>';
      return;
    }

    intervalosGlobais = agruparEventos(dados);
    let html = '';
    intervalosGlobais.forEach((grupo, index) => {
      const duracaoSegundos = (grupo.fim - grupo.inicio) / 1000;
      html += `
        <div class="card card-evento p-3">
          <div>
            <strong>Início:</strong> ${new Date(grupo.inicio).toLocaleString()}<br>
            <strong>Fim:</strong> ${new Date(grupo.fim).toLocaleString()}<br>
            <strong>Duração:</strong> ${formatDuration(duracaoSegundos)}
            <button class="btn btn-sm btn-outline-primary float-end" onclick="mostrarDetalhes(${index})">
              Ver detalhes
            </button>
            <div id="detalhes-${index}" class="mt-2"></div>
          </div>
        </div>`;
    });
    resultadoDiv.innerHTML = html;
  } catch (err) {
    resultadoDiv.innerHTML = `<div class="alert alert-danger">Erro: ${err.message}</div>`;
  }
}

window.onload = () => {
  carregarSensores('sensorSelect', null);
  const now = new Date();
  const fiveMinAgo = new Date(now.getTime() - 5 * 60 * 1000);
  document.getElementById('endDate').value   = formatDatetimeLocal(now);
  document.getElementById('startDate').value = formatDatetimeLocal(fiveMinAgo);
  carregarEventos();
};
