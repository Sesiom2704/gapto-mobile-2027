# ============================================================
# GAPTO MOBILE 2027
# Fichero: run_f03_02_concurrencia.ps1
# Ruta: scripts/postgres/run_f03_02_concurrencia.ps1
# Descripción: FASE 03, frente de concurrencia. Ejecuta la batería
#              tests/database/test_027_concurrencia.py contra la base de
#              laboratorio gapto2027_cleanroom de Neon y/o Supabase, con salida
#              JUnit XML en logs/ (ignorado por Git) y resumen de etiquetas por
#              caso.
#
#              Opcionalmente (-AplicarCadena) aplica antes la cadena 0002..0240
#              sobre el laboratorio mediante run_clean_room.py --desde 0002
#              (clean-room DE BASE: los roles gapto ya existen en la instancia).
#              Solo tiene sentido la primera vez sobre una base vacía; el runner
#              de clean-room se niega a aplicar encima de un schema gapto
#              existente.
#
#              Nunca apunta a gapto2027_test ni a la base postgres de Supabase:
#              exige que la URL termine en /gapto2027_cleanroom, y el propio test
#              vuelve a comprobar current_database().
#
# Uso (desde cualquier carpeta; el script se sitúa en la raíz del repositorio):
#   $env:GAPTO_NEON_CONCURRENCY_URL     = "postgresql://...neon.tech/gapto2027_cleanroom?sslmode=require"
#   $env:GAPTO_SUPABASE_CONCURRENCY_URL = "postgresql://...supabase.../gapto2027_cleanroom?sslmode=require"
#   ./scripts/postgres/run_f03_02_concurrencia.ps1 -Provider Supabase -AplicarCadena
#   ./scripts/postgres/run_f03_02_concurrencia.ps1 -Provider Both
#
# Conexión: directa o pooler en modo SESIÓN. El modo transacción no sirve
# (la batería mantiene transacciones abiertas en varias conexiones y el test
# lo detecta y falla en el preflight).
#
# Nunca hardcodear credenciales en este fichero: siempre por variable de entorno.
# Versión: 0.1.1  -- la salida de run_clean_room.py (-AplicarCadena) se guarda
#                   en logs/c27_<proveedor>_<marca>_cadena.log; salida de
#                   Python en UTF-8 para evitar caracteres corruptos en la
#                   consola de Windows; rutas con "/" (validas en Windows y en
#                   PowerShell 7 de Linux).
#                   v0.1.0: primera version.
# ============================================================

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Neon", "Supabase", "Both")]
    [string]$Provider,

    [switch]$AplicarCadena
)

$ErrorActionPreference = "Stop"

# Salida de Python en UTF-8 y consola en UTF-8 durante la ejecucion; se
# restauran al final.
$codificacionAnterior = [Console]::OutputEncoding
$pythonIoAnterior = $env:PYTHONIOENCODING
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$LogDir = Join-Path $RepoRoot "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

function Assert-UrlLaboratorio {
    param([string]$Proveedor, [string]$Url)
    if (-not $Url) {
        throw "Falta la URL de laboratorio para ${Proveedor}: define la variable de entorno correspondiente."
    }
    if ($Url -notmatch "/gapto2027_cleanroom(\?|$)") {
        throw "La URL de ${Proveedor} no apunta a /gapto2027_cleanroom. Esta bateria hace COMMIT real y solo se ejecuta contra el laboratorio."
    }
}

function Invoke-CadenaEnLaboratorio {
    param([string]$Proveedor, [string]$Url, [string]$Log)
    Write-Host "==> ${Proveedor}: aplicando la cadena del repositorio desde 0002 sobre gapto2027_cleanroom (clean-room DE BASE)..."
    $anterior = $env:GAPTO_CLEANROOM_URL
    $preferenciaAnterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $env:GAPTO_CLEANROOM_URL = $Url
        python (Join-Path $RepoRoot "scripts/postgres/run_clean_room.py") --desde 0002 2>&1 | Tee-Object -FilePath $Log
        $codigo = $LASTEXITCODE
    }
    finally {
        $env:GAPTO_CLEANROOM_URL = $anterior
        $ErrorActionPreference = $preferenciaAnterior
    }
    Write-Host "    Log cadena: $Log"
    if ($codigo -ne 0) {
        throw "run_clean_room.py fallo en ${Proveedor} (exit code $codigo). No se ejecuta la bateria."
    }
}

function Show-Resumen {
    param([string]$Proveedor, [string]$Xml)
    if (-not (Test-Path $Xml)) {
        Write-Host "    ${Proveedor}: no se genero JUnit XML." -ForegroundColor Red
        return
    }
    [xml]$doc = Get-Content -LiteralPath $Xml -Encoding UTF8
    $suite = $doc.testsuites.testsuite
    $props = @($suite.properties.property)
    $entorno = $props | Where-Object { $_.name -like "c27.*" }
    Write-Host ""
    Write-Host "    ${Proveedor} - tests=$($suite.tests) failures=$($suite.failures) errors=$($suite.errors) skipped=$($suite.skipped)"
    foreach ($p in $entorno) {
        Write-Host ("      {0,-24} {1}" -f $p.name, $p.value)
    }
    foreach ($p in ($props | Where-Object { $_.name -like "*.etiqueta" })) {
        $caso = $p.name.Split(".")[0]
        $color = "Green"
        if ($p.value -like "FAIL*" -or $p.value -eq "NO_CLASIFICABLE") { $color = "Red" }
        elseif ($p.value -eq "PASS_WITH_EXPECTED_DEADLOCK") { $color = "Yellow" }
        Write-Host ("      {0,-5} {1}" -f $caso, $p.value) -ForegroundColor $color
    }
    Write-Host "    JUnit: $Xml"
}

function Invoke-Bateria {
    param([string]$Proveedor, [string]$Url)
    Assert-UrlLaboratorio -Proveedor $Proveedor -Url $Url
    $marca = Get-Date -Format "yyyyMMdd-HHmmss"
    if ($AplicarCadena) {
        $logCadena = Join-Path $LogDir ("c27_{0}_{1}_cadena.log" -f $Proveedor.ToLower(), $marca)
        Invoke-CadenaEnLaboratorio -Proveedor $Proveedor -Url $Url -Log $logCadena
    }
    $xml = Join-Path $LogDir ("c27_{0}_{1}.xml" -f $Proveedor.ToLower(), $marca)
    $txt = Join-Path $LogDir ("c27_{0}_{1}.log" -f $Proveedor.ToLower(), $marca)

    Write-Host "==> ${Proveedor}: ejecutando test_027_concurrencia.py ..."
    $anterior = $env:GAPTO_CONCURRENCY_URL
    # En Windows PowerShell 5.1, 2>&1 sobre un ejecutable nativo con
    # ErrorActionPreference=Stop convierte cualquier linea de stderr en error
    # terminante. Se relaja solo durante la llamada a pytest.
    $preferenciaAnterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    Push-Location $RepoRoot
    try {
        $env:GAPTO_CONCURRENCY_URL = $Url
        python -m pytest "tests/database/test_027_concurrencia.py" -p no:cacheprovider -s -rA `
            "--junitxml=$xml" 2>&1 | Tee-Object -FilePath $txt
        $codigo = $LASTEXITCODE
    }
    finally {
        $env:GAPTO_CONCURRENCY_URL = $anterior
        $ErrorActionPreference = $preferenciaAnterior
        Pop-Location
    }
    Show-Resumen -Proveedor $Proveedor -Xml $xml
    Write-Host "    Log:   $txt"
    Write-Host "    pytest exit code: $codigo"
}

try {
    if ($Provider -eq "Neon" -or $Provider -eq "Both") {
        Invoke-Bateria -Proveedor "Neon" -Url $env:GAPTO_NEON_CONCURRENCY_URL
    }

    if ($Provider -eq "Supabase" -or $Provider -eq "Both") {
        Invoke-Bateria -Proveedor "Supabase" -Url $env:GAPTO_SUPABASE_CONCURRENCY_URL
    }
}
finally {
    [Console]::OutputEncoding = $codificacionAnterior
    $env:PYTHONIOENCODING = $pythonIoAnterior
}
