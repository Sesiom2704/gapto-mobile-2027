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
#   powershell -File scripts/dev/g4_runner.ps1 -Modo Neon -Ventana Neon -HostHija ep-... -HostRef ep-...
#     -Evidencia <dir_neon>
#   powershell -File scripts/dev/g4_runner.ps1 -Ventana Local -Evidencia <dir_local> -EvidenciaNeon <dir_neon>
#     -Dist <export> -CatalogoSerie <sh> -CatalogoMutantes <sh> -ManifiestoCatalogos <txt> [-Reanudar]
# Version: 0.1.0 (F05-07/GATE MANT-PRE-BATERIA ampliacion G)
# Version: 0.2.0 (MANT-PRE-BATERIA G, ensayo 1): sin rutas absolutas por
#   defecto (test_rv3_000); virginidad e inicio.txt con evidencia_neon_inicio.py.
# Version: 0.2.1 (MANT-PRE-BATERIA G, ensayo 2): Marca escribia en ficheros
#   sueltos del arbol ($t y $T son la misma variable en PowerShell).
# Version: 0.3.0 (F05-D053 paso 5; F05 §67.6, AJ-F0507G4-15/16): G4 en DOS
#   ventanas sobre el MISMO SHA. -Ventana Neon (hija, firma, replay, huellas,
#   suites, post) o Local (concurrencia, jest, e2e, mutantes); Todo = ambas.
#   Trazabilidad: tramos_g4.tsv (tramo, estado, HEAD, fin UTC) y head.txt; una
#   carpeta de evidencia solo admite su HEAD. -Reanudar repite solo los tramos
#   no OK de la ventana Local (los registros previos se mueven a
#   reanudacion_<ts>); una ventana Neon cortada NO se reanuda: se descarta y
#   se repite sobre una hija nueva. -EvidenciaNeon enlaza la ventana Local con
#   la Neon y exige el mismo HEAD. Autovacuum desactivado SOLO en el cluster
#   local 127.0.0.1:5463 durante los mutantes (f03, R-ARN-01) y restaurado
#   siempre (finally). Aislamiento entre suites en la misma hija: semillas
#   intactas y residuos por suite (residuos.py, solo lectura). lc_messages: si
#   el rol de la hija no puede fijarlo, STOP antes de las suites (no SKIP).
#   Catalogos congelados: -ManifiestoCatalogos (SHA-256) obligatorio fuera de
#   -Reducido para los catalogos y el lanzador que se usen.
# Version: 0.4.0 (F05-D055 paso 1; F05 §68.2, §68.3 y §69.1, AJ-F0507G6-02..06):
#   excepcion cerrada R-LOCALE con g4_rlocale.py y g4_rlocale_catalogo.json.
#   Preflight (tramo hija): lc_messages efectivo por SQL igual al autorizado
#   (C.UTF-8 en Neon) y evidencia de compatibilidad (-Compatibilidad) con su
#   SHA-256; si no puede comprobarse o difiere, STOP-LC. Sustituye a la
#   exigencia imposible «puede fijar lc_messages». La ventana Neon ejecuta
#   backend+api UNA vez con el lc_messages del servidor (sin PGOPTIONS), con
#   la sonda por conexion (-p g4_rlocale), y valida: los siete SKIP con su
#   motivo, ningun otro SKIP, FAIL, ERROR ni XFAIL (database y suite_neon).
#   La ventana Local agrega el tramo rlocale_local: backend+api en local C y
#   en local es_ES; los siete PASS, misma coleccion que Neon y misma
#   identidad. identidad.txt (SHA de producto, de tests, del runner, de
#   g4_rlocale y de los catalogos) se escribe al inicio y debe coincidir al
#   reanudar y al enlazar ventanas; arbol limpio obligatorio fuera de
#   -Reducido; -Reanudar exige -MotivoCorte. En Ensayo la hija local puede
#   fijar lc_messages: la parte Neon de R-LOCALE queda NO EJECUTADO.
# Version: 0.4.1 (F05 §68.3, AJ-F0507G5-14; R-RUN-01): -Reanudar ARCHIVA el
#   intento cortado en vez de sobrescribirlo. Antes de repetir nada copia TODA
#   la carpeta de evidencia (salvo archivos de intentos anteriores) a
#   intento_cortado_<ts>\instantanea, con manifest_sha256.txt y sello.txt (hora
#   UTC, motivo, HEAD, tramos OK y tramos a repetir, SHA del manifiesto),
#   comprueba la copia contra el manifiesto y despues retira a
#   intento_cortado_<ts>\retirados las salidas propias de cada tramo a repetir
#   ($SALIDAS_TRAMO: prefijo del tramo y ficheros sin prefijo como local_C.*,
#   local_es_ES.*, conc_muestra.*, mut_* o tsc.log). Las carpetas compartidas
#   entre tramos (serie) quedan en su sitio y conservadas en la instantanea.
#   Rev. tras la prueba de corte (DIAG-S1): la instantanea se toma ANTES de
#   cualquier escritura de la reanudacion (head.txt, status_antes_*, RESUMEN);
#   antes RESUMEN_G4.txt ya llevaba la linea del enlace con la ventana Neon y
#   no coincidia con el intento cortado. La retirada sigue tras las validaciones.
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
  [ValidateSet('Neon', 'Local', 'Todo')][string]$Ventana = 'Todo',
  [string[]]$Tramos = @(),
  [string]$EvidenciaNeon = '',
  [string]$ManifiestoCatalogos = '',
  [string]$Compatibilidad = '',
  [string]$MotivoCorte = '',
  [switch]$Reanudar,
  [switch]$Reducido
)
$TRAMOS_NEON = @('hija', 'firma_antes', 'replay', 'huellas_antes', 'suites', 'huellas_despues', 'post', 'firma_despues', 'manifiesto')
$TRAMOS_LOCAL = @('rlocale_local', 'concurrencia', 'jest', 'e2e', 'mutantes', 'manifiesto')
# 0.4.1: salidas de cada tramo de la ventana Local que NO empiezan por su nombre (se retiran al reanudar, tras archivarlas).
# 'serie' la comparten concurrencia y e2e: no se retira (queda en la instantanea del intento cortado).
$SALIDAS_TRAMO = @{
  rlocale_local = @('local_C*', 'local_es_ES*')
  concurrencia  = @('conc_muestra*', 'serie_consola.log')
  jest          = @('tsc.log')
  e2e           = @()
  mutantes      = @('mut_*', 'mut', 'rv3lab_replay.log', 'autovacuum_local.txt')
}
if (-not $Tramos) {
  $Tramos = switch ($Ventana) {
    'Neon' { $TRAMOS_NEON }
    'Local' { $TRAMOS_LOCAL }
    default { @('hija', 'firma_antes', 'replay', 'huellas_antes', 'suites', 'rlocale_local', 'concurrencia', 'jest', 'e2e',
                'huellas_despues', 'post', 'mutantes', 'firma_despues', 'manifiesto') }
  }
}
if ($Ventana -eq 'Todo' -and -not $EvidenciaNeon) { $EvidenciaNeon = $Evidencia }
$SUITE_RLOCALE_REDUCIDA = @('tests/api/test_160_f05_01_traduccion_locale.py', 'tests/api/test_183_f05_04_corte_concepto.py')
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
$Registro = Join-Path $Evidencia 'tramos_g4.tsv'
function Registra([string]$tramo, [string]$estado) {
  "$tramo`t$estado`t$script:HeadActual`t$((Get-Date).ToUniversalTime().ToString('o'))" | Out-File -Encoding utf8 -Append $Registro
}
function Tramos-OK {
  if (-not (Test-Path $Registro)) { return @() }
  return @(Get-Content $Registro | ForEach-Object { $c = $_ -split "`t"; if ($c[1] -eq 'OK') { $c[0] } })
}

# ---- destinos: nunca se imprime ninguna URL
function UrlNeon([string]$h, [string]$base) {
  if ($h -like '*-pooler*') { Stop-G4 'host pooler' }
  if ($h -notlike 'ep-*.neon.tech') { Stop-G4 'host no Neon' }
  return "postgresql://$RolNeon@$h/${base}?sslmode=require&connect_timeout=30"
}
foreach ($tr in $Tramos) {
  if ($Ventana -eq 'Neon' -and $tr -notin $TRAMOS_NEON) { Stop-G4 "el tramo $tr no es de la ventana Neon" }
  if ($Ventana -eq 'Local' -and $tr -notin $TRAMOS_LOCAL) { Stop-G4 "el tramo $tr no es de la ventana Local" }
}
if ($Modo -eq 'Neon' -and $Ventana -ne 'Local') {
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
# Autovacuum: SOLO el cluster local desechable 127.0.0.1:5463 (Psql-Local no admite otro destino); nunca Neon.
$script:AutovacuumOff = $false
function Autovacuum-Local([ValidateSet('off', 'restaurar')][string]$accion) {
  $f = Join-Path $Evidencia 'autovacuum_local.txt'
  $antes = (& $PSQL -h 127.0.0.1 -p 5463 -U postgres -d postgres -Atc 'SHOW autovacuum' 2>&1)
  if ($accion -eq 'off') { Psql-Local @('ALTER SYSTEM SET autovacuum = off', 'SELECT pg_reload_conf()') | Out-Null; $script:AutovacuumOff = $true }
  else { Psql-Local @('ALTER SYSTEM RESET autovacuum', 'SELECT pg_reload_conf()') | Out-Null; $script:AutovacuumOff = $false }
  Start-Sleep -Milliseconds 500
  $despues = (& $PSQL -h 127.0.0.1 -p 5463 -U postgres -d postgres -Atc 'SHOW autovacuum' 2>&1)
  "$(Get-Date -Format o) $accion 127.0.0.1:5463 autovacuum $antes -> $despues" | Out-File -Encoding utf8 -Append $f
  $esperado = if ($accion -eq 'off') { 'off' } else { 'on' }
  if ("$despues".Trim() -ne $esperado) { Stop-G4 "autovacuum local no quedo en $esperado" }
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
# Aislamiento entre suites en la MISMA hija (F05 §67.6; R-G4-03): solo lectura. «base» guarda las filas de las
# tablas no vacias tras el replay (semillas) y el recuento de cada tabla; «comparar» exige que TODAS esas filas sigan
# intactas (ni borradas ni modificadas) y anota los residuos (filas nuevas por tabla) que deja cada suite.
$RESIDUOS = @'
import json, os, sys, psycopg
modo, salida = sys.argv[1], sys.argv[2]
try:
    with psycopg.connect(os.environ["GAPTO_CLEANROOM_URL"], connect_timeout=30) as c:
        with c.transaction():
            c.execute("SET TRANSACTION READ ONLY")
            tablas = [r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'gapto' ORDER BY 1")]
            n = {t: c.execute(f"SELECT count(*) FROM gapto.{t}").fetchone()[0] for t in tablas}
            if modo == "base":
                filas = {t: sorted(r[0] for r in c.execute(f"SELECT x::text FROM gapto.{t} x")) for t in tablas if n[t]}
                json.dump({"recuentos": n, "filas": filas}, open(salida, "w", encoding="utf-8"))
                print(f"base: {sum(n.values())} filas en {len(filas)} tablas no vacias"); sys.exit(0)
            base = json.load(open(sys.argv[3], encoding="utf-8"))
            perdidas = {}
            for t, fb in base["filas"].items():
                ahora = set(r[0] for r in c.execute(f"SELECT x::text FROM gapto.{t} x"))
                falta = [f for f in fb if f not in ahora]
                if falta:
                    perdidas[t] = len(falta)
    residuos = {t: n[t] - base["recuentos"].get(t, 0) for t in tablas if n[t] != base["recuentos"].get(t, 0)}
    ok = not perdidas
    lineas = [f"{sys.argv[4]}: semillas {'INTACTAS' if ok else 'ALTERADAS ' + json.dumps(perdidas)}",
              f"  residuos (filas nuevas por tabla desde el replay): {json.dumps(residuos, sort_keys=True)}"]
    open(salida, "a", encoding="utf-8").write("\n".join(lineas) + "\n"); print("\n".join(lineas)); sys.exit(0 if ok else 1)
except Exception as e:
    print(f"RESIDUOS KO clase={type(e).__name__}"); sys.exit(2)
'@
$fResiduos = Join-Path $Evidencia 'residuos.py'; $RESIDUOS | Out-File -Encoding utf8 $fResiduos


$RLOCALE = Join-Path $Worktree 'scripts\dev\g4_rlocale.py'
$CAT_RLOCALE = Join-Path $Worktree 'scripts\dev\g4_rlocale_catalogo.json'
function Sha([string]$p) { return (Get-FileHash -Algorithm SHA256 $p).Hash.ToLower() }
function RLocale([string]$log, [string[]]$argumentos) { return (Py $log (@('-I', $RLOCALE) + $argumentos)) }

# Parametros que solo exigen los tramos que los usan
$faltan = @()
$largos = @($Tramos | Where-Object { $_ -in 'concurrencia', 'e2e', 'mutantes' })
if ($largos -and -not $Dist) { $faltan += '-Dist' }
if ('e2e' -in $Tramos -and $Reducido -and -not $Lanzador) { $faltan += '-Lanzador' }
if (-not $Reducido -and ('concurrencia' -in $Tramos -or 'e2e' -in $Tramos) -and -not $CatalogoSerie) { $faltan += '-CatalogoSerie' }
if (-not $Reducido -and 'mutantes' -in $Tramos -and -not $CatalogoMutantes) { $faltan += '-CatalogoMutantes' }
if (-not $Reducido -and -not $ManifiestoCatalogos) { $faltan += '-ManifiestoCatalogos' }
if ('hija' -in $Tramos -and -not $Compatibilidad) { $faltan += '-Compatibilidad' }
if ('rlocale_local' -in $Tramos -and -not $EvidenciaNeon) { $faltan += '-EvidenciaNeon' }
if ($Reanudar -and -not $MotivoCorte) { $faltan += '-MotivoCorte' }
if ($faltan) { Stop-G4 "faltan parametros: $($faltan -join ', ')" }
# Catalogos congelados (AJ-F0507G4-15): cada catalogo y lanzador usado debe estar en el manifiesto con su SHA-256.
if ($ManifiestoCatalogos) {
  if (-not (Test-Path $ManifiestoCatalogos)) { Stop-G4 'no existe el manifiesto de catalogos' }
  $congelados = @(Get-Content $ManifiestoCatalogos | Where-Object { $_ -match '^[0-9a-f]{64}\s' } | ForEach-Object { ($_ -split '\s+')[0] })
  # 0.4.0: tambien el runner, g4_rlocale.py y la lista cerrada R-LOCALE (AJ-F0507G6-06).
  foreach ($c in @($CatalogoSerie, $CatalogoMutantes, $Lanzador, $PSCommandPath, $RLOCALE, $CAT_RLOCALE) | Where-Object { $_ }) {
    if (-not (Test-Path $c)) { Stop-G4 "no existe el catalogo $(Split-Path $c -Leaf)" }
    $h = (Get-FileHash -Algorithm SHA256 $c).Hash.ToLower()
    if ($h -notin $congelados) { Stop-G4 "catalogo no congelado o modificado: $(Split-Path $c -Leaf) ($h)" }
  }
  Copy-Item $ManifiestoCatalogos (Join-Path $Evidencia 'manifiesto_catalogos.txt') -Force
}

Set-Location $Worktree
$script:HeadActual = (git rev-parse HEAD).Trim()
$fHead = Join-Path $Evidencia 'head.txt'
if (Test-Path $Registro) {
  if (-not $Reanudar) { Stop-G4 'la carpeta de evidencia ya tiene tramos: usa otra carpeta o -Reanudar' }
  if ($Tramos | Where-Object { $_ -in $TRAMOS_NEON -and $_ -ne 'manifiesto' }) {
    Stop-G4 'una ventana Neon cortada no se reanuda: la evidencia se descarta y se repite sobre una hija nueva'
  }
}
if ((Test-Path $fHead) -and ((Get-Content $fHead -Raw).Trim() -ne $script:HeadActual)) { Stop-G4 'la evidencia es de otro HEAD (mismo SHA en todo G4)' }
if ($Reanudar) {
  # 0.4.1 (F05 §68.3, AJ-F0507G5-14): instantanea del intento cortado ANTES de escribir nada en la carpeta
  # (head.txt, status_antes_*, identidad, RESUMEN); la retirada de salidas se hace tras las validaciones.
  $hechos = Tramos-OK
  $repetir = @($Tramos | Where-Object { $_ -notin $hechos -and $_ -ne 'manifiesto' })
  $ts = Get-Date -Format yyyyMMdd-HHmmss
  $dirR = Join-Path $Evidencia "intento_cortado_$ts"
  $dirI = Join-Path $dirR 'instantanea'
  $previos = '^(intento_cortado_|reanudacion_)'
  $origen = @(Get-ChildItem $Evidencia | Where-Object { $_.Name -notmatch $previos })
  New-Item -ItemType Directory -Force $dirI | Out-Null
  foreach ($x in $origen) { Copy-Item -Recurse -Force $x.FullName $dirI }
  $mI = Join-Path $dirR 'manifest_sha256.txt'
  $filas = @(Get-ChildItem $dirI -Recurse -File | Sort-Object FullName | ForEach-Object { '{0}  {1}' -f (Sha $_.FullName), $_.FullName.Substring($dirI.Length + 1) })
  $filas | Out-File -Encoding utf8 $mI
  foreach ($f in $filas) {
    $h, $rel = $f -split '  ', 2
    $o = Join-Path $Evidencia $rel
    if (-not (Test-Path $o) -or (Sha $o) -ne $h) { Stop-G4 "la instantanea del intento cortado no coincide con el original: $rel" }
  }
  $shaM = Sha $mI
  @("fecha_utc=$((Get-Date).ToUniversalTime().ToString('o'))", "motivo=$MotivoCorte", "head=$script:HeadActual",
    "tramos_ok=$($hechos -join ',')", "tramos_a_repetir=$($repetir -join ',')", "ficheros=$($filas.Count)",
    "manifest_sha256=$shaM") | Out-File -Encoding utf8 (Join-Path $dirR 'sello.txt')
}
$script:HeadActual | Out-File -Encoding utf8 $fHead
$sucio = git status --porcelain
$sucio | Out-File -Encoding utf8 (Join-Path $Evidencia "status_antes_$(Get-Date -Format yyyyMMdd-HHmmss).txt")
if ($sucio -and -not $Reducido) { Stop-G4 'arbol no limpio: G4 exige el candidato confirmado (F05 §68.3)' }
# Identidad (F05 §68.3, §69.1 G): SHA de producto, de tests, del runner, de g4_rlocale y de los catalogos.
$identidad = [ordered]@{
  head = $script:HeadActual
  tests = (git rev-parse HEAD:tests).Trim()
  runner = Sha $PSCommandPath
  rlocale = Sha $RLOCALE
  catalogo_rlocale = Sha $CAT_RLOCALE
  catalogos = if ($ManifiestoCatalogos) { Sha $ManifiestoCatalogos } else { 'ninguno' }
}
$lineasId = @($identidad.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" })
$fId = Join-Path $Evidencia 'identidad.txt'
if (Test-Path $fId) {
  $previa = @(Get-Content $fId | Where-Object { $_ -match '^(head|tests|runner|rlocale|catalogo_rlocale|catalogos)=' })
  if (Compare-Object $previa $lineasId) { Stop-G4 'identidad distinta de la registrada: mismo SHA, runner y catalogos en todo G4 (F05 §68.3)' }
} else { $lineasId | Out-File -Encoding utf8 $fId }
if ($EvidenciaNeon) {
  $hn = Join-Path $EvidenciaNeon 'head.txt'
  if (-not (Test-Path $hn) -or (Get-Content $hn -Raw).Trim() -ne $script:HeadActual) { Stop-G4 'la ventana Neon enlazada es de otro HEAD (o no existe)' }
  $idNeon = @(Get-Content (Join-Path $EvidenciaNeon 'identidad.txt') -ErrorAction SilentlyContinue | Where-Object { $_ -match '^(head|tests|runner|rlocale|catalogo_rlocale|catalogos)=' })
  if (-not $idNeon -or (Compare-Object $idNeon $lineasId)) { Stop-G4 'la ventana Neon enlazada tiene otra identidad (SHA de tests, runner o catalogos)' }
  $okNeon = @(Get-Content (Join-Path $EvidenciaNeon 'tramos_g4.tsv') -ErrorAction SilentlyContinue | Where-Object { ($_ -split "`t")[1] -eq 'OK' }).Count
  "ventana Neon enlazada: mismo HEAD; tramos OK registrados $okNeon" | Out-File -Encoding utf8 -Append $Resumen
}
if (-not $Reanudar) { $hechos = @() }
if ($Reanudar) {
  # Retirada de las salidas propias de cada tramo a repetir (ya conservadas en la instantanea, tomada antes de escribir nada).
  $dirX = Join-Path $dirR 'retirados'
  New-Item -ItemType Directory -Force $dirX | Out-Null
  foreach ($tr in $repetir) {
    foreach ($patron in @("$tr*") + @($SALIDAS_TRAMO[$tr])) {
      if (-not $patron) { continue }
      Get-ChildItem $Evidencia -Filter $patron | Where-Object { $_.Name -notmatch $previos } | Move-Item -Destination $dirX -Force
    }
  }
  "reanudacion: tramos ya OK $($hechos -join ','); intento cortado archivado en $(Split-Path $dirR -Leaf) ($($filas.Count) ficheros, manifest $shaM); motivo: $MotivoCorte" | Out-File -Encoding utf8 -Append $Resumen
}
"modo=$Modo ventana=$Ventana reducido=$($Reducido.IsPresent) head=$script:HeadActual head_cadena=$Head tramos=$($Tramos -join ',')" | Out-File -Encoding utf8 -Append $Resumen

try {
  foreach ($tr in $Tramos) {
    if ($tr -in $hechos -and $tr -ne 'manifiesto') { Marca "$tr ya OK (reanudacion)"; continue }
    Marca "$tr inicio"
    $t0 = Get-Date
    $estado = 'OK'
    switch ($tr) {
      'hija' {
        if ($Modo -eq 'Ensayo') {
          Base-Local 'g4e_hija' '' 'C' | Out-File -Encoding utf8 (Join-Path $Evidencia 'hija.log')
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
        # Preflight lc_messages (F05 §68.2): valor efectivo por SQL y evidencia de compatibilidad; si no, STOP-LC.
        $env:GAPTO_CLEANROOM_URL = $URL_HIJA
        $a = @('preflight', '--env', 'GAPTO_CLEANROOM_URL', '--compatibilidad', $Compatibilidad, '--salida', (Join-Path $Evidencia 'preflight_lc.txt'))
        if ($Modo -eq 'Ensayo') { $a += @('--ensayo-lc', 'C') }
        $rc = RLocale (Join-Path $Evidencia 'preflight_lc.log') $a
        Remove-Item Env:GAPTO_CLEANROOM_URL
        if ($rc -ne 0) { Stop-G4 'STOP-LC: lc_messages no comprobable o distinto del autorizado, o evidencia de compatibilidad ausente (preflight_lc.txt)' }
        $lc = (Select-String -Path (Join-Path $Evidencia 'preflight_lc.txt') -Pattern 'lc_messages efectivo: (.+)$' | Select-Object -Last 1).Matches[0].Groups[1].Value
        "lc_messages_neon=$lc" | Out-File -Encoding utf8 -Append $fId
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
        # Suites sobre la hija (proveedor) con el lc_messages efectivo del servidor (F05 §68.1); el preflight debe ser CONFORME.
        $fPre = Join-Path $Evidencia 'preflight_lc.txt'
        if (-not (Test-Path $fPre) -or -not (Select-String -Path $fPre -Pattern '^PREFLIGHT lc_messages: CONFORME' -Quiet)) { Stop-G4 'STOP-LC: falta el preflight de lc_messages CONFORME (tramo hija)' }
        # Sonda por conexion (-p g4_rlocale) y suite unica backend+api sin PGOPTIONS.
        function Suite-Neon([string[]]$objetivo) {
          Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
          $env:PYTHONPATH = Join-Path $Worktree 'scripts\dev'
          $env:G4_SONDA_LC_SALIDA = Join-Path $Evidencia 'sonda_suite_neon.json'
          $x = Pytest 'suite_neon' $URL_HIJA $objetivo @('--rootdir=tests/api', '-p', 'g4_rlocale')
          Remove-Item Env:PYTHONPATH, Env:G4_SONDA_LC_SALIDA -ErrorAction SilentlyContinue
          return $x
        }
        # Aislamiento: instantanea de las semillas tras el replay y comprobacion tras cada suite.
        $fAisl = Join-Path $Evidencia 'aislamiento_suites.txt'
        $env:GAPTO_CLEANROOM_URL = $URL_HIJA
        $rcB = Py (Join-Path $Evidencia 'aislamiento_base.log') @('-I', $fResiduos, 'base', (Join-Path $Evidencia 'aislamiento_base.json'))
        Remove-Item Env:GAPTO_CLEANROOM_URL
        if ($rcB -ne 0) { Stop-G4 'no se pudo tomar la instantanea de aislamiento' }
        $script:Aislamiento = @()
        function Tras-Suite([string]$n, [int]$rc) {
          $env:GAPTO_CLEANROOM_URL = $URL_HIJA
          $x = Py (Join-Path $Evidencia "aislamiento_$n.log") @('-I', $fResiduos, 'comparar', $fAisl, (Join-Path $Evidencia 'aislamiento_base.json'), $n)
          Remove-Item Env:GAPTO_CLEANROOM_URL
          $script:Aislamiento += $x
          return $rc
        }
        if ($Reducido) {
          $r = @(
            (Tras-Suite 'database' (Pytest 'database' $URL_HIJA @('tests/database/test_017_seeds_sistema.py', 'tests/database/test_045_f03_06_0350_tipo_hecho_condonacion.py'))),
            (Pytest 'sin_bd' '' @('tests/database/test_044_envdev_head_autorizado.py', 'tests/migration/test_rv3_000_repo_sin_datos_v3.py', 'tests/api/test_230_f05_d052_no_invocacion_f06.py')),
            (Tras-Suite 'api_es_ES' (Pytest 'api_es_ES' $URL_HIJA @('tests/api/test_154_f05_01_inventario_categorias.py') @('--rootdir=tests/api'))),
            (Tras-Suite 'suite_neon' (Suite-Neon $SUITE_RLOCALE_REDUCIDA))
          )
        } else {
          Base-Local 'g4e_rv3lab' | Out-Null
          $env:GAPTO_CLEANROOM_URL = $URL_LAB
          python scripts/postgres/run_clean_room.py --desde 0002 *> (Join-Path $Evidencia 'rv3lab_replay.log')
          Remove-Item Env:GAPTO_CLEANROOM_URL
          $r = @(
            (Tras-Suite 'database' (Pytest 'database' $URL_HIJA @('tests/database'))),
            (Pytest 'migration' '' @('tests/migration')),
            (& { $env:GAPTO_RV3_IMPORT_URL = $URL_LAB; $x = Pytest 'migration_lab' '' @('tests/migration'); Remove-Item Env:GAPTO_RV3_IMPORT_URL; $x }),
            (Pytest 'sin_bd' '' @('tests/database/test_044_envdev_head_autorizado.py', 'tests/migration/test_rv3_000_repo_sin_datos_v3.py', 'tests/api/test_230_f05_d052_no_invocacion_f06.py')),
            (Tras-Suite 'suite_neon' (Suite-Neon @('tests/backend', 'tests/api')))
          )
        }
        # Validacion posterior R-LOCALE (F05 §69.1): sobre las ejecuciones contra la hija (database y suite_neon).
        # Un SKIP no cambia el rc de pytest: el rc 0 no basta y lo decide la lista cerrada.
        $jn = @('--junit', (Join-Path $Evidencia 'suite_neon.xml'))
        if (Test-Path (Join-Path $Evidencia 'database.xml')) { $jn += @('--junit', (Join-Path $Evidencia 'database.xml')) }
        if ($Modo -eq 'Ensayo') {
          'R-LOCALE Neon: NO EJECUTADO (Ensayo: la hija local puede fijar lc_messages; los siete no pueden ser SKIP)' | Out-File -Encoding utf8 -Append $Resumen
        } else {
          $rcV = RLocale (Join-Path $Evidencia 'rlocale_neon.log') (@('validar-neon') + $jn + @('--salida', (Join-Path $Evidencia 'rlocale_neon.txt'),
            '--sonda', (Join-Path $Evidencia 'sonda_suite_neon.json'), '--coleccion', (Join-Path $Evidencia 'coleccion_suite_neon.txt')))
          if ($rcV -eq 3) { Stop-G4 'STOP-LC: lc_messages de las suites distinto del autorizado o no comprobado (rlocale_neon.txt)' }
          if ($rcV -ne 0) { $estado = 'KO'; 'R-LOCALE Neon: FAIL (rlocale_neon.txt)' | Out-File -Encoding utf8 -Append $Resumen }
        }
        if ($r | Where-Object { $_ -ne 0 }) { $estado = 'KO' }
        if ($script:Aislamiento | Where-Object { $_ -ne 0 }) { $estado = 'KO'; 'aislamiento entre suites: semillas ALTERADAS (aislamiento_suites.txt)' | Out-File -Encoding utf8 -Append $Resumen }
      }
      'rlocale_local' {
        # Cobertura obligatoria R-LOCALE (F05 §68.1 req. 4, §69.1): la MISMA coleccion que suite_neon en local C y es_ES.
        $obj = if ($Reducido) { $SUITE_RLOCALE_REDUCIDA } else { @('tests/backend', 'tests/api') }
        Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
        $rl = @()
        foreach ($lc in 'C', 'es_ES') {
          $n = "local_$lc"
          Base-Local "g4l_$($lc.ToLower() -replace '_', '')" 'm3_ref' $lc | Out-File -Encoding utf8 (Join-Path $Evidencia "$n.base.log")
          $rl += Pytest $n "postgresql://postgres@127.0.0.1:5463/g4l_$($lc.ToLower() -replace '_', '')" $obj @('--rootdir=tests/api')
        }
        "lc_messages_local=C,es_ES" | Out-File -Encoding utf8 -Append $fId
        $a = @('validar-local', '--neon', (Join-Path $EvidenciaNeon 'suite_neon.xml'), '--c', (Join-Path $Evidencia 'local_C.xml'),
               '--es', (Join-Path $Evidencia 'local_es_ES.xml'), '--identidad-neon', (Join-Path $EvidenciaNeon 'identidad.txt'),
               '--identidad-local', $fId, '--salida', (Join-Path $Evidencia 'rlocale_local.txt'))
        if ($Modo -eq 'Ensayo') { $a += '--ensayo' }
        $rcV = RLocale (Join-Path $Evidencia 'rlocale_local.log') $a
        if ($rcV -ne 0 -or ($rl | Where-Object { $_ -ne 0 })) { $estado = 'KO' }
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
        # Siempre local: el catalogo crea sus propias bases vm* en 5463. Autovacuum off solo aqui y en 5463 (f03).
        foreach ($v in $VARS) { Remove-Item "Env:$v" -ErrorAction SilentlyContinue }
        Autovacuum-Local 'off'
        try {
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
        } finally { Autovacuum-Local 'restaurar' }
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
    Registra $tr $estado
    Marca "$tr fin $estado"
  }
} finally {
  if ($script:AutovacuumOff) { Autovacuum-Local 'restaurar' }
  foreach ($v in $VARS + 'GAPTO_MANT_VINCULO_CONCURRENCIA') { Remove-Item "Env:$v" -ErrorAction SilentlyContinue }
}
Get-Content $Resumen
