# Adicionar Tailscale a uma Estação Existente

---

## Antes de começar

Ter à mão:

- IP Tailscale do **servidor** (`100.83.72.121`) — visível em [login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines)
- **Auth Key** gerada em [login.tailscale.com/admin/settings/keys](https://login.tailscale.com/admin/settings/keys) → marcar **Reusable, POR AGORA É:**

**kSU6bpZa9711CNTRL-7fPhfsEmbwcXefvsSi2mxcQYQqGrpD7f**

---

## Passo 1 — Instalar e autenticar o Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --authkey=tskey-auth-kSU6bpZa9711CNTRL-7fPhfsEmbwcXefvsSi2mxcQYQqGrpD7f
sudo systemctl enable tailscaled
```

Confirmar que está na rede:

```bash
tailscale ip -4          # deve mostrar 100.x.x.x
ping 100.83.72.121 -c 3     # IP do servidor — deve responder
```

---

## Passo 2 — Copiar os ficheiros atualizados

No **PC**, a partir da raiz do repositório SoundDash ( ou do zip ):

```bash
scp sensor/filesInSensor/SoundMeterSemaf_ver3_class.py  laa@<IP_PI>:/home/laa/SoundMeterSemaf2/
scp sensor/filesInSensor/station_config_receiver.py     laa@<IP_PI>:/home/laa/SoundMeterSemaf2/
scp sensor/filesInSensor/SoundMeterSemaf_config.json    laa@<IP_PI>:/home/laa/SoundMeterSemaf2/
```

---

## Passo 3 — Atualizar o broker no config.json

Na **Pi**:

```bash
nano /home/laa/SoundMeterSemaf2/SoundMeterSemaf_config.json
```

Alterar só o campo `broker`:

```json
"mqtt": {
    "broker": "100.83.72.121",
    "port": 1884
}
```

Guardar: `Ctrl+O` → Enter → `Ctrl+X`

---

## Passo 4 — Reiniciar e verificar

Primeiro confirmar o nome do serviço,

vai aparecer algo como "SoundMeterSemaf_ver2.service" que é o
Nome do Serviço

```bash
sudo systemctl list-units --type=service | grep -i sound
```

Depois reiniciar com o nome que aparecer:

```bash
sudo systemctl restart <NOME_DO_SERVICO>
sudo systemctl status  <NOME_DO_SERVICO>
```

Deve aparecer `active (running)` e nos logs:

---

## Verificação após reboot

```bash
sudo reboot
# (aguardar 30-60s e voltar a ligar por SSH)
tailscale status
sudo systemctl status <NOME_DO_SERVICO>
```
