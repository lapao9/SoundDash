// Painel 15 — Níveis por banda de frequência no período (gráfico de barras)
// Usado em: Monitorização por Período.
//
// Leq de cada banda em TODO o período selecionado (média energética).
// Antes mostrava só o último valor de cada banda (last()) e faltava a banda dos 2 kHz.
// Mesma escolha de dados do painel 1 (raw / 1 min / 1 h conforme a duração).
import "math"
import "strings"

duracao = int(v: v.timeRangeStop) - int(v: v.timeRangeStart)
raw = duracao <= int(v: 12h)
bucket = if raw then "SoundDashHosp" else if duracao <= int(v: 31d) then "SoundDashHosp_1m" else "SoundDashHosp_1h"

bandas = from(bucket: bucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "${sensorName}" and r._field =~ /^[0-9.]+_Hz$/)

linear = if raw then bandas |> map(fn: (r) => ({r with _value: 10.0 ^ (float(v: r._value) / 10.0)})) else bandas

linear
  |> group(columns: ["_field"])
  |> mean()
  // etiqueta: "00031.5_Hz" -> 31.5 Hz -> "31.5";  "02000_Hz" -> "2k";  "01250_Hz" -> "1.25k"
  |> map(fn: (r) => ({
      freq: float(v: strings.replaceAll(v: r._field, t: "_Hz", u: "")),
      _value: 10.0 * math.log10(x: r._value)
  }))
  |> map(fn: (r) => ({
      freq_ordem: r.freq,
      freq_label: if r.freq >= 1000.0 then string(v: r.freq / 1000.0) + "k" else string(v: r.freq),
      _value: r._value
  }))
  |> group()
  |> sort(columns: ["freq_ordem"])
  |> keep(columns: ["freq_label", "_value"])
