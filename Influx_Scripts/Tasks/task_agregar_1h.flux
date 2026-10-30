// ============================================================
// TASK — Agregação por hora (raw -> SoundDashHosp_1h)
// ============================================================
//
// Corre de hora a hora e agrega SÓ a última hora de dados raw
// (a task antiga "Aggregate_Hourly" relia as últimas 24 h a cada hora).
// Timestamp de cada ponto = início da hora (ex. 14:00 = 14:00–15:00).
//
// Mesmo formato do bucket de 1 minuto:
//   LAEA, LAEC, LAEZ e bandas -> média de 10^(L/10) na hora (escala LINEAR)
//   n                         -> nº de amostras LAEA na hora
//   LCpeak, LAFmax / LAFmin   -> máximo / mínimo da hora (dB)
//   EventDetect, EventType*   -> média na hora
//
// Com LAEA e n, qualquer LAeq (turno, dia, Lden, mês) é exato:
//   LAeq = 10·log10( Σ(LAEA·n) / Σn )
//
// Criar no InfluxDB: Tasks -> Create Task -> New Task
//   1) preencher o formulário: Name = SoundDash_agregar_1h, Every = 1h, Offset = 2m
//   2) colar este ficheiro inteiro no editor -> Save
// (O bucket SoundDashHosp_1h tem de existir antes.)
// ============================================================

origem = "SoundDashHosp"
destino = "SoundDashHosp_1h"
// Período lido em cada execução = Every do formulário (1h)
janela = 1h

// Níveis equivalentes: dB -> linear -> média
from(bucket: origem)
    |> range(start: -1h)
    |> filter(fn: (r) => r._field =~ /^(LAEA|LAEC|LAEZ|[0-9.]+_Hz)$/)
    // operador ^ (não math.pow): o Flux calcula-o em bloco, ~90x mais rápido
    |> map(fn: (r) => ({r with _value: 10.0 ^ (float(v: r._value) / 10.0)}))
    |> aggregateWindow(every: janela, fn: mean, createEmpty: false, timeSrc: "_start")
    |> to(bucket: destino, org: "ISEL")

// Nº de amostras
from(bucket: origem)
    |> range(start: -1h)
    |> filter(fn: (r) => r._field == "LAEA")
    |> aggregateWindow(every: janela, fn: count, createEmpty: false, timeSrc: "_start")
    |> map(fn: (r) => ({r with _field: "n", _value: float(v: r._value)}))
    |> to(bucket: destino, org: "ISEL")

// Picos e máximos
from(bucket: origem)
    |> range(start: -1h)
    |> filter(fn: (r) => r._field == "LCpeak" or r._field == "LAFmax")
    |> aggregateWindow(every: janela, fn: max, createEmpty: false, timeSrc: "_start")
    |> map(fn: (r) => ({r with _value: float(v: r._value)}))
    |> to(bucket: destino, org: "ISEL")

// Mínimos
from(bucket: origem)
    |> range(start: -1h)
    |> filter(fn: (r) => r._field == "LAFmin")
    |> aggregateWindow(every: janela, fn: min, createEmpty: false, timeSrc: "_start")
    |> map(fn: (r) => ({r with _value: float(v: r._value)}))
    |> to(bucket: destino, org: "ISEL")

// Eventos
from(bucket: origem)
    |> range(start: -1h)
    |> filter(fn: (r) => r._field =~ /^(EventDetect|EventType[0-9]+)$/)
    |> map(fn: (r) => ({r with _value: float(v: r._value)}))
    |> aggregateWindow(every: janela, fn: mean, createEmpty: false, timeSrc: "_start")
    |> to(bucket: destino, org: "ISEL")
