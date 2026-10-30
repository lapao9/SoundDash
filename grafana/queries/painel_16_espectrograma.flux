// Painel 16 — Espectrograma (bandas de 1/3 de oitava ao longo do tempo)
// Usado em: Monitorização em Tempo Real, Monitorização por Período, Display.
//
// Todas as 30 bandas (25 Hz ... 20 kHz, incluindo 31,5 Hz e 2 kHz que faltavam) e
// média ENERGÉTICA em cada janela (antes era a média aritmética dos dB).
// Mesma escolha de dados do painel 1 (raw / 1 min / 1 h conforme a duração).
//
// Transformação "Rename by regex" do painel: Match = 0*([\d.]+)_Hz   Replace = $1
// (a anterior, 0*(\d+)_Hz, não apanhava o ponto de "31.5")
import "math"

duracao = int(v: v.timeRangeStop) - int(v: v.timeRangeStart)
raw = duracao <= int(v: 12h)
bucket = if raw then "SoundDashHosp" else if duracao <= int(v: 31d) then "SoundDashHosp_1m" else "SoundDashHosp_1h"

bandas = from(bucket: bucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "${sensorName}" and r._field =~ /^[0-9.]+_Hz$/)

linear = if raw then bandas |> map(fn: (r) => ({r with _value: 10.0 ^ (float(v: r._value) / 10.0)})) else bandas

linear
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
  |> map(fn: (r) => ({r with _value: 10.0 * math.log10(x: r._value)}))
