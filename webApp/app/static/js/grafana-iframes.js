/**
 * grafana-iframes.js — helper para construir URLs de painéis Grafana
 * GRAFANA_URL é injetado pelo base.html como variável JS global
 */

function buildGrafanaURL(panelId, from, to, sensorParams, extra) {
  const base = (typeof GRAFANA_URL !== 'undefined' ? GRAFANA_URL : '');
  const extraStr = extra || '';
  return `${base}/d-solo/aemh0e2wamy2od/dash1?orgId=1&theme=dark&panelId=${panelId}&from=${from}&to=${to}&${sensorParams}${extraStr}`;
}
