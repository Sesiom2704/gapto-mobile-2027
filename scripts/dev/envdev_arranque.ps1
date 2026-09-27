# ============================================================
# GAPTO MOBILE 2027
# Fichero: envdev_arranque.ps1
# Ruta: scripts/dev/envdev_arranque.ps1
# Descripcion: Arranque diario de ENV-DEV (D-196 / F05-D006) en Windows.
#   1) arranca el cluster PostgreSQL dedicado (puerto 5434) si esta parado
#      y comprueba que solo escucha en loopback;
#   2) comprueba perfil de red Privado y reglas de firewall 8027/8081;
#   3) abre una ventana con el backend (uvicorn en la IP LAN, puerto 8027)
#      y verifica /v1/salud con el token de desarrollo;
#   4) regenera mobile/.env con la IP actual y abre una ventana con Expo
#      (npx expo start --lan).
#   Nunca muestra el token ni contrasenas. Sin tuneles. Solo desarrollo.
#   Uso: powershell -NoProfile -ExecutionPolicy Bypass -File envdev_arranque.ps1
# Version: 0.1.0
# ============================================================
param(
    [string]$Base = 'C:\DEV\gapto-envdev',
    [string]$PgBin = 'C:\Program Files\PostgreSQL\17\bin',
    [string]$Interfaz = 'Wi-Fi'
)
$ErrorActionPreference = 'Stop'
$R = Join-Path $Base 'repo'
$V = Join-Path $Base 'venv'
$D = Join-Path $Base 'pgdata'
$L = Join-Path $Base 'local'
$M = Join-Path $R 'mobile'

function Paso([int]$n, [string]$t) { Write-Host ("[{0}] {1}/5 {2}" -f (Get-Date -Format HH:mm:ss), $n, $t) -ForegroundColor Cyan }
function Stop-Envdev([string]$t) { Write-Host "STOP: $t" -ForegroundColor Red; exit 1 }

Paso 1 'Comprobaciones previas'
foreach ($p in @("$D\PG_VERSION", "$V\Scripts\python.exe", "$L\owner.txt", "$R\backend\app\api\app.py", "$M\package.json")) {
    if (-not (Test-Path $p)) { Stop-Envdev "falta $p" }
}
$perfil = (Get-NetConnectionProfile -InterfaceAlias $Interfaz).NetworkCategory
if ("$perfil" -ne 'Private') { Stop-Envdev "la red '$Interfaz' esta en perfil $perfil; D-196 exige Private (red de casa)" }
foreach ($regla in @('Gapto2027 ENV-DEV API 8027', 'Gapto2027 ENV-DEV Metro 8081')) {
    if (-not (Get-NetFirewallRule -DisplayName $regla -ErrorAction SilentlyContinue)) { Stop-Envdev "falta la regla de firewall '$regla'" }
}
$ip = (Get-NetIPAddress -InterfaceAlias $Interfaz -AddressFamily IPv4).IPAddress
if (-not $ip) { Stop-Envdev "sin IP IPv4 en '$Interfaz'" }
Write-Host "IP LAN: $ip"

Paso 2 'Cluster PostgreSQL 5434'
& "$PgBin\pg_ctl.exe" -D $D status *> $null
if ($LASTEXITCODE -ne 0) {
    & "$PgBin\pg_ctl.exe" -D $D -l "$L\pg_envdev.log" -w start
    if ($LASTEXITCODE -ne 0) { Stop-Envdev 'pg_ctl no pudo arrancar el cluster (ver local\pg_envdev.log)' }
}
Start-Sleep -Seconds 2
$esc = @(Get-NetTCPConnection -State Listen -LocalPort 5434 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalAddress -Unique)
if ($esc.Count -eq 0) { Stop-Envdev 'el cluster no escucha en 5434' }
if (@($esc | Where-Object { $_ -notin @('127.0.0.1', '::1') }).Count -gt 0) {
    & "$PgBin\pg_ctl.exe" -D $D stop
    Stop-Envdev "el cluster escuchaba fuera de loopback ($($esc -join ', ')); detenido"
}
Write-Host 'Cluster OK (solo loopback)'

Paso 3 'Backend 8027'
if (-not (Test-Path "$L\dev_token.txt")) {
    $b = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    Set-Content -Encoding ASCII "$L\dev_token.txt" (([Convert]::ToBase64String($b)) -replace '[+/=]', '')
}
$token = (Get-Content "$L\dev_token.txt").Trim()
if (@(Get-NetTCPConnection -State Listen -LocalPort 8027 -ErrorAction SilentlyContinue).Count -gt 0) {
    Write-Host 'El puerto 8027 ya esta en uso: se asume que el backend ya esta abierto.' -ForegroundColor Yellow
} else {
    $env:GAPTO_ENV = 'development'
    $env:GAPTO_DATABASE_URL = 'host=127.0.0.1 port=5434 dbname=gapto2027_dev user=app_dev'
    $env:GAPTO_DEV_OWNER_USER_ID = (Get-Content "$L\owner.txt").Trim()
    $env:GAPTO_DEV_TOKEN = $token
    $cmdBackend = "`$host.UI.RawUI.WindowTitle='GAPTO BACKEND 8027 (no cerrar)'; & '$V\Scripts\python.exe' -m uvicorn app.api.app:create_app_desde_entorno --factory --host $ip --port 8027"
    Start-Process powershell.exe -WorkingDirectory "$R\backend" -ArgumentList @('-NoExit', '-NoProfile', '-Command', $cmdBackend)
    Remove-Item Env:GAPTO_DEV_TOKEN
}
$ok = $false
for ($i = 0; $i -lt 30 -and -not $ok; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-RestMethod "http://${ip}:8027/v1/salud" -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 3
        if ($r.estado -eq 'OK' -and $r.base -eq 'gapto2027_dev') { $ok = $true }
    } catch { }
}
if (-not $ok) { Stop-Envdev 'el backend no responde OK en /v1/salud (mira la ventana GAPTO BACKEND)' }
Write-Host 'Backend OK (gapto2027_dev)'

Paso 4 'mobile/.env'
Set-Content -Encoding ASCII "$M\.env" ("EXPO_PUBLIC_GAPTO_API_URL=http://${ip}:8027`r`nEXPO_PUBLIC_GAPTO_DEV_TOKEN=$token")
Remove-Variable token
if (-not (Test-Path "$M\node_modules")) {
    Write-Host 'Instalando dependencias moviles (npm ci, solo la primera vez)...'
    Push-Location $M
    npm ci
    $rc = $LASTEXITCODE
    Pop-Location
    if ($rc -ne 0) { Stop-Envdev 'npm ci fallo' }
}

Paso 5 'Expo (Metro 8081)'
if (@(Get-NetTCPConnection -State Listen -LocalPort 8081 -ErrorAction SilentlyContinue).Count -gt 0) {
    Write-Host 'El puerto 8081 ya esta en uso: se asume que Expo ya esta abierto.' -ForegroundColor Yellow
} else {
    $env:REACT_NATIVE_PACKAGER_HOSTNAME = $ip
    $env:EXPO_NO_TELEMETRY = '1'
    $cmdExpo = "`$host.UI.RawUI.WindowTitle='GAPTO EXPO 8081 (no cerrar)'; npx expo start --lan"
    Start-Process powershell.exe -WorkingDirectory $M -ArgumentList @('-NoExit', '-NoProfile', '-Command', $cmdExpo)
}
Write-Host ''
Write-Host 'LISTO. Escanea el QR de la ventana GAPTO EXPO con la camara del iPhone.' -ForegroundColor Green
Write-Host 'Si Windows pregunta por node.exe: CANCELAR. Para apagar: cierra las ventanas GAPTO BACKEND y GAPTO EXPO.'
