# Correções à plataforma SoundPlatform: pedidos de 30/09/2026

Este documento descreve os 7 pontos indicados pelo Prof. Joel Paulo. Para cada um explica o problema observado, a causa no código, a solução implementada e o que muda para quem usa a plataforma.

| # | Pedido | Estado |
|---|--------|--------|
| 1 | Ordem das colunas do CSV descarregado | Corrigido |
| 2 | CSV parece acabar uma hora mais cedo | Corrigido |
| 3 | Valores com médias (LAeq, Lden, turnos) incorretos | Corrigido na webapp; queries do Grafana preparadas |
| 4 | Subtítulo "…Hospitalares e Urbanos" | Feito |
| 5 | "Níveis Sonoros em Tempo Real - dBA / dBC" | Feito |
| 6 | "Espectograma - dB" | Feito |
| 7 | Rodapé com "Lab. Áudio e Acústica (LAA) - ISEL" | Feito |

**Âmbito:** todas as alterações são na aplicação web (Flask) e afetam só a **leitura e a apresentação** dos dados. Não foram alterados os sensores, o MQTT, o Node-RED, os dados guardados no InfluxDB nem as tasks do InfluxDB.

---

## 1. Ordem das colunas do CSV

### Problema
No download do CSV (página *Monitorização por Período*), as colunas não seguiam a ordem do ficheiro gerado pelo sensor:

- **Esperado** (formato do sensor): `TimeStamp, SensorID, LAEZ, LAEC, LAEA, LZpeak, LZpeakT, LCpeak, LCpeakT, LApeak, LApeakT, LAFmax, …`
- **Obtido:** `timestamp, EventType1, 00040_Hz, LAFminT, LApeakT, LZpeakT, 00800_Hz, LAEA_SLOW_Event, EventType7, …`

### Causa
- **Ordem aleatória:** o endpoint `/api/download` juntava os nomes dos campos num `set` (conjunto) do Python. Um conjunto não tem ordem, por isso a ordem das colunas era arbitrária e podia mudar de um download para outro.
- **Nomes diferentes:** as bandas de 1/3 de oitava apareciam com o nome do InfluxDB (`00040_Hz`) em vez do nome do sensor (`BT40`).
- **Colunas em falta:** não existiam as colunas `TimeStamp` (epoch) e `SensorID`.

### Solução
- **Ordem fixa:** o CSV passa a ter uma lista fixa de 66 colunas, pela mesma ordem do ficheiro produzido pelo sensor:
  `TimeStamp, SensorID, LAEZ, LAEC, LAEA, LZpeak, LZpeakT, LCpeak, LCpeakT, LApeak, LApeakT, LAFmax, LAFmaxT, LAFmin, LAFminT, LZeq, LCeq, LAeq, BT25 … BT20000, LAEA_SLOW_Event, EventDetect, EventType1 … EventType10, Class1ID, Class1Score, Class2ID, Class2Score, Class3ID, Class3Score`
- **Nomes das bandas:** são convertidos para a nomenclatura do sensor (`00040_Hz → BT40`, `00031.5_Hz → BT31_5`).
- **`TimeStamp`:** é o instante da amostra em *epoch* (segundos, 2 casas decimais), como no ficheiro do sensor.
- **`SensorID`:** é o identificador numérico da estação (ex.: `5.0`).
- **Campos novos:** um campo que exista no InfluxDB e não conste da lista é colocado no fim, em vez de se perder.
- **Coluna de leitura:** foi acrescentada no fim uma coluna `DataHora_Lisboa` com a data e hora legíveis em hora local (ver ponto 2). Como fica no fim, não altera a posição das restantes colunas.

**Ficheiro alterado:** `webApp/app/blueprints/api/routes.py` (rota `/api/download`).

---

## 2. Intervalo do CSV "uma hora mais cedo"

### Problema
Ao pedir, por exemplo, o intervalo 18:00–19:00, o ficheiro parecia conter dados das 17:00 às 18:00.

### Causa
O intervalo pedido à base de dados estava correto. O problema estava na forma como as horas eram escritas no ficheiro:

- O InfluxDB guarda todos os instantes em **UTC**, e o CSV mostrava-os nesse fuso (ex.: `2026-09-30T17:57:00+00:00`).
- Em Portugal, na hora de verão, a hora local é **UTC+1**. Por isso, 17:57 UTC corresponde a 18:57 em Lisboa.
- Lido como hora local, o ficheiro parecia adiantado uma hora.

### Solução
- **`TimeStamp` em epoch:** é independente do fuso horário. Convertido para hora local, dá sempre a hora correta.
- **Coluna `DataHora_Lisboa`:** mostra a hora já convertida para Lisboa (ex.: `2026-09-30 18:57:00.110`), tendo em conta automaticamente as mudanças de hora de verão e de inverno.
- **Nome do ficheiro:** passa também a usar a hora local (ex.: `SoundData_Sensor5_20260930_1800_20260930_1900.csv`).

**Ficheiros alterados:**
- `webApp/app/blueprints/api/routes.py`
- `webApp/app/services/influx.py`: funções de conversão UTC ↔ hora de Lisboa.
- `webApp/app/config.py`: definição do fuso `Europe/Lisbon`.

---

## 3. Valores calculados com médias (LAeq, Lden, turnos)

### Problema
Os valores de LAeq, Lden e níveis por turno apresentados na plataforma não coincidiam com os cálculos feitos manualmente a partir dos dados.

### Causas
Foram identificados **dois erros independentes**.

#### 3a. Média aritmética de valores em dB

Nas páginas de **Estatísticas**, os valores eram calculados em duas etapas:
1. o InfluxDB calculava, para cada hora, a **média aritmética** dos níveis em dB;
2. a aplicação combinava essas médias horárias em médias diárias, por turno e Ld/Le/Ln.

Como os níveis sonoros são logarítmicos, a média tem de ser **energética**:

$$L_{eq} = 10 \log_{10}\left(\frac{1}{N}\sum_{i=1}^{N} 10^{L_i/10}\right)$$

Exemplo com dois valores, 40 dB e 60 dB:
- média aritmética: 50 dB (incorreta);
- média energética: ≈ 57 dB (correta).

A média aritmética **subestima sempre** o nível equivalente.

Nos indicadores de pico e extremos havia um problema semelhante: o LCpeak e o LAFmax de cada hora eram também uma média. Deviam ser o **máximo** da hora, e o LAFmin devia ser o **mínimo**.

O mesmo acontecia no LAeq da página *Monitorização por Período* (`/api/stats`), que era calculado sobre médias aritméticas por minuto.

#### 3b. Horas e dias contados em UTC

A divisão dos dados por hora, turno e dia era feita com a hora **UTC** e não com a hora de Lisboa. Na hora de verão, isto deslocava todos os intervalos em uma hora:

- o turno T2 (08–16h) correspondia, na prática, às 09–17h locais;
- o mesmo acontecia com o Ld (07–19h), o Le (19–23h), o Ln (23–07h) e com o limite de cada dia (meia-noite).

### Solução

**Agregação horária correta**, feita no InfluxDB (Estatísticas, vistas mensal e semanal):

| Grandeza | Agregação por hora |
|----------|--------------------|
| LAEA (e restantes níveis equivalentes) | Média energética: dB → linear → média → dB |
| LCpeak, LAFmax | Máximo |
| LAFmin | Mínimo |

- **Hora local:** os dias, os turnos (T1 00–08h, T2 08–16h, T3 16–24h) e os períodos Ld/Le/Ln são definidos em **hora de Lisboa**. O intervalo de cada dia vai da meia-noite local à meia-noite local seguinte. A contagem de eventos por hora também usa a hora local.
- **Lden diário** (`/api/lden`, usado ao clicar num dia das Estatísticas e na *Monitorização por Período*):
  - lê os valores de LAEA do dia completo e divide-os por hora local em T1/T2/T3 e Ld/Le/Ln;
  - calcula cada nível por média energética sobre os valores originais;
  - aplica a fórmula do Lden da Diretiva 2002/49/CE (Ld 12h; Le 4h, +5 dB; Ln 8h, +10 dB).
  - A fórmula já estava correta e não foi alterada. Mudou o intervalo de dados a que é aplicada.
  - Faz agora 1 consulta à base de dados em vez de 7.
- **LAeq do período** (`/api/stats`): a agregação por minuto do LAEA passou a ser energética.
- **Vista semanal:** o LCpeak por turno passou a ser o **máximo** do turno, como na vista mensal (antes era uma média).
- **Página *Monitorização por Período*:** foi corrigido o cálculo do "dia anterior" enviado para o Lden. Misturava funções de data UTC e locais, o que podia dar o dia errado perto da meia-noite.

**Ficheiros alterados:**
- `webApp/app/services/acoustics.py`: agregação horária e contagem de eventos em hora local.
- `webApp/app/blueprints/api/routes.py`: rotas `/api/lden`, `/api/calendario`, `/api/semanal` e `/api/stats`.
- `webApp/app/static/js/tempo.js`

#### Grafana

Alguns painéis do Grafana também usam média aritmética: o painel *Níveis Sonoros em Tempo Real* (LAEA) e o painel *Comparativo por Parâmetro*. Estes painéis estão configurados no servidor e não no código da aplicação.

As queries corrigidas (média energética para LAEA, máximo para picos, mínimo para LAFmin) estão em `GUIAS/GRAFANA_MEDIAS_ENERGETICAS.md`, prontas a aplicar.

Foi também detetado que os painéis de **bandas de 1/3 de oitava** não incluem a banda de **2000 Hz**. A correção está descrita no mesmo guia.

### O que muda nos valores apresentados
- Os valores de LAeq, por turno e Lden passam a ser **iguais ou superiores** aos anteriores, porque a média energética é sempre maior ou igual à aritmética.
- Na hora de verão, os valores por turno e período podem também mudar por passarem a corresponder às horas locais corretas.
- Os valores de LCpeak e LAFmax diários passam a ser os picos reais, e não picos de médias horárias.

---

## 4 a 7. Alterações de texto

| # | Local | Antes | Depois |
|---|-------|-------|--------|
| 4 | Cabeçalho (todas as páginas) | Monitorização Sonora Avançada para Ambientes Hospitalares | Monitorização Sonora Avançada para Ambientes Hospitalares **e Urbanos** |
| 5 | Monitorização em Tempo Real | Níveis Sonoros em Tempo Real - dBA | Níveis Sonoros em Tempo Real - dBA **/ dBC** |
| 6 | Monitorização em Tempo Real | Espectograma | Espectograma **- dB** |
| 7 | Rodapé (todas as páginas) | © 2025 SoundPlatform. Todos os direitos reservados. | © 2025 SoundPlatform. **Lab. Áudio e Acústica (LAA) - ISEL -** Todos os direitos reservados. |

Por coerência, os títulos equivalentes da página *Monitorização por Período* foram alterados da mesma forma ("… - dBA / dBC" e "Espectograma - dB").

**Ficheiros alterados:** `webApp/app/templates/base.html`, `atual.html` e `tempo.html`.

---

## Instalação e verificação

1. **Dependência nova:** instalar o pacote `tzdata` no Python do servidor, com `pip install tzdata`. No Windows é necessário para o Python conhecer o fuso `Europe/Lisbon`.
2. Reiniciar o serviço Flask (`nssm restart SoundDash-Flask`).
3. **CSV:** descarregar um intervalo curto (ex.: 18:00–18:05) e confirmar:
   - a ordem das colunas;
   - que a coluna `DataHora_Lisboa` começa e termina nas horas pedidas.
4. **Médias:** escolher um dia e comparar o LAeq, os turnos e o Lden da plataforma com o cálculo manual, `10·log10(média(10^(LAEA/10)))` sobre os valores do CSV desse dia, com os intervalos em hora local.
   - Pode haver diferenças da ordem de 0,1 dB nas Estatísticas, devidas a arredondamentos e ao cálculo diário ser feito a partir de valores horários.
