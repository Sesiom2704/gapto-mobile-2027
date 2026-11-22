# ============================================================
# GAPTO MOBILE 2027
# Fichero: swipe_cuota.py
# Ruta: backend/app/hipotecas/swipe_cuota.py
# Descripcion: D-C7-10 · bloque `cuota` de las filas de lista de la prevision de una cuota (Inicio y Pendientes)
#   para el gesto «Pagado» (mandato F06 T4 DC710 v1.0 §2.2-§2.3; diseno v0.1 con AJ-DC710-01..08; decision de
#   Moises «opcion A»: con dudas no hay gesto). SOLO LECTURA, sin locks: no es una segunda autoridad de negocio;
#   el pago sigue siendo W-HIP-02 (`pago.pagar`) con todas sus guardas bajo sus locks.
#   - Lectura EN LOTE (R-DC710-03): una consulta para todas las filas de cuota de la lista (cuota, financiacion,
#     version, primera cuota sin REALIZADA de cada financiacion) y, solo para la cuota que puede ofrecer el gesto
#     (como mucho UNA por financiacion: la primera sin REALIZADA), las tres lecturas del escritor: propuesta
#     (`pago.propuesta`), participacion de la cuenta de cargo (`alta.participacion_cuenta`) y elegibilidad de la
#     cuenta (`elegibilidad_cuentas.motivo_cuenta`). Nunca consultas por fila.
#   - `swipe_disponible` (AJ-DC710-01): cuota identificada sin ambiguedad (una sola fila de cuota para la
#     prevision, financiacion HIPOTECA) y prevision ABIERTA; vencimiento <= hoy del owner; financiacion ACTIVA con
#     apertura conocida; todas las cuotas anteriores REALIZADAS (D14 de W-HIP-02); cuenta de cargo en la prevision;
#     sin realidad previa (sin pagos ni realidad vinculada ni cobertura) e importe de la prevision = cuota.
#     `PAGO_CUOTA_EXPUESTO` es una constante de CODIGO del cliente (N-40): el cliente la aplica encima.
#   - `sin_dudas`: ademas, cuenta de cargo plenamente elegible para GASTO en el vencimiento (contrato comun), la
#     propuesta del escritor completa y valida (actores unicos, 0 < % <= 100, suma 100; nunca SELF_100 supuesto),
#     participacion de la cuenta de cargo EN EL VENCIMIENTO conocida y valida, y sin discrepancia con la propuesta
#     (`alta.aviso_reparto_distinto(cuenta, propuesta)`; NO el aviso de L-HIP, que compara el desembolso,
#     AJ-DC710-02), y version de la financiacion conocida.
#   - Ante NULL, dato desconocido o inconsistencia: false (fail-closed). `propuesta_atribucion` solo se calcula
#     para la cuota con `swipe_disponible`; en las demas es null (no se usa: no hay gesto).
# Version: 0.1.0 (F06 T4 · D-C7-10, mandato 7041970a…)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from app.comun.elegibilidad_cuentas import motivo_cuenta
from app.core.unidad_trabajo import SesionMotor
from app.hipotecas import alta, pago
from app.patrimonio import atribucion as m2

_CENT = decimal.Decimal("0.01")

#: Una consulta para todas las filas de cuota: la cuota, su financiacion y la primera cuota sin REALIZADA de cada
#: financiacion (mismo predicado que la guarda D14 de W-HIP-02: `estado IS DISTINCT FROM 'REALIZADA'`).
_LOTE = (
    "WITH q AS ("
    "  SELECT q.prevision_id, q.financiacion_entidad_id AS fid, q.numero_cuota, q.fecha_vencimiento, "
    "         q.importe_total_previsto, count(*) OVER (PARTITION BY q.prevision_id) AS n_cuotas "
    "  FROM gapto.financiacion_cuotas q WHERE q.prevision_id = ANY(%s)), "
    "primera AS ("
    "  SELECT x.financiacion_entidad_id AS fid, min(x.numero_cuota) AS numero "
    "  FROM gapto.financiacion_cuotas x LEFT JOIN gapto.previsiones p ON p.id = x.prevision_id "
    "  WHERE x.financiacion_entidad_id IN (SELECT fid FROM q) AND p.estado IS DISTINCT FROM 'REALIZADA' "
    "  GROUP BY x.financiacion_entidad_id) "
    "SELECT q.prevision_id, q.fid, q.numero_cuota, q.fecha_vencimiento, q.importe_total_previsto, q.n_cuotas, "
    "       e.row_version, f.estado, f.tipo_financiacion, f.saldo_principal_apertura IS NOT NULL, primera.numero "
    "FROM q JOIN gapto.entidades e ON e.id = q.fid JOIN gapto.financiaciones f ON f.entidad_id = q.fid "
    "LEFT JOIN primera ON primera.fid = q.fid"
)


def _validas(partes: list[tuple[uuid.UUID, decimal.Decimal]]) -> bool:
    """Distribucion completa: no vacia, actores unicos, 0 < % <= 100 y suma exacta 100."""
    if not partes or len({a for a, _ in partes}) != len(partes):
        return False
    if any(a is None or x is None or x <= 0 or x > m2.CIEN for a, x in partes):
        return False
    return sum((x for _, x in partes), decimal.Decimal(0)) == m2.CIEN


def _swipe_disponible(fila: dict[str, Any], c: tuple, hoy: dt.date) -> bool:
    (_, _, numero, vencimiento, importe_cuota, n_cuotas, row_version, estado, tipo, apertura, primera) = c
    esperado = fila.get("_esperado")
    return bool(
        n_cuotas == 1 and tipo == "HIPOTECA" and numero is not None
        and fila["estado"] == "ABIERTA"
        and vencimiento is not None and vencimiento <= hoy
        and estado == "ACTIVA" and apertura is True
        and primera is not None and primera == numero
        and fila["cuenta_salida"] is not None
        and fila["pagos"] == 0 and not fila["con_realidad"] and fila.get("_cubierto") == 0
        and esperado is not None and importe_cuota is not None
        and decimal.Decimal(esperado).quantize(_CENT) == decimal.Decimal(importe_cuota).quantize(_CENT)
        and row_version is not None
    )


def _sin_dudas(sesion: SesionMotor, fid: uuid.UUID, vencimiento: dt.date, cuenta: uuid.UUID,
               propuesta: list[tuple[uuid.UUID, decimal.Decimal]]) -> bool:
    if motivo_cuenta(sesion, cuenta, "GASTO", vencimiento) is not None:
        return False
    if not _validas(propuesta):
        return False
    participacion = alta.participacion_cuenta(sesion, cuenta, vencimiento)
    if not _validas(participacion):
        return False
    return not alta.aviso_reparto_distinto(participacion, propuesta)


def _pct(x: decimal.Decimal) -> str:
    return format(decimal.Decimal(x).quantize(m2.ESCALA_PCT), "f")


def anadir_bloques(sesion: SesionMotor, filas: list[dict[str, Any]], hoy: dt.date) -> list[dict[str, Any]]:
    """Anade `cuota` a las filas ya marcadas PREVISION_DE_CUOTA (Inicio y Pendientes). No cambia orden, filtros,
    recuentos ni las filas ordinarias (que no ganan ninguna clave)."""
    # una vez por fila aunque la lista la repita (Pendientes: una parcial sin fecha esta en dos secciones)
    marcadas = list({id(f): f for f in filas if f.get("codigo") == "PREVISION_DE_CUOTA"}.values())
    if not marcadas:
        return filas
    with sesion.conexion.cursor() as cur:
        cur.execute(_LOTE, ([f["id"] for f in marcadas],))
        lote: dict[uuid.UUID, tuple] = {}
        for c in cur.fetchall():
            lote.setdefault(c[0], c)
    for f in marcadas:
        c = lote.get(f["id"])
        if c is None:   # marcada pero sin fila legible: fail-closed sin datos
            f["cuota"] = {"financiacion_id": None, "numero": None, "financiacion_row_version": None,
                          "fecha_vencimiento": None, "cuenta_cargo": f["cuenta_salida"], "propuesta_atribucion": None,
                          "swipe_disponible": False, "sin_dudas": False}
            continue
        fid, numero, vencimiento, row_version = c[1], c[2], c[3], c[6]
        disponible = _swipe_disponible(f, c, hoy)
        propuesta = None
        dudas_fuera = False
        if disponible:
            partes = pago.propuesta(sesion, fid, vencimiento)
            propuesta = [{"actor_id": a, "porcentaje": _pct(x)} for a, x in partes]
            dudas_fuera = _sin_dudas(sesion, fid, vencimiento, f["cuenta_salida"]["id"], partes)
        f["cuota"] = {"financiacion_id": fid, "numero": numero, "financiacion_row_version": row_version,
                      "fecha_vencimiento": vencimiento, "cuenta_cargo": f["cuenta_salida"],
                      "propuesta_atribucion": propuesta, "swipe_disponible": disponible,
                      "sin_dudas": disponible and dudas_fuera}
    return filas
