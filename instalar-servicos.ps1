<#
.SYNOPSIS
    Instala e arranca todos os serviços NSSM do SoundDash.
    Auto-detecta Python, Node.js, Nginx, Mosquitto e InfluxDB.
    Se não encontrar um componente, pede o path ao utilizador.

.NOTES
    Executar em PowerShell como Administrador.
    Colocar este ficheiro na raiz da pasta SoundDash.
#>

# ── Verificar que é Administrador ────────────────────────────────────────────
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERRO: Executa este script como Administrador." -ForegroundColor Red
    pause; exit 1
}

$ErrorActionPreference = 'Stop'

# ── Helpers de UI ─────────────────────────────────────────────────────────────
function Write-Step { Write-Host "`n► $args" -ForegroundColor Cyan }
function Write-OK   { Write-Host "  OK  $args" -ForegroundColor Green }
function Write-Warn { Write-Host "  AV  $args" -ForegroundColor Yellow }
function Write-Fail { Write-Host "  ERR $args" -ForegroundColor Red; pause; exit 1 }

function Find-Exe {
    param(
        [string]   $Label,
        [string[]] $Candidates,   # paths absolutos a verificar
        [string]   $CommandName   # nome no PATH (ex: "python", "node")
    )
    foreach ($c in $Candidates) {
        if ($c -and (Test-Path $c)) { Write-OK "$Label detectado: $c"; return $c }
    }
    if ($CommandName) {
        try {
            $found = (Get-Command $CommandName -ErrorAction Stop).Source
            Write-OK "$Label detectado via PATH: $found"
            return $found
        } catch {}
    }
    Write-Warn "$Label nao encontrado automaticamente."
    $manual = Read-Host "  Introduz o path completo para $Label"
    if (-not (Test-Path $manual)) { Write-Fail "Path invalido: $manual" }
    return $manual
}

# ── Raiz do projecto (pasta onde este .ps1 está) ─────────────────────────────
$Root      = $PSScriptRoot
$WebAppDir = Join-Path $Root "webApp"

Write-Host ""
Write-Host "================================================" -ForegroundColor Magenta
Write-Host "   SoundDash -- Instalacao de Servicos NSSM    " -ForegroundColor Magenta
Write-Host "================================================" -ForegroundColor Magenta
Write-Host "  Raiz do projecto: $Root"
Write-Host "  WebApp:           $WebAppDir"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. PYTHON
# ═══════════════════════════════════════════════════════════════════════════════
Write-Step "A detectar Python..."
$PythonExe = Find-Exe -Label "python.exe" -CommandName "python" -Candidates @(
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Python\bin\python.exe",
    "C:\Python311\python.exe",
    "C:\Python312\python.exe"
)
$pyVer = & $PythonExe --version 2>&1
Write-OK "Versao: $pyVer"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. INFLUXDB
# ═══════════════════════════════════════════════════════════════════════════════
Write-Step "A detectar InfluxDB..."
$InfluxExe = Find-Exe -Label "influxd.exe" -Candidates @(
    (Join-Path $Root "InfluxData\influxd.exe"),
    "C:\InfluxData\influxd.exe",
    "C:\Program Files\InfluxData\influxdb\influxd.exe"
)
# Dados do InfluxDB ficam em AppData do utilizador actual
$InfluxData = Join-Path $env:USERPROFILE ".influxdbv2"
Write-OK "Dados InfluxDB: $InfluxData"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. MOSQUITTO
# ═══════════════════════════════════════════════════════════════════════════════
Write-Step "A detectar Mosquitto..."
$MosquittoExe = Find-Exe -Label "mosquitto.exe" -CommandName "mosquitto" -Candidates @(
    (Join-Path $Root "mosquitto\mosquitto.exe"),
    "C:\Program Files\mosquitto\mosquitto.exe",
    "C:\mosquitto\mosquitto.exe"
)
$MosquittoDir  = Split-Path $MosquittoExe
$MosquittoConf = Join-Path $MosquittoDir "mosquittoV1.conf"
if (-not (Test-Path $MosquittoConf)) {
    Write-Warn "mosquittoV1.conf nao encontrado em $MosquittoDir"
    $MosquittoConf = Read-Host "  Introduz o path completo para o ficheiro .conf do Mosquitto"
    if (-not (Test-Path $MosquittoConf)) { Write-Fail "Ficheiro nao encontrado." }
}
Write-OK "Conf: $MosquittoConf"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. NODE-RED
# ═══════════════════════════════════════════════════════════════════════════════
Write-Step "A detectar Node.js e Node-RED..."
$NodeExe = Find-Exe -Label "node.exe" -CommandName "node" -Candidates @(
    "C:\Program Files\nodejs\node.exe",
    "$env:APPDATA\npm\node.exe"
)
$nodeVer = & $NodeExe --version 2>&1
Write-OK "Node.js versao: $nodeVer"

# Procurar red.js nos locais habituais de npm global
$NodeRedScript = $null
$npmGlobalRoot = $null
try { $npmGlobalRoot = (& npm root -g 2>&1) } catch {}

foreach ($candidate in @(
    $(if ($npmGlobalRoot) { Join-Path $npmGlobalRoot "node-red\red.js" } else { $null }),
    (Join-Path $env:APPDATA "npm\node_modules\node-red\red.js"),
    "C:\Program Files\nodejs\node_modules\node-red\red.js"
)) {
    if ($candidate -and (Test-Path $candidate)) { $NodeRedScript = $candidate; break }
}

if ($NodeRedScript) {
    Write-OK "red.js encontrado: $NodeRedScript"
} else {
    Write-Warn "Node-RED (red.js) nao encontrado automaticamente."
    $NodeRedScript = Read-Host "  Introduz o path completo para red.js"
    if (-not (Test-Path $NodeRedScript)) { Write-Fail "Ficheiro nao encontrado." }
}
$NodeRedUserDir = Join-Path $env:USERPROFILE ".node-red"
Write-OK "Node-RED userDir: $NodeRedUserDir"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. NGINX
# ═══════════════════════════════════════════════════════════════════════════════
Write-Step "A detectar Nginx..."
$NginxExe = $null

# Procurar nginx.exe em C:\ (apanha qualquer versao: nginx-1.x.x, nginx, etc.)
$nginxFound = Get-ChildItem "C:\" -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "nginx*" } |
    ForEach-Object { Get-ChildItem $_.FullName -Filter "nginx.exe" -Recurse -ErrorAction SilentlyContinue } |
    Select-Object -First 1

if ($nginxFound) { $NginxExe = $nginxFound.FullName }

if (-not $NginxExe) {
    $NginxExe = Find-Exe -Label "nginx.exe" -CommandName "nginx" -Candidates @(
        "C:\nginx\nginx.exe",
        "C:\Program Files\nginx\nginx.exe"
    )
} else {
    Write-OK "nginx.exe encontrado: $NginxExe"
}
$NginxDir = Split-Path $NginxExe


# ═══════════════════════════════════════════════════════════════════════════════
# RESUMO — confirmar antes de instalar
# ═══════════════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  Configuracao detectada:" -ForegroundColor White
Write-Host "------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  Python      : $PythonExe"
Write-Host "  InfluxDB    : $InfluxExe"
Write-Host "  InfluxData  : $InfluxData"
Write-Host "  Mosquitto   : $MosquittoExe"
Write-Host "  Mosq. conf  : $MosquittoConf"
Write-Host "  Node.js     : $NodeExe"
Write-Host "  Node-RED    : $NodeRedScript"
Write-Host "  NR userDir  : $NodeRedUserDir"
Write-Host "  Nginx       : $NginxExe"
Write-Host "  WebApp      : $WebAppDir"
Write-Host "------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

$confirm = Read-Host "Instalar os servicos NSSM com esta configuracao? (s/n)"
if ($confirm.ToLower() -ne 's') { Write-Host "Cancelado." -ForegroundColor Yellow; exit 0 }


# ═══════════════════════════════════════════════════════════════════════════════
# INSTALAR SERVICOS
# Remove o servico se ja existir, depois reinstala limpo.
# ═══════════════════════════════════════════════════════════════════════════════
function Install-Service {
    param($Name, $Exe, $AppParams, $AppDir, $Display)

    # Remover se existir
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Warn "$Name ja existe. A remover..."
        & nssm stop    $Name 2>&1 | Out-Null
        & nssm remove  $Name confirm 2>&1 | Out-Null
        Start-Sleep -Seconds 1
    }

    & nssm install $Name $Exe
    if ($AppParams) { & nssm set $Name AppParameters $AppParams }
    if ($AppDir)    { & nssm set $Name AppDirectory  $AppDir    }
    & nssm set $Name DisplayName  $Display
    & nssm set $Name Start        SERVICE_AUTO_START
    Write-OK "$Name instalado."
}

Write-Step "A instalar servicos..."

Install-Service `
    -Name      "SoundDash-InfluxDB" `
    -Exe       $InfluxExe `
    -AppParams "--bolt-path=`"$InfluxData\influxd.bolt`" --engine-path=`"$InfluxData\engine`"" `
    -Display   "SoundDash InfluxDB"

Install-Service `
    -Name      "SoundDash-Mosquitto" `
    -Exe       $MosquittoExe `
    -AppParams "-c `"$MosquittoConf`"" `
    -AppDir    $MosquittoDir `
    -Display   "SoundDash Mosquitto"

Install-Service `
    -Name      "SoundDash-NodeRED" `
    -Exe       $NodeExe `
    -AppParams "`"$NodeRedScript`" -u `"$NodeRedUserDir`"" `
    -Display   "SoundDash NodeRED"

Install-Service `
    -Name      "SoundDash-Flask" `
    -Exe       $PythonExe `
    -AppParams "run.py" `
    -AppDir    $WebAppDir `
    -Display   "SoundDash Flask Web"

Install-Service `
    -Name      "SoundDash-Nginx" `
    -Exe       $NginxExe `
    -AppDir    $NginxDir `
    -Display   "SoundDash Nginx"


# ═══════════════════════════════════════════════════════════════════════════════
# ARRANCAR TUDO
# ═══════════════════════════════════════════════════════════════════════════════
Write-Step "A arrancar servicos..."

$services = @(
    @{ Name = "SoundDash-InfluxDB";  Wait = 4 },
    @{ Name = "SoundDash-Mosquitto"; Wait = 2 },
    @{ Name = "SoundDash-NodeRED";   Wait = 4 },
    @{ Name = "SoundDash-Flask";     Wait = 3 },
    @{ Name = "SoundDash-Nginx";     Wait = 2 }
)

foreach ($svc in $services) {
    & nssm start $svc.Name 2>&1 | Out-Null
    Start-Sleep -Seconds $svc.Wait
    $state = (& nssm status $svc.Name 2>&1) -join ""
    if ($state -match "RUNNING") {
        Write-OK "$($svc.Name) -- RUNNING"
    } else {
        Write-Warn "$($svc.Name) -- $state  (verifica com: nssm status $($svc.Name))"
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
# FIM
# ═══════════════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "   Instalacao concluida!                       " -ForegroundColor Green
Write-Host "   Acede em: http://localhost                  " -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
pause
