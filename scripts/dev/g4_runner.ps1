# ============================================================
# GAPTO MOBILE 2027
# Fichero: g4_runner.ps1
# Ruta: scripts/dev/g4_runner.ps1
# Descripcion: Runner de G4 de F05-GATE (F05 §49.16.2 G4; §64.7: G4 en Neon
#   virgen sobre el HEAD final). Encadena EN SERIE los tramos del G4 completo
#   y deja un manifiesto SHA-256 y la duracion de cada tramo:
#     hija            base del gate: se COMPRUEBA que la hija esta virgen y se
#                     escribe inicio.txt (evidencia_neon_inicio.py: inicio_utc,
#                     virginidad, lc_messages). El runner no crea ramas Neon
#                     (las crea la orquestacion). En Ensayo se recrea antes
#                     una base local vacia.
#     firma_antes     firma READ ONLY de la referencia gapto2027_cleanroom.
#     replay          run_clean_room.py --desde 0002 sobre la hija.
#     huellas_antes   huellas D-111 tras el replay (evidencia_neon_huellas.py).
#     suites          tests/database, tests/migration (y laboratorio RV3
#                     LOCAL), inventarios, sin BD, backend+api en es_ES y en C.
#     concurrencia    catalogo de series en serie (+ test_027 aparte), LOCAL.
#     jest            Jest --runInBand y tsc, LOCAL.
#     e2e             catalogo de E2E web, LOCAL.
#     huellas_despues huellas D-111 tras las suites.
#     post            postcomprobacion «base virgen» (evidencia_neon_post.py).
#     mutantes        catalogo de arneses, SOLO LOCAL (nunca contra la hija ni
#                     la referencia).
#     firma_despues   firma de la referencia: debe ser igual a firma_antes.
#     manifiesto      manifest_sha256.txt de la carpeta de evidencia.
#   Modo Ensayo: todo contra el cluster desechable 127.0.0.1:5463; la «hija» y
#   la «referencia» son bases locales (simulacion de la parte Neon). Con
#   -Reducido, cada tramo largo ejecuta solo una muestra fija (no es una
#   regresion completa) para medir el guion y su sobrecarga.
#   Modo Neon: exige -HostHija y -HostRef (ep-*.neon.tech, sin pooler, y
#   distintos). La URL se construye SIN contrasena: libpq la toma de
#   pgpass.conf, que nadie lee. Ninguna URL se imprime ni se escribe. Si la
#   autenticacion falla: STOP-NEON, sin otras vias.
#   Los catalogos de concurrencia, E2E y mutantes son los scripts sh de la
#   regresion integral (por defecto, los de F05-D052 paso 8) y se pasan por
#   parametro; el runner fija el orden, la serie y la evidencia. No lleva
#   rutas absolutas (test_rv3_000): -Dist, -Lanzador y los catalogos se pasan
#   siempre por parametro y se exigen solo en los tramos que los usan.
# Uso:
#   powershell -File scripts/dev/g4_runner.ps1 -Modo Ensayo -Evidencia <dir> -Dist <export>
#     -Lanzador <lanzar_e2e_mpg.ps1> [-Reducido] [-Tramos a,b]
#   powershell -File scripts/dev/g4_runner.ps1 -Modo Neon -HostHija ep-... -HostRef ep-...
#     -Evidencia <dir> -Dist <export> -CatalogoSerie <sh> -CatalogoMutantes <sh>
# Version: 0.1.0 (F05-07/GATE MANT-PRE-BATERIA ampliacion G)
# Version: 0.2.0 (MANT-PRE-BATERIA G, ensayo 1): sin rutas absolutas por
#   defecto (test_rv3_000); virginidad e inicio.txt con evidencia_neon_inicio.py.
# Version: 0.2.1 (MANT-PRE-BATERIA G, ensayo 2): Marca escribia en ficheros
#   sueltos del arbol ($t y $T son la misma variable en PowerShell).
# ============================================================
param(
  [ValidateSet('Ensayo', 'Neon')][string]$Modo = 'Ensayo',
  [Parameter(Mandatory = $true)][string]$Evidencia,
  [string]$Worktree = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
  [string]$Dist = '',
  [string]$HostHija = '',
  [string]$HostRef = '',
  [string]$RolNeon = 'neondb_owner',
  [string]$BaseNeon = 'gapto2027_cleanroom',
  [string]$Head = '0350',
  [string]$CatalogoSerie = '',
  [string]$CatalogoMutantes = '',
  [string]$Lanzador = '',
  [string]$Psql = 'psql',
  [string[]]$Tramos = @('hija', 'firma_antes', 'replay', 'huellas_antes', 'suites', 'concurrencia', 'jest', 'e2e',
                        'huellas_despues', 'post', 'mutantes', 'firma_despues', 'manifiesto'),
  [switch]$Reducido
)
$ErrorActionPreference = 'Continue'
$LOCAL = 'host=127.0.0.1 port=5463 user=postgres'
$PSQL = $Psql
$VARS = 'GAPTO_CLEANROOM_URL', 'GAPTO_SONDA_URL', 'GAPTO_TEST_DATABASE_URL', 'GAPTO_RV3_IMPORT_URL', 'GAPTO_CONCURRENCY_URL', 'PGPASSWORD', 'PGOPTIONS'
New-Item -ItemType Directory -Force $Evidencia | Out-Null
$Tiempos = Join-Path $Evidencia 'tiempos_g4.txt'
$Resumen = Join-Path $Evidencia 'RESUMEN_G4.txt'
$env:PYTHONIOENCODING = 'utf-8'

function Marca([string]$texto) { "$texto $(Get-Date -Format o)" | Out-File -Encoding utf8 -Append $Tiempos }
function Anota([string]$tramo, [string]$estado, [double]$seg) {
  ('{0,-16} {1,-10} {2,8:N1} s' -f $tramo, $estado, $seg) | Out-File -Encoding utf8 -Append $Resumen
}
function Stop-G4([string]$motivo) { "STOP: $motivo" | Out-File -Encoding utf8 -Append $Resumen; throw "STOP-G4: $motivo" }

# ---- destinos: nunca se imprime ninguna URL
function UrlNeon([string]$h, [string]$base) {
  if ($h -like '*-pooler*') { Stop-G4 'host pooler' }
  if ($h -notlike 'ep-*.neon.tech') { Stop-G4 'host no Neon' }
  return "postgresql://$RolNeon@$h/${base}?sslmode=require&connect_timeout=30"
}
if ($Modo -eq 'Neon') {
  if (-not $HostHija -or -not $HostRef) { Stop-G4 'modo Neon sin -HostHija o -HostRef' }
  if ($HostHija -eq $HostRef) { Stop-G4 'la hija no puede ser la referencia' }
  $URL_HIJA = UrlNeon $HostHija $BaseNeon
  $URL_REF = UrlNeon $HostRef $BaseNeon
} else {
  $URL_HIJA = "$LOCAL dbname=g4e_hija"
  $URL_REF = "$LOCAL dbname=g4e_ref"
}
$URL_LAB = "$LOCAL dbname=g4e_rv3lab"   # laboratorio RV3: siempre local

function Psql-Local([string[]]$sql) {
  $a = @('-h', '127.0.0.1', '-p', '5463', '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-q')
  foreach ($s in $sql) { $a += @('-c', $s) }
  & $PSQL @a 2>&1
}
function Base-Local([string]$nombre, [string]$plantilla = '', [string]$lc = '') {
  $crear = if ($plantilla) { "CREATE DATABASE $nombre TEMPLATE $plantilla" } else { "CREATE DATABASE $nombre" }
  $sql = @("DROP DATABASE IF EXISTS $nombre WITH (FORCE)", $crear)
  if ($lc) { $sql += "ALTER DATABASE $nombre SET lc_messages='$lc'" }
  Psql-Local $sql
}
function Py([string]$log, [string[]]$argumentos) {
  python @argumentos *> $log
  $rc = $LASTEXITCODE
  "rc=$rc" | Out-File -Encoding utf8 -Append $log
  return $rc
}
function Pytest([string]$nombre, [string]$url, [string[]]$objetivo, [string[]]$extra = @()) {
  if ($url) { $env:GAPTO_TEST_DATABASE_URL = $url } else { Remove-Item Env:GAPTO_TEST_DATABASE_URL -ErrorAction SilentlyContinue }
  $rc = Py (Join-Path $Evidencia "$nombre.log") (@('-m', 'pytest') + $objetivo + @('-q', '--tb=short', '-p', 'no:cacheprovider', "--junitxml=$(Join-Path $Evidencia "$nombre.xml")") + $extra)
  Remove-Item Env:GAPTO_TEST_DATABASE_URL -ErrorAction SilentlyContinue
  return $rc
}
# Firma READ ONLY de la referencia (mismas magnitudes que la firma de F04-R1 F7c §3). DSN por variable; solo la clase del error.
$FIRMA = @'
import os, sys, psycopg
SQL = ("SELECT pg_current_wal_lsn(), (SELECT count(*) FROM gapto.auditoria), (SELECT count(*) FROM gapto.hechos_financieros), "
       "(SELECT count(*) FROM gapto.categorias_financieras), (SELECT count(*) FROM gapto.cuentas), (SELECT count(*) FROM gapto.usuarios), "
       "(SELECT md5(string_agg(t::text, '|' ORDER BY t::text)) FROM gapto.tipos_hecho t), "
       "(SELECT count(*) FROM information_schema.tables WHERE table_schema='gapto' AND table_type='BASE TABLE'), pg_database_size(current_database())")
N = ("lsn", "auditoria", "hechos", "categorias", "cuentas", "usuarios", "md5_tipos", "tablas", "tamano")
try:
    with psycopg.connect(os.environ["GAPTO_SONDA_URL"], connect_timeout=30) as c:
        with c.transaction():
            c.execute("SET TRANSACTION READ ONLY")
            f = c.execute(SQL).fetchone()
    t = "\n".join(f"{n}={v}" for n, v in zip(N, f)); rc = 0
except Exception as e:
    t = f"FIRMA KO clase={type(e).__name__}"; rc = 1
open(sys.argv[1], "w", encoding="utf-8").write(t + "\n"); sys.exit(rc)
'@
$fFirma = Join-Path $Evidencia 'firma_ref.py'; $FIRMA | Out-File -Encoding utf8 $fFirma

# Parametros que solo exigen los tramos que los usan
$faltan = @()
$largos = @($Tramos | Where-Object { $_ -in 'concurrencia', 'e2e', 'mutantes' })
if ($largos -and -not $Dist) { $faltan += '-Dist' }
if ('e2e' -in $Tramos -and $Reducido -and -not $Lanzador) { $faltan += '-Lanzador' }
if (-not $Reducido -and ('concurrencia' -in $Tramos -or 'e2e' -in $Tramos) -and -not $CatalogoSerie) { $faltan += '-CatalogoSerie' }
if (-not $Reducido -and 'mutantes' -in $Tramos -and -not $CatalogoMutantes) { $faltan += '-CatalogoMutantes' }
if ($faltan) { Stop-G4 "faltan parametros: $($faltan -join ', ')" }

Set-Location $Worktree
git rev-parse HEAD | Out-File -Encoding utf8 (Join-Path $Evidencia 'head.txt')
git status --porcelain | Out-File -Encoding utf8 (Join-Path $Evidencia 'status_antes.txt')
"modo=$Modo reducido=$($Reducido.IsPresent) head_cadena=$Head tramos=$($Tramos -join ',')" | Out-File -Encoding utf8 $Resumen

try {
  foreach ($tr in $Tramos) {
    Marca "$tr inicio"
    $t0 = Get-Date
    $estado = 'OK'
    switch ($tr) {
      'hija' {
        if ($Modo -eq 'Ensayo') {
          Base-Local 'g4e_hija' | Out-File -Encoding utf8 (Join-Path $Evidencia 'hija.log')
          # «referencia» simulada: copia de una base en head 0350 con datos sinteticos (no se toca despues)
          Base-Local 'g4e_ref' 'm3_ref' | Out-File -Encoding utf8 -Append (Join-Path $Evidencia 'hija.log')
        }
        # inicio_utc (reloj del servidor), virginidad y lc_messages, ANTES del replay
        $env:GAPTO_CLEANROOM_URL = $URL_HIJA
        $rc = Py (Join-Path $Evidencia 'hija_inicio.log') @('scripts/dev/evidencia_neon_inicio.py', '--env', 'GAPTO_CLEANROOM_URL',
          '--salida', (Join-Path $Evidencia 'inicio.txt'), '--bloque', "F05-GATE G4 $Modo")
        Remove-Item Env:GAPTO_CLEANROOM_URL
        if ($rc -ne 0) {
          if (Select-String -Path (Join-Path $Evidencia 'hija_inicio.log') -Pattern 'OperationalError' -Quiet) { Stop-G4 'STOP-NEON: conexion a la hija fallida' }
          Stop-G4 'la hija no esta virgen (ver inicio.txt)'
        }
      }
      { $_ -in 'firma_antes', 'firma_despues' } {
        $env:GAPTO_SONDA_URL = $URL_REF
        $rc = Py (Join-Path $Evidencia "$tr.log") @('-I', $fFirma, (Join-Path $Evidencia "$tr.txt"))
        Remove-Item Env:GAPTO_SONDA_URL
        if ($rc -ne 0) { Stop-G4 'STOP-NEON: firma de la referencia fallida' }
        if ($tr -eq 'firma_despues') {
          $a = Get-Content (Join-Path $Evidencia 'firma_antes.txt') | Where-Object { $_ -notlike 'lsn=*' }
          $d = Get-Content (Join-Path $Evidencia 'firma_despues.txt') | Where-Object { $_ -notlike 'lsn=*' }
          if (Compare-Object $a $d) { $estado = 'DIFERENTE'; 'firma de la referencia DIFERENTE' | Out-File -Encoding utf8 -Append $Resumen }
        }
      }
      'replay' {
        $env:GAPTO_CLEANROOM_URL = $URL_HIJA
        $rc = Py (Join-Path $Evidencia 'replay.log') @('scripts/postgres/run_clean_room.py', '--desde', '0002')
        Remove-Item Env:GAPTO_CLEANROOM_URL
        if ($rc -ne 0) { Stop-G4 'replay fallido' }
      }
      { $_ -in 'huellas_antes', 'huellas_despues' } {
        $env:GAPTO_CLEANROOM_URL = $URL_HIJA
        $momento = if ($tr -eq 'huellas_antes') { 'tras el replay' } else { 'tras las suites' }
        $rc = Py (Join-Path $Evidencia "$tr.log") @('scripts/dev/evidencia_neon_huellas.py', '--env', 'GAPTO_CLEANROOM_URL',
          '--salida', (Join-Path $Evidencia 'huellas_d111.txt'), '--head', $Head, '--momento', "G4 $Modo $momento")
        Remove-Item Env:GAPTO_CLEANROOM_URL
        if ($rc -ne 0) { $estado = 'KO' }
      }
      'suites' {
        # Suites sobre la hija (proveedor). Laboratorio RV3 y es_ES/C: ver riesgos del informe de ensayo.
        if ($Reducido) {
          $r = @(
            (Pytest 'database' $URL_HIJA @('tests/database/test_017_seeds_sistema.py', 'tests/database/test_045_f03_06_0350_tipo_hecho_condonacion.py')),
            (Pytest 'sin_bd' '' @('tests/database/test_044_envdev_head_autorizado.py', 'tests/migration/test_rv3_000_repo_sin_datos_v3.py', 'tests/api/test_230_f05_d052_no_invocacion_f06.py')),
            (Pytest 'api_es_ES' $URL_HIJA @('tests/api/test_154_f05_01_inventario_categorias.py') @('--rootdir=tests/api'))
          )
        } else {
          Base-Local 'g4e_rv3lab' | Out-Null
          $env:GAPTO_CLEANROOM_URL = $URL_LAB
          python scripts/postgres/run_clean_room.py --desde 0002 *> (Join-Path $Evidencia 'rv3lab_replay.log')
          Remove-Item Env:GAPTO_CLEANROOM_URL
          $r = @(
            (Pytest 'database' $URL_HIJA @('tests/database')),
            (Pytest 'migration' '' @('tests/migration')),
            (& { $env:GAPTO_RV3_IMPORT_URL = $URL_LAB; $x = Pytest 'migration_lab' '' @('tests/migration'); Remove-Item Env:GAPTO_RV3_IMPORT_URL; $x }),
            (Pytest 'sin_bd' '' @('tests/database/test_044_envdev_head_autorizado.py', 'tests/migration/test_rv3_000_repo_sin_datos_v3.py', 'tests/api/test_230_f05_d052_no_invocacion_f06.py')),
            (& { $env:PGOPTIONS = '-c lc_messages=es_ES'; $x = Pytest 'suite_es_ES' $URL_HIJA @('tests/backend', 'tests/api') @('--rootdir=tests/api'); Remove-Item Env:PGOPTIONS; $x }),
            (& { $env:PGOPTIONS = '-c lc_messages=C'; $x = Pytest 'suite_C' $URL_HIJA @('tests/backend', 'tests/api') @('--rootdir=tests/api'); Remove-Item Env:PGOPTIONS; $x })
          )
        }
        if ($r | Where-Object { $_ -ne 0 }) { $estado = 'KO' }
      }
      'concurrencia' {
        if ($Reducido) {
          Base-Local 'g4e_conc' 'm3_ref' 'es_ES' | Out-Null
          $env:GAPTO_MANT_VINCULO_CONCURRENCIA = '1'
          $rc = Pytest 'conc_muestra' 'postgresql://postgres@127.0.0.1:5463/g4e_conc' @('tests/backend/test_14h_mant_vinculo_concurrencia_serial.py')
          Remove-Item Env:GAPTO_MANT_VINCULO_CONCURRENCIA
          if ($rc -ne 0) { $estado = 'KO' }
        } else {
          sh $CatalogoSerie $Worktree (Join-Path $Evidencia 'serie') $Dist g4c conc *> (Join-Path $Evidencia 'serie_consola.log')
        }
      }
      'jest' {
        Push-Location mobile
        if ($Reducido) { npx jest --runInBand __tests__/ds_conformidad.test.ts *> (Join-Path $Evidencia 'jest.log') }
        else { npx jest --no-cache --runInBand *> (Join-Path $Evidencia 'jest.log') }
        "rc=$LASTEXITCODE" | Out-File -Encoding utf8 -Append (Join-Path $Evidencia 'jest.log')
        if ($LASTEXITCODE -ne 0) { $estado = 'KO' }
        if (-not $Reducido) { npx tsc --noEmit *> (Join-Path $Evidencia 'tsc.log'); "rc=$LASTEXITCODE" | Out-File -Encoding utf8 -Append (Join-Path $Evidencia 'tsc.log') }
        Pop-Location
      }
      'e2e' {
        if ($Reducido) {
          & $Lanzador -Script e2e_vs01.py -Salida (Join-Path $Evidencia 'e2e_vs01') -Repo $Worktree -Dist $Dist -SinApi *> (Join-Path $Evidencia 'e2e_consola.log')
          $u = Get-Content (Join-Path $Evidencia 'e2e_vs01\e2e.log') -Tail 1
          if ($u -ne 'rc=0') { $estado = 'KO' }
        } else {
          sh $CatalogoSerie $Worktree (Join-Path $Evidencia 'serie') $Dist g4e e2e *> (Join-Path $Evidencia 'e2e_consola.log')
        }
      }
      'post' {
        $env:GAPTO_CLEANROOM_URL = $URL_HIJA
        $rc = Py (Join-Path $Evidencia 'post.log') @('scripts/dev/evidencia_neon_post.py', '--env', 'GAPTO_CLEANROOM_URL',
          '--inicio', (Join-Path $Evidencia 'inicio.txt'), '--salida', (Join-Path $Evidencia 'postcomprobacion.txt'))
        Remove-Item Env:GAPTO_CLEANROOM_URL
        if ($rc -ne 0) { $estado = 'KO' }
      }
      'mutantes' {
        # Siempre local: el catalogo crea sus propias bases vm* en 5463.
        foreach ($v in $VARS) { Remove-Item "Env:$v" -ErrorAction SilentlyContinue }
        if ($Reducido) {
          Base-Local 'g4e_rv3lab' | Out-Null
          $env:GAPTO_CLEANROOM_URL = $URL_LAB
          python scripts/postgres/run_clean_room.py --desde 0002 *> (Join-Path $Evidencia 'rv3lab_replay.log')
          Remove-Item Env:GAPTO_CLEANROOM_URL
          $env:GAPTO_RV3_IMPORT_URL = $URL_LAB
          $rc = Py (Join-Path $Evidencia 'mut_rv3_p5_muestra.log') @('scripts/dev/lanzar_mutantes_rv3_p5.py', 'M160', 'M161', 'M162')
          Remove-Item Env:GAPTO_RV3_IMPORT_URL
          if ($rc -ne 0) { $estado = 'KO' }
        } else {
          sh $CatalogoMutantes $Worktree (Join-Path $Evidencia 'mut') $Dist g4m *> (Join-Path $Evidencia 'mut_consola.log')
        }
      }
      'manifiesto' {
        git status --porcelain | Out-File -Encoding utf8 (Join-Path $Evidencia 'status_despues.txt')
        $m = Join-Path $Evidencia 'manifest_sha256.txt'
        Get-ChildItem $Evidencia -Recurse -File | Where-Object { $_.Name -ne 'manifest_sha256.txt' } | Sort-Object FullName |
          ForEach-Object { '{0}  {1}' -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.FullName.Substring($Evidencia.Length + 1) } |
          Out-File -Encoding utf8 $m
      }
      default { Stop-G4 "tramo desconocido: $tr" }
    }
    $seg = ((Get-Date) - $t0).TotalSeconds
    Anota $tr $estado $seg
    Marca "$tr fin $estado"
  }
} finally {
  foreach ($v in $VARS + 'GAPTO_MANT_VINCULO_CONCURRENCIA') { Remove-Item "Env:$v" -ErrorAction SilentlyContinue }
}
Get-Content $Resumen
