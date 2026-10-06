/**
 * utils.js — funções partilhadas por múltiplas páginas
 * Carregado globalmente via base.html
 */

async function carregarSensores(selectId, onLoadCallback) {
  try {
    const res = await fetch('/api/sensores');
    const sensores = await res.json();
    const select = document.getElementById(selectId);
    if (!select) return;
    select.innerHTML = '';
    sensores.forEach((s, i) => {
      const opt = document.createElement('option');
      opt.value = s;
      opt.textContent = s.charAt(0).toUpperCase() + s.slice(1);
      if (i === 0) opt.selected = true;
      select.appendChild(opt);
    });
    if (typeof onLoadCallback === 'function') onLoadCallback();
  } catch (err) {
    console.error('Erro ao carregar sensores:', err);
  }
}

// ── Famílias de eventos sonoros (EventType1..10) ─────────────────────────────
// O sensor classifica sempre em 10 tipos; o nome de cada tipo depende da família
// (Hospital ou Urbano/Aircraft). A escolha é guardada no browser e partilhada entre páginas.

const FAMILIAS_EVENTOS = {
  hospital: {
    EventType1: 'Alarme',   EventType2: 'Impacto',    EventType3: 'Música',
    EventType4: 'Gritos',   EventType5: 'Respiração', EventType6: 'Conversas',
    EventType7: 'Telefone', EventType8: 'Líquidos',   EventType9: 'Rodas',
    EventType10: 'Assobios'
  },
  urbano: {
    EventType1: 'Aviões',   EventType2: 'Comboios',      EventType3: 'Gritos',
    EventType4: 'Impulsivo', EventType5: 'Música',       EventType6: 'Conversas',
    EventType7: 'Buzinas',  EventType8: 'Cães a ladrar', EventType9: 'Atmosfera',
    EventType10: 'Automóvel'
  }
};

function getFamiliaEventos() {
  try {
    const f = localStorage.getItem('familiaEventos');
    if (f && FAMILIAS_EVENTOS[f]) return f;
  } catch (e) { /* storage indisponível */ }
  return 'hospital';
}

function setFamiliaEventos(familia) {
  try { localStorage.setItem('familiaEventos', familia); } catch (e) { /* ignorar */ }
}

function nomeTipoEvento(key) {
  return FAMILIAS_EVENTOS[getFamiliaEventos()][key] || key;
}

// Parâmetro para os painéis Grafana de tipos de eventos (variável de dashboard "familia")
function familiaGrafanaParam() {
  return `&var-familia=${getFamiliaEventos()}`;
}

// Atualiza só a família num iframe Grafana já carregado (evita recarregar os outros painéis)
function atualizarFamiliaIframe(iframeId) {
  const frame = document.getElementById(iframeId);
  if (!frame || !frame.src || !frame.src.includes('var-familia=')) return;
  frame.src = frame.src.replace(/var-familia=[a-z]+/, `var-familia=${getFamiliaEventos()}`);
}

// Cria os botões Hospital / Urbano dentro do elemento indicado
function renderFamiliaToggle(containerId, onChange) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const opcoes = [['hospital', 'Hospital'], ['urbano', 'Urbano']];
  el.innerHTML = '';
  el.className = 'btn-group btn-group-sm';
  el.setAttribute('role', 'group');
  opcoes.forEach(([valor, texto]) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = texto;
    btn.className = valor === getFamiliaEventos() ? 'btn btn-primary' : 'btn btn-outline-primary';
    btn.addEventListener('click', () => {
      if (valor === getFamiliaEventos()) return;
      setFamiliaEventos(valor);
      renderFamiliaToggle(containerId, onChange);
      if (typeof onChange === 'function') onChange(valor);
    });
    el.appendChild(btn);
  });
}

function formatDatetimeLocal(date) {
  const pad = n => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatDuration(segundos) {
  if (segundos >= 3600) {
    const h = Math.floor(segundos / 3600);
    const m = Math.floor((segundos % 3600) / 60);
    return `${h}h ${m}min`;
  }
  if (segundos >= 60) {
    const m = Math.floor(segundos / 60);
    const s = Math.floor(segundos % 60);
    return `${m}min ${s}s`;
  }
  return `${segundos.toFixed(1)}s`;
}
