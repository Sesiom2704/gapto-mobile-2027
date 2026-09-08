# ============================================================
# GAPTO MOBILE 2027
# Fichero: run_f03_01_b05.ps1
# Ruta: scripts/postgres/run_f03_01_b05.ps1
# Descripción: Aplica 0050_f03_01_tables_b05_dominios_especializados.sql
#              contra Neon y/o Supabase vía psql. Detecta si el bloque ya
#              está materializado en el proveedor y no lo reaplica.
# Versión: 0.1.0
#
# Uso:
#   $env:GAPTO_NEON_URL     = "postgresql://...neon.tech/gapto2027_test?sslmode=require"
#   $env:GAPTO_SUPABASE_URL = "postgresql://...supabase.co:5432/postgres?sslmode=require"
#   ./run_f03_01_b05.ps1 -Provider Neon
#   ./run_f03_01_b05.ps1 -Provider Supabase
#   ./run_f03_01_b05.ps1 -Provider Both
#
# Nunca hardcodear credenciales en este fichero: siempre por variable de entorno.
# ============================================================

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Neon", "Supabase", "Both")]
    [string]$Provider
)

$ErrorActionPreference = "Stop"

$MigrationFile = Join-Path $PSScriptRoot "..\..\migrations\0050_f03_01_tables_b05_dominios_especializados.sql"
$B05Marker = "derechos_obligaciones_financieras"  # primera tabla del bloque

function Test-BlockAlreadyApplied {
    param([string]$ConnString)
    $checkSql = "SELECT to_regclass('gapto.$B05Marker') IS NOT NULL;"
    $result = psql $ConnString -tAc $checkSql
    return ($result.Trim() -eq "t")
}

function Invoke-MigrationOn {
    param([string]$ProviderName, [string]$ConnString)

    if (-not $ConnString) {
        throw "No hay cadena de conexion para ${ProviderName}: define la variable de entorno correspondiente."
    }

    Write-Host "==> ${ProviderName}: comprobando si F03-01-B05 ya esta materializado..."
    if (Test-BlockAlreadyApplied -ConnString $ConnString) {
        Write-Host "==> ${ProviderName}: F03-01-B05 ya presente. No se reaplica 0050." -ForegroundColor Yellow
        return
    }

    Write-Host "==> ${ProviderName}: aplicando 0050_f03_01_tables_b05_dominios_especializados.sql ..."
    psql $ConnString -v ON_ERROR_STOP=1 -f $MigrationFile
    if ($LASTEXITCODE -ne 0) {
        throw "F03-01-B05 fallo en ${ProviderName} (psql exit code $LASTEXITCODE)."
    }
    Write-Host "==> ${ProviderName}: F03-01-B05 aplicado correctamente." -ForegroundColor Green
}

if ($Provider -eq "Neon" -or $Provider -eq "Both") {
    Invoke-MigrationOn -ProviderName "Neon" -ConnString $env:GAPTO_NEON_URL
}

if ($Provider -eq "Supabase" -or $Provider -eq "Both") {
    Invoke-MigrationOn -ProviderName "Supabase" -ConnString $env:GAPTO_SUPABASE_URL
}

Write-Host "F03-01-B05: ejecucion finalizada." -ForegroundColor Cyan
