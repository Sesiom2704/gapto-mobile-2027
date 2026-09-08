# ============================================================
# GAPTO MOBILE 2027
# Fichero: run_f03_01_b04.ps1
# Ruta: scripts/postgres/run_f03_01_b04.ps1
# Descripción: Aplica 0040_f03_01_tables_b04_hechos_tesoreria.sql contra
#              Neon y/o Supabase vía psql. Detecta si el bloque ya está
#              materializado en el proveedor y no lo reaplica (idempotente).
# Versión: 0.1.0
#
# Uso:
#   $env:GAPTO_NEON_URL     = "postgresql://...neon.tech/gapto2027_test?sslmode=require"
#   $env:GAPTO_SUPABASE_URL = "postgresql://...supabase.co:5432/postgres?sslmode=require"
#   ./run_f03_01_b04.ps1 -Provider Neon
#   ./run_f03_01_b04.ps1 -Provider Supabase
#   ./run_f03_01_b04.ps1 -Provider Both
#
# Nunca hardcodear credenciales en este fichero: siempre por variable de entorno.
# ============================================================

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Neon", "Supabase", "Both")]
    [string]$Provider
)

$ErrorActionPreference = "Stop"

$MigrationFile = Join-Path $PSScriptRoot "..\..\migrations\0040_f03_01_tables_b04_hechos_tesoreria.sql"
$B04Marker = "hechos_financieros"  # primera tabla del bloque; su existencia = bloque ya aplicado

function Test-BlockAlreadyApplied {
    param([string]$ConnString)
    $checkSql = "SELECT to_regclass('gapto.$B04Marker') IS NOT NULL;"
    $result = psql $ConnString -tAc $checkSql
    return ($result.Trim() -eq "t")
}

function Invoke-MigrationOn {
    param([string]$ProviderName, [string]$ConnString)

    if (-not $ConnString) {
        throw "No hay cadena de conexion para ${ProviderName}: define la variable de entorno correspondiente."
    }

    Write-Host "==> ${ProviderName}: comprobando si F03-01-B04 ya esta materializado..."
    if (Test-BlockAlreadyApplied -ConnString $ConnString) {
        Write-Host "==> ${ProviderName}: F03-01-B04 ya presente. No se reaplica 0040." -ForegroundColor Yellow
        return
    }

    Write-Host "==> ${ProviderName}: aplicando 0040_f03_01_tables_b04_hechos_tesoreria.sql ..."
    psql $ConnString -v ON_ERROR_STOP=1 -f $MigrationFile
    if ($LASTEXITCODE -ne 0) {
        throw "F03-01-B04 fallo en ${ProviderName} (psql exit code $LASTEXITCODE)."
    }
    Write-Host "==> ${ProviderName}: F03-01-B04 aplicado correctamente." -ForegroundColor Green
}

if ($Provider -eq "Neon" -or $Provider -eq "Both") {
    Invoke-MigrationOn -ProviderName "Neon" -ConnString $env:GAPTO_NEON_URL
}

if ($Provider -eq "Supabase" -or $Provider -eq "Both") {
    Invoke-MigrationOn -ProviderName "Supabase" -ConnString $env:GAPTO_SUPABASE_URL
}

Write-Host "F03-01-B04: ejecucion finalizada." -ForegroundColor Cyan
