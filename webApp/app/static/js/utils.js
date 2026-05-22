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
