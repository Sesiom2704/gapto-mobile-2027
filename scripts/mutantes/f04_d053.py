#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f04_d053.py
# Ruta: scripts/mutantes/f04_d053.py
# Descripcion: Arnes de mutacion de F04-D053 (integridad de la posicion
#   generica). CC-D053-4: un mutante por regla (A1, B2, B3, B4, B5, B6, B8) y
#   por la entrada de OP-09 (dictamen v0.3), todos muertos.
#
#   Cada mutante retira UNA guarda y declara su DISCRIMINANTE: el test
#   concreto que debe caer. No se da por muerto si solo caen tests
#   colaterales. Cada mutante declara su suite (test_146 solo para B8: es la
#   bateria de concurrencia, de ~2 min).
#
#   Mecanismo D-181/D-192 heredado de f04_d052: E/S byte a byte, patron que
#   debe aparecer EXACTAMENTE una vez, marcador previo con el contenido
#   original para recuperarse de una ejecucion abortada, restauracion
#   verificada por SHA-256 tambien si pytest aborta, y arbol limpio exigido
#   antes y despues.
# Uso:
#   python scripts/mutantes/f04_d053.py             # todos
#   python scripts/mutantes/f04_d053.py D053-M4     # subconjunto
# Version: 0.1.0
#   0.1.0 (F04-D053 B1 · v0.2/v0.3): 16 mutantes (A1 x3, B2, B3 x2, B4 x2,
#   B5 x2, B6 x2, OP-09, B8 x3).
# ============================================================
from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys
from dataclasses import dataclass

RAIZ = pathlib.Path(__file__).resolve().parents[2]
T144 = "tests/backend/test_144_f04_d052_causas_reduccion.py"
T145 = "tests/backend/test_145_f04_d052_e1_op04_op21.py"
T146 = "tests/backend/test_146_f04_d053_raiz_bloqueo.py"
T147 = "tests/backend/test_147_f04_d053_integridad.py"
FUNCIONAL = (T144, T145, T147)
CONCURRENCIA = (T146,)
INT = "backend/app/services/integridad_posicion.py"
REPO = "backend/app/repositories/posiciones_repository.py"
POS = "backend/app/services/posiciones_service.py"
COR = "backend/app/services/correcciones_service.py"
TES = "backend/app/services/tesoreria_service.py"
MARCADOR = RAIZ / ".mutante_f04_d053_en_curso"


@dataclass(frozen=True)
class Mutante:
    ident: str
    guarda: str
    fichero: str
    viejo: str
    nuevo: str
    discriminante: str
    suite: tuple[str, ...] = FUNCIONAL


MUTANTES = (
    # --- A1 ---------------------------------------------------------------
    Mutante(
        "D053-M1", "A1: frontera inclusiva (>=)",
        REPO,
        'FRONTERA_A1 = "h.fecha_hecho >= {p}.fecha_inicio_seguimiento"',
        'FRONTERA_A1 = "h.fecha_hecho > {p}.fecha_inicio_seguimiento"',
        "test_a1_delta_exactamente_en_el_inicio_cuenta",
    ),
    Mutante(
        "D053-M2", "A1: los deltas anteriores al inicio no se suman",
        REPO,
        'FRONTERA_A1 = "h.fecha_hecho >= {p}.fecha_inicio_seguimiento"',
        'FRONTERA_A1 = "{p}.fecha_inicio_seguimiento IS NOT NULL"',
        "test_a1_corpus_sintetico_80_a_40",
    ),
    Mutante(
        "D053-M3", "A1 uniforme: el neto (OP-20) usa la misma frontera",
        REPO,
        '                         WHERE h.moneda = a.moneda AND {frontera_a1("a")})\n',
        '                         WHERE h.moneda = a.moneda)\n',
        "test_a1_delta_anterior_al_inicio_no_suma",
    ),
    # --- B2 / B3 ----------------------------------------------------------
    Mutante(
        "D053-M4", "B2: ningun cierre de fecha negativo",
        INT,
        "        if s_post < CERO and s_post < s_pre:\n",
        "        if False:\n",
        "test_b2_creacion_intermedio_negativo_final_positivo",
    ),
    Mutante(
        "D053-M5", "B3 lectura (a) fecha a fecha frente a (b) peor cierre",
        INT,
        "        s_pre = _saldo_en(antes.cierres, fecha, apertura)\n"
        "        s_post = _saldo_en(despues.cierres, fecha, apertura)\n",
        "        s_pre = min([apertura] + [v for _, v in antes.cierres])\n"
        "        s_post = min([apertura] + [v for _, v in despues.cierres])\n",
        "test_b3_discriminante_a_frente_a_b",
    ),
    Mutante(
        "D053-M6", "B3: mantener una incoherencia preexistente no se bloquea",
        INT,
        "        if s_post < CERO and s_post < s_pre:\n",
        "        if s_post < CERO:\n",
        "test_b3_mantener_no_se_bloquea",
    ),
    # --- B4 ---------------------------------------------------------------
    Mutante(
        "D053-M7", "B4: delta nuevo o cambio de fecha anterior al inicio",
        INT,
        "    if foto.determinado and foto.inicio is not None and fecha < foto.inicio:\n",
        "    if False:\n",
        "test_b4_creacion_anterior_al_inicio",
    ),
    Mutante(
        "D053-M8", "B4 en el alta (OP-12A y via OP-22)",
        INT,
        "    if repo_pos.delta_de_hecho_anterior_al_inicio(sesion, entidad_id, hecho_id):\n",
        "    if False:\n",
        "test_b4_alta_anterior_al_inicio",
    ),
    # --- B5 ---------------------------------------------------------------
    Mutante(
        "D053-M9", "B5: posicion cerrada inmutable aunque el saldo no cambie",
        INT,
        "    if antes.estado == ESTADO_CERRADA and despues.firma != antes.firma:\n",
        "    if False:\n",
        "test_b5_fecha_sin_cambio_de_saldo_rechazada",
    ),
    Mutante(
        "D053-M10", "B5: las conciliaciones de los hechos forman parte de la posicion",
        REPO,
        "                 WHERE c.hecho_id IN (\n",
        "                 WHERE FALSE AND c.hecho_id IN (\n",
        "test_b5_op09_anadir_asignacion_rechazada",
    ),
    # --- B6 ---------------------------------------------------------------
    Mutante(
        "D053-M11", "B6 L2: asignado = |efectos de posicion| (no agravar)",
        INT,
        "    if diferencia_post > diferencia_pre or (\n",
        "    if False and (\n",
        "test_b6_op21_descuadra_efecto_y_conciliacion",
    ),
    Mutante(
        "D053-M12", "B6: CONDONACION sin asignaciones",
        INT,
        "        if despues.asignado != 0 and abs(despues.asignado) > abs(antes.asignado):\n",
        "        if False:\n",
        "test_b6_op09_condonacion_sin_asignaciones",
    ),
    Mutante(
        "D053-M13", "Entrada de OP-09 en B1 (solo B5/B6)",
        TES,
        "            integridad_posicion.validar(sesion, fotos, reglas_saldo=False)\n",
        "",
        "test_b6_op09_dejaria_incompatible",
    ),
    # --- B8 ---------------------------------------------------------------
    Mutante(
        "D053-M14", "B8: raiz por posicion (FOR NO KEY UPDATE de entidades)",
        INT,
        "    return repo_pos.bloquear_posiciones(sesion, list(objetivo))\n",
        "    return list(objetivo)\n",
        "test_1_misma_posicion_serializa[op21_descripcion-op02]",
        CONCURRENCIA,
    ),
    Mutante(
        "D053-M15", "B8: advisory D-080 antes de cualquier fila en la creacion",
        POS,
        "                sesion, owner, posiciones=[entidad_id], advisory=True\n",
        "                sesion, owner, posiciones=[entidad_id], advisory=False\n",
        "test_4_mismo_owner_creaciones_serializan_en_advisory",
        CONCURRENCIA,
    ),
    Mutante(
        "D053-M16", "B8: advisory adelantado en OP-21 si cambia importe/tipo (D-158)",
        COR,
        '                        "importe_delta" in cambios or "tipo_efecto" in cambios\n',
        "                        False\n",
        "test_5_interbloqueo_d158_pausado[pareja0]",
        CONCURRENCIA,
    ),
)


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _recuperar_si_aborto_previo() -> None:
    if MARCADOR.exists():
        ruta_rel, original_hex = MARCADOR.read_text("ascii").split("\n", 1)
        (RAIZ / ruta_rel).write_bytes(bytes.fromhex(original_hex.strip()))
        MARCADOR.unlink()
        raise SystemExit(
            f"ABORTADO: habia una mutacion a medias en {ruta_rel}; restaurada. "
            "Revisa el arbol y vuelve a ejecutar."
        )


def _arbol_limpio() -> None:
    salida = subprocess.run(
        ["git", "status", "--porcelain"], cwd=RAIZ, capture_output=True, text=True
    ).stdout.strip()
    if salida:
        raise SystemExit("ABORTADO: el arbol de trabajo no esta limpio antes de empezar.")


def _pytest(suite: tuple[str, ...]) -> tuple[int, str]:
    proceso = subprocess.run(
        [sys.executable, "-m", "pytest", *suite, "-q", "-p", "no:cacheprovider", "-rf"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    return proceso.returncode, proceso.stdout + proceso.stderr


def ejecutar(m: Mutante) -> str:
    ruta = RAIZ / m.fichero
    original = ruta.read_bytes()
    sha_original = _sha(original)
    texto = original.decode("utf-8")
    apariciones = texto.count(m.viejo)
    if apariciones != 1:
        return f"DUDOSO    patron encontrado {apariciones} veces (se exige 1)"
    MARCADOR.write_text(f"{m.fichero}\n{original.hex()}", "ascii")
    try:
        ruta.write_bytes(texto.replace(m.viejo, m.nuevo, 1).encode("utf-8"))
        codigo, salida = _pytest(m.suite)
    finally:
        ruta.write_bytes(original)
        if _sha(ruta.read_bytes()) != sha_original:
            raise SystemExit(f"ABORTADO: restauracion fallida en {m.fichero}")
        MARCADOR.unlink()
    if "passed" not in salida and "failed" not in salida:
        return "DUDOSO    pytest no llego a ejecutarse"
    fallos = [l for l in salida.splitlines() if l.startswith("FAILED")]
    if codigo == 0:
        return "VIVO      ningun test cae"
    if not any(m.discriminante in l for l in fallos):
        return f"DUDOSO    caen {len(fallos)} tests pero no el discriminante"
    return f"MUERTO    fallos={len(fallos)}"


def main(argv: list[str]) -> int:
    _recuperar_si_aborto_previo()
    _arbol_limpio()
    for suite in (FUNCIONAL, CONCURRENCIA):
        codigo, _ = _pytest(suite)
        if codigo != 0:
            raise SystemExit(f"ABORTADO: la suite {suite} no esta verde antes de mutar.")
    seleccion = [m for m in MUTANTES if not argv or m.ident in argv]
    print("=== F04-D053 · MUTANTES ===")
    muertos = 0
    for m in seleccion:
        veredicto = ejecutar(m)
        muertos += veredicto.startswith("MUERTO")
        print(f"  {m.ident:9}  {veredicto}   [{m.guarda}] -> {m.discriminante}", flush=True)
    _arbol_limpio()
    print(f"RESULTADO: {muertos}/{len(seleccion)} muertos")
    return 0 if muertos == len(seleccion) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
