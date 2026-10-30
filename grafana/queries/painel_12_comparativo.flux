// Painel 12 — Comparativo por parâmetro (vários sensores, ${param})
// Usado em: Monitorização em Tempo Real e por Período, com 2 ou mais sensores selecionados.
//
// Mesma escolha de dados do painel 1 (raw / 1 min / 1 h conforme a duração).
// ${sensorName:regex} dá "(sensor1|sensor2|...)": um filtro com regex é aplicado pelo próprio
// InfluxDB na leitura (o contains() da versão anterior obrigava a ler todos os sensores e campos).
import "math"

param = "${param}"
duracao = int(v: v.timeRangeStop) - int(v: v.timeRangeStart)
raw = duracao <= int(v: 12h)
bucket = if raw then "SoundDashHosp" else if duracao <= int(v: 31d) then "SoundDashHosp_1m" else "SoundDashHosp_1h"

dados = from(bucket: bucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement =~ /^${sensorName:regex}$/ and r._field == param)

linear = if raw then dados |> map(fn: (r) => ({r with _value: 10.0 ^ (float(v: r._value) / 10.0)})) else dados

resultado =
  if param == "LCpeak" or param == "LAFmax" then
    dados |> aggregateWindow(every: v.windowPeriod, fn: max, createEmpty: false)
  else if param == "LAFmin" then
    dados |> aggregateWindow(every: v.windowPeriod, fn: min, createEmpty: false)
  else
    // LAEA: média energética
    linear
      |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
      |> map(fn: (r) => ({r with _value: 10.0 * math.log10(x: r._value)}))

resultado
  // uma linha por sensor, com o nome "LAEA sensor1", "LAEA sensor2", ...
  |> map(fn: (r) => ({r with _field: param + " " + r._measurement}))
  |> keep(columns: ["_time", "_value", "_field"])
