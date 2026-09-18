# ============================================================
# GAPTO MOBILE 2027
# Fichero: f0405.py
# Ruta: scripts/mutantes/f0405.py
# Descripcion: Arnes de mutacion de F04-05. Aplica una a una las veinte
#   mutaciones CONTRACTUALES del mandato 80 y las adicionales E1..E12, ejecuta
#   la suite discriminante y restaura el fichero.
#
#   POR QUE VIVE EN EL REPOSITORIO. En F04-05 el resultado de mutacion ES
#   evidencia de cierre. Una tabla "20/20 muertos" en un handoff no es
#   verificable por nadie mas; este fichero hace que la evidencia sea
#   reproducible desde el mismo commit que se certifica.
#
#   POR QUE TIENE TANTAS GUARDAS. Todas vienen de un fallo real de esta fase:
#
#   - ARBOL LIMPIO ANTES. Mutar sobre un arbol sucio mezcla mutacion y trabajo
#     en curso: `git checkout` revierte lo trackeado y deja lo demas, y el
#     recuento sale falso.
#   - SHA-256 ANTES/DESPUES. Un patron que no casa, o que casa sin cambiar
#     nada, produce una MUTACION INERTE que pasa por superviviente.
#   - RESUMEN DE PYTEST OBLIGATORIO. Un argumento invalido hace que pytest
#     aborte sin ejecutar ni un test; "cero fallos" pasaria por superviviente.
#     Esta guarda existe porque ocurrio: una pasada entera dio 0/32 falsos.
#   - DISCRIMINANTE DECLARADO. No basta con que fallen tests: debe fallar el
#     que se declara como discriminante. Asi un mutante no puede darse por
#     muerto por un fallo colateral.
#   - RESTAURACION VERIFICADA Y ARBOL LIMPIO AL TERMINAR.
#
#   Cualquiera de esas guardas deja el resultado en estado DUDOSO, y el codigo
#   de salida deja de ser 0. Un arnes que no puede demostrar que hizo su
#   trabajo no vale mas que no ejecutarlo.
#
#   NO toca PostgreSQL, no aplica DDL, no lee credenciales y no depende de
#   rutas del entorno de quien lo ejecuta: el root se resuelve desde la
#   posicion de este fichero. Usa la conexion que ya define
#   `GAPTO_TEST_DATABASE_URL`, como el resto de la suite.
#
# Uso:
#   python scripts/mutantes/f0405.py            # los 32
#   python scripts/mutantes/f0405.py M1 M2 E7   # un lote
#
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys
from dataclasses import dataclass

# El root se deduce de la posicion del fichero: scripts/mutantes/f0405.py
RAIZ = pathlib.Path(__file__).resolve().parents[2]

REC = "backend/app/core/recurrencia.py"
SRV = "backend/app/services/previsiones_service.py"
REP = "backend/app/repositories/previsiones_repository.py"
RGR = "backend/app/repositories/reglas_repository.py"
HEC = "backend/app/services/hechos_service.py"

SUITE = "tests/backend"


@dataclass(frozen=True)
class Mutante:
    """Una mutacion contractual o adicional.

    `discriminante` es el fragmento del identificador de test que DEBE
    aparecer entre los fallos. Sin el, un mutante podria darse por muerto por
    un fallo colateral que no tiene nada que ver con la invariante vigilada.
    """

    ident: str
    descripcion: str
    fichero: str
    viejo: str
    nuevo: str
    discriminante: str
    suite: str = SUITE


# ==================================================================
# M1..M20 — CONTRACTUALES (mandato 80)
# ==================================================================
CONTRACTUALES: list[Mutante] = [
    Mutante(
        "M1", "lock por regla RODANTE eliminado", RGR,
        '"SELECT row_version FROM gapto.reglas_financieras "\n        "WHERE id = %s::uuid FOR UPDATE",',
        '"SELECT row_version FROM gapto.reglas_financieras "\n        "WHERE id = %s::uuid",',
        "test_c1_doble_generador_rodante_sobre_cabeza_terminada",
    ),
    Mutante(
        "M2", "permite dos cabezas ABIERTAS", SRV,
        '        if cabeza is not None:\n            return ResultadoGeneracion(',
        '        if False:\n            return ResultadoGeneracion(',
        "test_con_cabeza_abierta_un_cambio_de_cadencia_no_crea_una_segunda",
    ),
    Mutante(
        "M3", "suma meses sucesivamente (deriva acumulativa)", REC,
        '    if cadencia.periodicidad == MENSUAL:\n        total = (origen.year * 12 + origen.month - 1) + paso\n        return _con_dia_recortado(total // 12, total % 12 + 1, origen.day)',
        '    if cadencia.periodicidad == MENSUAL:\n        fecha = origen\n        for _ in range(k):\n            _t = (fecha.year * 12 + fecha.month - 1) + int(cadencia.intervalo)\n            fecha = _con_dia_recortado(_t // 12, _t % 12 + 1, fecha.day)\n        return fecha',
        "test_111_recurrencia_pura",
    ),
    Mutante(
        "M4", "infiere fin de mes desde 30/04", REC,
        '    return dt.date(anio, mes, min(dia_ordinal, _ultimo_dia(anio, mes)))',
        '    if dia_ordinal >= 30:\n        return dt.date(anio, mes, _ultimo_dia(anio, mes))\n    return dt.date(anio, mes, min(dia_ordinal, _ultimo_dia(anio, mes)))',
        "test_111_recurrencia_pura",
    ),
    Mutante(
        "M5", "un hecho ANULADO cuenta como ancla", REP,
        "         WHERE pv.prevision_id = %s::uuid\n           AND h.estado = 'ACTIVO'",
        "         WHERE pv.prevision_id = %s::uuid\n           AND h.estado IS NOT NULL",
        "test_amb009",
    ),
    Mutante(
        "M6", "usa el objetivo como respaldo de la fecha real", REC,
        '        if hechos_activos == 0 or fecha_real_maxima is None:\n            return None\n        return fecha_real_maxima',
        '        if hechos_activos == 0 or fecha_real_maxima is None:\n            return fecha_objetivo\n        return fecha_real_maxima',
        "test_111_recurrencia_pura",
    ),
    Mutante(
        "M7", "el primer vinculo marca REALIZADA", SRV,
        '            if datos.marcar_realizada:\n                cambios["estado"] = REALIZADA',
        '            if True:\n                cambios["estado"] = REALIZADA',
        "test_primer_vinculo_no_realiza_pero_congela",
    ),
    Mutante(
        "M8", "exige igualdad previsto=real para REALIZADA", SRV,
        '            if datos.marcar_realizada:\n                cambios["estado"] = REALIZADA',
        '            if datos.marcar_realizada and (\n                prevision["importe_esperado"] is not None\n                and decimal.Decimal(datos.importe_asignado)\n                != decimal.Decimal(prevision["importe_esperado"])\n            ):\n                raise ErrorMotor(\n                    CodigoError.ESTADO_PREVISION_INCOMPATIBLE,\n                    "mutante M8: exige cuadratura previsto=real",\n                )\n            if datos.marcar_realizada:\n                cambios["estado"] = REALIZADA',
        "test_vector_d126_cadena_rodante_de_tres_eslabones",
    ),
    Mutante(
        "M9", "recalcula previsiones con realidad asociada", SRV,
        '                if not fila["recalculo_automatico"]:\n                    congeladas.append(fila["id"])\n                    continue',
        '                if False:\n                    congeladas.append(fila["id"])\n                    continue',
        "test_c02_alquiler_con_subida",
    ),
    Mutante(
        "M10", "una CANCELADA genera sucesor", SRV,
        '                if terminal["estado"] == CANCELADA:\n                    return ResultadoGeneracion(',
        '                if False:\n                    return ResultadoGeneracion(',
        "test_cancelada_no_genera_sucesor",
    ),
    Mutante(
        "M11", "OMITIDA avanza desde el override, no del objetivo", REC,
        '    if estado == OMITIDA:\n        return fecha_objetivo',
        '    if estado == OMITIDA:\n        return fecha_objetivo + dt.timedelta(days=15)',
        "test_omitida_ancla_en_el_objetivo_no_en_un_override",
    ),
    Mutante(
        "M12", "el recalculo modifica fecha_objetivo_regla", SRV,
        '        cambios: dict[str, Any] = {\n            "regla_version_id": version_id,',
        '        cambios: dict[str, Any] = {\n            "fecha_objetivo_regla": ventana.desde,\n            "regla_version_id": version_id,',
        "test_el_recalculo_no_mueve_la_identidad_con_ventana",
    ),
    Mutante(
        "M13", "CALENDARIO se desplaza con la fecha real", SRV,
        '            origen = segmento["origen"]\n            limite = self._limite_del_segmento(segmento, hasta_fecha)',
        '            origen = segmento["origen"]\n            _t = repo_prev.ultima_terminal_de_versiones(\n                sesion, segmento["version_ids"]\n            )\n            if _t is not None:\n                _r = repo_prev.resumen_realidad(sesion, _t["id"])\n                if _r["fecha_real_maxima"] is not None:\n                    origen = _r["fecha_real_maxima"]\n            limite = self._limite_del_segmento(segmento, hasta_fecha)',
        "test_una_realizacion_no_desplaza_el_calendario",
    ),
    Mutante(
        "M14", "el historico usa importe_total del hecho", REP,
        "                   sum(pv.importe_asignado) AS importe_real,",
        "                   sum(h.importe_total) AS importe_real,",
        "test_media_historica_sobre_ocurrencias_de_la_misma_regla",
    ),
    Mutante(
        "M15", "incluye ABIERTA parcial en la muestra historica", REP,
        "               AND p.estado = 'REALIZADA'\n               AND p.fecha_objetivo_regla IS NOT NULL",
        "               AND p.estado IN ('REALIZADA', 'ABIERTA')\n               AND p.fecha_objetivo_regla IS NOT NULL",
        "test_una_abierta_parcial_no_entra_en_la_muestra_historica",
    ),
    Mutante(
        "M16", "inventa FX en multidivisa", SRV,
        '        if fila[0] != moneda_prevision and not datos.equivalencia_declarada:',
        '        if False:',
        "test_multidivisa_sin_equivalencia_declarada",
    ),
    Mutante(
        "M17", "ULTIMO_REAL por orden de captura", REC,
        '    return max(muestra, key=lambda h: h.fecha_objetivo).importe_real',
        '    return muestra[-1].importe_real',
        "ultimo_real",
    ),
    Mutante(
        "M18", "el retry de OP-17 crea identidad nueva", SRV,
        '            existente = repo_prev.leer_vinculo(sesion, datos.vinculo_id)\n            if existente is not None:',
        '            existente = repo_prev.leer_vinculo(sesion, datos.vinculo_id)\n            if False:',
        "test_retry_idempotente_de_op17",
    ),
    Mutante(
        "M19", "auditoria de F04-05 desactivada", SRV,
        "from app.repositories import auditoria_repository as auditoria",
        "from app.repositories import auditoria_repository as _auditoria_real\n\n\nclass _AuditoriaMuda:\n    ACCION_CREAR = _auditoria_real.ACCION_CREAR\n    ACCION_ACTUALIZAR = _auditoria_real.ACCION_ACTUALIZAR\n    ACCION_ANULAR = _auditoria_real.ACCION_ANULAR\n\n    @staticmethod\n    def registrar(*_a, **_k):\n        return None\n\n\nauditoria = _AuditoriaMuda",
        "test_d024_cancelada_a_abierta_solo_por_correccion_auditada",
    ),
    Mutante(
        "M20", "terminales incompatibles concurrentes admitidas", SRV,
        '        nueva = repo_prev.tocar_prevision(sesion, prevision_id, esperada)\n        if nueva is None:',
        '        nueva = repo_prev.tocar_prevision(sesion, prevision_id, esperada)\n        if nueva is None:\n            _f = sesion.uno(\n                "UPDATE gapto.previsiones SET row_version = row_version + 1 "\n                "WHERE id = %s::uuid RETURNING row_version",\n                (prevision_id,),\n            )\n            nueva = None if _f is None else _f[0]\n        if nueva is None:',
        "test_c4_realizada_frente_a_cancelada",
    ),
]

# ==================================================================
# E1..E12 — ADICIONALES. No sustituyen a ningun contractual.
# ==================================================================
ADICIONALES: list[Mutante] = [
    Mutante(
        "E1", "CANCELADA no se reabre por correccion (contra F04-D024.3)", SRV,
        '            if estado == ABIERTA:\n                raise ErrorMotor(\n                    CodigoError.ESTADO_PREVISION_INCOMPATIBLE,',
        '            if estado in (ABIERTA, CANCELADA):\n                raise ErrorMotor(\n                    CodigoError.ESTADO_PREVISION_INCOMPATIBLE,',
        "test_d024_cancelada_a_abierta_solo_por_correccion_auditada",
    ),
    Mutante(
        "E2", "la reapertura reactiva el recalculo", SRV,
        '                    "estado": ABIERTA,\n                    # Hay realidad vinculada o la hubo: la expectativa no\n                    # vuelve a ser recalculable automaticamente.\n                    "recalculo_automatico": False,',
        '                    "estado": ABIERTA,\n                    "recalculo_automatico": True,',
        "test_d024_la_reapertura_nunca_reactiva_el_recalculo",
    ),
    Mutante(
        "E3", "un terminal posterior no bloquea la reapertura", SRV,
        '            if posterior is not None:\n                raise ErrorMotor(\n                    CodigoError.TRAMO_RODANTE_REQUIERE_REVISION,',
        '            if False:\n                raise ErrorMotor(\n                    CodigoError.TRAMO_RODANTE_REQUIERE_REVISION,',
        "test_d024_sucesor_terminal_posterior_tambien_rechaza",
    ),
    Mutante(
        "E4", "cancela un sucesor que tiene realidad", SRV,
        '        if realidad["hechos_activos"] > 0:\n            raise ErrorMotor(\n                CodigoError.TRAMO_RODANTE_REQUIERE_REVISION,',
        '        if False:\n            raise ErrorMotor(\n                CodigoError.TRAMO_RODANTE_REQUIERE_REVISION,',
        "test_d024_sucesor_con_realidad_rechaza_sin_cambios_parciales",
    ),
    Mutante(
        "E5", "la generacion sin horizonte no falla", SRV,
        '        if hasta_fecha is None and max_ocurrencias is None:',
        '        if False:',
        "test_la_generacion_exige_horizonte_finito",
    ),
    Mutante(
        "E6", "reutiliza una identidad CANCELADA", REC,
        '    consumidas = set(identidades_consumidas)',
        '    consumidas = set()',
        "test_una_identidad_cancelada_no_se_reutiliza",
    ),
    Mutante(
        "E7", "ignora la excepcion omitida al generar", SRV,
        '        if excepcion is not None and excepcion["omitida"]:\n            return {"tipo": "OMITIDA", "id": None}',
        '        if False:\n            return {"tipo": "OMITIDA", "id": None}',
        "test_una_excepcion_omitida_no_materializa",
    ),
    Mutante(
        "E8", "SALDO_OBJETIVO asume cero si el saldo es indeterminado", REC,
        '    if saldo_real is None:\n        return None',
        '    if saldo_real is None:\n        saldo_real = CERO',
        "saldo_objetivo",
    ),
    Mutante(
        "E9", "SALDO_OBJETIVO ignora los movimientos de la cuenta", REP,
        '    return decimal.Decimal(fila[0]) + decimal.Decimal(fila[1])',
        '    return decimal.Decimal(fila[0])',
        "test_e2e_saldo_objetivo_cuenta_los_movimientos_activos",
    ),
    Mutante(
        "E10", "MEDIANA devuelve la media", REC,
        '    valores = sorted(h.importe_real for h in muestra)\n    mitad = len(valores) // 2\n    if len(valores) % 2 == 1:\n        return valores[mitad]',
        '    valores = sorted(h.importe_real for h in muestra)\n    mitad = len(valores) // 2\n    if False:\n        return valores[mitad]',
        "mediana",
    ),
    Mutante(
        "E11", "la media sin muestra devuelve cero", REC,
        '    if not muestra:\n        return None\n    total = sum((h.importe_real for h in muestra), start=CERO)',
        '    if not muestra:\n        return CERO\n    total = sum((h.importe_real for h in muestra), start=CERO)',
        "media",
    ),
    Mutante(
        "E12", "OP-02 propaga el cambio de ancla en silencio", HEC,
        '            impacto = self._impacto_ancla(sesion, hecho_id)',
        '            impacto = {\n                "afectadas": (),\n                "propagadas": (),\n                "requiere_revision": False,\n                "motivo": None,\n            }',
        "test_op02",
    ),
]


def sha256(ruta: pathlib.Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def arbol_limpio() -> bool:
    salida = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=RAIZ, capture_output=True, text=True, check=False,
    )
    return not salida.stdout.strip()


def ejecutar_suite(suite: str) -> tuple[str, list[str]]:
    """Devuelve la linea de resumen y los identificadores de test fallidos."""
    res = subprocess.run(
        [sys.executable, "-m", "pytest", suite, "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=RAIZ, capture_output=True, text=True, check=False, timeout=3600,
    )
    lineas = [l for l in res.stdout.strip().splitlines() if l.strip()]
    resumen = lineas[-1] if lineas else "(sin salida)"
    fallidos = [
        l.split(" ")[1] for l in lineas
        if l.startswith("FAILED ") and len(l.split(" ")) > 1
    ]
    return resumen, fallidos


def correr(lote: list[Mutante]) -> list[tuple[Mutante, str, int, list[str]]]:
    filas: list[tuple[Mutante, str, int, list[str]]] = []
    for mut in lote:
        ruta = RAIZ / mut.fichero
        original = ruta.read_text()
        antes = sha256(ruta)

        if mut.viejo not in original:
            filas.append((mut, "PATRON NO ENCONTRADO", 0, []))
            print(f"  {mut.ident:4} DUDOSO    patron no encontrado", flush=True)
            continue

        ruta.write_text(original.replace(mut.viejo, mut.nuevo, 1))
        despues = sha256(ruta)
        if despues == antes:
            ruta.write_text(original)
            filas.append((mut, "MUTACION INERTE", 0, []))
            print(f"  {mut.ident:4} DUDOSO    la mutacion no cambio el fichero",
                  flush=True)
            continue

        try:
            resumen, fallidos = ejecutar_suite(mut.suite)
        finally:
            ruta.write_text(original)
        if sha256(ruta) != antes:  # pragma: no cover
            raise SystemExit(f"{mut.ident}: la restauracion no devolvio el SHA")

        if "passed" not in resumen and "failed" not in resumen:
            filas.append((mut, f"SUITE NO EJECUTADA: {resumen[:50]}", 0, []))
            print(f"  {mut.ident:4} DUDOSO    la suite no llego a ejecutarse",
                  flush=True)
            continue

        n = int(resumen.split(" failed")[0].split()[-1]) if " failed" in resumen else 0
        if n == 0:
            estado = "SOBREVIVE"
        elif not any(mut.discriminante in f for f in fallidos):
            estado = "DUDOSO: fallos colaterales, no el discriminante"
        else:
            estado = "MUERTO"
        filas.append((mut, estado, n, fallidos))
        print(f"  {mut.ident:4} {estado.split(':')[0]:9} fallos={n:<3} "
              f"{mut.descripcion}", flush=True)
    return filas


def main() -> int:
    filtro = set(sys.argv[1:])
    contractuales = [m for m in CONTRACTUALES if not filtro or m.ident in filtro]
    adicionales = [m for m in ADICIONALES if not filtro or m.ident in filtro]

    if not arbol_limpio():
        print("ABORTADO: el arbol de trabajo no esta limpio antes de empezar.")
        subprocess.run(["git", "status", "--short"], cwd=RAIZ, check=False)
        return 2

    print(f"raiz={RAIZ}")
    print("=== CONTRACTUALES M1..M20 (mandato 80) ===", flush=True)
    res_c = correr(contractuales)
    print("=== ADICIONALES E1..E12 ===", flush=True)
    res_a = correr(adicionales)

    if not arbol_limpio():
        print("!!! EL ARBOL NO QUEDO LIMPIO TRAS LA RESTAURACION")
        subprocess.run(["git", "status", "--short"], cwd=RAIZ, check=False)
        return 3

    muertos_c = sum(1 for _, e, _, _ in res_c if e == "MUERTO")
    muertos_a = sum(1 for _, e, _, _ in res_a if e == "MUERTO")
    print(f"\nRESULTADO: {muertos_c}/{len(res_c)} contractuales muertos + "
          f"{muertos_a}/{len(res_a)} adicionales muertos")
    print("Arbol limpio tras la restauracion: OK")

    dudosos = [m.ident for m, e, _, _ in res_c + res_a if e not in ("MUERTO", "SOBREVIVE")]
    if dudosos:
        print(f"DUDOSOS (el arnes no puede demostrar su resultado): {dudosos}")
        return 4
    if muertos_c != len(res_c) or muertos_a != len(res_a):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
