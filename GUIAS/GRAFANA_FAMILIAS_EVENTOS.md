# Grafana: nomes dos eventos por família (Hospital / Urbano)

O gráfico **"Tipos de Eventos Sonoros"** é o painel 13 do dashboard `Dash1` (uid `aemh0e2wamy2od`). Aparece nas páginas *Monitorização em Tempo Real*, *Monitorização por Período* e *Display*.

A webapp tem botões **Hospital / Urbano** e envia a escolha ao Grafana no URL do painel (`&var-familia=hospital` ou `&var-familia=urbano`). Para o Grafana usar esse valor, é preciso fazer **dois passos no servidor**.

> Enquanto estes passos não forem feitos, o gráfico continua a mostrar os nomes Hospital, como hoje. Nada deixa de funcionar.

## Correspondência dos nomes

Correspondência Hospital → Urbano enviada pelo André (nov 2026). Confirmada pelo código do sensor
(`SoundMeterSemaf_ver3_class.py`): no modelo urbano os índices 0 e 9 são "Atmosfera" e "Music";
no modelo hospital o índice 2 é "Music".

| Campo | Hospital | Urbano (família Aircraft) |
|---|---|---|
| EventType1 | Alarme | Atmosfera |
| EventType2 | Impacto | Automóveis |
| EventType3 | Música | Aviões |
| EventType4 | Gritos | Buzinas |
| EventType5 | Respiração | Comboios |
| EventType6 | Conversas | Conversas |
| EventType7 | Telefone | Cães |
| EventType8 | Líquidos | Gritos |
| EventType9 | Rodas | Impulsivo |
| EventType10 | Assobios | Música |

A mesma tabela está em `webApp/app/static/js/utils.js` (`FAMILIAS_EVENTOS`) e na query do painel 13
(`grafana/queries/painel_13_eventos.flux`). Se mudar um nome, alterar nos dois sítios e colar de novo
a query no painel 13 do Grafana.

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
2. Substituir a query por todo o conteúdo do ficheiro `grafana/queries/painel_13_eventos.flux`
   (abrir o ficheiro, copiar tudo e colar no editor da query). Esse ficheiro é a única versão
   atualizada: já tem os nomes corrigidos e escolhe os dados raw / 1 min / 1 h conforme a duração.

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

- Na página *Monitorização em Tempo Real*, carregar em **Urbano**: o eixo deve mostrar, de cima para baixo, Música, Impulsivo, Gritos, …, Automóveis, Atmosfera, Evento detetado, sem nomes cortados.
- Carregar em **Hospital**: deve mostrar Assobios, Rodas, Líquidos, …, Impacto, Alarme, Evento detetado, pela mesma ordem.
- A escolha fica guardada no browser e aplica-se também a *Monitorização por Período*, *Display* e *Eventos Detetados*.
