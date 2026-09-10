# ============================================================
# GAPTO MOBILE 2027
# Fichero: run_f03_01_b15.ps1
# Ruta: scripts/postgres/run_f03_01_b15.ps1
# Descripción: Aplica 0180_f03_01_b15_secdef_internal_auditoria.sql contra
#              Neon y/o Supabase vía psql. Detecta si el bloque ya está
#              materializado y no lo reaplica. Tras aplicar, imprime la
#              huella de paridad (owner, prosecdef, search_path, firma y
#              md5 del cuerpo) para comparar entre proveedores sin
#              depender de la suite de pytest.
# Versión: 0.1.0
#
# Uso:
#   $env:GAPTO_NEON_URL     = "postgresql://...neon.tech/gapto2027_test?sslmode=require"
#   $env:GAPTO_SUPABASE_URL = "postgresql://...supabase.co:5432/postgres?sslmode=require"
#   ./run_f03_01_b15.ps1 -Provider Neon
#   ./run_f03_01_b15.ps1 -Provider Supabase
#   ./run_f03_01_b15.ps1 -Provider Both
#
# Nunca hardcodear credenciales en este fichero: siempre por variable de entorno.
# ============================================================

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Neon", "Supabase", "Both")]
    [string]$Provider
)

$ErrorActionPreference = "Stop"

$MigrationFile = Join-Path $PSScriptRoot "..\..\migrations\0180_f03_01_b15_secdef_internal_auditoria.sql"

# Marcador del bloque: la unica funcion SECURITY DEFINER de F03-01-B15.
$B15Marker = "gapto.fn_registrar_auditoria(varchar,uuid,varchar,jsonb,jsonb,text)"

# Huella de paridad. El md5 del cuerpo detecta cualquier divergencia de
# texto entre proveedores, no solo de metadatos.
$FingerprintSql = @"
SELECT p.proname
    || '|owner=' || pg_catalog.pg_get_userbyid(p.proowner)
    || '|secdef=' || p.prosecdef::text
    || '|' || pg_catalog.array_to_string(p.proconfig, ',')
    || '|args=' || pg_catalog.pg_get_function_identity_arguments(p.oid)
    || '|md5body=' || pg_catalog.md5(p.prosrc)
  FROM pg_catalog.pg_proc p
 WHERE p.oid = '$B15Marker'::regprocedure;
"@

# Comprobaciones de contrato que no requieren impersonar gapto_runtime.
# Ver F03-01-B15 / D-4: el rol administrativo de Neon/Supabase NO tiene
# camino SET ROLE hacia gapto_runtime, asi que la verificacion funcional
# completa depende de la suite pytest con un rol que si pueda hacerlo.
$ContractSql = @"
SELECT 'secdef_total=' || (SELECT count(*) FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'gapto' AND p.prosecdef)
    || ' runtime_insert_auditoria=' || pg_catalog.has_table_privilege('gapto_runtime','gapto.auditoria','INSERT')::text
    || ' runtime_select_auditoria=' || pg_catalog.has_table_privilege('gapto_runtime','gapto.auditoria','SELECT')::text
    || ' runtime_insert_tablas=' || (SELECT count(*) FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
          CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) acl
          JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
         WHERE n.nspname = 'gapto' AND c.relkind = 'r'
           AND r.rolname = 'gapto_runtime' AND acl.privilege_type = 'INSERT')
    || ' internal_usage=' || pg_catalog.has_schema_privilege('gapto_internal','gapto','USAGE')::text
    || ' internal_create=' || pg_catalog.has_schema_privilege('gapto_internal','gapto','CREATE')::text
    || ' internal_superficie=' || (SELECT count(*) FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
          CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) acl
          JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
         WHERE n.nspname = 'gapto' AND c.relkind = 'r' AND r.rolname = 'gapto_internal')
    || ' internal_bypassrls=' || (SELECT rolbypassrls FROM pg_catalog.pg_roles WHERE rolname = 'gapto_internal')::text
    || ' public_execute=' || pg_catalog.has_function_privilege('public','$B15Marker','EXECUTE')::text
    || ' runtime_execute=' || pg_catalog.has_function_privilege('gapto_runtime','$B15Marker','EXECUTE')::text
    || ' backup_execute=' || pg_catalog.has_function_privilege('gapto_backup','$B15Marker','EXECUTE')::text;
"@

function Test-BlockAlreadyApplied {
    param([string]$ConnString)
    $checkSql = "SELECT to_regprocedure('$B15Marker') IS NOT NULL;"
    $result = psql $ConnString -tAc $checkSql
    return ($result.Trim() -eq "t")
}

function Show-Fingerprint {
    param([string]$ProviderName, [string]$ConnString)
    $fp = (psql $ConnString -tAc $FingerprintSql).Trim()
    $ct = (psql $ConnString -tAc $ContractSql).Trim()
    Write-Host "    ${ProviderName} huella  : $fp"
    Write-Host "    ${ProviderName} contrato: $ct"
}

function Invoke-MigrationOn {
    param([string]$ProviderName, [string]$ConnString)

    if (-not $ConnString) {
        throw "No hay cadena de conexion para ${ProviderName}: define la variable de entorno correspondiente."
    }

    Write-Host "==> ${ProviderName}: comprobando si F03-01-B15 ya esta materializado..."
    if (Test-BlockAlreadyApplied -ConnString $ConnString) {
        Write-Host "==> ${ProviderName}: F03-01-B15 ya presente. No se reaplica 0180." -ForegroundColor Yellow
        Show-Fingerprint -ProviderName $ProviderName -ConnString $ConnString
        return
    }

    Write-Host "==> ${ProviderName}: aplicando 0180_f03_01_b15_secdef_internal_auditoria.sql ..."
    psql $ConnString -v ON_ERROR_STOP=1 -f $MigrationFile
    if ($LASTEXITCODE -ne 0) {
        throw "F03-01-B15 fallo en ${ProviderName} (psql exit code $LASTEXITCODE)."
    }
    Write-Host "==> ${ProviderName}: F03-01-B15 aplicado correctamente." -ForegroundColor Green
    Show-Fingerprint -ProviderName $ProviderName -ConnString $ConnString
}

if ($Provider -eq "Neon" -or $Provider -eq "Both") {
    Invoke-MigrationOn -ProviderName "Neon" -ConnString $env:GAPTO_NEON_URL
}

if ($Provider -eq "Supabase" -or $Provider -eq "Both") {
    Invoke-MigrationOn -ProviderName "Supabase" -ConnString $env:GAPTO_SUPABASE_URL
}

Write-Host "F03-01-B15: ejecucion finalizada." -ForegroundColor Cyan
Write-Host "Recuerda: la huella y el contrato deben ser IDENTICOS en ambos proveedores." -ForegroundColor Cyan
Write-Host "La verificacion funcional completa (camino correcto/denegado como gapto_runtime)" -ForegroundColor Cyan
Write-Host "requiere pytest con un rol que pueda SET ROLE gapto_runtime. Ver D-4." -ForegroundColor Cyan
