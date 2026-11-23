# ============================================================
# GAPTO MOBILE 2027
# Fichero: rotar_token_dev.ps1
# Ruta: scripts/dev/rotar_token_dev.ps1
# Descripcion: Rotacion del token de desarrollo GAPTO_DEV_TOKEN (F06 T4 token
#   BETA_LOCAL, mandato 4f0e40af... par. 3; dictamen AJ-TOK-03).
#   - Genera un token nuevo con el generador criptografico del sistema
#     (RandomNumberGenerator), de -Longitud caracteres (minimo 32, por defecto
#     40) de un alfabeto sin caracteres ambiguos, facil de teclear en el iPhone.
#   - Lo escribe en el fichero local -Destino, que nunca se versiona:
#       * si termina en .env: sustituye (o anade) la linea <Variable>=<token>
#         y conserva las demas lineas;
#       * si no: el fichero entero es el token (p. ej. local\dev_token.txt de
#         ENV-DEV, que lee envdev_arranque.ps1).
#     Escritura atomica (fichero temporal en la misma carpeta y sustitucion).
#   - NUNCA imprime el token ni lo escribe en el registro: -Registro (opcional)
#     recibe una linea con fecha, destino, modo, longitud y resultado.
#   - No reinicia nada: el token anterior deja de valer cuando se reinicia el
#     backend con el nuevo (lo hace el despliegue, con Moises). No toca ENV-DEV
#     salvo que se le pase expresamente su fichero como -Destino.
#   Uso: powershell -NoProfile -ExecutionPolicy Bypass -File rotar_token_dev.ps1 -Destino <fichero> [-Registro <log>]
# Version: 0.1.0 (F06 T4 token BETA_LOCAL)
# ============================================================
param(
    [Parameter(Mandatory = $true)][string]$Destino,
    [string]$Registro = '',
    [int]$Longitud = 40,
    [string]$Variable = 'GAPTO_DEV_TOKEN'
)
$ErrorActionPreference = 'Stop'
if ($Longitud -lt 32) { throw "La longitud minima del token es 32 (pedida: $Longitud)." }
if ($Variable -notmatch '^[A-Z_][A-Z0-9_]*$') { throw 'Nombre de variable no valido.' }
$dir = Split-Path -Parent ([IO.Path]::GetFullPath($Destino))
if (-not (Test-Path -LiteralPath $dir -PathType Container)) { throw "No existe la carpeta del destino: $dir" }

# 31 simbolos sin ambiguos (sin i, l, o, 0, 1); muestreo por rechazo para no sesgar.
$alfabeto = 'abcdefghjkmnpqrstuvwxyz23456789'
$n = $alfabeto.Length
$limite = 256 - (256 % $n)
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$sb = New-Object Text.StringBuilder
$buf = New-Object byte[] 64
while ($sb.Length -lt $Longitud) {
    $rng.GetBytes($buf)
    foreach ($b in $buf) {
        if ($b -lt $limite -and $sb.Length -lt $Longitud) { [void]$sb.Append($alfabeto[$b % $n]) }
    }
}
$rng.Dispose()
$token = $sb.ToString()
[void]$sb.Clear()

$modo = if ($Destino.ToLower().EndsWith('.env')) { 'env' } else { 'fichero' }
if ($modo -eq 'env') {
    $lineas = @()
    if (Test-Path -LiteralPath $Destino) { $lineas = @(Get-Content -LiteralPath $Destino) }
    $nuevas = New-Object Collections.Generic.List[string]
    $puesto = $false
    foreach ($l in $lineas) {
        if ($l -match "^\s*$Variable\s*=") {
            if (-not $puesto) { $nuevas.Add("$Variable=$token"); $puesto = $true }
        } else { $nuevas.Add($l) }
    }
    if (-not $puesto) { $nuevas.Add("$Variable=$token") }
    $contenido = ($nuevas -join "`n") + "`n"
} else {
    $contenido = $token + "`n"
}
$tmp = Join-Path $dir ('.rotar_' + [Guid]::NewGuid().ToString('N') + '.tmp')
[IO.File]::WriteAllText($tmp, $contenido, (New-Object Text.UTF8Encoding($false)))
Move-Item -LiteralPath $tmp -Destination $Destino -Force
Remove-Variable token, contenido
if ($modo -eq 'env') { Remove-Variable nuevas, lineas }

if ($Registro) {
    $fecha = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
    $linea = "$fecha destino=$Destino modo=$modo variable=$Variable longitud=$Longitud resultado=ROTADO valor=NO_REGISTRADO"
    Add-Content -LiteralPath $Registro -Value $linea -Encoding ASCII
}
Write-Host "Token rotado en $Destino (modo $modo, longitud $Longitud). El valor no se muestra."
Write-Host 'Reinicia el backend con el token nuevo para que el anterior deje de valer.'
