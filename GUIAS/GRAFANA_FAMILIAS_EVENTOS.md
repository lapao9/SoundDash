# Grafana: nomes dos eventos por família (Hospital / Urbano)

O gráfico **"Tipos de Eventos Sonoros"** é o painel 13 do dashboard `Dash1` (uid `aemh0e2wamy2od`). Aparece nas páginas *Monitorização em Tempo Real*, *Monitorização por Período* e *Display*.

A webapp tem botões **Hospital / Urbano** e envia a escolha ao Grafana no URL do painel (`&var-familia=hospital` ou `&var-familia=urbano`). Para o Grafana usar esse valor, é preciso fazer **dois passos no servidor**.

> Enquanto estes passos não forem feitos, o gráfico continua a mostrar os nomes Hospital, como hoje. Nada deixa de funcionar.

## Correspondência dos nomes

| Campo | Hospital | Urbano (família Aircraft) |
|---|---|---|
| EventType1 | Alarme | Aviões |
| EventType2 | Impacto | Comboios |
| EventType3 | Música | Gritos |
| EventType4 | Gritos | Impulsivo |
| EventType5 | Respiração | Música |
| EventType6 | Conversas | Conversas |
| EventType7 | Telefone | Buzinas |
| EventType8 | Líquidos | Cães a ladrar |
| EventType9 | Rodas | Atmosfera |
| EventType10 | Assobios | Automóvel |

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
import "strings"

familia = "${familia}"

// Carácter invisível (zero-width space). Serve só para fixar a ordem das linhas:
// o heatmap ordena pelo nome, e cada linha leva um número diferente destes caracteres à frente.
z = "\xe2\x80\x8b"

// Posição de cada tipo: 10 = linha de cima (tipo 10) ... 1 = penúltima (tipo 1), 0 = última (Evento detetado)
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
  |> map(fn: (r) => ({ r with _field: strings.repeat(v: z, i: pos(f: r._field)) + nome(f: r._field) }))
  // só tempo, valor e nome: sem isto o Grafana acrescenta o sensor ao nome ("Gritos sensor1")
  |> keep(columns: ["_time", "_value", "_field"])
```

3. Abrir o separador **Transform data** (ou **Transformations**), por baixo do gráfico, ao lado de **Query**. Apagar todas as transformações *Rename by regex* (`EventType1 → Alarme`, `EventType2 → Impacto`, …, e a última `(.*) → $1`) com o ícone do caixote do lixo 🗑️.
   - Os nomes passam a vir da query, por isso estas renomeações deixam de ser precisas.
   - Se ficassem, a regex `EventType1` também apanharia `EventType10` e podia trocar nomes.
   - Se algo correr mal antes de guardar, basta não gravar e recarregar a página para voltar ao estado anterior.
4. **Eixo Y** (painel da direita, secção **Y Axis**):
   - **Reverse:** desligado. A ordem já vem da query: tipo 10 em cima, tipo 1 em baixo, "Evento detetado" na última linha.
   - **Axis width:** `130`. Fixa a largura da coluna dos nomes para nenhum ficar cortado à esquerda. É obrigatório: os caracteres invisíveis enganam o cálculo automático da largura. O nome mais comprido é "Evento detetado"; se algum continuar cortado, aumentar para `150`.
5. **Apply** e guardar o dashboard.
6. Exportar o JSON do dashboard para a pasta `grafana/` do repositório, para ficar registado.

## Verificação

- Na página *Monitorização em Tempo Real*, carregar em **Urbano**: o eixo deve mostrar, de cima para baixo, Automóvel, Atmosfera, Cães a ladrar, …, Comboios, Aviões, Evento detetado, sem nomes cortados.
- Carregar em **Hospital**: deve mostrar Assobios, Rodas, Líquidos, …, Impacto, Alarme, Evento detetado, pela mesma ordem.
- A escolha fica guardada no browser e aplica-se também a *Monitorização por Período*, *Display* e *Eventos Detetados*.
