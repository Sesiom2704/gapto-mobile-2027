# ============================================================
# GAPTO MOBILE 2027
# Fichero: run_f03_01_b03.ps1
# Ruta: scripts/postgres/run_f03_01_b03.ps1
# Descripción: Ejecuta y valida F03-01-B03 secuencialmente en Neon y Supabase.
# Versión: 0.1.1
# ============================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Migration = Join-Path $ProjectRoot 'migrations\0030_f03_01_tables_b03_reglas_previsiones.sql'
$Tests = @(
    (Join-Path $ProjectRoot 'tests\database\test_001_bootstrap.py'),
    (Join-Path $ProjectRoot 'tests\database\test_002_tables_b01.py'),
    (Join-Path $ProjectRoot 'tests\database\test_003_tables_b02.py'),
    (Join-Path $ProjectRoot 'tests\database\test_004_tables_b03.py')
)
foreach ($Path in @($Migration) + $Tests) { if (-not (Test-Path -LiteralPath $Path)) { throw "F03-01-B03 RUNNER: falta $Path" } }

function Invoke-PsqlScalar {
    param([Parameter(Mandatory=$true)][string]$Url,[Parameter(Mandatory=$true)][string]$Sql)
    $Output = & psql $Url -v ON_ERROR_STOP=1 -At -c $Sql 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($Output -join [Environment]::NewLine) }
    return (($Output -join "`n").Trim())
}

function Invoke-B03Provider {
    param([string]$Provider,[string]$Url,[string]$ExpectedDatabase,[string]$ExpectedUser)
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "F03-01-B03 :: $Provider"
    Write-Host "============================================================"
    $Identity = Invoke-PsqlScalar -Url $Url -Sql "SELECT current_database() || '|' || current_user || '|' || current_setting('server_version');"
    $P = $Identity -split '\|',3
    if ($P.Count -ne 3) { throw "F03-01-B03 ${Provider}: identidad no interpretable: $Identity" }
    if ($P[0] -ne $ExpectedDatabase) { throw "F03-01-B03 ${Provider}: base incorrecta. Esperada=$ExpectedDatabase; real=$($P[0])" }
    if ($P[1] -ne $ExpectedUser) { throw "F03-01-B03 ${Provider}: usuario incorrecto. Esperado=$ExpectedUser; real=$($P[1])" }
    if (-not $P[2].StartsWith('17.')) { throw "F03-01-B03 ${Provider}: PostgreSQL 17.x requerido; real=$($P[2])" }
    Write-Host "Database: $($P[0]) | User: $($P[1]) | PostgreSQL: $($P[2])"

    $State = Invoke-PsqlScalar -Url $Url -Sql @"
SELECT (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='gapto' AND c.relkind='r')
|| '|' ||
(SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='gapto' AND c.relkind='r' AND c.relname IN ('reglas_financieras','regla_versiones','regla_excepciones','previsiones'));
"@
    $S = $State -split '\|',2
    if ($S.Count -ne 2) { throw "F03-01-B03 ${Provider}: estado no interpretable: $State" }
    $Total=[int]$S[0]; $Block=[int]$S[1]
    if ($Total -eq 28 -and $Block -eq 0) {
        Write-Host 'Estado previo correcto. Aplicando 0030...'
        & psql $Url -v ON_ERROR_STOP=1 -f $Migration
        if ($LASTEXITCODE -ne 0) { throw "F03-01-B03 ${Provider}: fallo aplicando 0030." }
    } elseif ($Total -eq 32 -and $Block -eq 4) {
        Write-Host 'B03 ya materializado; no se reaplica.'
    } else {
        throw "F03-01-B03 ${Provider}: drift previo. total_gapto=$Total; tablas_b03=$Block"
    }

    $env:GAPTO_TEST_DATABASE_URL=$Url
    Write-Host 'Ejecutando regresion B00+B01+B02+B03...'
    & py -m pytest $Tests -v
    if ($LASTEXITCODE -ne 0) { throw "F03-01-B03 ${Provider}: pytest ha fallado." }

    $Final = Invoke-PsqlScalar -Url $Url -Sql @"
SELECT (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='gapto' AND c.relkind='r')
|| '|' ||
(SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='gapto' AND c.relkind='r' AND c.relname IN ('reglas_financieras','regla_versiones','regla_excepciones','previsiones'));
"@
    if ($Final -ne '32|4') { throw "F03-01-B03 ${Provider}: postestado inesperado: $Final; esperado=32|4" }
    Write-Host "F03-01-B03 ${Provider}: PASSED (32 tablas acumuladas; 4 tablas B03)."
}

if ([string]::IsNullOrWhiteSpace($env:GAPTO_NEON_DATABASE_URL)) { throw 'F03-01-B03 RUNNER: falta GAPTO_NEON_DATABASE_URL.' }
if ([string]::IsNullOrWhiteSpace($env:GAPTO_SUPABASE_DATABASE_URL)) { throw 'F03-01-B03 RUNNER: falta GAPTO_SUPABASE_DATABASE_URL.' }

Push-Location $ProjectRoot
try {
    Invoke-B03Provider -Provider 'Neon' -Url $env:GAPTO_NEON_DATABASE_URL -ExpectedDatabase 'gapto2027_test' -ExpectedUser 'neondb_owner'
    Invoke-B03Provider -Provider 'Supabase' -Url $env:GAPTO_SUPABASE_DATABASE_URL -ExpectedDatabase 'postgres' -ExpectedUser 'postgres'
    Write-Host ""
    Write-Host '============================================================'
    Write-Host 'F03-01-B03 PORTABILIDAD: PASSED EN NEON + SUPABASE'
    Write-Host '============================================================'
} finally { Pop-Location }
