// ============================================================
// TASK 2 — Downsampling automático (raw → médias por minuto)
// ============================================================
//
// O QUE FAZ:
//   Corre a cada hora.
//   Pega nos dados raw da última hora do bucket "sounddash"
//   (16 medições/segundo = ~57.600 pontos/hora por sensor)
//   e comprime em médias por minuto no bucket "sounddash_1m"
//   (60 pontos/hora por sensor).
//
//   Para campos de pressão sonora (dB), faz a conversão
//   correta: dB → linear → média por minuto → dB
//   usando map(), sem descarregar dados para Python.
//
//   Para campos de eventos (EventDetect, EventType1-10),
//   usa max() em vez de mean() — queremos saber se houve
//   evento na janela, não a média.
//
// VANTAGEM:
//   A app para ranges > 6h pode consultar "sounddash_1m"
//   em vez de "sounddash", sendo muito mais rápida.
//   Ex: 1 semana de dados = 10.080 pontos em vez de 8M.
//
// ONDE CRIAR NO INFLUXDB:
//   localhost:8086 → Tasks → + Create Task
//   Every: 1h
//   Offset: 5m  (espera 5 min para garantir que os dados chegaram)
//   Colar este script no editor
//
// BUCKETS NECESSÁRIOS:
//   Leitura:  sounddash    (já existe)
//   Escrita:  sounddash_1m (criar antes em Load Data → Buckets)
// ============================================================

import "math"

// ── Campos dB (pressão sonora) — conversão linear obrigatória ──────────────
// Estes campos estão em dB e precisam de conversão antes de calcular médias
campos_db = [
    "LAEA", "LAEC", "LAEZ",
    "LCpeak", "LCpeakT", "LApeak", "LApeakT", "LZpeak", "LZpeakT",
    "LAFmax", "LAFmaxT", "LAFmin", "LAFminT",
    "LZeq", "LCeq", "LAeq",
    "LAEA_SLOW_Event",
    "BT25", "BT31_5", "BT40", "BT50", "BT63", "BT80",
    "BT100", "BT125", "BT160", "BT200", "BT250", "BT315",
    "BT400", "BT500", "BT630", "BT800", "BT1000", "BT1250",
    "BT1600", "BT2000", "BT2500", "BT3150", "BT4000", "BT5000",
    "BT6300", "BT8000", "BT10000", "BT12500", "BT16000", "BT20000"
]

// ── Campos de eventos — usar max() (houve evento ou não) ───────────────────
campos_eventos = [
    "EventDetect",
    "EventType1", "EventType2", "EventType3", "EventType4", "EventType5",
    "EventType6", "EventType7", "EventType8", "EventType9", "EventType10"
]

// ── Campos de classificação — usar last() (último valor da janela) ─────────
campos_class = [
    "Class1ID", "Class1Score",
    "Class2ID", "Class2Score",
    "Class3ID", "Class3Score"
]

// ── Downsampling campos dB com conversão logarítmica correta ───────────────
from(bucket: "sounddash")
    |> range(start: -1h)
    |> filter(fn: (r) => contains(value: r._field, set: campos_db))
    // Passo 1: dB → linear
    |> map(fn: (r) => ({r with _value: math.pow(x: 10.0, y: r._value / 10.0)}))
    // Passo 2: média por janela de 1 minuto em escala linear
    |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
    // Passo 3: linear → dB
    |> map(fn: (r) => ({r with _value: 10.0 * math.log(x: r._value) / math.log(x: 10.0)}))
    |> to(bucket: "sounddash_1m", org: "admin")

// ── Downsampling campos de eventos com max() ───────────────────────────────
from(bucket: "sounddash")
    |> range(start: -1h)
    |> filter(fn: (r) => contains(value: r._field, set: campos_eventos))
    |> aggregateWindow(every: 1m, fn: max, createEmpty: false)
    |> to(bucket: "sounddash_1m", org: "admin")

// ── Downsampling campos de classificação com last() ────────────────────────
from(bucket: "sounddash")
    |> range(start: -1h)
    |> filter(fn: (r) => contains(value: r._field, set: campos_class))
    |> aggregateWindow(every: 1m, fn: last, createEmpty: false)
    |> to(bucket: "sounddash_1m", org: "admin")
