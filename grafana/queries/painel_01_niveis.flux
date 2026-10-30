// Painel 1 — Níveis sonoros ao longo do tempo (LAF energético, LCpeak, LAFmax, LAFmin)
// Usado em: Monitorização em Tempo Real, Monitorização por Período, Display.
//
// Dados conforme a duração do período pedido:
//   até 12 h  -> raw (SoundDashHosp)
//   até 31 d  -> médias por minuto (SoundDashHosp_1m)
//   mais      -> médias por hora   (SoundDashHosp_1h)
// Nos buckets agregados os níveis equivalentes já estão em escala linear (média de 10^(L/10)).
// Cada ramo tem o seu from/range/filter completo: assim o InfluxDB só lê os campos pedidos.
import "math"

duracao = int(v: v.timeRangeStop) - int(v: v.timeRangeStart)
raw = duracao <= int(v: 12h)
bucket = if raw then "SoundDashHosp" else if duracao <= int(v: 31d) then "SoundDashHosp_1m" else "SoundDashHosp_1h"

maximos = from(bucket: bucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "${sensorName}" and (r._field == "LCpeak" or r._field == "LAFmax"))
  |> aggregateWindow(every: v.windowPeriod, fn: max, createEmpty: false)

minimos = from(bucket: bucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "${sensorName}" and r._field == "LAFmin")
  |> aggregateWindow(every: v.windowPeriod, fn: min, createEmpty: false)

// LAF: média energética (dB -> linear -> média -> dB); o operador ^ é muito mais rápido que math.pow
laea = from(bucket: bucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "${sensorName}" and r._field == "LAEA")
laea_linear = if raw then laea |> map(fn: (r) => ({r with _value: 10.0 ^ (float(v: r._value) / 10.0)})) else laea
media = laea_linear
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
  |> map(fn: (r) => ({r with _value: 10.0 * math.log10(x: r._value)}))

union(tables: [maximos, minimos, media])
