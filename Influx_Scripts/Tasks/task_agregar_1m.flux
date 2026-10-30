// ============================================================
// TASK — Agregação por minuto (raw -> SoundDashHosp_1m)
// ============================================================
//
// Corre de 5 em 5 minutos e agrega os últimos 5 minutos de dados raw
// de todos os sensores em janelas de 1 minuto (timestamp = início do minuto).
//
// O que guarda (mesmo measurement do raw, ex. "sensor1"):
//   LAEA, LAEC, LAEZ e bandas (00025_Hz ... 20000_Hz)
//       -> média ENERGÉTICA em escala LINEAR: média de 10^(L/10) no minuto
//          (para voltar a dB: 10·log10(valor))
//   n   -> nº de amostras LAEA no minuto (permite médias exatas ponderadas)
//   LCpeak, LAFmax -> máximo do minuto (dB)
//   LAFmin         -> mínimo do minuto (dB)
//   EventDetect, EventType1..10 -> média no minuto (fração de amostras)
//
// Cada amostra raw é lida uma única vez. Os gráficos de períodos longos
// leem este bucket em vez do raw.
//
// Criar no InfluxDB: Tasks -> Create Task -> New Task
//   1) preencher o formulário: Name = SoundDash_agregar_1m, Every = 5m, Offset = 1m
//   2) colar este ficheiro inteiro no editor -> Save
// (O bucket SoundDashHosp_1m tem de existir antes.)
// ============================================================

origem = "SoundDashHosp"
destino = "SoundDashHosp_1m"
// Período lido em cada execução = Every do formulário (5m)
janela = 1m

// Níveis equivalentes: dB -> linear -> média
from(bucket: origem)
    |> range(start: -5m)
    |> filter(fn: (r) => r._field =~ /^(LAEA|LAEC|LAEZ|[0-9.]+_Hz)$/)
    // operador ^ (não math.pow): o Flux calcula-o em bloco, ~90x mais rápido
    |> map(fn: (r) => ({r with _value: 10.0 ^ (float(v: r._value) / 10.0)}))
    |> aggregateWindow(every: janela, fn: mean, createEmpty: false, timeSrc: "_start")
    |> to(bucket: destino, org: "ISEL")

// Nº de amostras
from(bucket: origem)
    |> range(start: -5m)
    |> filter(fn: (r) => r._field == "LAEA")
    |> aggregateWindow(every: janela, fn: count, createEmpty: false, timeSrc: "_start")
    |> map(fn: (r) => ({r with _field: "n", _value: float(v: r._value)}))
    |> to(bucket: destino, org: "ISEL")

// Picos e máximos
from(bucket: origem)
    |> range(start: -5m)
    |> filter(fn: (r) => r._field == "LCpeak" or r._field == "LAFmax")
    |> aggregateWindow(every: janela, fn: max, createEmpty: false, timeSrc: "_start")
    |> map(fn: (r) => ({r with _value: float(v: r._value)}))
    |> to(bucket: destino, org: "ISEL")

// Mínimos
from(bucket: origem)
    |> range(start: -5m)
    |> filter(fn: (r) => r._field == "LAFmin")
    |> aggregateWindow(every: janela, fn: min, createEmpty: false, timeSrc: "_start")
    |> map(fn: (r) => ({r with _value: float(v: r._value)}))
    |> to(bucket: destino, org: "ISEL")

// Eventos
from(bucket: origem)
    |> range(start: -5m)
    |> filter(fn: (r) => r._field =~ /^(EventDetect|EventType[0-9]+)$/)
    |> map(fn: (r) => ({r with _value: float(v: r._value)}))
    |> aggregateWindow(every: janela, fn: mean, createEmpty: false, timeSrc: "_start")
    |> to(bucket: destino, org: "ISEL")
