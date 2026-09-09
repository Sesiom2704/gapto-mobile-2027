# ============================================================
# GAPTO MOBILE 2027
# Fichero: run_f03_01_b02.ps1
# Ruta: scripts/postgres/run_f03_01_b02.ps1
# Descripción: Ejecuta y valida F03-01-B02 de forma secuencial en Neon
#              y Supabase, con prechecks de identidad/estado y pytest.
# Versión: 0.1.1
# ============================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Migration = Join-Path $ProjectRoot 'migrations\0020_f03_01_tables_b02_catalogos_cuentas_entidades.sql'
$TestBootstrap = Join-Path $ProjectRoot 'tests\database\test_001_bootstrap.py'
$TestB01 = Join-Path $ProjectRoot 'tests\database\test_002_tables_b01.py'
$TestB02 = Join-Path $ProjectRoot 'tests\database\test_003_tables_b02.py'

foreach ($Path in @($Migration, $TestBootstrap, $TestB01, $TestB02)) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "F03-01-B02 RUNNER: falta el fichero requerido: $Path"
    }
}

function Invoke-PsqlScalar {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Sql
    )

    $Output = & psql $Url -v ON_ERROR_STOP=1 -At -c $Sql 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($Output -join [Environment]::NewLine)
    }

    return (($Output -join "`n").Trim())
}

function Invoke-B02Provider {
    param(
        [Parameter(Mandatory = $true)][string]$Provider,
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$ExpectedDatabase,
        [Parameter(Mandatory = $true)][string]$ExpectedUser
    )

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "F03-01-B02 :: $Provider"
    Write-Host "============================================================"

    $Identity = Invoke-PsqlScalar -Url $Url -Sql @"
SELECT current_database()
       || '|' || current_user
       || '|' || current_setting('server_version');
"@

    $IdentityParts = $Identity -split '\|', 3
    if ($IdentityParts.Count -ne 3) {
        throw "F03-01-B02 ${Provider}: respuesta de identidad no interpretable: $Identity"
    }

    $Database = $IdentityParts[0]
    $User = $IdentityParts[1]
    $Version = $IdentityParts[2]

    Write-Host "Destino:  $Provider"
    Write-Host "Database: $Database"
    Write-Host "User:     $User"
    Write-Host "Version:  $Version"

    if ($Database -ne $ExpectedDatabase) {
        throw "F03-01-B02 ${Provider}: base incorrecta. Esperada=$ExpectedDatabase; real=$Database"
    }

    if ($User -ne $ExpectedUser) {
        throw "F03-01-B02 ${Provider}: usuario efectivo incorrecto. Esperado=$ExpectedUser; real=$User"
    }

    if (-not $Version.StartsWith('17.')) {
        throw "F03-01-B02 ${Provider}: PostgreSQL 17.x requerido; real=$Version"
    }

    $State = Invoke-PsqlScalar -Url $Url -Sql @"
SELECT
    (SELECT count(*)
       FROM pg_catalog.pg_class c
       JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'gapto'
        AND c.relkind = 'r')
    || '|'
    ||
    (SELECT count(*)
       FROM pg_catalog.pg_class c
       JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'gapto'
        AND c.relkind = 'r'
        AND c.relname IN (
            'tipos_hecho',
            'magnitudes',
            'categoria_magnitudes',
            'preferencias_registro',
            'plantillas_registro',
            'cuentas',
            'cuenta_capacidades',
            'cuenta_participaciones',
            'entidades',
            'entidad_participaciones',
            'entidad_relaciones',
            'contextos'
        ));
"@

    $StateParts = $State -split '\|', 2
    if ($StateParts.Count -ne 2) {
        throw "F03-01-B02 ${Provider}: estado de tablas no interpretable: $State"
    }

    $TotalTables = [int]$StateParts[0]
    $B02Tables = [int]$StateParts[1]

    if ($TotalTables -eq 16 -and $B02Tables -eq 0) {
        Write-Host "Estado previo correcto: 16 tablas B01; B02 aún no aplicado."
        Write-Host "Aplicando migration B02..."

        & psql $Url -v ON_ERROR_STOP=1 -f $Migration
        if ($LASTEXITCODE -ne 0) {
            throw "F03-01-B02 ${Provider}: fallo aplicando la migration."
        }
    }
    elseif ($TotalTables -eq 28 -and $B02Tables -eq 12) {
        Write-Host "B02 ya está materializado en $Provider; no se reaplica. Se validará el estado existente."
    }
    else {
        throw "F03-01-B02 ${Provider}: drift previo. total_gapto=$TotalTables; tablas_b02=$B02Tables. No se ejecuta SQL."
    }

    $env:GAPTO_TEST_DATABASE_URL = $Url

    Write-Host "Ejecutando regresión B00+B01+B02..."
    & py -m pytest $TestBootstrap $TestB01 $TestB02 -v
    if ($LASTEXITCODE -ne 0) {
        throw "F03-01-B02 ${Provider}: pytest ha fallado."
    }

    $FinalState = Invoke-PsqlScalar -Url $Url -Sql @"
SELECT
    (SELECT count(*)
       FROM pg_catalog.pg_class c
       JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'gapto'
        AND c.relkind = 'r')
    || '|'
    ||
    (SELECT count(*)
       FROM pg_catalog.pg_class c
       JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'gapto'
        AND c.relkind = 'r'
        AND c.relname IN (
            'tipos_hecho',
            'magnitudes',
            'categoria_magnitudes',
            'preferencias_registro',
            'plantillas_registro',
            'cuentas',
            'cuenta_capacidades',
            'cuenta_participaciones',
            'entidades',
            'entidad_participaciones',
            'entidad_relaciones',
            'contextos'
        ));
"@

    if ($FinalState -ne '28|12') {
        throw "F03-01-B02 ${Provider}: postestado inesperado: $FinalState; esperado=28|12"
    }

    Write-Host "F03-01-B02 ${Provider}: PASSED (28 tablas acumuladas; 12 tablas B02)."
}

if ([string]::IsNullOrWhiteSpace($env:GAPTO_NEON_DATABASE_URL)) {
    throw 'F03-01-B02 RUNNER: falta GAPTO_NEON_DATABASE_URL.'
}

if ([string]::IsNullOrWhiteSpace($env:GAPTO_SUPABASE_DATABASE_URL)) {
    throw 'F03-01-B02 RUNNER: falta GAPTO_SUPABASE_DATABASE_URL.'
}

Push-Location $ProjectRoot
try {
    Invoke-B02Provider `
        -Provider 'Neon' `
        -Url $env:GAPTO_NEON_DATABASE_URL `
        -ExpectedDatabase 'gapto2027_test' `
        -ExpectedUser 'neondb_owner'

    Invoke-B02Provider `
        -Provider 'Supabase' `
        -Url $env:GAPTO_SUPABASE_DATABASE_URL `
        -ExpectedDatabase 'postgres' `
        -ExpectedUser 'postgres'

    Write-Host ""
    Write-Host '============================================================'
    Write-Host 'F03-01-B02 PORTABILIDAD: PASSED EN NEON + SUPABASE'
    Write-Host '============================================================'
}
finally {
    Pop-Location
}
