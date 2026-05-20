// ============================================================
// TASK 3 — Estatísticas horárias por sensor
// ============================================================
//
// O QUE FAZ:
//   Corre a cada hora.
//   Para cada sensor no bucket "SoundDashHosp", calcula:
//     - LAeq  (média energética correta em linear)
//     - LAFmax (máximo do período)
//     - LAFmin (mínimo do período)
//     - P50   (percentil 50 — mediana)
//     - P95   (percentil 95)
//   Guarda tudo no bucket "sounddash_stats".
//
// PORQUÊ EM LINEAR:
//   Os valores dos sensores estão em dB (logarítmico).
//   Não se podem calcular médias ou percentis diretamente em dB
//   — é matematicamente errado. A conversão correta é:
//     dB → linear:  10^(val/10)
//     linear → dB:  10 * log10(val)
//   Esta Task faz essa conversão internamente com map(),
//   sem descarregar dados para Python.
//
// ONDE CRIAR NO INFLUXDB:
//   localhost:8086 → Tasks → + Create Task
//   Every: 1h
//   Offset: 2m  (espera 2 min para garantir que os dados chegaram)
//
// BUCKETS NECESSÁRIOS:
//   Leitura:  SoundDashHosp  (já existe)
//   Escrita:  sounddash_stats (criar antes em Load Data → Buckets)
//             Retention recomendada: sem limite (para sempre)
// ============================================================

import "math"
import "influxdata/influxdb/schema"

// Período da última hora
inicio = -1h
fim = now()

// Buscar todos os measurements (sensores) disponíveis no bucket
sensores = schema.measurements(bucket: "SoundDashHosp")

// ── LAeq — média energética correta (dB → linear → média → dB) ────────────
from(bucket: "SoundDashHosp")
    |> range(start: inicio, stop: fim)
    |> filter(fn: (r) => r["_field"] == "LAEA")
    // Passo 1: dB → linear
    |> map(fn: (r) => ({r with _value: math.pow(x: 10.0, y: r._value / 10.0)}))
    // Passo 2: média em linear por sensor
    |> mean()
    // Passo 3: linear → dB
    |> map(fn: (r) => ({r with
        _value: 10.0 * math.log(x: r._value) / math.log(x: 10.0),
        _field: "LAeq_horario"
    }))
    |> to(bucket: "sounddash_stats", org: "ISEL")

// ── LAFmax — máximo do período (dB, não precisa conversão) ────────────────
from(bucket: "SoundDashHosp")
    |> range(start: inicio, stop: fim)
    |> filter(fn: (r) => r["_field"] == "LAFmax")
    |> max()
    |> map(fn: (r) => ({r with _field: "LAFmax_horario"}))
    |> to(bucket: "sounddash_stats", org: "ISEL")

// ── LAFmin — mínimo do período (dB, não precisa conversão) ────────────────
from(bucket: "SoundDashHosp")
    |> range(start: inicio, stop: fim)
    |> filter(fn: (r) => r["_field"] == "LAFmin")
    |> min()
    |> map(fn: (r) => ({r with _field: "LAFmin_horario"}))
    |> to(bucket: "sounddash_stats", org: "ISEL")

// ── P50 — percentil 50 em linear (mediana) ────────────────────────────────
from(bucket: "SoundDashHosp")
    |> range(start: inicio, stop: fim)
    |> filter(fn: (r) => r["_field"] == "LAEA")
    // dB → linear
    |> map(fn: (r) => ({r with _value: math.pow(x: 10.0, y: r._value / 10.0)}))
    // percentil 50 em linear
    |> quantile(q: 0.50, method: "estimate_tdigest")
    // linear → dB
    |> map(fn: (r) => ({r with
        _value: 10.0 * math.log(x: r._value) / math.log(x: 10.0),
        _field: "LA50_horario"
    }))
    |> to(bucket: "sounddash_stats", org: "ISEL")

// ── P95 — percentil 95 em linear ──────────────────────────────────────────
from(bucket: "SoundDashHosp")
    |> range(start: inicio, stop: fim)
    |> filter(fn: (r) => r["_field"] == "LAEA")
    // dB → linear
    |> map(fn: (r) => ({r with _value: math.pow(x: 10.0, y: r._value / 10.0)}))
    // percentil 95 em linear
    |> quantile(q: 0.95, method: "estimate_tdigest")
    // linear → dB
    |> map(fn: (r) => ({r with
        _value: 10.0 * math.log(x: r._value) / math.log(x: 10.0),
        _field: "LA95_horario"
    }))
    |> to(bucket: "sounddash_stats", org: "ISEL")

// ── EventDetect — contagem de eventos por hora ────────────────────────────
// Não é dB, por isso soma diretamente
from(bucket: "SoundDashHosp")
    |> range(start: inicio, stop: fim)
    |> filter(fn: (r) => r["_field"] == "EventDetect")
    |> filter(fn: (r) => r["_value"] > 0.0)
    |> count()
    |> map(fn: (r) => ({r with _field: "EventCount_horario"}))
    |> to(bucket: "sounddash_stats", org: "ISEL")
