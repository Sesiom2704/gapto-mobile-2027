# ============================================================
# GAPTO MOBILE 2027
# Fichero: copiar_d200.ps1
# Ruta: scripts/docs/copiar_d200.ps1
# Descripcion: MANT D200-ESCRITURA. Unica via de escritura de Claude Code en
#   00_CORE (D-200): copia binaria en sitio de los candidatos de un mandato
#   sobre canonicos que YA existen, segun el PLAN_D200.csv del mandato.
#   El script solo ejecuta la copia: no decide, no crea, no renombra y no
#   borra ficheros en el destino. La revisora sigue siendo obligatoria donde
#   lo es (D-200/D-203).
#
#   Uso (PowerShell 5.1):
#     & <repo>\scripts\docs\copiar_d200.ps1 -Plan <ruta a PLAN_D200.csv> [-Simulacion]
#
#   Raices (MANT H-B, sin rutas de maquina versionadas): se leen SOLO del
#   ambito de usuario ([Environment]::GetEnvironmentVariable(..., 'User'));
#   $env: no cuenta, asi no se pueden sobrescribir dentro del mismo comando.
#   No hay parametro para cambiarlas.
#     GAPTO_D200_ORIGEN  -> ...\gapto-canal\mandatos
#     GAPTO_D200_DESTINO -> ...\GaptoMobile 2027\00_CORE
#
#   PLAN_D200.csv (UTF-8, separador ;), cabecera exacta:
#     orden;origen;destino_relativo;bytes_pre;sha_pre;bytes_post;sha_post
#   origen es relativo a la carpeta del plan; destino_relativo, a
#   GAPTO_D200_DESTINO. pre = estado vigente del destino; post = candidato.
#
#   Guardas (fail-closed; el lote entero se valida antes de escribir nada):
#     G1 variables de usuario definidas, sufijos esperados y carpetas existentes.
#     G2 plan y cada origen bajo GAPTO_D200_ORIGEN (sin absolutas, '..' ni
#        puntos de reanalisis en ningun tramo).
#     G3 cada destino bajo GAPTO_D200_DESTINO (mismas reglas) y YA existe.
#     G4 el nombre de cada destino aparece una sola vez en el arbol destino
#        (y una sola vez en el plan).
#     G5 origen: tamano y SHA-256 = bytes_post/sha_post.
#     G6 destino: tamano y SHA-256 = bytes_pre/sha_pre (precondicion D-200).
#     G7 orden: enteros unicos y consecutivos desde 1; se ejecuta ascendente.
#     G8 copia de seguridad en <padre de gapto-canal>\evidencia_d200\<mandato>\pre\
#        (pre_<yyyyMMdd-HHmmss>\ si pre\ ya contiene alguno de los ficheros):
#        nunca en la unidad de GAPTO_D200_DESTINO ni bajo ella.
#     PLAN formato del plan (cabecera, columnas, enteros, SHA-256).
#   Ejecucion fila a fila: copia de seguridad del destino (verificada contra
#   sha_pre), copia binaria en sitio con File.Copy(origen, destino, $true)
#   (sin temporales ni renombrados en el destino), postcomprobacion de tamano,
#   SHA-256 y unicidad del nombre. Si falla: STOP inmediato, la fila siguiente
#   no se toca y se indica la copia de seguridad que restaura el estado previo.
#   Log con hora por paso y SHA256SUMS junto a la copia de seguridad.
#   -Simulacion ejecuta todas las guardas y no escribe nada.
#
#   Cargado con dot-sourcing (tests) no ejecuta nada: solo define funciones.
#   Antes de invocarlo (CLAUDE.md): git diff --quiet HEAD -- scripts/docs/copiar_d200.ps1
# Version: 0.1.0
# ============================================================
param(
    [string]$Plan,
    [switch]$Simulacion
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:SufijoOrigen = '\gapto-canal\mandatos'
$script:SufijoDestino = '\GaptoMobile 2027\00_CORE'
$script:CabeceraPlan = 'orden;origen;destino_relativo;bytes_pre;sha_pre;bytes_post;sha_post'
$script:LogD200 = $null

function Fallar([string]$Guarda, [string]$Mensaje) {
    throw ('D200[{0}] {1}' -f $Guarda, $Mensaje)
}

function Registrar([string]$Texto) {
    $linea = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Texto
    Write-Host $linea
    if ($script:LogD200) {
        [System.IO.File]::AppendAllText($script:LogD200, $linea + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
    }
}

function Leer-VariableUsuario([string]$Nombre) {
    # Solo el ambito de usuario: un $env: fijado en linea no cuenta.
    return [Environment]::GetEnvironmentVariable($Nombre, 'User')
}

function Esta-Bajo([string]$Ruta, [string]$Raiz) {
    return $Ruta.StartsWith($Raiz + '\', [System.StringComparison]::OrdinalIgnoreCase)
}

function Test-SinReanalisis([string]$Ruta, [string]$Guarda) {
    # Recorre todos los tramos existentes, de la ruta hasta la raiz de la unidad.
    $p = $Ruta
    while ($p) {
        if (Test-Path -LiteralPath $p) {
            $i = Get-Item -LiteralPath $p -Force
            if ($i.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                Fallar $Guarda ("punto de reanalisis en el tramo '{0}'" -f $p)
            }
        }
        $padre = [System.IO.Path]::GetDirectoryName($p)
        if (-not $padre -or $padre -eq $p) { break }
        $p = $padre
    }
}

function Hash-Fichero([string]$Ruta) {
    return (Get-FileHash -LiteralPath $Ruta -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Resolver-Relativa([string]$Raiz, [string]$Relativa, [string]$Guarda) {
    if ([string]::IsNullOrWhiteSpace($Relativa)) { Fallar $Guarda 'ruta relativa vacia' }
    if ([System.IO.Path]::IsPathRooted($Relativa) -or $Relativa.Contains(':')) {
        Fallar $Guarda ("ruta absoluta, con unidad o con flujo: '{0}'" -f $Relativa)
    }
    if ($Relativa.IndexOfAny([System.IO.Path]::GetInvalidPathChars()) -ge 0 -or $Relativa.IndexOfAny([char[]]'*?') -ge 0) {
        Fallar $Guarda ("caracteres no validos en '{0}'" -f $Relativa)
    }
    foreach ($t in ($Relativa -split '[\\/]')) {
        if ($t -eq '..' -or $t -eq '.' -or $t -eq '') { Fallar $Guarda ("tramo no permitido en '{0}'" -f $Relativa) }
    }
    $ruta = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($Raiz, $Relativa))
    if (-not (Esta-Bajo $ruta $Raiz)) { Fallar $Guarda ("fuera de la raiz: '{0}'" -f $Relativa) }
    Test-SinReanalisis $ruta $Guarda
    return $ruta
}

function Test-G1Raices([string]$Origen, [string]$Destino) {
    foreach ($par in @(@('GAPTO_D200_ORIGEN', $Origen, $script:SufijoOrigen), @('GAPTO_D200_DESTINO', $Destino, $script:SufijoDestino))) {
        $nombre = $par[0]; $valor = $par[1]; $sufijo = $par[2]
        if ([string]::IsNullOrWhiteSpace($valor)) { Fallar 'G1' ("{0} no definida en el ambito de usuario" -f $nombre) }
        if ($valor -notmatch '^[A-Za-z]:\\') { Fallar 'G1' ("{0} no es una ruta absoluta con unidad" -f $nombre) }
        $n = [System.IO.Path]::GetFullPath($valor).TrimEnd('\')
        if (-not $n.EndsWith($sufijo, [System.StringComparison]::OrdinalIgnoreCase)) {
            Fallar 'G1' ("{0} no termina en '{1}'" -f $nombre, $sufijo)
        }
        if (-not (Test-Path -LiteralPath $n -PathType Container)) { Fallar 'G1' ("{0} no existe" -f $nombre) }
        Test-SinReanalisis $n 'G1'
    }
    return @{ Origen = [System.IO.Path]::GetFullPath($Origen).TrimEnd('\'); Destino = [System.IO.Path]::GetFullPath($Destino).TrimEnd('\') }
}

function Obtener-RaizCopia([string]$Origen, [string]$Destino) {
    # <padre de gapto-canal>\evidencia_d200, fuera de la unidad destino.
    $canal = [System.IO.Path]::GetDirectoryName($Origen)
    $base = if ($canal) { [System.IO.Path]::GetDirectoryName($canal) } else { $null }
    if (-not $base) { Fallar 'G8' 'gapto-canal no tiene carpeta padre' }
    $copia = [System.IO.Path]::Combine($base, 'evidencia_d200')
    if ([System.IO.Path]::GetPathRoot($copia) -ieq [System.IO.Path]::GetPathRoot($Destino)) {
        Fallar 'G8' ("la copia de seguridad '{0}' estaria en la misma unidad que el destino" -f $copia)
    }
    if ($copia -ieq $Destino -or (Esta-Bajo $copia $Destino)) {
        Fallar 'G8' ("la copia de seguridad '{0}' estaria bajo el destino" -f $copia)
    }
    Test-SinReanalisis $copia 'G8'
    return $copia
}

function Resolver-Plan([string]$Plan, [string]$Origen) {
    if ([string]::IsNullOrWhiteSpace($Plan)) { Fallar 'G2' 'falta -Plan' }
    if (($Plan -split '[\\/]') -contains '..') { Fallar 'G2' ("'..' en la ruta del plan: '{0}'" -f $Plan) }
    $ruta = [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Plan))
    if (-not (Esta-Bajo $ruta $Origen)) { Fallar 'G2' ("el plan no esta bajo GAPTO_D200_ORIGEN: '{0}'" -f $ruta) }
    $partes = $ruta.Substring($Origen.Length + 1).Split('\')
    if ($partes.Count -lt 2) { Fallar 'G2' 'el plan debe estar dentro de la carpeta de un mandato' }
    Test-SinReanalisis $ruta 'G2'
    if (-not (Test-Path -LiteralPath $ruta -PathType Leaf)) { Fallar 'G2' ("el plan no existe: '{0}'" -f $ruta) }
    return @{ Ruta = $ruta; Carpeta = [System.IO.Path]::GetDirectoryName($ruta); Mandato = $partes[0] }
}

function Leer-Plan([string]$Ruta) {
    $lineas = [System.IO.File]::ReadAllLines($Ruta, [System.Text.Encoding]::UTF8)
    if ($lineas.Count -lt 1 -or $lineas[0] -cne $script:CabeceraPlan) {
        Fallar 'PLAN' ("cabecera distinta de '{0}'" -f $script:CabeceraPlan)
    }
    $filas = @()
    for ($k = 1; $k -lt $lineas.Count; $k++) {
        $l = $lineas[$k]
        if ([string]::IsNullOrWhiteSpace($l)) { continue }
        $c = $l.Split(';')
        if ($c.Count -ne 7) { Fallar 'PLAN' ("linea {0}: {1} columnas, se esperan 7" -f ($k + 1), $c.Count) }
        $orden = 0; $bpre = [long]0; $bpost = [long]0
        if (-not [int]::TryParse($c[0], [ref]$orden)) { Fallar 'PLAN' ("linea {0}: orden no entero" -f ($k + 1)) }
        if (-not [long]::TryParse($c[3], [ref]$bpre) -or $bpre -lt 0) { Fallar 'PLAN' ("linea {0}: bytes_pre no valido" -f ($k + 1)) }
        if (-not [long]::TryParse($c[5], [ref]$bpost) -or $bpost -lt 0) { Fallar 'PLAN' ("linea {0}: bytes_post no valido" -f ($k + 1)) }
        foreach ($s in @($c[4], $c[6])) {
            if ($s -notmatch '^[0-9a-fA-F]{64}$') { Fallar 'PLAN' ("linea {0}: SHA-256 no valido" -f ($k + 1)) }
        }
        $filas += New-Object PSObject -Property @{
            Orden = $orden; Origen = $c[1]; DestinoRelativo = $c[2]
            BytesPre = $bpre; ShaPre = $c[4].ToLowerInvariant(); BytesPost = $bpost; ShaPost = $c[6].ToLowerInvariant()
        }
    }
    if ($filas.Count -eq 0) { Fallar 'PLAN' 'el plan no tiene filas' }
    return ,$filas
}

function Test-G7Orden($Filas) {
    $ordenes = @($Filas | ForEach-Object { $_.Orden } | Sort-Object)
    for ($k = 0; $k -lt $ordenes.Count; $k++) {
        if ($ordenes[$k] -ne ($k + 1)) {
            Fallar 'G7' ("los numeros de orden deben ser unicos y consecutivos desde 1: {0}" -f ($ordenes -join ','))
        }
    }
}

function Contar-Nombres([string]$Destino) {
    $conteo = @{}
    Get-ChildItem -LiteralPath $Destino -Recurse -File -Force | ForEach-Object {
        $conteo[$_.Name] = 1 + [int]$conteo[$_.Name]
    }
    return $conteo
}

function Validar-Lote($Filas, $PlanInfo, [string]$Origen, [string]$Destino) {
    $lote = @()
    foreach ($f in $Filas) {
        $o = Resolver-Relativa $PlanInfo.Carpeta $f.Origen 'G2'
        if (-not (Esta-Bajo $o $Origen)) { Fallar 'G2' ("fila {0}: origen fuera de GAPTO_D200_ORIGEN" -f $f.Orden) }
        if (-not (Test-Path -LiteralPath $o -PathType Leaf)) { Fallar 'G2' ("fila {0}: el origen no existe: '{1}'" -f $f.Orden, $o) }
        $d = Resolver-Relativa $Destino $f.DestinoRelativo 'G3'
        if (-not (Test-Path -LiteralPath $d -PathType Leaf)) {
            Fallar 'G3' ("fila {0}: el destino no existe (el script nunca crea ficheros): '{1}'" -f $f.Orden, $d)
        }
        $lote += New-Object PSObject -Property @{ Fila = $f; Origen = $o; Destino = $d; Nombre = [System.IO.Path]::GetFileName($d) }
    }
    $conteo = Contar-Nombres $Destino
    $vistos = @{}
    foreach ($x in $lote) {
        if ($vistos.ContainsKey($x.Nombre)) { Fallar 'G4' ("'{0}' aparece mas de una vez en el plan" -f $x.Nombre) }
        $vistos[$x.Nombre] = $true
        if ([int]$conteo[$x.Nombre] -ne 1) {
            Fallar 'G4' ("'{0}' aparece {1} veces en el arbol destino" -f $x.Nombre, [int]$conteo[$x.Nombre])
        }
    }
    foreach ($x in $lote) {
        $f = $x.Fila
        $len = (Get-Item -LiteralPath $x.Origen -Force).Length
        if ($len -ne $f.BytesPost -or (Hash-Fichero $x.Origen) -ne $f.ShaPost) {
            Fallar 'G5' ("fila {0}: el origen no coincide con bytes_post/sha_post" -f $f.Orden)
        }
    }
    foreach ($x in $lote) {
        $f = $x.Fila
        $len = (Get-Item -LiteralPath $x.Destino -Force).Length
        if ($len -ne $f.BytesPre -or (Hash-Fichero $x.Destino) -ne $f.ShaPre) {
            Fallar 'G6' ("fila {0}: el destino vigente no coincide con bytes_pre/sha_pre" -f $f.Orden)
        }
    }
    return ,$lote
}

function Elegir-CarpetaPre([string]$RaizCopia, [string]$Mandato, $Lote) {
    $pre = [System.IO.Path]::Combine([System.IO.Path]::Combine($RaizCopia, $Mandato), 'pre')
    $choca = $false
    foreach ($x in $Lote) {
        if (Test-Path -LiteralPath ([System.IO.Path]::Combine($pre, $x.Nombre))) { $choca = $true }
    }
    if ($choca) {
        $pre = '{0}_{1}' -f $pre, (Get-Date -Format 'yyyyMMdd-HHmmss')
        if (Test-Path -LiteralPath $pre) { Fallar 'G8' ("la carpeta de copia de seguridad ya existe: '{0}'" -f $pre) }
    }
    Test-SinReanalisis $pre 'G8'
    return $pre
}

function Copiar-Binario([string]$Origen, [string]$Destino) {
    # Sobrescritura en sitio: sin temporales ni renombrados en el destino.
    [System.IO.File]::Copy($Origen, $Destino, $true)
}

function Invocar-CopiaD200 {
    param([string]$Plan, [switch]$Simulacion, [string]$RaizOrigen, [string]$RaizDestino)
    $script:LogD200 = $null
    $r = Test-G1Raices $RaizOrigen $RaizDestino
    $raizCopia = Obtener-RaizCopia $r.Origen $r.Destino
    $planInfo = Resolver-Plan $Plan $r.Origen
    $filas = Leer-Plan $planInfo.Ruta
    Test-G7Orden $filas
    $filas = @($filas | Sort-Object Orden)
    $lote = Validar-Lote $filas $planInfo $r.Origen $r.Destino
    $pre = Elegir-CarpetaPre $raizCopia $planInfo.Mandato $lote

    if ($Simulacion) {
        Registrar ("SIMULACION: guardas G1-G8 superadas; {0} fila(s); no se escribe nada" -f $lote.Count)
        foreach ($x in $lote) {
            Registrar ("  fila {0}: {1} -> {2} (pre {3}, post {4})" -f $x.Fila.Orden, $x.Origen, $x.Destino, $x.Fila.ShaPre, $x.Fila.ShaPost)
        }
        Registrar ("  copia de seguridad prevista en '{0}'" -f $pre)
        return 'SIMULACION'
    }

    [void](New-Item -ItemType Directory -Path $pre -Force)
    $script:LogD200 = [System.IO.Path]::Combine($pre, 'copiar_d200.log')
    $sumas = [System.IO.Path]::Combine($pre, 'SHA256SUMS')
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    Registrar ("inicio: plan '{0}' ({1}), {2} fila(s)" -f $planInfo.Ruta, (Hash-Fichero $planInfo.Ruta), $lote.Count)
    $resumen = @()
    foreach ($x in $lote) {
        $f = $x.Fila
        $copia = [System.IO.Path]::Combine($pre, $x.Nombre)
        Registrar ("fila {0}: copia de seguridad '{1}' -> '{2}'" -f $f.Orden, $x.Destino, $copia)
        [System.IO.File]::Copy($x.Destino, $copia, $false)
        if ((Hash-Fichero $copia) -ne $f.ShaPre) {
            Fallar 'PRE' ("fila {0}: el destino cambio tras la validacion; no se ha escrito en el destino" -f $f.Orden)
        }
        [System.IO.File]::AppendAllText($sumas, ('{0}  {1}' -f $f.ShaPre, $x.Nombre) + "`n", $utf8)
        Registrar ("fila {0}: copia '{1}' -> '{2}'" -f $f.Orden, $x.Origen, $x.Destino)
        Copiar-Binario $x.Origen $x.Destino
        $len = (Get-Item -LiteralPath $x.Destino -Force).Length
        $sha = Hash-Fichero $x.Destino
        $veces = [int](Contar-Nombres $r.Destino)[$x.Nombre]
        if ($len -ne $f.BytesPost -or $sha -ne $f.ShaPost -or $veces -ne 1) {
            Fallar 'POST' ("fila {0}: postcomprobacion fallida (bytes {1}, sha {2}, apariciones {3}). STOP: no se toca ninguna fila mas. Restaurar con la copia de seguridad '{4}' -> '{5}'" -f $f.Orden, $len, $sha, $veces, $copia, $x.Destino)
        }
        Registrar ("fila {0}: OK bytes {1} sha {2}" -f $f.Orden, $len, $sha)
        $resumen += ('fila {0}: {1} OK ({2} -> {3})' -f $f.Orden, $x.Nombre, $f.ShaPre, $f.ShaPost)
    }
    Registrar 'resumen:'
    foreach ($l in $resumen) { Registrar ('  ' + $l) }
    return 'COPIADO'
}

function Main-D200([string]$Plan, [switch]$Simulacion) {
    $origen = Leer-VariableUsuario 'GAPTO_D200_ORIGEN'
    $destino = Leer-VariableUsuario 'GAPTO_D200_DESTINO'
    return Invocar-CopiaD200 -Plan $Plan -Simulacion:$Simulacion -RaizOrigen $origen -RaizDestino $destino
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        [void](Main-D200 -Plan $Plan -Simulacion:$Simulacion)
        exit 0
    } catch {
        if ($script:LogD200) { Registrar ('STOP: ' + $_.Exception.Message) } else { Write-Host ('STOP: ' + $_.Exception.Message) }
        exit 1
    }
}
