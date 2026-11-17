# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/hipotecas/lecturas.py
# Descripcion: L-HIP · lectura de la hipoteca de una propiedad (F06-01H; contrato v0.4 §1.3, §1.4 y §3.3).
#   Solo lectura, dentro de la transaccion de la UnidadDeTrabajo como gapto_runtime con RLS (patron
#   propiedades/lecturas.py): lo que no es del owner no se ve.
#   - Hipoteca: la financiacion HIPOTECA con relacion GARANTIZADA_POR hacia la propiedad (una como maximo en
#     v1; si hubiera varias, primero la ACTIVA y despues la de entidad_id menor, orden determinista).
#   - Version vigente: la que contiene hoy (vigente_desde <= hoy <= vigente_hasta o abierta); si ninguna la
#     contiene, la abierta (vigente_hasta NULL). Condiciones ordenadas por vigente_desde.
#   - Estado derivado de cada cuota (§1.3): prevision ABIERTA -> PENDIENTE, o VENCIDA si fecha_vencimiento <
#     hoy (solo en lectura); REALIZADA -> PAGADA; otro estado de la prevision -> ese estado (la cuota no es
#     PENDIENTE); cuota sin prevision (forma legacy V3) -> SIN_PREVISION.
#   - pendiente de cada fila = P - Σ capital previsto acumulado (P = capital_original_contratado).
#   - Deuda pendiente (§1.4): Σ importe_delta de los efectos DEUDA vinculados a la financiacion a NIVEL DE
#     EFECTO (hecho_entidades.efecto_id = efecto, AFECTA_A) de hechos ACTIVOS. Legacy V3 con saldo inicial
#     desconocido (saldo_principal_apertura NULL): deuda_pendiente = None y deuda_indeterminada = True, NUNCA 0
#     (Q-T3D-13).
#   - Desembolso: el hecho causa (Hd) de la version ALTA, con su cuenta (movimiento conciliado), fecha e importe
#     del efecto DEUDA; None si la version ALTA no tiene hecho causa (legacy).
#   - compra_hecho_id: H0 de la propiedad (hecho ACTIVO ADQUISICION_PATRIMONIAL con VALOR_ACTIVO ADQUISICION y
#     AFECTA_A principal a la propiedad que no es PARTE_DE de otro); None si no hay compra.
#   La lectura no dice si una revision fue por bonificacion ni su desglose (Q-H-11).
#   Importes como texto exacto a centimos; tasas como texto decimal sin ceros sobrantes.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 4)
# Version: 0.2.0 (F06 T3-F06 bloque 2 F06-01H, paso 5; contrato v0.4 §3.2.7-5): `aviso_reparto_distinto` = la
#   distribucion de la cuenta del desembolso y la del prestamo en la fecha de Hd difieren (sin Hd: False).
# Version: 0.3.0 (F06 T3-F06 bloque 2 F06-01H; N-30, firma 0f3e5633…, enmienda 52ef5511… del contrato v0.4 en
#   L-HIP): campo ADITIVO `titularidad_prestamo` = participaciones del prestamo con su vigencia (actor, porcentaje
#   a 4 decimales, yo, tercero, nombre, vigente_desde, vigente_hasta); el cliente propone la atribucion de los
#   intereses con las vigentes en el vencimiento, igual que W-HIP-02 (Q-T3D-08). Sin participaciones: [].
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from app.core.unidad_trabajo import SesionMotor
from app.hipotecas import calculadora as calc

TIPO_HECHO_COMPRA = "ADQUISICION_PATRIMONIAL"
PAGADA, PENDIENTE, VENCIDA, SIN_PREVISION = "PAGADA", "PENDIENTE", "VENCIDA", "SIN_PREVISION"


def _importe(valor: Any) -> str | None:
    return None if valor is None else str(calc.r2(Decimal(valor)))


def _tasa(valor: Any) -> str | None:
    return None if valor is None else format(Decimal(valor).normalize(), "f")


def _filas(sesion: SesionMotor, sql: str, params: tuple) -> list[tuple]:
    with sesion.conexion.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def financiacion_de_propiedad(sesion: SesionMotor, propiedad_id: uuid.UUID) -> uuid.UUID | None:
    fila = sesion.uno(
        "SELECT f.entidad_id FROM gapto.entidad_relaciones r JOIN gapto.financiaciones f "
        "ON f.entidad_id = r.entidad_origen_id AND f.tipo_financiacion = 'HIPOTECA' "
        "WHERE r.entidad_destino_id = %s AND r.tipo_relacion = 'GARANTIZADA_POR' "
        "ORDER BY (f.estado = 'ACTIVA') DESC, f.entidad_id LIMIT 1", (propiedad_id,))
    return None if fila is None else fila[0]


def _versiones(sesion: SesionMotor, fid: uuid.UUID) -> list[dict[str, Any]]:
    return [{"id": f[0], "vigente_desde": f[1], "vigente_hasta": f[2], "motivo": f[3], "tipo_interes": f[4],
             "tasa_anual": _tasa(f[5]), "indice_referencia": f[6], "diferencial": _tasa(f[7]),
             "cuota_referencia": _importe(f[8]), "numero_cuotas": f[9], "hecho_causa_id": f[10]}
            for f in _filas(sesion,
                            "SELECT id, vigente_desde, vigente_hasta, motivo_version, tipo_interes, tasa_anual_pct, "
                            "indice_referencia, diferencial_pct, importe_cuota_referencia, numero_cuotas_referencia, "
                            "hecho_causa_id FROM gapto.financiacion_condiciones_versiones "
                            "WHERE financiacion_entidad_id = %s ORDER BY vigente_desde, id", (fid,))]


def _cuotas(sesion: SesionMotor, fid: uuid.UUID) -> list[tuple]:
    return _filas(
        sesion,
        "SELECT q.numero_cuota, q.fecha_vencimiento, q.importe_total_previsto, q.interes_previsto, "
        "q.capital_previsto, q.condicion_version_id, q.prevision_id, p.estado, p.cuenta_salida_esperada_id, "
        "(SELECT v.hecho_id FROM gapto.prevision_hechos v WHERE v.prevision_id = p.id ORDER BY v.created_at, v.id "
        "LIMIT 1) FROM gapto.financiacion_cuotas q LEFT JOIN gapto.previsiones p ON p.id = q.prevision_id "
        "WHERE q.financiacion_entidad_id = %s ORDER BY q.numero_cuota", (fid,))


def _estado_cuota(estado_prevision: str | None, vencimiento: dt.date, hoy: dt.date) -> str:
    if estado_prevision is None:
        return SIN_PREVISION
    if estado_prevision == "ABIERTA":
        return VENCIDA if vencimiento < hoy else PENDIENTE
    if estado_prevision == "REALIZADA":
        return PAGADA
    return estado_prevision


def deuda_pendiente(sesion: SesionMotor, fid: uuid.UUID) -> Decimal:
    """Σ importe_delta de los efectos DEUDA vinculados a F a nivel de efecto, de hechos ACTIVOS (§1.4)."""
    fila = sesion.uno(
        "SELECT coalesce(sum(e.importe_delta), 0) FROM gapto.hecho_efectos e "
        "JOIN gapto.hechos_financieros h ON h.id = e.hecho_id AND h.estado = 'ACTIVO' "
        "WHERE e.tipo_efecto = 'DEUDA' AND EXISTS (SELECT 1 FROM gapto.hecho_entidades x "
        "WHERE x.efecto_id = e.id AND x.entidad_id = %s AND x.tipo_relacion = 'AFECTA_A')", (fid,))
    return calc.r2(Decimal(fila[0]))


def _desembolso(sesion: SesionMotor, fid: uuid.UUID, hd: uuid.UUID | None) -> dict[str, Any] | None:
    if hd is None:
        return None
    fila = sesion.uno(
        "SELECT h.fecha_hecho, (SELECT e.importe_delta FROM gapto.hecho_efectos e JOIN gapto.hecho_entidades x "
        "ON x.efecto_id = e.id AND x.entidad_id = %s AND x.tipo_relacion = 'AFECTA_A' WHERE e.hecho_id = h.id "
        "AND e.tipo_efecto = 'DEUDA' ORDER BY e.id LIMIT 1), (SELECT m.cuenta_id FROM "
        "gapto.hecho_movimientos_tesoreria c JOIN gapto.movimientos_tesoreria m ON m.id = c.movimiento_tesoreria_id "
        "WHERE c.hecho_id = h.id ORDER BY c.id LIMIT 1) FROM gapto.hechos_financieros h WHERE h.id = %s", (fid, hd))
    if fila is None:
        return None
    return {"hecho_id": hd, "cuenta_id": fila[2], "fecha": fila[0], "importe": _importe(fila[1])}


def _compra_hecho_id(sesion: SesionMotor, propiedad_id: uuid.UUID | None) -> uuid.UUID | None:
    if propiedad_id is None:
        return None
    fila = sesion.uno(
        "SELECT h.id FROM gapto.hecho_entidades x JOIN gapto.hechos_financieros h ON h.id = x.hecho_id "
        "AND h.estado = 'ACTIVO' JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id AND th.codigo = %s "
        "JOIN gapto.hecho_efectos e ON e.hecho_id = h.id AND e.tipo_efecto = 'VALOR_ACTIVO' "
        "AND e.causa_valor_activo = 'ADQUISICION' AND (x.efecto_id IS NULL OR x.efecto_id = e.id) "
        "WHERE x.entidad_id = %s AND x.tipo_relacion = 'AFECTA_A' AND x.principal AND NOT EXISTS ("
        "SELECT 1 FROM gapto.hecho_relaciones r WHERE r.hecho_origen_id = h.id AND r.tipo_relacion = 'PARTE_DE') "
        "ORDER BY h.id LIMIT 1", (TIPO_HECHO_COMPRA, propiedad_id))
    return None if fila is None else fila[0]


def _financiador(sesion: SesionMotor, actor_id: uuid.UUID | None) -> dict[str, Any] | None:
    if actor_id is None:
        return None
    fila = sesion.uno(
        "SELECT a.tercero_id, t.nombre FROM gapto.actores_financieros a LEFT JOIN gapto.terceros t "
        "ON t.id = a.tercero_id WHERE a.id = %s", (actor_id,))
    return {"actor_id": actor_id, "tercero_id": None if fila is None else fila[0],
            "nombre": None if fila is None else fila[1]}


def _titularidad_prestamo(sesion: SesionMotor, fid: uuid.UUID) -> list[dict[str, Any]]:
    """N-30: participaciones DEL PRESTAMO (no de la propiedad) con su vigencia, por vigente_desde y actor (texto).
    La propuesta de W-HIP-02 es la de las filas vigentes en el vencimiento (pago.propuesta, Q-T3D-08)."""
    return [{"actor_id": a, "porcentaje": format(Decimal(p).quantize(Decimal("0.0001")), "f"), "yo": tid is None,
             "tercero_id": tid, "nombre": nombre, "vigente_desde": desde, "vigente_hasta": hasta}
            for a, p, tid, nombre, desde, hasta in _filas(
                sesion, "SELECT x.actor_id, x.porcentaje, a.tercero_id, t.nombre, x.vigente_desde, x.vigente_hasta "
                "FROM gapto.entidad_participaciones x JOIN gapto.actores_financieros a ON a.id = x.actor_id "
                "LEFT JOIN gapto.terceros t ON t.id = a.tercero_id WHERE x.entidad_id = %s "
                "ORDER BY x.vigente_desde, x.actor_id::text", (fid,))]


def _aviso(sesion: SesionMotor, fid: uuid.UUID, desembolso: dict[str, Any] | None) -> bool:
    from app.hipotecas import alta
    if desembolso is None or desembolso["cuenta_id"] is None:
        return False
    fecha = desembolso["fecha"]
    prestamo = [(a, Decimal(p)) for a, p in _filas(
        sesion, "SELECT actor_id, porcentaje FROM gapto.entidad_participaciones WHERE entidad_id = %s "
        "AND vigente_desde <= %s AND (vigente_hasta IS NULL OR vigente_hasta >= %s) ORDER BY actor_id::text",
        (fid, fecha, fecha))]
    return alta.aviso_reparto_distinto(alta.participacion_cuenta(sesion, desembolso["cuenta_id"], fecha), prestamo)


def leer(sesion: SesionMotor, fid: uuid.UUID, hoy: dt.date) -> dict[str, Any] | None:
    """Vista L-HIP de una financiacion HIPOTECA (None si no es visible)."""
    fila = sesion.uno(
        "SELECT e.nombre, e.row_version, f.estado, f.capital_original_contratado, f.fecha_inicio, "
        "f.fecha_vencimiento_final_prevista, f.saldo_principal_apertura, f.financiador_actor_id, "
        "(SELECT r.entidad_destino_id FROM gapto.entidad_relaciones r WHERE r.entidad_origen_id = e.id "
        "AND r.tipo_relacion = 'GARANTIZADA_POR' ORDER BY r.vigente_desde DESC NULLS LAST, r.id LIMIT 1) "
        "FROM gapto.entidades e JOIN gapto.financiaciones f ON f.entidad_id = e.id "
        "WHERE e.id = %s AND f.tipo_financiacion = 'HIPOTECA'", (fid,))
    if fila is None:
        return None
    nombre, row_version, estado, capital, inicio, fin, apertura, financiador, propiedad = fila
    versiones = _versiones(sesion, fid)
    vigente = next((v for v in versiones if v["vigente_desde"] <= hoy
                    and (v["vigente_hasta"] is None or hoy <= v["vigente_hasta"])), None) \
        or next((v for v in versiones if v["vigente_hasta"] is None), None)
    alta = next((v for v in versiones if v["motivo"] == "ALTA"), None)
    desembolso = _desembolso(sesion, fid, None if alta is None else alta["hecho_causa_id"])
    capital_p = None if capital is None else Decimal(capital)
    acumulado, filas = Decimal(0), []
    for numero, venc, total, interes, cap, version_id, prevision_id, estado_prev, cuenta, hecho_pago in _cuotas(
            sesion, fid):
        acumulado += Decimal(cap or 0)
        filas.append({"numero": numero, "vencimiento": venc, "cuota": _importe(total), "interes": _importe(interes),
                      "capital": _importe(cap),
                      "pendiente": None if capital_p is None else _importe(capital_p - acumulado),
                      "estado": _estado_cuota(estado_prev, venc, hoy), "version_id": version_id,
                      "hecho_pago_id": hecho_pago if estado_prev == "REALIZADA" else None,
                      "_cuenta": cuenta})
    pagadas = [f for f in filas if f["estado"] == PAGADA]
    proxima = next((f for f in filas if f["estado"] in (PENDIENTE, VENCIDA)), None)
    cargo = next((f["_cuenta"] for f in ([proxima] if proxima else []) + filas[::-1] if f["_cuenta"]), None)
    for f in filas:
        del f["_cuenta"]
    indeterminada = apertura is None
    return {
        "financiacion_id": fid, "nombre": nombre, "row_version": row_version, "estado": estado,
        "propiedad_id": propiedad, "compra_hecho_id": _compra_hecho_id(sesion, propiedad),
        "desembolso": desembolso, "aviso_reparto_distinto": _aviso(sesion, fid, desembolso),
        "financiador": _financiador(sesion, financiador), "titularidad_prestamo": _titularidad_prestamo(sesion, fid),
        "capital": _importe(capital),
        "fecha_inicio": inicio, "fecha_fin_prevista": fin, "convencion": calc.CONVENCION,
        "cuenta_cargo_id": cargo,
        "tipo_vigente": None if vigente is None else vigente["tasa_anual"],
        "vigente_desde": None if vigente is None else vigente["vigente_desde"],
        "cuota_vigente": proxima["cuota"] if proxima else (None if vigente is None else vigente["cuota_referencia"]),
        "deuda_pendiente": None if indeterminada else _importe(deuda_pendiente(sesion, fid)),
        "deuda_indeterminada": indeterminada,
        "capital_amortizado": _importe(sum((Decimal(f["capital"] or 0) for f in pagadas), Decimal(0))),
        "intereses_pagados": _importe(sum((Decimal(f["interes"] or 0) for f in pagadas), Decimal(0))),
        "cuotas_pagadas": len(pagadas), "numero_cuotas": len(filas), "proxima_cuota": proxima,
        "condiciones": versiones, "cuotas": filas,
    }


def leer_de_propiedad(sesion: SesionMotor, propiedad_id: uuid.UUID, hoy: dt.date) -> dict[str, Any] | None:
    """La hipoteca de la propiedad o None si la propiedad no tiene hipoteca."""
    fid = financiacion_de_propiedad(sesion, propiedad_id)
    return None if fid is None else leer(sesion, fid, hoy)
