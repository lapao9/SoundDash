// ============================================================
// TASK 1 — Cálculo automático do Lden diário
// ============================================================
//
// O QUE FAZ:
//   Corre todos os dias à meia-noite.
//   Calcula o Lden do dia anterior para cada sensor,
//   fazendo a conversão dB → linear → média → dB corretamente
//   com o operador map(), sem descarregar dados para Python.
//   Guarda o resultado no bucket "sounddash_lden".
//
// FÓRMULA Lden (norma europeia):
//   Lden = 10 * log10(
//     (12 * 10^(Lday/10) + 4 * 10^((Levening+5)/10) + 8 * 10^((Lnight+10)/10)) / 24
//   )
//   Períodos:
//     Dia     (08h–20h) → sem penalização
//     Tarde   (20h–23h) → +5 dB
//     Noite   (23h–08h) → +10 dB
//
// ONDE CRIAR NO INFLUXDB:
//   localhost:8086 → Tasks → + Create Task
//   Every: 1d
//   Offset: 0s  (corre à meia-noite)
//   Colar este script no editor
//
// BUCKETS NECESSÁRIOS:
//   Leitura:  sounddash       (já existe)
//   Escrita:  sounddash_lden  (criar antes em Load Data → Buckets)
// ============================================================

import "math"
import "date"

// Dia anterior
ontem = date.sub(d: now(), duration: 1d)
dia_inicio = date.truncate(t: ontem, unit: 1d)

// Períodos do dia
periodo_dia_inicio    = date.add(d: dia_inicio, duration: 8h)
periodo_dia_fim       = date.add(d: dia_inicio, duration: 20h)
periodo_tarde_inicio  = date.add(d: dia_inicio, duration: 20h)
periodo_tarde_fim     = date.add(d: dia_inicio, duration: 23h)
periodo_noite1_inicio = dia_inicio
periodo_noite1_fim    = date.add(d: dia_inicio, duration: 8h)
periodo_noite2_inicio = date.add(d: dia_inicio, duration: 23h)
periodo_noite2_fim    = date.add(d: dia_inicio, duration: 24h)

// Função auxiliar: média em dB correta (dB → linear → média → dB)
calcularMediaDB = (bucket_name, sensor, start, stop) =>
    from(bucket: bucket_name)
        |> range(start: start, stop: stop)
        |> filter(fn: (r) => r["_measurement"] == sensor)
        |> filter(fn: (r) => r["_field"] == "LAEA")
        // Passo 1: converter dB → linear (pressão sonora: base 10)
        |> map(fn: (r) => ({r with _value: math.pow(x: 10.0, y: r._value / 10.0)}))
        // Passo 2: média em escala linear
        |> mean()
        // Passo 3: converter linear → dB
        |> map(fn: (r) => ({r with _value: 10.0 * math.log(x: r._value) / math.log(x: 10.0)}))

// Lista de sensores a calcular
sensores = ["sensor1", "sensor2", "sensor3"]

// Para cada sensor, calcula os 3 períodos e o Lden
sensores |> array.map(fn: (x) => {
    sensor = x

    // Médias dos 3 períodos em dB
    Lday_tables    = calcularMediaDB(bucket_name: "sounddash", sensor: sensor, start: periodo_dia_inicio,    stop: periodo_dia_fim)
    Levening_tables = calcularMediaDB(bucket_name: "sounddash", sensor: sensor, start: periodo_tarde_inicio, stop: periodo_tarde_fim)
    // Noite = 23h-24h + 00h-08h (dois segmentos)
    Lnight1_tables = calcularMediaDB(bucket_name: "sounddash", sensor: sensor, start: periodo_noite1_inicio, stop: periodo_noite1_fim)
    Lnight2_tables = calcularMediaDB(bucket_name: "sounddash", sensor: sensor, start: periodo_noite2_inicio, stop: periodo_noite2_fim)

    Lday     = (Lday_tables |> findRecord(fn: (key) => true, idx: 0))._value
    Levening  = (Levening_tables |> findRecord(fn: (key) => true, idx: 0))._value
    Lnight1  = (Lnight1_tables |> findRecord(fn: (key) => true, idx: 0))._value
    Lnight2  = (Lnight2_tables |> findRecord(fn: (key) => true, idx: 0))._value

    // Média da noite (juntar os dois segmentos)
    Lnight_linear = (math.pow(x: 10.0, y: Lnight1 / 10.0) + math.pow(x: 10.0, y: Lnight2 / 10.0)) / 2.0
    Lnight = 10.0 * math.log(x: Lnight_linear) / math.log(x: 10.0)

    // Fórmula Lden oficial
    lden_linear = (
        12.0 * math.pow(x: 10.0, y: Lday / 10.0) +
        4.0  * math.pow(x: 10.0, y: (Levening + 5.0) / 10.0) +
        8.0  * math.pow(x: 10.0, y: (Lnight + 10.0) / 10.0)
    ) / 24.0

    Lden = 10.0 * math.log(x: lden_linear) / math.log(x: 10.0)

    // Guardar resultado no bucket sounddash_lden
    array.from(rows: [{
        _time:        dia_inicio,
        _measurement: sensor,
        _field:       "Lden",
        _value:       Lden,
        Lday:         Lday,
        Levening:      Levening,
        Lnight:       Lnight
    }])
        |> to(bucket: "sounddash_lden", org: "admin")

    return {sensor: sensor, Lden: Lden}
})
