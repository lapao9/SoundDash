# Otimização da plataforma (out 2026) — aplicar na VM

Objetivo: acabar com a lentidão e as quedas da plataforma (downloads de 1 dia, gráficos de 2–3 dias,
RAM sempre cheia), mantendo todos os cálculos exatos.

## O que muda e porquê

Testado num InfluxDB 2.7 local com dados sintéticos iguais aos do raw (~4,4 amostras/s, 66 campos):

| Problema | Antes | Depois |
|---|---|---|
| Conversão dB → linear em Flux | `math.pow(...)`: 11,7 s por hora de 1 sensor | operador `10.0 ^ (x / 10.0)`: **0,11 s** (mesmo resultado) |
| Query com variável `base` partilhada por vários ramos | lê os 66 campos em cada ramo: 2,9 s | cada ramo com o seu filtro: **0,02 s** |
| Task horária antiga (`Aggregate_Hourly`) | relê **24 h** × todos os sensores a cada hora, com `math.pow`: ~23 s por sensor·hora → com 7 sensores, mais de 1 h de trabalho por cada execução | só a última hora, com `^`: ~0,1 s por sensor·hora |
| Calendário / semana / Lden (3 h de dados) | 7,9 s (calculado sobre o raw) | **0,01 s** (bucket horário) |
| Gráficos de períodos longos | leem sempre o raw (3 dias = dezenas de milhões de pontos) | raw até 12 h; médias por minuto até 31 dias; médias por hora acima |
| Servidor web | `run.py` com `debug=True` (2 processos, debugger exposto) | `serve.py` com Waitress |
| Downloads | vários em simultâneo | um de cada vez (os outros recebem uma mensagem) |

### Dados agregados (novos buckets)

| Bucket | Preenchido por | Conteúdo (por sensor, measurement igual ao raw, ex. `sensor1`) |
|---|---|---|
| `SoundDashHosp_1m` | task `SoundDash_agregar_1m` (5 em 5 min) | 1 ponto por minuto |
| `SoundDashHosp_1h` | task `SoundDash_agregar_1h` (de hora a hora) | 1 ponto por hora |

Campos dos dois buckets (timestamp = início do minuto/hora):

- `LAEA`, `LAEC`, `LAEZ` e bandas `00025_Hz` … `20000_Hz` → média de 10^(L/10) — **escala linear**
- `n` → nº de amostras LAEA
- `LCpeak`, `LAFmax` → máximo · `LAFmin` → mínimo (dB)
- `EventDetect`, `EventType1..10` → média (fração de amostras com o evento)

Com `LAEA` e `n`, qualquer LAeq (hora, turno, dia, Lden, mês) é exato:
`LAeq = 10·log10( Σ(LAEA·n) / Σn )` — confirmado nos testes (diferença 0,0000 dB face ao raw,
incluindo horas com falhas de dados).

Nos gráficos do Grafana com períodos > 12 h, a média de cada janela é feita sobre as médias por minuto
(sem ponderar por `n`); só difere do raw em minutos com amostras em falta, e é apenas visual.
Os valores numéricos da webapp (calendário, turnos, Lden) usam sempre a ponderação exata.

---

## Antes de começar

1. **Versão do InfluxDB** (o ganho do operador `^` foi medido na 2.7). Numa linha de comandos:
   ```
   C:\Users\laa\Desktop\SoundDash\InfluxData\influxd.exe version
   ```
   Se for inferior a 2.7, avisar antes de continuar.
2. **Duração atual da task antiga** (útil para o relatório): InfluxDB → **Tasks** → `Aggregate_Hourly` →
   separador **Runs**: anotar a duração das últimas execuções.
3. **RAM atual**: Gestor de Tarefas → **Detalhes** → ordenar por *Memória*. Anotar `influxd.exe`,
   `python.exe`, `grafana-server.exe`, `node.exe`.

---

## Fase 1 — InfluxDB

### 1.1 Desativar a task antiga
**Tasks** → `Aggregate_Hourly` → desligar o interruptor (fica inativa; **não apagar** ainda).

### 1.2 Criar os buckets
**Load Data → Buckets → + Create Bucket**:
- Name: `SoundDashHosp_1m` · Delete Data: **Never** → Create
- Name: `SoundDashHosp_1h` · Delete Data: **Never** → Create

### 1.3 Criar as duas tasks
**Tasks → + Create Task → New Task**, uma de cada vez:

| Ficheiro | Name | Every | Offset |
|---|---|---|---|
| `Influx_Scripts/Tasks/task_agregar_1m.flux` | `SoundDash_agregar_1m` | `5m` | `1m` |
| `Influx_Scripts/Tasks/task_agregar_1h.flux` | `SoundDash_agregar_1h` | `1h` | `2m` |

Preencher os campos do formulário (Name, Every, Offset) como na tabela, colar o ficheiro inteiro no
editor → **Save**. (Os ficheiros não têm a linha `option task`: o editor cria-a a partir do formulário.)

### 1.4 Confirmar que correm
Passados ~5 min: **Tasks** → `SoundDash_agregar_1m` → **Runs**: estado *success*, duração de poucos
segundos. No **Data Explorer**, o bucket `SoundDashHosp_1m` deve mostrar os sensores.
A task de 1 h corre à hora certa seguinte (HH:02).

### 1.5 Preencher o histórico
As tasks só tratam dados novos. Numa linha de comandos, na pasta do projeto:
```
python Influx_Scripts\preencher_agregados.py --pausa 1
```
- Processa de hora a hora, **da mais recente para a mais antiga** (o último mês fica pronto primeiro)
  e mostra o tempo estimado.
- Pode ser interrompido com **Ctrl+C**; voltar a correr o mesmo comando continua de onde parou.
- Usa exatamente as queries das tasks (lê os ficheiros `.flux`).
- `--pausa` = segundos entre horas; aumentar (ex. `--pausa 3`) se a plataforma ficar lenta enquanto corre.

No fim, confirmar a exatidão num dia qualquer (datas em UTC):
```
python Influx_Scripts\preencher_agregados.py --verificar 2026-10-20 --sensor sensor1
```
As linhas `SoundDashHosp_1m` e `SoundDashHosp_1h` devem mostrar `diferença = +0.0000 dB`.

---

## Fase 2 — Webapp

> Fazer depois de o preenchimento (1.5) ter chegado pelo menos aos meses que se querem ver no calendário:
> o calendário passa a ler o bucket horário.

1. Atualizar o código na VM (`git pull` na pasta do projeto).
2. Instalar o Waitress no Python do serviço:
   ```
   C:\Users\laa\AppData\Local\Python\bin\python.exe -m pip install waitress
   ```
3. Passar o serviço para o `serve.py` (PowerShell como administrador):
   ```
   nssm set SoundDash-Flask AppParameters serve.py
   nssm restart SoundDash-Flask
   ```
   Os `.bat` (start/stop/restart/status) continuam iguais.
4. Testar:
   - **Estatísticas**: o calendário de um mês deve abrir em ~1 s.
   - **Monitorização por Período**: descarregar 1 h de CSV; abrir um segundo download noutro separador
     ao mesmo tempo → deve aparecer *"Já está a decorrer outro download…"*.

---

## Fase 3 — Grafana (6 painéis)

Para cada painel: abrir o link de edição, selecionar **todo** o texto da query **A**, substituir pelo
conteúdo do ficheiro e carregar em **Back to dashboard**. No fim, **Save dashboard**.

Links (na VM, com sessão iniciada como administrador):
`http://localhost:3000/grafana/d/aemh0e2wamy2od/dash1?orgId=1&editPanel=N`

| N | Painel | Ficheiro (`grafana/queries/`) | O que muda |
|---|---|---|---|
| 1 | Níveis ao longo do tempo | `painel_01_niveis.flux` | LAF passa a média energética; buckets |
| 7 | Bandas em tempo real (barras) | `painel_07_bandas_tempo_real.flux` | banda dos 2 kHz |
| 12 | Comparativo multi-sensor | `painel_12_comparativo.flux` | `^` e filtro por regex (2,5 s → 0,1 s); buckets |
| 13 | Eventos (heatmap) | `painel_13_eventos.flux` | buckets |
| 15 | Bandas no período (barras) | `painel_15_bandas_periodo.flux` | Leq de cada banda no período (era o último valor); 2 kHz; buckets |
| 16 | Espectrograma | `painel_16_espectrograma.flux` | 31,5 Hz e 2 kHz; média energética; buckets |

**Painel 16 — também a transformação:** no separador **Transform data** → *Rename fields by regex*:
Match = `0*([\d.]+)_Hz` · Replace = `$1` (a anterior não apanhava o ponto de "31.5").

O painel 14 (gauges) não muda.

No fim: **Dashboard settings → JSON Model** (ou Export → Save to file) e guardar como
`grafana/Dash1.json` no repositório.

Testar na webapp, página **Monitorização por Período**: 1 h, 1 dia, 3 dias e 20 dias — todos os gráficos
devem aparecer em poucos segundos; o espectrograma deve ter as linhas 31.5 e 2000.

---

## Fase 4 — Nginx (compressão)

Em `C:\nginx\nginx-1.29.8\conf\nginx.conf`, dentro de `http { ... }`, logo a seguir a `keepalive_timeout 65;`:
```nginx
    gzip              on;
    gzip_comp_level   1;
    gzip_min_length   1024;
    gzip_proxied      any;
    gzip_types        text/csv application/json text/css application/javascript text/plain;
```
Testar e reiniciar (PowerShell como administrador):
```
cd C:\nginx\nginx-1.29.8
.\nginx.exe -t
nssm restart SoundDash-Nginx
```
O CSV passa a viajar comprimido (~4–5× menos dados); o browser descomprime sozinho.

> O `nginx.conf` tem o token do Grafana em claro: não o copiar para o repositório sem o substituir.

---

## Fase 5 — Limpeza (1–2 semanas depois, com tudo a funcionar)

1. **Tasks** → `Aggregate_Hourly` → apagar.
2. **Load Data → Buckets** → `SoundDashHosp_hourly` → apagar (**irreversível**; depois da Fase 2 já nada o usa).

---

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| Run da task com erro *bucket not found* | bucket da Fase 1.2 em falta ou com outro nome |
| `preencher_agregados.py` dá *unauthorized* | o token de `webApp/app/config.py` não pode escrever nos buckets novos → usar `--token` com um token *All Access* |
| Calendário vazio em meses antigos | preenchimento (1.5) ainda não chegou a esses meses |
| Gráficos vazios para períodos > 12 h | task de 1 min parada ou bucket ainda vazio |
| Hora atual a faltar nos gráficos > 12 h | normal: o bucket de 1 min tem até ~6 min de atraso |
