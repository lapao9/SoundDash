# Grafana — corrigir médias (média energética)

Os painéis do dashboard `Dash1` (uid `aemh0e2wamy2od`) faziam `aggregateWindow(fn: mean)` diretamente
sobre valores em dB. Isso é uma média **aritmética** de decibéis, que subestima o nível equivalente.

A média correta de níveis sonoros é **energética**:

```
Leq = 10 · log10( (1/N) · Σ 10^(Li/10) )
```

Em Flux: converter para linear → `mean` → voltar a dB.
Picos e máximos (`LCpeak`, `LAFmax`, ...) agregam-se com `max`; mínimos (`LAFmin`) com `min`.

Como aplicar: Grafana → Dash1 → painel → *Edit* → substituir a query → *Apply* → guardar o dashboard.
(Depois exportar o JSON para `grafana/` para ficar no repositório.)

---

## Painel 1 — "Níveis Sonoros em Tempo Real" (LAEA, LCpeak, LAFmax, LAFmin)

Só muda o bloco `Auxmean`:

```flux
import "math"

Auxmax = from(bucket: "SoundDashHosp")
    |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
    |> filter(fn: (r) =>
      r["_measurement"] == "${sensorName}" and
      ( r["_field"] == "LCpeak" or r["_field"] == "LAFmax" )
    )
    |> aggregateWindow(every: v.windowPeriod, fn: max, createEmpty: false)

Auxmin = from(bucket: "SoundDashHosp")
    |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
    |> filter(fn: (r) => r["_measurement"] == "${sensorName}" and r["_field"] == "LAFmin")
    |> aggregateWindow(every: v.windowPeriod, fn: min, createEmpty: false)

// LAEA: média ENERGÉTICA (dB -> linear -> média -> dB)
Auxmean = from(bucket: "SoundDashHosp")
    |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
    |> filter(fn: (r) => r["_measurement"] == "${sensorName}" and r["_field"] == "LAEA")
    |> map(fn: (r) => ({ r with _value: math.pow(x: 10.0, y: r._value / 10.0) }))
    |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
    |> map(fn: (r) => ({ r with _value: 10.0 * math.log10(x: r._value) }))

union(tables: [Auxmax, Auxmin, Auxmean])
```

---

## Painel 12 — "Comparativo por Parâmetro" (multi-sensor, `${param}`)

A função de agregação passa a depender do parâmetro escolhido. Substituir **cada uma** das queries
(A = `sensor_id[0]`, B = `sensor_id[1]`, C = `sensor_id[2]`) pelo modelo abaixo, mudando só o índice
`IDX` (0, 1, 2) e a condição `length(arr: sensor_id) > IDX`:

```flux
import "math"

sensor_id = ${sensorName:json}
IDX = 0
param = "${param}"

dados = if length(arr: sensor_id) > IDX then
  from(bucket: "SoundDashHosp")
    |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
    |> filter(fn: (r) => r["_measurement"] == sensor_id[IDX] and r["_field"] == param)
else
  from(bucket: "SoundDashHosp")
    |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
    |> filter(fn: (r) => false)

resultado =
  if param == "LCpeak" or param == "LAFmax" then
    dados |> aggregateWindow(every: v.windowPeriod, fn: max, createEmpty: false)
  else if param == "LAFmin" then
    dados |> aggregateWindow(every: v.windowPeriod, fn: min, createEmpty: false)
  else
    // LAEA e restantes níveis equivalentes: média energética
    dados
      |> map(fn: (r) => ({ r with _value: math.pow(x: 10.0, y: r._value / 10.0) }))
      |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
      |> map(fn: (r) => ({ r with _value: 10.0 * math.log10(x: r._value) }))

resultado
  |> map(fn: (r) => ({ r with _field: param + " " + string(v: r._measurement) }))
```

> Na query A a condição é sempre verdadeira (há pelo menos 1 sensor); pode-se usar a versão
> sem o `if` se preferires.

---

## Nota — Painéis 7 e 15 (bandas de 1/3 de oitava)

A lista de campos destes painéis **não inclui `02000_Hz`** (salta de `01600_Hz` para `02500_Hz`).
Acrescentar:

```flux
    r._field == "02000_Hz" or
```

ao `filter`, e no `map` atribuir-lhe ordem e etiqueta entre 1.6k e 2.5k, por exemplo:

```flux
      else if r._field == "02000_Hz" then "019b"
...
      else if r._field == "02000_Hz" then "2k"
```

(`"019b"` ordena-se entre `"019"` e `"020"` sem ser preciso renumerar as restantes.)

---

## Fuso horário

O dashboard está configurado com `timezone: browser`, por isso o Grafana já mostra as horas locais
(Lisboa). Não é preciso alterar nada.
