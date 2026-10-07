#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f04_d055.py
# Ruta: scripts/mutantes/f04_d055.py
# Descripcion: Arnes de mutacion de F04-D055 (ciclo de vida de la posicion
#   generica). CC-D055-3: A1 en cada via, A2, A4, B1 (estado, motivo,
#   row_version, raiz, NULLs, datos_antes), B2, B4; R-Q1 (L1 permisiva,
#   NO_DETERMINABLE que participa, ventana ignorada, ultima reduccion); R-Q2
#   (cualquier CERRAR global, ultimo evento por created_at, ACTUALIZAR como
#   CERRAR); R-Q3 / ajuste 10 (la lectura dentro del canonico y en F04-D053;
#   indicador por saldo.importe o ausente). Todos deben morir.
#
#   Cada mutante retira o deforma UNA regla (una o varias sustituciones de
#   texto exacto, p. ej. la guarda de servicio y su defensa en profundidad en
#   el repositorio) y declara su DISCRIMINANTE: el test concreto que debe
#   caer. No se da por muerto si solo caen tests colaterales. Los mutantes de
#   la raiz B8 y de created_at usan la bateria de concurrencia (test_149).
#
#   Mecanismo D-181/D-192 heredado de f04_d053: E/S byte a byte, cada patron
#   EXACTAMENTE una vez, marcador previo con los contenidos originales para
#   recuperarse de una ejecucion abortada, restauracion verificada por SHA-256
#   tambien si pytest aborta, y arbol limpio exigido antes y despues.
# Uso:
#   python scripts/mutantes/f04_d055.py             # todos
#   python scripts/mutantes/f04_d055.py D055-M4     # subconjunto
# Version: 0.1.0
#   0.1.0 (F04-D055 B1): 23 mutantes (DISENO_D055 §0.7).
# ============================================================
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
from dataclasses import dataclass

RAIZ = pathlib.Path(__file__).resolve().parents[2]
T109 = "tests/backend/test_109_op12_posiciones.py"
T144 = "tests/backend/test_144_f04_d052_causas_reduccion.py"
T148 = "tests/backend/test_148_f04_d055_ciclo_vida.py"
T149 = "tests/backend/test_149_f04_d055_concurrencia.py"
FUNCIONAL = (T148, T109, T144)
CONCURRENCIA = (T149,)
POS = "backend/app/services/posiciones_service.py"
REPO = "backend/app/repositories/posiciones_repository.py"
MOD = "backend/app/core/modelos_posicion.py"
INT = "backend/app/services/integridad_posicion.py"
MARCADOR = RAIZ / ".mutante_f04_d055_en_curso"


@dataclass(frozen=True)
class Mutante:
    ident: str
    regla: str
    sustituciones: tuple[tuple[str, str, str], ...]  # (fichero, viejo, nuevo)
    discriminante: str
    suite: tuple[str, ...] = FUNCIONAL


def _s(fichero: str, viejo: str, nuevo: str) -> tuple[str, str, str]:
    return (fichero, viejo, nuevo)


MUTANTES = (
    # --- A1 / A2 ------------------------------------------------------------
    Mutante("D055-M1", "A1 via cerrar_posicion", (
        _s(POS, "            self._exigir_saldo_cero(sesion, entidad_id, posicion)\n", ""),),
        "test_cc1_cierre_explicito_con_residual_rechazado"),
    Mutante("D055-M2", "A1 via _aplicar_delta con cierre", (
        _s(POS, "                self._exigir_saldo_cero(\n"
                "                    sesion, entidad_id, self._exigir_posicion(sesion, entidad_id)\n"
                "                )\n", ""),),
        "test_cc1_pago_parcial_con_cierre_rechazado"),
    Mutante("D055-M3", "A1 solo con saldo determinado (A3)", (
        _s(POS, "        if saldo.conocido and saldo.importe != CERO:\n",
                "        if not saldo.conocido or saldo.importe != CERO:\n"),),
        "test_cc1_cierre_indeterminado_por_declaracion"),
    Mutante("D055-M4", "A2: solo LIQUIDADA/CONDONADA en runtime", (
        _s(POS, "        if cierre.motivo_cierre not in MOTIVOS_CIERRE_RUNTIME:\n",
                "        if False:\n"),),
        "test_cc1_cancelada_y_otro_rechazados"),
    # --- R-Q1 -----------------------------------------------------------------
    Mutante("D055-M5", "R-Q1: L1 permisiva (sin determinacion)", (
        _s(POS, "        if len(motivos) == 1 and motivo_cierre not in motivos:\n",
                "        if False:\n"),),
        "test_rq1_pago_solo_liquidada"),
    Mutante("D055-M6", "R-Q1: NO_DETERMINABLE participa en S", (
        _s(POS, "            if leida.causa != CAUSA_NO_DETERMINABLE\n"
                "        }\n"
                "        motivos = {MOTIVO_CIERRE_DE_CAUSA[CausaReduccion(c)] for c in causas}\n",
                "        }\n"
                "        motivos = {MOTIVO_CIERRE_DE_CAUSA[CausaReduccion(c)] if c != CAUSA_NO_DETERMINABLE"
                " else c for c in causas}\n"),),
        "test_rq1_pago_y_no_determinable_solo_liquidada"),
    Mutante("D055-M7", "R-Q1: ventana canonica ignorada", (
        _s(POS, "                sesion, entidad_id, posicion, en_ventana=True\n",
                "                sesion, entidad_id, posicion, en_ventana=False\n"),),
        "test_rq1_reduccion_anterior_al_inicio_fuera_de_s"),
    Mutante("D055-M8", "R-Q1: motivo por la ultima reduccion", (
        _s(POS, "        motivos = {MOTIVO_CIERRE_DE_CAUSA[CausaReduccion(c)] for c in causas}\n",
                "        _ultima = [x.causa for x in self._causas_leidas(sesion, entidad_id, posicion,"
                " en_ventana=True) if x.causa != CAUSA_NO_DETERMINABLE][-1:]\n"
                "        motivos = {MOTIVO_CIERRE_DE_CAUSA[CausaReduccion(c)] for c in _ultima}\n"),),
        "test_rq1_no_depende_de_la_ultima_reduccion"),
    # --- A4 / R-Q3 --------------------------------------------------------------
    Mutante("D055-M9", "A4: una CERRADA se lee con el canonico", (
        _s(POS, '            return Saldo.de(CERO), posicion["saldo_apertura"] is None\n',
                '            return self._calcular_saldo(sesion, entidad_id, posicion),'
                ' posicion["saldo_apertura"] is None\n'),),
        "test_rq3_cerrada_legacy_con_residual"),
    Mutante("D055-M10", "A4: indicador transportado por saldo.importe", (
        _s(POS, '            return Saldo.de(CERO), posicion["saldo_apertura"] is None\n',
                '            return (Saldo.indeterminado() if posicion["saldo_apertura"] is None'
                ' else Saldo.de(CERO)), False\n'),),
        "test_rq3_cerrada_indeterminada"),
    Mutante("D055-M11", "A4: indicador ausente", (
        _s(POS, '            return Saldo.de(CERO), posicion["saldo_apertura"] is None\n',
                '            return Saldo.de(CERO), False\n'),),
        "test_rq3_cerrada_indeterminada"),
    Mutante("D055-M16", "R-Q3 (ajuste 10): la lectura dentro del canonico", (
        _s(POS, '        if posicion["saldo_apertura"] is None:\n'
                '            return Saldo.indeterminado()\n',
                '        if posicion["estado"] == ESTADO_CERRADA:\n'
                '            return Saldo.de(CERO)\n'
                '        if posicion["saldo_apertura"] is None:\n'
                '            return Saldo.indeterminado()\n'),),
        "test_rq3_ningun_validador_lee_la_lectura"),
    Mutante("D055-M17", "R-Q3 (ajuste 10): F04-D053 lee la CERRADA como 0", (
        _s(INT, "            cierres=_cierres(sesion, entidad_id, posicion) if determinado else (),\n",
                "            cierres=_cierres(sesion, entidad_id, posicion)"
                " if determinado and posicion[\"estado\"] != ESTADO_CERRADA else (),\n"),),
        "test_a1_cierre_con_trayectoria_invalida_lo_rechaza_d053"),
    # --- B1 -------------------------------------------------------------------
    Mutante("D055-M12", "B1: solo desde CERRADA (servicio y WHERE)", (
        _s(POS, '            if posicion["estado"] != ESTADO_CERRADA:\n'
                '                raise ErrorMotor(\n'
                '                    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,\n'
                '                    "Solo se reabre una posicion CERRADA.",\n'
                '                )\n'
                '            self._tocar_entidad(sesion, entidad_id, entidad_row_version_esperada)\n',
                '            self._tocar_entidad(sesion, entidad_id, entidad_row_version_esperada)\n'),
        _s(REPO, "         WHERE p.entidad_id = %s::uuid\n"
                 "           AND p.estado = 'CERRADA'\n",
                 "         WHERE p.entidad_id = %s::uuid\n")),
        "test_cc1_reabrir_activa_rechazada"),
    Mutante("D055-M13", "B1: motivo textual obligatorio", (
        _s(POS, "        if not isinstance(motivo, str) or not motivo.strip():\n",
                "        if False:\n"),),
        "test_cc1_reabrir_sin_motivo_rechazada"),
    Mutante("D055-M14", "B1: control optimista (row_version)", (
        _s(POS, "            self._tocar_entidad(sesion, entidad_id, entidad_row_version_esperada)\n"
                "            cerrar, reabrir = repo_pos.recuento_ciclo(sesion, entidad_id)\n",
                "            cerrar, reabrir = repo_pos.recuento_ciclo(sesion, entidad_id)\n"),),
        "test_cc1_reabrir_version_obsoleta_rechazada"),
    Mutante("D055-M15", "B1: motivo y fecha de cierre a NULL", (
        _s(REPO, "               fecha_cierre = NULL\n",
                 "               fecha_cierre = p.fecha_cierre\n"),),
        "test_cc1_reabrir_y_volver_a_cerrar"),
    Mutante("D055-M18", "B1: datos_antes = estado encontrado", (
        _s(POS, '                datos_antes_json=posicion["snapshot"],\n',
                "                datos_antes_json=snapshot,\n"),),
        "test_rq2_cerrar_reabrir"),
    Mutante("D055-M23", "B1: reabrir bajo la raiz B8", (
        _s(POS, "            integridad_posicion.adquirir_raiz(sesion, owner, posiciones=[entidad_id])\n"
                "            posicion = self._exigir_posicion(sesion, entidad_id)\n"
                '            if posicion["estado"] != ESTADO_CERRADA:\n',
                "            posicion = self._exigir_posicion(sesion, entidad_id)\n"
                '            if posicion["estado"] != ESTADO_CERRADA:\n'),),
        "test_1_reapertura_misma_posicion_serializa[cerrar-reabrir]", CONCURRENCIA),
    # --- B2 / B4 / R-Q2 -------------------------------------------------------
    Mutante("D055-M19", "B2: el cierre se audita CERRAR", (
        _s(POS, "            accion=auditoria.ACCION_CERRAR,\n",
                "            accion=auditoria.ACCION_ACTUALIZAR,\n"),),
        "test_rq2_cerrar_reabrir"),
    Mutante("D055-M20", "R-Q2: no basta con cualquier CERRAR global", (
        _s(POS, "            legacy = cerrar < max(reabrir, 1)\n",
                "            legacy = cerrar == 0\n"),),
        "test_rq2_varias_reaperturas_y_cierre_sql_directo"),
    Mutante("D055-M21", "R-Q2: no se decide por el ultimo evento segun created_at", (
        _s(POS, "            legacy = cerrar < max(reabrir, 1)\n",
                "            legacy = sesion.uno(\"SELECT accion FROM gapto.auditoria"
                " WHERE tabla = 'derechos_obligaciones_financieras' AND registro_id = %s::uuid"
                " AND accion IN ('CERRAR', 'REABRIR') ORDER BY created_at DESC, id DESC LIMIT 1\","
                " (entidad_id,)) != ('CERRAR',)\n"),),
        "test_3_rq2_orden_created_at_no_decide", CONCURRENCIA),
    Mutante("D055-M22", "R-Q2: ACTUALIZAR no cuenta como CERRAR", (
        _s(REPO, "        SELECT count(*) FILTER (WHERE a.accion = 'CERRAR'),\n",
                 "        SELECT count(*) FILTER (WHERE a.accion IN ('CERRAR', 'ACTUALIZAR')),\n"),),
        "test_rq2_cierre_antiguo_actualizar"),
)


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _recuperar_si_aborto_previo() -> None:
    if MARCADOR.exists():
        originales = json.loads(MARCADOR.read_text("ascii"))
        for ruta_rel, original_hex in originales.items():
            (RAIZ / ruta_rel).write_bytes(bytes.fromhex(original_hex))
        MARCADOR.unlink()
        raise SystemExit(
            f"ABORTADO: habia una mutacion a medias en {sorted(originales)}; restaurada. "
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
    ficheros = sorted({f for f, _, _ in m.sustituciones})
    originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
    textos = {f: originales[f].decode("utf-8") for f in ficheros}
    for fichero, viejo, nuevo in m.sustituciones:
        apariciones = textos[fichero].count(viejo)
        if apariciones != 1:
            return f"DUDOSO    patron en {fichero} encontrado {apariciones} veces (se exige 1)"
        textos[fichero] = textos[fichero].replace(viejo, nuevo, 1)
    MARCADOR.write_text(json.dumps({f: originales[f].hex() for f in ficheros}), "ascii")
    try:
        for fichero in ficheros:
            (RAIZ / fichero).write_bytes(textos[fichero].encode("utf-8"))
        codigo, salida = _pytest(m.suite)
    finally:
        for fichero in ficheros:
            (RAIZ / fichero).write_bytes(originales[fichero])
            if _sha((RAIZ / fichero).read_bytes()) != _sha(originales[fichero]):
                raise SystemExit(f"ABORTADO: restauracion fallida en {fichero}")
        MARCADOR.unlink()
    if "passed" not in salida and "failed" not in salida:
        return "DUDOSO    pytest no llego a ejecutarse"
    fallos = [linea for linea in salida.splitlines() if linea.startswith("FAILED")]
    if codigo == 0:
        return "VIVO      ningun test cae"
    if not any(m.discriminante in linea for linea in fallos):
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
    print("=== F04-D055 · MUTANTES ===")
    muertos = 0
    for m in seleccion:
        veredicto = ejecutar(m)
        muertos += veredicto.startswith("MUERTO")
        print(f"  {m.ident:9}  {veredicto}   [{m.regla}] -> {m.discriminante}", flush=True)
    _arbol_limpio()
    print(f"RESULTADO: {muertos}/{len(seleccion)} muertos")
    return 0 if muertos == len(seleccion) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
