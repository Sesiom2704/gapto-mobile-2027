#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f04_d052.py
# Ruta: scripts/mutantes/f04_d052.py
# Descripcion: Arnes de mutacion de F04-D052 B2 (causa de reduccion,
#   condonacion de obligacion y cuenta Gapto en pagos y cobros propios).
#
#   Cada mutante retira UNA guarda y declara su DISCRIMINANTE: el test
#   concreto de test_144 que debe caer. No se da por muerto si solo caen
#   tests colaterales.
#
#   Mecanismo D-181/D-192 heredado de f04d046_r2: E/S byte a byte, patron que
#   debe aparecer EXACTAMENTE una vez, marcador previo con el contenido
#   original para recuperarse de una ejecucion abortada, restauracion
#   verificada por SHA-256 tambien si pytest aborta, y arbol limpio exigido
#   antes y despues.
#
#   Cobertura exigida (mandato B2 v0.3 §2): causa invalida (M1), cuenta en
#   OP-12B (M3) y OP-14 (M4), REEMBOLSO sin movimiento (M17), CONDONACION
#   con movimiento (M2), pago por tercero (M5), subtipo de financiacion (M6),
#   tope de INGRESO (M7), INGRESO duplicado (M9), NO_APLICA con INGRESO
#   (M18), §9 saldo indeterminado (M19) y motivo_cierre <-> causa (M12).
#
#   Enmienda E1 (frontera OP-04/OP-21 por arquetipo; discriminantes en
#   test_145): I1 (M20), I4 (M21), I2 (M22), I3/I5 (M23, una sola comprobacion
#   fisica sobre el estado final), I6 al crear (M24) e I6 al mutar (M25).
# Uso:
#   python scripts/mutantes/f04_d052.py            # todos
#   python scripts/mutantes/f04_d052.py D052-M3    # subconjunto
# Version: 0.2.1
#   0.2.1 (F04-D055 B1): D052-M16 sigue a la clasificacion de causas, que
#   pasa a `PosicionesService._causas_leidas` (sangria de 20 a 16 espacios).
#   Misma mutacion y mismo discriminante.
# Version: 0.2.0
#   0.2.0 (F04-D052 enmienda E1): suite test_144 + test_145 y mutantes
#   D052-M20..M25 sobre las guardas I1-I6 de OP-04/OP-21.
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
    "tests/backend/test_144_f04_d052_causas_reduccion.py",
    "tests/backend/test_145_f04_d052_e1_op04_op21.py",
)
POS = "backend/app/services/posiciones_service.py"
EFE = "backend/app/services/efectos_service.py"
REPO = "backend/app/repositories/posiciones_repository.py"
MARCADOR = RAIZ / ".mutante_f04_d052_en_curso"


@dataclass(frozen=True)
class Mutante:
    ident: str
    guarda: str
    fichero: str
    viejo: str
    nuevo: str
    discriminante: str


MUTANTES = (
    Mutante(
        "D052-M1", "Causa obligatoria y de la operacion (ausente/ajena/desconocida -> STOP)",
        POS,
        "        if (\n"
        "            not isinstance(delta.causa, CausaReduccion)\n"
        "            or delta.causa is not causa_esperada\n"
        "        ):\n",
        "        if False:\n",
        "test_7_op12b_causa_erronea_stop[ausente]",
    ),
    Mutante(
        "D052-M2", "CONDONACION con movimiento no entra por OP-12B",
        POS,
        "            or delta.causa is not causa_esperada\n",
        "            or delta.causa not in (causa_esperada, CausaReduccion.CONDONACION)\n",
        "test_7_op12b_causa_erronea_stop[condonacion_con_movimiento]",
    ),
    Mutante(
        "D052-M3", "PAGO sin movimiento -> CUENTA_GAPTO_REQUERIDA (OP-12B)",
        POS,
        "            causa_esperada=CausaReduccion.PAGO,\n"
        "            tesoreria=movimiento,\n"
        "            exige_tesoreria=True,\n",
        "            causa_esperada=CausaReduccion.PAGO,\n"
        "            tesoreria=movimiento,\n",
        "test_2_pago_sin_cuenta_stop",
    ),
    Mutante(
        "D052-M4", "COBRO sin movimiento -> CUENTA_GAPTO_REQUERIDA (OP-14)",
        POS,
        "            causa_esperada=CausaReduccion.COBRO,\n"
        "            tesoreria=datos.tesoreria,\n"
        "            exige_tesoreria=True,\n",
        "            causa_esperada=CausaReduccion.COBRO,\n"
        "            tesoreria=datos.tesoreria,\n",
        "test_3_cobro_sin_cuenta_stop",
    ),
    Mutante(
        "D052-M5", "Pago por tercero -> STOP sin escrituras (R-F04-038)",
        POS,
        "        if pagado_por_tercero is not False:\n",
        "        if False:\n",
        "test_7_pago_por_tercero_stop_sin_nada",
    ),
    Mutante(
        "D052-M6", "Cuota/entidad de financiacion formal no entra por CONDONACION (subtipo exigido, D4)",
        REPO,
        "        SELECT e.row_version, p.tipo, p.moneda, p.estado, p.saldo_apertura,\n"
        "               p.fecha_inicio_seguimiento, p.contraparte_actor_id,\n"
        "               p.importe_original_documentado, ({})::text AS snap_posicion\n"
        "          FROM gapto.derechos_obligaciones_financieras p\n"
        "          JOIN gapto.entidades e ON e.id = p.entidad_id\n"
        "         WHERE p.entidad_id = %s::uuid\n",
        "        SELECT e.row_version, COALESCE(p.tipo, 'OBLIGACION_PAGO'),\n"
        "               COALESCE(p.moneda, 'EUR'), COALESCE(p.estado, 'ACTIVA'),\n"
        "               p.saldo_apertura,\n"
        "               p.fecha_inicio_seguimiento, p.contraparte_actor_id,\n"
        "               p.importe_original_documentado, ({})::text AS snap_posicion\n"
        "          FROM gapto.entidades e\n"
        "          LEFT JOIN gapto.derechos_obligaciones_financieras p ON p.entidad_id = e.id\n"
        "         WHERE e.id = %s::uuid\n",
        "test_8_financiacion_formal_no_entra_por_condonacion[entidad]",
    ),
    Mutante(
        "D052-M7", "INGRESO declarado no excede lo condonado",
        POS,
        "            if datos.delta.importe is not None and importe_ingreso > decimal.Decimal(\n",
        "            if False and importe_ingreso > decimal.Decimal(\n",
        "test_6_ingreso_fuera_de_rango_rechazado[40.0001]",
    ),
    Mutante(
        "D052-M8", "INGRESO declarado mayor que cero",
        POS,
        "            if importe_ingreso <= CERO:\n",
        "            if False:\n",
        "test_6_ingreso_fuera_de_rango_rechazado[0]",
    ),
    Mutante(
        "D052-M9", "Como maximo un INGRESO por hecho de condonacion (D6)",
        POS,
        "            artefactos_extra=(\n"
        "                []\n"
        "                if datos.efecto_ingreso_id is None\n"
        "                else [(\"hecho_efectos\", datos.efecto_ingreso_id)]\n"
        "            ),\n",
        "            artefactos_extra=[],\n",
        "test_6_ingreso_duplicado_sobre_la_misma_porcion_rechazado",
    ),
    Mutante(
        "D052-M10", "INGRESO nunca inferido: cero por defecto",
        POS,
        "        con_ingreso = datos.importe_ingreso is not None\n",
        "        con_ingreso = True\n",
        "test_6_ingreso_cero_por_defecto",
    ),
    Mutante(
        "D052-M11", "INGRESO declarado sigue el contrato E01 (presupuestable explicito)",
        POS,
        "        decision_hecho = self._decision_hecho_condonacion(datos, con_ingreso)\n",
        "        decision_hecho = self._decision_hecho_condonacion(datos, False)\n",
        "test_6_ingreso_declarado_sigue_el_contrato_e01",
    ),
    Mutante(
        "D052-M12", "Motivo de cierre coherente con la causa (sin causa mixta)",
        POS,
        "            if delta.cierre.motivo_cierre != MOTIVO_CIERRE_DE_CAUSA[causa_esperada]:\n",
        "            if False:\n",
        "test_7_motivo_de_cierre_incoherente_con_la_causa",
    ),
    Mutante(
        "D052-M13", "PAGO usa el arquetipo REEMBOLSO",
        POS,
        "            tipo_esperado=TIPO_OBLIGACION,\n"
        "            tipo_hecho_codigo=TIPO_HECHO_REEMBOLSO,\n",
        "            tipo_esperado=TIPO_OBLIGACION,\n"
        "            tipo_hecho_codigo=TIPO_HECHO_POSICION,\n",
        "test_1_pago_es_reembolso_con_movimiento",
    ),
    Mutante(
        "D052-M14", "Condonacion de obligacion usa el arquetipo CONDONACION",
        POS,
        "            tipo_esperado=TIPO_OBLIGACION,\n"
        "            tipo_hecho_codigo=TIPO_HECHO_CONDONACION,\n",
        "            tipo_esperado=TIPO_OBLIGACION,\n"
        "            tipo_hecho_codigo=TIPO_HECHO_POSICION,\n",
        "test_4_condonacion_parcial_queda_activa",
    ),
    Mutante(
        "D052-M15", "Condonacion de derecho usa el arquetipo CONDONACION",
        POS,
        "            tipo_esperado=TIPO_DERECHO,\n"
        "            tipo_hecho_codigo=TIPO_HECHO_CONDONACION,\n",
        "            tipo_esperado=TIPO_DERECHO,\n"
        "            tipo_hecho_codigo=TIPO_HECHO_POSICION,\n",
        "test_5_cobro_y_condonacion_de_derecho_fisicamente_diferenciables",
    ),
    Mutante(
        "D052-M16", "Lectura: GENERACION_DERECHO_OBLIGACION -> causa no determinable",
        POS,
        "                causa = CAUSA_NO_DETERMINABLE\n",
        "                causa = causa_reembolso.value\n",
        "test_cc4_historico_causa_no_determinable_sin_reclasificar",
    ),
    Mutante(
        "D052-M17", "Nucleo: REEMBOLSO (pago/cobro) nunca sin movimiento en cuenta Gapto",
        POS,
        "        if exige_tesoreria and tesoreria is None:\n",
        "        if False:\n",
        "test_2_pago_sin_cuenta_stop",
    ),
    Mutante(
        "D052-M18", "INGRESO declarado rechaza NO_APLICA (E01)",
        POS,
        "            if datos.estado_localizacion == LOCALIZACION_POSICION:\n",
        "            if False:\n",
        "test_6_ingreso_declarado_sin_contrato_e01_rechazado[no_aplica]",
    ),
    Mutante(
        "D052-M19", "§9: saldo indeterminado admitido sin validar importe",
        POS,
        "            if saldo.conocido and importe > saldo.importe:\n",
        "            if importe > saldo.importe:\n",
        "test_4_condonacion_saldo_indeterminado_sin_validar_importe",
    ),
    Mutante(
        "D052-M20", "E1-I1: OP-04/OP-21 no crean GASTO/INGRESO en un hecho CONDONACION",
        EFE,
        "        raise ErrorMotor(\n"
        "            CodigoError.CONDONACION_EFECTO_NO_PERMITIDO,\n"
        "            \"I1: ",
        "        if False: raise ErrorMotor(\n"
        "            CodigoError.CONDONACION_EFECTO_NO_PERMITIDO,\n"
        "            \"I1: ",
        "test_i1_op04_no_crea_gasto_ni_ingreso_en_condonacion",
    ),
    Mutante(
        "D052-M21", "E1-I4: como maximo un efecto declarado por hecho CONDONACION",
        EFE,
        "        if _declarados_de(sesion, hecho_id):\n",
        "        if False:\n",
        "test_i4_op04_segundo_ingreso_declarado",
    ),
    Mutante(
        "D052-M22", "E1-I2: sin reclasificar hacia/desde GASTO/INGRESO en CONDONACION",
        EFE,
        "        arquetipo == ARQUETIPO_CONDONACION\n"
        "        and tipo_antes != tipo_despues\n",
        "        False\n"
        "        and tipo_antes != tipo_despues\n",
        "test_i2_op21_no_cambia_la_naturaleza_del_declarado",
    ),
    Mutante(
        "D052-M23", "E1-I3/I5: el declarado no supera lo condonado (estado final)",
        EFE,
        "    if decimal.Decimal(declarados[0][\"neto\"]) > condonado:\n",
        "    if False:\n",
        "test_i5_op21_reducir_lo_condonado_por_debajo_del_declarado",
    ),
    Mutante(
        "D052-M24", "E1-I6: REEMBOLSO sin INGRESO ni GASTO negativo al crear",
        EFE,
        "    if arquetipo == ARQUETIPO_REEMBOLSO and (\n",
        "    if False and (\n",
        "test_i6_op04_reembolso_sin_ingreso_ni_gasto_negativo",
    ),
    Mutante(
        "D052-M25", "E1-I6: REEMBOLSO sin INGRESO ni GASTO negativo al mutar",
        EFE,
        "        if muta and (\n",
        "        if False and (\n",
        "test_i6_regresion_gasto_positivo_admitido_y_no_mutable_a_negativo",
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
    codigo, _ = _pytest()
    if codigo != 0:
        raise SystemExit("ABORTADO: la suite D052 no esta verde antes de mutar.")
    seleccion = [m for m in MUTANTES if not argv or m.ident in argv]
    print("=== F04-D052 B2 · MUTANTES ===")
    muertos = 0
    for m in seleccion:
        veredicto = ejecutar(m)
        muertos += veredicto.startswith("MUERTO")
        print(f"  {m.ident:9}  {veredicto}   [{m.guarda}] -> {m.discriminante}")
    _arbol_limpio()
    print(f"RESULTADO: {muertos}/{len(seleccion)} muertos")
    return 0 if muertos == len(seleccion) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
