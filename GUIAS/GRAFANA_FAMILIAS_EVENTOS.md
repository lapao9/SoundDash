# Grafana: nomes dos eventos por família (Hospital / Urbano)

O gráfico **"Tipos de Eventos Sonoros"** é o painel 13 do dashboard `Dash1` (uid `aemh0e2wamy2od`). Aparece nas páginas *Monitorização em Tempo Real*, *Monitorização por Período* e *Display*.

A webapp tem botões **Hospital / Urbano** e envia a escolha ao Grafana no URL do painel (`&var-familia=hospital` ou `&var-familia=urbano`). Para o Grafana usar esse valor, é preciso fazer **dois passos no servidor**.

> Enquanto estes passos não forem feitos, o gráfico continua a mostrar os nomes Hospital, como hoje. Nada deixa de funcionar.

## Correspondência dos nomes

| Campo (nº no gráfico) | Hospital | Urbano (família Aircraft) |
|---|---|---|
| EventType1 (01) | Alarme | Aviões |
| EventType2 (02) | Impacto | Comboios |
| EventType3 (03) | Música | Gritos |
| EventType4 (04) | Gritos | Impulsivo |
| EventType5 (05) | Respiração | Música |
| EventType6 (06) | Conversas | Conversas |
| EventType7 (07) | Telefone | Buzinas |
| EventType8 (08) | Líquidos | Cães a ladrar |
| EventType9 (09) | Rodas | Atmosfera |
| EventType10 (10) | Assobios | Automóvel |

A mesma tabela está em `webApp/app/static/js/utils.js` (`FAMILIAS_EVENTOS`). Se mudar um nome, alterar nos dois sítios.

---

## Passo 1: criar a variável `familia` no dashboard

1. Abrir o dashboard **Dash1** → ⚙️ **Settings** → **Variables** → **New variable**.
2. Preencher:
   - **Variable type:** `Custom`
   - **Name:** `familia`
   - **Label:** `Família de eventos`
   - **Custom options (values separated by comma):** `hospital,urbano`
   - **Hide:** `Variable` (a escolha é feita pelos botões da webapp)
3. **Apply** e guardar o dashboard (💾 **Save dashboard**).

## Passo 2: alterar o painel 13 ("Tipos de Eventos Sonoros")

1. No painel → **Edit**.
2. Substituir a query por:

```flux
familia = "${familia}"

// Nomes numerados (01..10 = EventType1..10) para o heatmap manter sempre a mesma ordem
nome = (f) =>
  if familia == "urbano" then
    (if f == "EventType1" then "01 Aviões"
     else if f == "EventType2" then "02 Comboios"
     else if f == "EventType3" then "03 Gritos"
     else if f == "EventType4" then "04 Impulsivo"
     else if f == "EventType5" then "05 Música"
     else if f == "EventType6" then "06 Conversas"
     else if f == "EventType7" then "07 Buzinas"
     else if f == "EventType8" then "08 Cães a ladrar"
     else if f == "EventType9" then "09 Atmosfera"
     else if f == "EventType10" then "10 Automóvel"
     else if f == "EventDetect" then "Evento detetado"
     else f)
  else
    (if f == "EventType1" then "01 Alarme"
     else if f == "EventType2" then "02 Impacto"
     else if f == "EventType3" then "03 Música"
     else if f == "EventType4" then "04 Gritos"
     else if f == "EventType5" then "05 Respiração"
     else if f == "EventType6" then "06 Conversas"
     else if f == "EventType7" then "07 Telefone"
     else if f == "EventType8" then "08 Líquidos"
     else if f == "EventType9" then "09 Rodas"
     else if f == "EventType10" then "10 Assobios"
     else if f == "EventDetect" then "Evento detetado"
     else f)

from(bucket: "SoundDashHosp")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) =>
    r["_measurement"] == "${sensorName}" and
    (
      r["_field"] == "EventType1" or r["_field"] == "EventType2" or
      r["_field"] == "EventType3" or r["_field"] == "EventType4" or
      r["_field"] == "EventType5" or r["_field"] == "EventType6" or
      r["_field"] == "EventType7" or r["_field"] == "EventType8" or
      r["_field"] == "EventType9" or r["_field"] == "EventType10" or
      r["_field"] == "EventDetect"
    )
  )
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
  |> map(fn: (r) => ({ r with _field: nome(f: r._field) }))
  // só tempo, valor e nome: sem isto o Grafana acrescenta o sensor ao nome ("Gritos sensor1")
  |> keep(columns: ["_time", "_value", "_field"])
```

3. Abrir o separador **Transform data** (ou **Transformations**), por baixo do gráfico, ao lado de **Query**. Apagar todas as transformações *Rename by regex* (`EventType1 → Alarme`, `EventType2 → Impacto`, …, e a última `(.*) → $1`) com o ícone do caixote do lixo 🗑️.
   - Os nomes passam a vir da query, por isso estas renomeações deixam de ser precisas.
   - Se ficassem, a regex `EventType1` também apanharia `EventType10` e podia trocar nomes.
   - Se algo correr mal antes de guardar, basta não gravar e recarregar a página para voltar ao estado anterior.
4. **Ordem das linhas:** no painel da direita, secção **Y Axis**, ativar **Reverse**.
   - O heatmap ordena as linhas pelo nome. Com os nomes numerados e o Reverse ligado, fica **01 em cima e 10 em baixo**, com "Evento detetado" na última linha.
   - Se a ordem aparecer ao contrário, basta desligar o Reverse.
5. **Apply** e guardar o dashboard.
6. Exportar o JSON do dashboard para a pasta `grafana/` do repositório, para ficar registado.

## Verificação

- Na página *Monitorização em Tempo Real*, carregar em **Urbano**: o eixo deve mostrar, de cima para baixo, 01 Aviões, 02 Comboios, …, 10 Automóvel, Evento detetado.
- Carregar em **Hospital**: deve mostrar 01 Alarme, 02 Impacto, …, 10 Assobios, Evento detetado, pela mesma ordem.
- A escolha fica guardada no browser e aplica-se também a *Monitorização por Período*, *Display* e *Eventos Detetados*.
