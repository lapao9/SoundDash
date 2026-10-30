// Painel 7 — Níveis por banda de frequência em tempo real (gráfico de barras)
// Usado em: Monitorização em Tempo Real (últimos minutos).
//
// Último valor de cada banda (faz sentido em tempo real). Passa a incluir a banda dos 2 kHz.
// Período sempre curto: lê o raw.
import "strings"

from(bucket: "SoundDashHosp")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "${sensorName}" and r._field =~ /^[0-9.]+_Hz$/)
  |> group(columns: ["_field"])
  |> last()
  // etiqueta: "00031.5_Hz" -> 31.5 Hz -> "31.5";  "02000_Hz" -> "2k";  "01250_Hz" -> "1.25k"
  |> map(fn: (r) => ({
      freq: float(v: strings.replaceAll(v: r._field, t: "_Hz", u: "")),
      _value: r._value
  }))
  |> map(fn: (r) => ({
      freq_ordem: r.freq,
      freq_label: if r.freq >= 1000.0 then string(v: r.freq / 1000.0) + "k" else string(v: r.freq),
      _value: r._value
  }))
  |> group()
  |> sort(columns: ["freq_ordem"])
  |> keep(columns: ["freq_label", "_value"])
