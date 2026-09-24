#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f04d046_r2.py
# Ruta: scripts/mutantes/f04d046_r2.py
# Descripcion: Arnes de mutacion de F04-D046 R2 (A20 + A08-bis):
#   `presupuestable` y localizacion en OP-13, OP-18 y OP-21.
#
#   Cada mutante retira UNA guarda de codigo y declara su DISCRIMINANTE: el
#   test concreto de `test_136` que debe caer. No se da por muerto si solo
#   caen tests colaterales.
#
#   Guardas heredadas de f0406/f0407 (D-181): E/S byte a byte, patron que
#   debe aparecer EXACTAMENTE una vez, marcador previo con el contenido
#   original para recuperarse de una ejecucion abortada, restauracion
#   verificada por SHA-256 tambien si pytest aborta, y arbol limpio exigido.
# Uso:
#   python scripts/mutantes/f04d046_r2.py          # todos
#   python scripts/mutantes/f04d046_r2.py R2-M3    # subconjunto
# Version: 0.2.0
#   0.2.0 (mandato F04 R1+R2 v0.3 + E01): la suite pasa a ser test_136 +
#   test_137 y se anaden R2-M8..R2-M21 sobre las guardas de frontera
#   generalizadas (OP-04, OP-19, OP-21, OP-13/OP-18 NO_APLICA, condonacion y
#   defaults de los helpers de posiciones). Mismo mecanismo D-181/D-192.
# Version: 0.1.0
# ============================================================
from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys
from dataclasses import dataclass

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SUITE = (
    "tests/backend/test_136_f04_d046_r2_presupuestable_localizacion.py",
    "tests/backend/test_137_f04_r1r2_v03_fronteras.py",
)
DEV = "backend/app/services/devoluciones_service.py"
COR = "backend/app/services/correcciones_service.py"
EFE = "backend/app/services/efectos_service.py"
COM = "backend/app/services/compartidos_service.py"
POS = "backend/app/services/posiciones_service.py"
MARCADOR = RAIZ / ".mutante_f04d046_r2_en_curso"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    fichero: str
    viejo: str
    nuevo: str
    discriminante: str


MUTANTES = (
    Mutante(
        "R2-M1",
        "OP-13/OP-18 persisten la decision declarada, no un false fijo",
        DEV,
        "        decision = bool(presupuestable)\n",
        "        decision = False\n",
        "test_r2_03_consumo_neto_60",
    ),
    Mutante(
        "R2-M2",
        "Localizacion aplicable sin dato -> DESCONOCIDA, nunca NO_APLICA",
        DEV,
        '        estado = "DESCONOCIDA" if localidad_id is None else "CONOCIDA"\n',
        '        estado = "NO_APLICA" if localidad_id is None else "CONOCIDA"\n',
        "test_r2_07_devolucion_con_localizacion_desconocida",
    ),
    Mutante(
        "R2-M3",
        "Sin default oculto: GASTO/INGRESO exige decision explicita",
        DEV,
        "    if tipo_efecto in NATURALEZAS_PRESUPUESTABLES:\n        if presupuestable is None:\n",
        "    if tipo_efecto in NATURALEZAS_PRESUPUESTABLES:\n        if False:\n",
        "test_r2_04b_devolucion_sin_decision_se_rechaza",
    ),
    Mutante(
        "R2-M4",
        "Sin GASTO/INGRESO, declarar true se rechaza (false derivado)",
        DEV,
        "        if presupuestable is True:\n",
        "        if False:\n",
        "test_r2_10b_declarar_true_sin_gasto_ni_ingreso_se_rechaza",
    ),
    Mutante(
        "R2-M5",
        "OP-21 que introduce el primer GASTO/INGRESO exige decision",
        COR,
        "        if not elegible_antes and elegible_despues:\n            if datos.presupuestable is None:\n",
        "        if not elegible_antes and elegible_despues:\n            if False:\n",
        "test_r2_11_primer_gasto_por_op21_exige_decision",
    ),
    Mutante(
        "R2-M6",
        "OP-21 que retira el ultimo GASTO/INGRESO deriva false",
        COR,
        "        elif elegible_antes and not elegible_despues:\n",
        "        elif False:\n",
        "test_r2_10_solo_inversion_deriva_presupuestable_false",
    ),
    Mutante(
        "R2-M7",
        "El replay de OP-13 compara la decision historica (otra = conflicto)",
        DEV,
        "        if not repo_hechos.creacion_previa_coincide(\n            sesion, self._datos_hecho(datos), tipo_hecho_id\n        ):\n",
        "        if False:\n",
        "test_r2_idem_misma_identidad_otra_decision_es_conflicto",
    ),
    Mutante(
        "R2-M8",
        "OP-04: la transicion sin->con GASTO/INGRESO exige decision",
        EFE,
        '        if presupuestable is None:\n            raise ErrorMotor(\n                CodigoError.ENTRADA_INVALIDA,\n                "OP-04 introduce',
        '        if False:\n            raise ErrorMotor(\n                CodigoError.ENTRADA_INVALIDA,\n                "OP-04 introduce',
        "test_14_op04_sin_decision_rollback_total",
    ),
    Mutante(
        "R2-M9",
        "OP-04: el valor almacenado INACTIVO no sustituye la decision",
        EFE,
        "        transicion = escribe_elegible and not elegible_antes\n",
        "        transicion = escribe_elegible and not elegible_antes and presupuestable is not None\n",
        "test_15_16_valor_inactivo_almacenado_no_sustituye_decision_en_op04",
    ),
    Mutante(
        "R2-M10",
        "OP-04: GASTO/INGRESO no admite NO_APLICA",
        EFE,
        "            escribe_elegible\n            and snapshot.get(",
        "            False\n            and snapshot.get(",
        "test_20_op04_gasto_en_hecho_no_aplica_se_rechaza",
    ),
    Mutante(
        "R2-M11",
        "OP-04 sin transicion rechaza `presupuestable` explicito",
        EFE,
        '            if presupuestable is not None:\n                raise ErrorMotor(\n                    CodigoError.ENTRADA_INVALIDA,\n                    "Esta llamada',
        '            if False:\n                raise ErrorMotor(\n                    CodigoError.ENTRADA_INVALIDA,\n                    "Esta llamada',
        "test_op04_sin_transicion_rechaza_decision_explicita",
    ),
    Mutante(
        "R2-M12",
        "OP-19 propaga a OP-04 la decision de datos.hecho",
        COM,
        "                presupuestable=(\n                    datos.hecho.presupuestable\n",
        "                presupuestable=(\n                    None\n",
        "test_24_op19_propaga_la_decision_explicita",
    ),
    Mutante(
        "R2-M13",
        "OP-21 que escribe GASTO/INGRESO no admite NO_APLICA",
        COR,
        "        if not escribe_elegible:\n            return\n",
        "        if True:\n            return\n",
        "test_21_op21_crear_gasto_en_hecho_no_aplica_se_rechaza",
    ),
    Mutante(
        "R2-M14",
        "OP-13/OP-18 con GASTO/INGRESO rechazan NO_APLICA declarado",
        DEV,
        '            estado_localizacion == "NO_APLICA"\n            and tipo_efecto in NATURALEZAS_PRESUPUESTABLES\n',
        '            False\n            and tipo_efecto in NATURALEZAS_PRESUPUESTABLES\n',
        "test_17_op13_gasto_con_no_aplica_se_rechaza",
    ),
    Mutante(
        "R2-M15",
        "Condonacion con GASTO exige decision presupuestaria",
        POS,
        "        if datos.presupuestable is None or not isinstance(\n            datos.presupuestable, bool\n        ):\n",
        "        if False:\n",
        "test_22_27_condonacion_con_gasto_sin_decision_se_rechaza",
    ),
    Mutante(
        "R2-M16",
        "Condonacion con GASTO rechaza NO_APLICA",
        POS,
        "            if datos.estado_localizacion == LOCALIZACION_POSICION:\n",
        "            if False:\n",
        "test_23_28_condonacion_con_gasto_y_no_aplica_se_rechaza",
    ),
    Mutante(
        "R2-M17",
        "Condonacion persiste la decision aportada, no el false fijo de posicion",
        POS,
        '            "presupuestable_hecho": datos.presupuestable,\n',
        '            "presupuestable_hecho": False,\n',
        "test_25_26_29_condonacion_con_gasto_persiste_la_decision",
    ),
    Mutante(
        "R2-M18",
        "Replay de condonacion compara la decision persistida",
        POS,
        "                if verificar_hecho_en_replay:\n",
        "                if False:\n",
        "test_condonacion_reintento_con_otra_decision_es_otra_intencion",
    ),
    Mutante(
        "R2-M19",
        "Replay de OP-04 compara la decision presupuestaria",
        EFE,
        "                if presupuestable is not None and (\n",
        "                if False and (\n",
        "test_op04_reintento_con_otra_decision_es_otra_intencion",
    ),
    Mutante(
        "R2-M20",
        "OP-21: en la transicion la decision se persiste aunque coincida",
        COR,
        "        if actual == objetivo and elegible_antes:\n",
        "        if actual == objetivo:\n",
        "test_r2_11b_primer_gasto_con_decision_explicita",
    ),
    Mutante(
        "R2-M21",
        "Defaults de los helpers de posiciones = comportamiento previo",
        POS,
        "        presupuestable_hecho: bool = PRESUPUESTABLE_POSICION,\n",
        "        presupuestable_hecho: bool = True,\n",
        "test_31_resto_de_operaciones_de_posiciones_sin_cambio_observable",
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


def _pytest() -> tuple[int, str]:
    proceso = subprocess.run(
        [sys.executable, "-m", "pytest", *SUITE, "-q", "-p", "no:cacheprovider", "-rf"],
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
        codigo, salida = _pytest()
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
    codigo, salida = _pytest()
    if codigo != 0:
        raise SystemExit("ABORTADO: la suite R2 no esta verde antes de mutar.")
    seleccion = [m for m in MUTANTES if not argv or m.ident in argv]
    print("=== F04-D046 R2 · MUTANTES ===")
    muertos = 0
    for m in seleccion:
        veredicto = ejecutar(m)
        muertos += veredicto.startswith("MUERTO")
        print(f"  {m.ident:7}  {veredicto}   [{m.invariante}]")
    _arbol_limpio()
    print(f"RESULTADO: {muertos}/{len(seleccion)} muertos")
    return 0 if muertos == len(seleccion) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
