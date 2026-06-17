# Guia de Atualização das Estações de Monitorização
## Suporte a Tailscale + Arranque Automático Robusto

---

## Pré-requisitos

- Acesso SSH à Pi da estação
- Conhecer o **IP Tailscale do servidor** (formato `100.x.x.x`) — visível em [login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines)
- Uma **Tailscale Auth Key** gerada em [login.tailscale.com/admin/settings/keys](https://login.tailscale.com/admin/settings/keys) (marcar **Reusable**)

---

## Passo 1 — Instalar o Tailscale na Pi

Ligar à Pi por SSH e executar:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

Autenticar sem browser (usar a Auth Key gerada nos pré-requisitos):

```bash
sudo tailscale up --authkey=tskey-auth-XXXXXXXXXXXXXXXX
```

Confirmar que a Pi entrou na rede Tailscale:

```bash
tailscale ip -4
# deve mostrar um IP do tipo 100.x.x.x

ping 100.X.X.X -c 3
# substituir pelo IP Tailscale do SERVIDOR — deve responder
```

Garantir que o Tailscale arranca automaticamente no boot:

```bash
sudo systemctl enable tailscaled
```

---

## Passo 2 — Atualizar os ficheiros do script

Copiar os dois ficheiros atualizados do repositório para a Pi.

**Via `scp` (do PC com o repositório):**

```bash
scp sensor/filesInSensor/SoundMeterSemaf_ver3_class.py  laa@<IP_PI>:/home/laa/SoundMeterSemaf2/
scp sensor/filesInSensor/station_config_receiver.py      laa@<IP_PI>:/home/laa/SoundMeterSemaf2/
```


### O que mudou nos ficheiros

**`SoundMeterSemaf_ver3_class.py`**
- O `StationConfigReceiver` passa a ler o broker do `config.json` em vez de ter o IP hardcoded — alterar o `config.json` é suficiente, sem tocar no código
- A ligação MQTT principal tem **retry automático** (até 15 tentativas × 8 segundos ≈ 2 minutos) — o script aguarda que o Tailscale esteja ligado antes de conectar, **sem precisar de alterar o systemd**

**`station_config_receiver.py`**
- A ligação MQTT tem **retry automático** igual ao script principal
- Subscreve ao tópico `sound/control/reboot/{sensor_id}` — aceita comandos de reboot remotos enviados pela app web (página Acesso Técnico)

---

## Passo 3 — Atualizar o ficheiro de configuração

Editar o ficheiro de configuração da estação:

```bash
nano /home/laa/SoundMeterSemaf2/SoundMeterSemaf_config.json
```

Alterar a secção `mqtt`:

```json
"mqtt": {
    "broker": "100.X.X.X",
    "broker2": "ISEL-LAA.isel.priv",
    "broker3": "10.63.13.39",
    "port": 1884,
    "transport": "tcp",
    "path": "/mqtt",
    "topic": "sound/levels"
}
```

> **Atenção:** substituir `100.X.X.X` pelo IP Tailscale do servidor (ver pré-requisitos).

Guardar: `Ctrl+O` → Enter → `Ctrl+X`

---

## Passo 4 — Testar

Testar a ligação MQTT antes de reiniciar o serviço:

```bash
mosquitto_pub -h 100.X.X.X -p 1884 -t "test/ping" -m "hello"
# se não aparecer erro → ligação OK
```

Correr o script manualmente para confirmar que arranca sem erros:

```bash
cd /home/laa/SoundMeterSemaf2
python3 SoundMeterSemaf_ver3_class.py
```

Deve aparecer no terminal algo como:
```
[MQTT] Tentativa 1/15...
[MQTT] Conectado a 100.X.X.X:1884
[StationConfig] Conectado ao broker 100.X.X.X:1884
```

Se funcionar, parar com `Ctrl+C` e reiniciar o serviço oficial:

```bash
sudo systemctl restart soundmeter.service
```

---

## Passo 5 — Verificar o arranque automático

Fazer reboot completo da Pi:

```bash
sudo reboot
```

Após 30–60 segundos, ligar novamente por SSH e confirmar:

```bash
# Tailscale está ligado?
tailscale status

# Script está a correr?
sudo systemctl status soundmeter.service

# Dados a chegar ao servidor?
mosquitto_sub -h localhost -p 1884 -t "sound/levels" -C 1
# (correr no SERVIDOR — deve mostrar uma linha JSON com dados do sensor)
```

---

## Resolução de Problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| Script não arranca no boot | Tailscale ainda não ligou quando o serviço iniciou | Normal — o retry aguarda até 2 min automaticamente |
| `ping 100.X.X.X` não responde | Tailscale não está ligado | `sudo tailscale up --authkey=...` |
| `mosquitto_pub` falha | Mosquitto não está a correr no servidor | Reiniciar o serviço Mosquitto no servidor |
| Dados não chegam ao InfluxDB | IP Tailscale errado no config.json | Confirmar IP em [login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines) |
| Script crasha imediatamente | Erro no config.json | `python3 SoundMeterSemaf_ver3_class.py` manualmente para ver o erro |

---

## Notas

- Este processo repete-se para cada estação nova. Os passos 1, 2 e 3 são sempre iguais — só muda o IP da Pi no SSH.
- A Auth Key pode ser reutilizada em várias Pi (se criada como **Reusable**).
- O Tailscale é gratuito para até 100 dispositivos na mesma conta.
- Para reiniciar uma estação remotamente através da app web, aceder a **Acesso Técnico** → selecionar o sensor → **Reiniciar Estação**.
