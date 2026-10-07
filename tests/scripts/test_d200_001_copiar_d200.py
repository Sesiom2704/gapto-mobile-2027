# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_d200_001_copiar_d200.py
# Ruta: tests/scripts/test_d200_001_copiar_d200.py
# Descripcion: MANT D200-ESCRITURA. Pruebas de scripts/docs/copiar_d200.ps1
#              sobre un arbol simulado en temporal (nunca toca la unidad real
#              de Drive). pytest lanza powershell.exe y carga el script con
#              dot-sourcing; cada prueba negativa rompe UNA sola condicion y
#              exige el codigo de su guarda (D200[Gx]), no otro.
#
#   El destino simulado se monta en una letra de unidad temporal (subst) para
#   que la copia de seguridad (en la unidad del canal) quede en otra unidad,
#   como exige G8. La letra se libera al terminar cada prueba.
#
#   Si powershell.exe no existe, las pruebas se SALTAN con motivo explicito
#   (no cuentan como aprobadas). No necesita base de datos:
#       python -m pytest tests/scripts -q
#
# Version: 0.1.0
# ============================================================
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "docs" / "copiar_d200.ps1"
POWERSHELL = shutil.which("powershell.exe")
CABECERA = "orden;origen;destino_relativo;bytes_pre;sha_pre;bytes_post;sha_post"

pytestmark = pytest.mark.skipif(
    POWERSHELL is None, reason="powershell.exe no disponible: copiar_d200.ps1 no se ha podido probar")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _ps(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


@dataclass
class Arbol:
    base: Path
    origen: Path            # ...\gapto-canal\mandatos
    mandato: Path           # ...\mandatos\MANDATO_X
    destino_real: Path      # carpeta real (bajo la unidad subst)
    destino: str            # <letra>:\GaptoMobile 2027\00_CORE
    copia: Path             # <padre de gapto-canal>\evidencia_d200
    vigentes: dict = field(default_factory=dict)
    candidatos: dict = field(default_factory=dict)

    def huella_destino(self) -> dict:
        return {p.relative_to(self.destino_real).as_posix(): p.read_bytes()
                for p in self.destino_real.rglob("*") if p.is_file()}

    def fila(self, orden, origen, destino_rel, *, pre=None, post=None):
        pre = self.vigentes[destino_rel] if pre is None else pre
        post = self.candidatos[origen] if post is None else post
        return f"{orden};{origen};{destino_rel};{len(pre)};{_sha(pre)};{len(post)};{_sha(post)}"

    def plan(self, filas, cabecera=CABECERA, nombre="PLAN_D200.csv") -> Path:
        p = self.mandato / nombre
        p.write_text("\n".join([cabecera, *filas]) + "\n", encoding="utf-8-sig")
        return p

    def plan_estandar(self) -> Path:
        # Filas escritas en orden inverso: el script debe ejecutarlas por 'orden' ascendente.
        return self.plan([self.fila(2, "cand\\B.md", "sub\\B.md"), self.fila(1, "cand\\A.md", "A.md")])


@pytest.fixture
def unidad(tmp_path):
    real = tmp_path / "unidad"
    real.mkdir()
    libres = [l for l in "ZYXWVUTSRQPONM" if not os.path.exists(f"{l}:\\")]
    assert libres, "no hay letra de unidad libre para subst"
    letra = libres[0]
    r = subprocess.run(["subst", f"{letra}:", str(real)], capture_output=True)
    assert r.returncode == 0, r.stderr
    try:
        yield letra, real
    finally:
        subprocess.run(["subst", f"{letra}:", "/D"], capture_output=True)


def _hacer_arbol(tmp_path: Path, letra: str | None, real: Path | None) -> Arbol:
    base = tmp_path / "maquina"
    origen = base / "gapto-canal" / "mandatos"
    mandato = origen / "MANDATO_X"
    (mandato / "cand").mkdir(parents=True)
    if letra is None:
        real = tmp_path / "misma_unidad"
        real.mkdir()
        destino = str(real / "GaptoMobile 2027" / "00_CORE")
    else:
        destino = f"{letra}:\\GaptoMobile 2027\\00_CORE"
    destino_real = real / "GaptoMobile 2027" / "00_CORE"
    (destino_real / "sub").mkdir(parents=True)
    vigentes = {"A.md": b"vigente A\n", "sub\\B.md": b"vigente B\r\n"}
    (destino_real / "A.md").write_bytes(vigentes["A.md"])
    (destino_real / "sub" / "B.md").write_bytes(vigentes["sub\\B.md"])
    (destino_real / "otro.txt").write_bytes(b"no se toca\n")
    candidatos = {"cand\\A.md": b"candidato A nuevo\n", "cand\\B.md": "candidato B ñ\n".encode("utf-8")}
    (mandato / "cand" / "A.md").write_bytes(candidatos["cand\\A.md"])
    (mandato / "cand" / "B.md").write_bytes(candidatos["cand\\B.md"])
    return Arbol(base, origen, mandato, destino_real, destino, base / "evidencia_d200", vigentes, candidatos)


@pytest.fixture
def arbol(tmp_path, unidad) -> Arbol:
    letra, real = unidad
    return _hacer_arbol(tmp_path, letra, real)


def _ejecutar(tmp_path: Path, llamada: str, previo: str = "") -> tuple[str, str]:
    arnes = tmp_path / "arnes.ps1"
    arnes.write_text(
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
        f". {_ps(SCRIPT)}\n"
        f"{previo}\n"
        f"try {{ $r = {llamada}; Write-Host ('RESULTADO:OK:' + $r) }}\n"
        "catch { Write-Host ('RESULTADO:ERROR:' + $_.Exception.Message) }\n",
        encoding="utf-8-sig")
    r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-File", str(arnes)], capture_output=True, timeout=180)
    salida = r.stdout.decode("utf-8", errors="replace") + r.stderr.decode("utf-8", errors="replace")
    lineas = [l for l in salida.splitlines() if l.startswith("RESULTADO:")]
    assert lineas, f"el arnes no ha devuelto resultado:\n{salida}"
    return lineas[-1], salida


def _invocar(tmp_path, a: Arbol, plan, simulacion=False, previo="", origen=None, destino=None):
    llamada = (f"Invocar-CopiaD200 -Plan {_ps(plan)} -RaizOrigen {_ps(origen or a.origen)} "
               f"-RaizDestino {_ps(destino or a.destino)}" + (" -Simulacion" if simulacion else ""))
    return _ejecutar(tmp_path, llamada, previo)


def _guarda(resultado: str) -> str | None:
    m = re.search(r"D200\[(\w+)\]", resultado)
    return m.group(1) if m else None


def _rechazo(tmp_path, a: Arbol, plan, guarda: str, **kw):
    antes = a.huella_destino()
    res, salida = _invocar(tmp_path, a, plan, **kw)
    assert res.startswith("RESULTADO:ERROR:"), salida
    assert _guarda(res) == guarda, f"se esperaba {guarda}: {res}"
    assert a.huella_destino() == antes, "una guarda no puede dejar el destino modificado"
    assert not a.copia.exists(), "una guarda no puede escribir la copia de seguridad"
    return res


# ---------------------------------------------------------------- camino feliz

def test_camino_feliz_dos_filas_en_orden(tmp_path, arbol):
    res, salida = _invocar(tmp_path, arbol, arbol.plan_estandar())
    assert res == "RESULTADO:OK:COPIADO", salida
    assert (arbol.destino_real / "A.md").read_bytes() == arbol.candidatos["cand\\A.md"]
    assert (arbol.destino_real / "sub" / "B.md").read_bytes() == arbol.candidatos["cand\\B.md"]
    assert (arbol.destino_real / "otro.txt").read_bytes() == b"no se toca\n"
    assert sorted(p.name for p in arbol.destino_real.rglob("*") if p.is_file()) == ["A.md", "B.md", "otro.txt"]
    pre = arbol.copia / "MANDATO_X" / "pre"
    assert (pre / "A.md").read_bytes() == arbol.vigentes["A.md"]
    assert (pre / "B.md").read_bytes() == arbol.vigentes["sub\\B.md"]
    sumas = (pre / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert sumas == [f"{_sha(arbol.vigentes['A.md'])}  A.md", f"{_sha(arbol.vigentes['sub\\B.md'])}  B.md"]
    log = (pre / "copiar_d200.log").read_text(encoding="utf-8")
    assert log.index("fila 1: copia '") < log.index("fila 2: copia de seguridad"), "orden ascendente"
    assert "fila 2: OK" in log and "resumen:" in log
    assert re.search(r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\] ", log, re.M)


def test_pre_existente_no_se_sobrescribe(tmp_path, arbol):
    pre = arbol.copia / "MANDATO_X" / "pre"
    pre.mkdir(parents=True)
    (pre / "A.md").write_bytes(b"copia anterior")
    res, salida = _invocar(tmp_path, arbol, arbol.plan_estandar())
    assert res == "RESULTADO:OK:COPIADO", salida
    assert (pre / "A.md").read_bytes() == b"copia anterior"
    nuevas = [p for p in (arbol.copia / "MANDATO_X").iterdir() if re.fullmatch(r"pre_\d{8}-\d{6}", p.name)]
    assert len(nuevas) == 1
    assert (nuevas[0] / "A.md").read_bytes() == arbol.vigentes["A.md"]


def test_simulacion_no_escribe(tmp_path, arbol):
    antes = arbol.huella_destino()
    res, salida = _invocar(tmp_path, arbol, arbol.plan_estandar(), simulacion=True)
    assert res == "RESULTADO:OK:SIMULACION", salida
    assert arbol.huella_destino() == antes
    assert not arbol.copia.exists()


def test_postcomprobacion_fallida_en_fila_1_no_toca_fila_2(tmp_path, arbol):
    # Inyeccion: la copia binaria deja un byte de mas en el destino.
    previo = ("function Copiar-Binario([string]$Origen, [string]$Destino) { "
              "[System.IO.File]::Copy($Origen, $Destino, $true); "
              "[System.IO.File]::AppendAllText($Destino, 'x') }")
    res, salida = _invocar(tmp_path, arbol, arbol.plan_estandar(), previo=previo)
    assert _guarda(res) == "POST", salida
    copia_a = arbol.copia / "MANDATO_X" / "pre" / "A.md"
    assert str(copia_a) in res, "el STOP debe indicar la copia de seguridad que restaura"
    assert copia_a.read_bytes() == arbol.vigentes["A.md"]
    assert (arbol.destino_real / "sub" / "B.md").read_bytes() == arbol.vigentes["sub\\B.md"]
    assert not (arbol.copia / "MANDATO_X" / "pre" / "B.md").exists()


# ---------------------------------------------------------------- G1

@pytest.mark.parametrize("ausente", ["GAPTO_D200_ORIGEN", "GAPTO_D200_DESTINO"])
def test_g1_env_de_proceso_no_cuenta_sin_variable_de_usuario(tmp_path, arbol, ausente):
    # $env: apunta a raices validas; en el ambito de usuario falta UNA variable (la otra es valida).
    previo = (f"$env:GAPTO_D200_ORIGEN = {_ps(arbol.origen)}; $env:GAPTO_D200_DESTINO = {_ps(arbol.destino)}; "
              "function Leer-VariableUsuario([string]$Nombre) { "
              f"if ($Nombre -eq '{ausente}') {{ return $null }} "
              f"if ($Nombre -eq 'GAPTO_D200_ORIGEN') {{ {_ps(arbol.origen)} }} else {{ {_ps(arbol.destino)} }} }}")
    antes = arbol.huella_destino()
    res, salida = _ejecutar(tmp_path, f"Main-D200 -Plan {_ps(arbol.plan_estandar())} -Simulacion", previo)
    assert _guarda(res) == "G1", salida
    assert f"{ausente} no definida en el ambito de usuario" in res
    assert arbol.huella_destino() == antes


def test_g1_lector_real_ignora_env_de_proceso(tmp_path):
    # El lector real consulta el ambito de usuario: una variable que solo existe en $env: da $null.
    nombre = "GAPTO_D200_PRUEBA_SOLO_PROCESO"
    previo = f"$env:{nombre} = 'C:\\x'"
    res, salida = _ejecutar(tmp_path, f"[string]::IsNullOrEmpty((Leer-VariableUsuario '{nombre}'))", previo)
    assert res == "RESULTADO:OK:True", salida


def test_main_lee_las_raices_del_ambito_de_usuario(tmp_path, arbol):
    # Control positivo del anterior: con la lectura de usuario disponible, Main-D200 pasa.
    previo = ("function Leer-VariableUsuario([string]$Nombre) { "
              f"if ($Nombre -eq 'GAPTO_D200_ORIGEN') {{ {_ps(arbol.origen)} }} else {{ {_ps(arbol.destino)} }} }}")
    res, salida = _ejecutar(tmp_path, f"Main-D200 -Plan {_ps(arbol.plan_estandar())} -Simulacion", previo)
    assert res == "RESULTADO:OK:SIMULACION", salida


def test_g1_sufijo_de_origen(tmp_path, arbol):
    otra = arbol.base / "gapto-canal" / "handoffs"
    otra.mkdir()
    _rechazo(tmp_path, arbol, arbol.plan_estandar(), "G1", origen=otra)


def test_g1_sufijo_de_destino(tmp_path, arbol):
    _rechazo(tmp_path, arbol, arbol.plan_estandar(), "G1", destino=arbol.destino.rsplit("\\", 1)[0])


def test_g1_raiz_inexistente(tmp_path, arbol):
    _rechazo(tmp_path, arbol, arbol.plan_estandar(), "G1",
             origen=arbol.base / "no_existe" / "gapto-canal" / "mandatos")


# ---------------------------------------------------------------- G2

def test_g2_plan_fuera_de_origen(tmp_path, arbol):
    p = arbol.plan_estandar()
    fuera = arbol.base / "PLAN_D200.csv"
    shutil.copy(p, fuera)
    _rechazo(tmp_path, arbol, fuera, "G2")


def test_g2_plan_con_puntos(tmp_path, arbol):
    p = arbol.plan_estandar()
    _rechazo(tmp_path, arbol, str(arbol.mandato / "cand" / ".." / p.name), "G2")


def test_g2_origen_absoluto(tmp_path, arbol):
    abs_a = str(arbol.mandato / "cand" / "A.md")
    plan = arbol.plan([arbol.fila(1, abs_a, "A.md", post=arbol.candidatos["cand\\A.md"])])
    _rechazo(tmp_path, arbol, plan, "G2")


def test_g2_origen_con_puntos(tmp_path, arbol):
    plan = arbol.plan([arbol.fila(1, "cand\\..\\cand\\A.md", "A.md", post=arbol.candidatos["cand\\A.md"])])
    _rechazo(tmp_path, arbol, plan, "G2")


def test_g2_origen_por_punto_de_reanalisis(tmp_path, arbol):
    fuera = arbol.base / "fuera"
    fuera.mkdir()
    (fuera / "A.md").write_bytes(arbol.candidatos["cand\\A.md"])
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(arbol.mandato / "enlace"), str(fuera)], capture_output=True)
    assert r.returncode == 0, r.stderr
    plan = arbol.plan([arbol.fila(1, "enlace\\A.md", "A.md", post=arbol.candidatos["cand\\A.md"])])
    _rechazo(tmp_path, arbol, plan, "G2")


def test_g2_origen_inexistente(tmp_path, arbol):
    plan = arbol.plan([arbol.fila(1, "cand\\C.md", "A.md", post=b"x")])
    _rechazo(tmp_path, arbol, plan, "G2")


# ---------------------------------------------------------------- G3

def test_g3_destino_inexistente_no_se_crea(tmp_path, arbol):
    plan = arbol.plan([arbol.fila(1, "cand\\A.md", "Nuevo.md", pre=b"")])
    _rechazo(tmp_path, arbol, plan, "G3")
    assert not (arbol.destino_real / "Nuevo.md").exists()


def test_g3_destino_absoluto(tmp_path, arbol):
    plan = arbol.plan([arbol.fila(1, "cand\\A.md", arbol.destino + "\\A.md", pre=arbol.vigentes["A.md"])])
    _rechazo(tmp_path, arbol, plan, "G3")


def test_g3_destino_con_puntos(tmp_path, arbol):
    plan = arbol.plan([arbol.fila(1, "cand\\A.md", "sub\\..\\A.md", pre=arbol.vigentes["A.md"])])
    _rechazo(tmp_path, arbol, plan, "G3")


def test_g3_destino_por_punto_de_reanalisis(tmp_path, arbol):
    fuera = arbol.base / "fuera_destino"
    fuera.mkdir()
    (fuera / "C.md").write_bytes(b"fuera\n")
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(arbol.destino_real / "enlace"), str(fuera)],
                       capture_output=True)
    assert r.returncode == 0, r.stderr
    plan = arbol.plan([arbol.fila(1, "cand\\A.md", "enlace\\C.md", pre=b"fuera\n")])
    _rechazo(tmp_path, arbol, plan, "G3")
    assert (fuera / "C.md").read_bytes() == b"fuera\n"


# ---------------------------------------------------------------- G4

def test_g4_nombre_duplicado_en_el_arbol_destino(tmp_path, arbol):
    (arbol.destino_real / "otra").mkdir()
    (arbol.destino_real / "otra" / "A.md").write_bytes(b"homonimo\n")
    _rechazo(tmp_path, arbol, arbol.plan_estandar(), "G4")


def test_g4_destino_repetido_en_el_plan(tmp_path, arbol):
    plan = arbol.plan([arbol.fila(1, "cand\\A.md", "A.md"), arbol.fila(2, "cand\\B.md", "A.md")])
    _rechazo(tmp_path, arbol, plan, "G4")


# ---------------------------------------------------------------- G5 / G6

def test_g5_origen_distinto_de_post(tmp_path, arbol):
    plan = arbol.plan_estandar()
    (arbol.mandato / "cand" / "B.md").write_bytes(b"candidato B modificado tras el plan\n")
    _rechazo(tmp_path, arbol, plan, "G5")


def test_g6_destino_distinto_de_pre(tmp_path, arbol):
    plan = arbol.plan_estandar()
    (arbol.destino_real / "sub" / "B.md").write_bytes(b"otra revision en Drive\n")
    _rechazo(tmp_path, arbol, plan, "G6")


# ---------------------------------------------------------------- G7

def test_g7_orden_no_consecutivo(tmp_path, arbol):
    plan = arbol.plan([arbol.fila(1, "cand\\A.md", "A.md"), arbol.fila(3, "cand\\B.md", "sub\\B.md")])
    _rechazo(tmp_path, arbol, plan, "G7")


def test_g7_orden_repetido(tmp_path, arbol):
    plan = arbol.plan([arbol.fila(1, "cand\\A.md", "A.md"), arbol.fila(1, "cand\\B.md", "sub\\B.md")])
    _rechazo(tmp_path, arbol, plan, "G7")


# ---------------------------------------------------------------- G8

def test_g8_copia_en_la_misma_unidad_que_el_destino(tmp_path):
    a = _hacer_arbol(tmp_path, None, None)
    _rechazo(tmp_path, a, a.plan_estandar(), "G8")


# ---------------------------------------------------------------- PLAN

def test_plan_con_cabecera_distinta(tmp_path, arbol):
    plan = arbol.plan([arbol.fila(1, "cand\\A.md", "A.md")], cabecera=CABECERA.replace(";", ","))
    _rechazo(tmp_path, arbol, plan, "PLAN")
