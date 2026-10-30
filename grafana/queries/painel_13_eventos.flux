// Painel 13 — Eventos por tipo ao longo do tempo (heatmap)
// Usado em: Monitorização em Tempo Real, Monitorização por Período, Display.
//
// Igual à versão anterior (famílias hospital/urbano, ordem fixa das linhas), mas com a
// mesma escolha de dados do painel 1 (raw / 1 min / 1 h conforme a duração).
// Os buckets agregados guardam a média de cada EventType por minuto/hora, por isso a
// média por janela continua a ser a fração de tempo com o evento.
import "strings"

familia = "${familia}"

duracao = int(v: v.timeRangeStop) - int(v: v.timeRangeStart)
bucket = if duracao <= int(v: 12h) then "SoundDashHosp" else if duracao <= int(v: 31d) then "SoundDashHosp_1m" else "SoundDashHosp_1h"

// Carácter invisível (zero-width space). Serve só para fixar a ordem das linhas:
// o heatmap ordena pelo nome, e cada linha leva um número diferente destes caracteres à frente.
z = "\xe2\x80\x8b"

// Posição de cada tipo: 10 = linha de cima ... 1 = penúltima, 0 = última (Evento detetado)
pos = (f) =>
  if f == "EventType1" then 1
  else if f == "EventType2" then 2
  else if f == "EventType3" then 3
  else if f == "EventType4" then 4
  else if f == "EventType5" then 5
  else if f == "EventType6" then 6
  else if f == "EventType7" then 7
  else if f == "EventType8" then 8
  else if f == "EventType9" then 9
  else if f == "EventType10" then 10
  else 0

nome = (f) =>
  if familia == "urbano" then
    (if f == "EventType1" then "Aviões"
     else if f == "EventType2" then "Comboios"
     else if f == "EventType3" then "Gritos"
     else if f == "EventType4" then "Impulsivo"
     else if f == "EventType5" then "Música"
     else if f == "EventType6" then "Conversas"
     else if f == "EventType7" then "Buzinas"
     else if f == "EventType8" then "Cães a ladrar"
     else if f == "EventType9" then "Atmosfera"
     else if f == "EventType10" then "Automóvel"
     else if f == "EventDetect" then "Evento detetado"
     else f)
  else
    (if f == "EventType1" then "Alarme"
     else if f == "EventType2" then "Impacto"
     else if f == "EventType3" then "Música"
     else if f == "EventType4" then "Gritos"
     else if f == "EventType5" then "Respiração"
     else if f == "EventType6" then "Conversas"
     else if f == "EventType7" then "Telefone"
     else if f == "EventType8" then "Líquidos"
     else if f == "EventType9" then "Rodas"
     else if f == "EventType10" then "Assobios"
     else if f == "EventDetect" then "Evento detetado"
     else f)

from(bucket: bucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "${sensorName}" and r._field =~ /^(EventDetect|EventType[0-9]+)$/)
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
  |> map(fn: (r) => ({ r with _field: strings.repeat(v: z, i: pos(f: r._field)) + nome(f: r._field) }))
  // só tempo, valor e nome: sem isto o Grafana acrescenta o sensor ao nome ("Gritos sensor1")
  |> keep(columns: ["_time", "_value", "_field"])
