# ============================================================
# GAPTO MOBILE 2027
# Fichero: pago.py
# Ruta: backend/app/hipotecas/pago.py
# Descripcion: W-HIP-02 · pagar una cuota (modo COINCIDE) por su SERVICIO PROPIO (F06-01H; contrato v0.4 §3.4;
#   #96; mandato T3-F06 bloque 2 v1.1 §2.3). No pasa por los adaptadores que frena S10 (R-PLAN-05).
#   Guardas en el orden del contrato: forma -> 0P de la intencion (advisory de raiz de OP-22, raiz = intencion_id)
#   -> INVERSIONES -> cuenta FOR NO KEY UPDATE (+ FOR SHARE de su capacidad) -> financiacion FOR NO KEY UPDATE
#   (AGREGADO_NO_ENCONTRADO) -> cuota FOR UPDATE (AGREGADO_NO_ENCONTRADO) -> identidad -> no ACTIVA
#   (OPERACION_NO_PERMITIDA_EN_ESTADO) -> legacy (SALDO_PRINCIPAL_INDETERMINADO) -> prevision no ABIERTA
#   (CUOTA_NO_PENDIENTE) -> VERSION_DESFASADA -> cuota anterior sin pagar (CUOTA_ANTERIOR_PENDIENTE, D14) ->
#   fecha_pago > hoy (FECHA_PAGO_INCOHERENTE) -> capital > deuda (EXCEDE_SALDO_POSICION) -> cuenta sin PAGAR_GASTO
#   en la fecha (CUENTA_DESCONOCIDA) -> propuesta de atribucion releida != propuesta_vista
#   (ATRIBUCION_PROPUESTA_DESFASADA).
#   Composicion (OP-22 adscrito, raiz = intencion_id): hecho GASTO (fecha = vencimiento, presupuestable,
#   importe = cuota); efecto GASTO +intereses (si > 0) y efecto DEUDA -capital (si > 0) con la atribucion
#   confirmada (propuesta: titularidad DEL PRESTAMO en el vencimiento; Q-T3D-08); salida -cuota en la cuenta en
#   fecha_pago conciliada ENTERA; aportaciones de la cuenta de cargo por su participacion (PARTICIPACION_CUENTA,
#   sin PAG); prevision REALIZADA por el flujo M5 (OP-17 con marcar_realizada, importe = cuota). Despues: vinculo
#   AFECTA_A de NIVEL EFECTO de la DEUDA a la financiacion por el writer propio; la financiacion sube su
#   row_version; auditoria ACTUALIZAR. Rechazo -> estado identico (la UnidadDeTrabajo hace ROLLBACK).
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 6)
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal
from typing import Any

from app.api.ejecucion_registro import tomar_inversiones
from app.comun.elegibilidad_cuentas import motivo_cuenta
from app.comun.fecha_funcional import Reloj, hoy_owner, reloj_sistema
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_compuesto import DatosHechoCompuesto, DatosPagoCompuesto, DatosPrevisionCompuesta
from app.core.modelos_efectos import DatosEfecto
from app.core.modelos_tesoreria import DatosAportacion, DatosConciliacion, DatosMovimiento
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor
from app.hipotecas import alta, lecturas, vinculo
from app.patrimonio import atribucion as m2
from app.patrimonio.completitud import Rechazo
from app.repositories import auditoria_repository as auditoria
from app.repositories import compuesto_repository as repo_comp
from app.services.compuesto_service import HechosCompuestosService
from app.services.previsiones_service import impacto_correccion_ancla

CENT = Decimal("0.01")
NO_ENCONTRADA = "AGREGADO_NO_ENCONTRADO"
REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
NO_ACTIVA = "OPERACION_NO_PERMITIDA_EN_ESTADO"
INDETERMINADO = "SALDO_PRINCIPAL_INDETERMINADO"
CUOTA_NO_PENDIENTE = "CUOTA_NO_PENDIENTE"
VERSION_DESFASADA = "VERSION_DESFASADA"
CUOTA_ANTERIOR_PENDIENTE = "CUOTA_ANTERIOR_PENDIENTE"
FECHA_PAGO_INCOHERENTE = "FECHA_PAGO_INCOHERENTE"
EXCEDE_SALDO = "EXCEDE_SALDO_POSICION"
CUENTA_DESCONOCIDA = "CUENTA_DESCONOCIDA"
PROPUESTA_DESFASADA = m2.PROPUESTA_DESFASADA
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"
MOTIVO = "F06-01H W-HIP-02: pago de una cuota"


def _partes(lista: list[dict] | None) -> list[tuple[uuid.UUID, Decimal]]:
    return sorted(((uuid.UUID(str(p["actor_id"])), Decimal(str(p["porcentaje"])).quantize(m2.ESCALA_PCT))
                   for p in lista or []), key=lambda x: str(x[0]))


def forma(p: dict[str, Any]) -> str | None:
    partes = _partes(p["atribucion"]["partes"])
    if not partes or len({a for a, _ in partes}) != len(partes):
        return ENTRADA_INVALIDA
    if any(x <= 0 or x > m2.CIEN for _, x in partes) or sum((x for _, x in partes), Decimal(0)) != m2.CIEN:
        return m2.SUMA_NO_CUADRA
    return None


def propuesta(sesion: SesionMotor, fid: uuid.UUID, fecha: dt.date) -> list[tuple[uuid.UUID, Decimal]]:
    """Titularidad DEL PRESTAMO vigente en el vencimiento (Q-T3D-08), ordenada por actor (texto)."""
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT actor_id, porcentaje FROM gapto.entidad_participaciones WHERE entidad_id = %s "
                    "AND vigente_desde <= %s AND (vigente_hasta IS NULL OR vigente_hasta >= %s) "
                    "ORDER BY actor_id::text", (fid, fecha, fecha))
        return [(a, Decimal(x).quantize(m2.ESCALA_PCT)) for a, x in cur.fetchall()]


def ids(intencion: uuid.UUID) -> dict[str, uuid.UUID]:
    return {k: uuid.uuid5(intencion, f"gapto.f06.hipoteca.pago.{k}") for k in (
        "efecto_gasto", "efecto_deuda", "movimiento", "conciliacion", "vinculo", "prevision_vinculo")}


def composicion(intencion: uuid.UUID, cuota: dict[str, Any], cuenta: uuid.UUID, fecha_pago: dt.date,
                partes: list[tuple[uuid.UUID, Decimal]], cuenta_partes: list[tuple[uuid.UUID, Decimal]],
                prevision_rv: int) -> DatosHechoCompuesto:
    i = ids(intencion)
    total, interes, capital = cuota["total"], cuota["interes"], cuota["capital"]
    efectos = []
    if interes > 0:
        estado, filas = m2.filas(i["efecto_gasto"], interes, partes, m2.MANUAL, "gapto.f06.hipoteca.pago.atribucion:")
        efectos.append(DatosEfecto(efecto_id=i["efecto_gasto"], tipo_efecto="GASTO", importe_delta=interes,
                                   estado_atribucion=estado, atribuciones=filas))
    if capital > 0:
        estado, filas = m2.filas(i["efecto_deuda"], -capital, partes, m2.MANUAL, "gapto.f06.hipoteca.pago.atribucion:")
        efectos.append(DatosEfecto(efecto_id=i["efecto_deuda"], tipo_efecto="DEUDA", importe_delta=-capital,
                                   estado_atribucion=estado, atribuciones=filas))
    importes = m2.repartir(total, cuenta_partes) if cuenta_partes else {}
    return DatosHechoCompuesto(
        hecho=DatosCreacionHecho(hecho_id=intencion, fecha_hecho=cuota["vencimiento"], moneda="EUR",
                                 presupuestable=True, estado_localizacion="DESCONOCIDA", tipo_hecho_codigo="GASTO",
                                 concepto=f"CUOTA {cuota['numero']} HIPOTECA", importe_total=total, notas=None),
        efectos=efectos,
        pagos=[DatosPagoCompuesto(
            movimiento=DatosMovimiento(movimiento_id=i["movimiento"], cuenta_id=cuenta, fecha_movimiento=fecha_pago,
                                       importe=-total, clase_movimiento="OPERACION",
                                       descripcion=f"CUOTA {cuota['numero']} HIPOTECA"),
            conciliacion=DatosConciliacion(conciliacion_id=i["conciliacion"], hecho_id=intencion,
                                           movimiento_tesoreria_id=i["movimiento"], importe_asignado=-total))],
        aportaciones=[DatosAportacion(aportacion_id=uuid.uuid5(intencion, f"gapto.f06.hipoteca.pago.aportacion:{a}"),
                                      importe=importes[a], criterio_aportacion="PARTICIPACION_CUENTA", actor_id=a,
                                      porcentaje_aplicado=x, hecho_movimiento_tesoreria_id=i["conciliacion"])
                      for a, x in cuenta_partes if importes[a] > 0],
        prevision=DatosPrevisionCompuesta(prevision_id=cuota["prevision_id"], prevision_row_version_esperada=prevision_rv,
                                          vinculo_id=i["prevision_vinculo"], importe_asignado=total,
                                          marcar_realizada=True),
    )


def _coincide(sesion: SesionMotor, d: DatosHechoCompuesto, fid: uuid.UUID) -> bool:
    """Replay: identidades del agregado y campos por igualdad exacta (mismo criterio que B2, F04-D050)."""
    from app.patrimonio.compra import _fila, _iguales
    i = ids(d.hecho_id)
    declaradas: dict[str, set[uuid.UUID]] = {t: set() for t in repo_comp.FILTROS_AGREGADO}
    declaradas["hecho_efectos"] = {e.efecto_id for e in d.efectos}
    declaradas["efecto_atribuciones"] = {a.atribucion_id for e in d.efectos for a in e.atribuciones}
    declaradas["hecho_movimientos_tesoreria"] = {i["conciliacion"]}
    declaradas["hecho_aportaciones_pago"] = {a.aportacion_id for a in d.aportaciones}
    declaradas["hecho_entidades"] = {i["vinculo"]} if any(e.tipo_efecto == "DEUDA" for e in d.efectos) else set()
    declaradas["prevision_hechos"] = {i["prevision_vinculo"]}
    if repo_comp.identidades_del_agregado(sesion, d.hecho_id) != declaradas:
        return False
    h = d.hecho
    fila = repo_comp.leer(sesion, "hechos_financieros", d.hecho_id)
    if fila is None or repo_comp.codigo_tipo_hecho(sesion, fila["tipo_hecho_id"]) != "GASTO" or not all(
            _iguales(fila.get(k), v) for k, v in {"fecha_hecho": h.fecha_hecho, "importe_total": h.importe_total,
                                                  "concepto": h.concepto, "presupuestable": True}.items()):
        return False
    for e in d.efectos:
        if not _fila(sesion, "hecho_efectos", e.efecto_id, {"hecho_id": d.hecho_id, "tipo_efecto": e.tipo_efecto,
                                                            "importe_delta": e.importe_delta}):
            return False
        for a in e.atribuciones:
            if not _fila(sesion, "efecto_atribuciones", a.atribucion_id, {
                    "efecto_id": e.efecto_id, "actor_id": a.actor_id, "importe_atribuido": a.importe_atribuido}):
                return False
    m = d.pagos[0].movimiento
    if not _fila(sesion, "movimientos_tesoreria", m.movimiento_id, {"cuenta_id": m.cuenta_id,
                                                                    "fecha_movimiento": m.fecha_movimiento,
                                                                    "importe": m.importe}):
        return False
    if declaradas["hecho_entidades"] and not _fila(sesion, "hecho_entidades", i["vinculo"], {
            "entidad_id": fid, "efecto_id": i["efecto_deuda"], "tipo_relacion": "AFECTA_A"}):
        return False
    return _fila(sesion, "prevision_hechos", i["prevision_vinculo"], {"prevision_id": d.prevision.prevision_id,
                                                                      "importe_asignado": d.prevision.importe_asignado})


def pagar(sesion: SesionMotor, *, financiacion_id: uuid.UUID, numero: int, peticion: dict[str, Any],
          reloj: Reloj = reloj_sistema) -> dict | Rechazo:
    motivo = forma(peticion)
    if motivo is not None:
        return Rechazo(motivo)
    intencion = uuid.UUID(str(peticion["intencion_id"]))
    cuenta = uuid.UUID(str(peticion["cuenta_id"]))
    fecha_pago = peticion["fecha_pago"]
    repo_comp.tomar_advisory_raiz(sesion, intencion)                                   # 0P / raiz OP-22
    tomar_inversiones(sesion)                                                          # INVERSIONES
    sesion.uno("SELECT id FROM gapto.cuentas WHERE id = %s FOR NO KEY UPDATE", (cuenta,))          # cuenta FNKU
    sesion.uno("SELECT id FROM gapto.cuenta_capacidades WHERE cuenta_id = %s AND capacidad_codigo = 'PAGAR_GASTO' "
               "FOR SHARE", (cuenta,))
    fin = sesion.uno("SELECT e.row_version, f.estado, f.saldo_principal_apertura FROM gapto.entidades e "
                     "JOIN gapto.financiaciones f ON f.entidad_id = e.id WHERE e.id = %s AND "
                     "f.tipo_financiacion = 'HIPOTECA' FOR NO KEY UPDATE OF e, f", (financiacion_id,))
    if fin is None:
        return Rechazo(NO_ENCONTRADA)
    fila = sesion.uno("SELECT q.id, q.fecha_vencimiento, q.importe_total_previsto, q.interes_previsto, "
                      "q.capital_previsto, q.prevision_id FROM gapto.financiacion_cuotas q WHERE "
                      "q.financiacion_entidad_id = %s AND q.numero_cuota = %s FOR UPDATE", (financiacion_id, numero))
    if fila is None:
        return Rechazo(NO_ENCONTRADA)
    prev = None if fila[5] is None else sesion.uno(
        "SELECT estado, row_version FROM gapto.previsiones WHERE id = %s FOR UPDATE", (fila[5],))
    cuota = {"numero": numero, "vencimiento": fila[1], "total": Decimal(fila[2]).quantize(CENT),
             "interes": Decimal(fila[3] or 0).quantize(CENT), "capital": Decimal(fila[4] or 0).quantize(CENT),
             "prevision_id": fila[5]}
    partes = _partes(peticion["atribucion"]["partes"])
    hoy = hoy_owner(sesion, reloj)
    cuenta_partes = alta.participacion_cuenta(sesion, cuenta, fecha_pago)
    if repo_comp.leer(sesion, "hechos_financieros", intencion) is not None:            # identidad
        if fila[5] is None:
            return Rechazo(REUTILIZADA)
        d = composicion(intencion, cuota, cuenta, fecha_pago, partes, cuenta_partes, 0)
        if not _coincide(sesion, d, financiacion_id):
            return Rechazo(REUTILIZADA)
        return {"idempotente": True, "hecho_id": str(intencion),
                "hipoteca": lecturas.leer(sesion, financiacion_id, hoy)}
    row_version, estado, apertura = fin
    if estado != "ACTIVA":
        return Rechazo(NO_ACTIVA)
    if apertura is None:
        return Rechazo(INDETERMINADO)
    if prev is None or prev[0] != "ABIERTA":
        return Rechazo(CUOTA_NO_PENDIENTE)
    if row_version != peticion["row_version_esperada"]:
        return Rechazo(VERSION_DESFASADA)
    anterior = sesion.uno(
        "SELECT 1 FROM gapto.financiacion_cuotas q LEFT JOIN gapto.previsiones p ON p.id = q.prevision_id "
        "WHERE q.financiacion_entidad_id = %s AND q.numero_cuota < %s AND (p.estado IS DISTINCT FROM 'REALIZADA') "
        "LIMIT 1", (financiacion_id, numero))
    if anterior is not None:
        return Rechazo(CUOTA_ANTERIOR_PENDIENTE)
    if fecha_pago > hoy:
        return Rechazo(FECHA_PAGO_INCOHERENTE)
    if cuota["capital"] > lecturas.deuda_pendiente(sesion, financiacion_id):
        return Rechazo(EXCEDE_SALDO)
    if motivo_cuenta(sesion, cuenta, "GASTO", fecha_pago, bloquear=True) is not None:
        return Rechazo(CUENTA_DESCONOCIDA)
    vista = _partes(peticion["atribucion"]["propuesta_vista"]["partes"])
    if propuesta(sesion, financiacion_id, cuota["vencimiento"]) != vista:
        return Rechazo(PROPUESTA_DESFASADA)
    d = composicion(intencion, cuota, cuenta, fecha_pago, partes, cuenta_partes, prev[1])
    HechosCompuestosService(UnidadDeTrabajoAdscrita(sesion), impacto_ancla=impacto_correccion_ancla
                            ).registrar_hecho_compuesto(sesion.contexto, d)
    if cuota["capital"] > 0:
        i = ids(intencion)
        vinculo.escribir(sesion, vinculo.capacidad_pago(i["vinculo"]), hecho_id=intencion,
                         efecto_id=i["efecto_deuda"], financiacion_id=financiacion_id)
    antes = sesion.uno("SELECT row_to_json(e)::text FROM gapto.entidades e WHERE id = %s", (financiacion_id,))[0]
    sesion.ejecutar("UPDATE gapto.entidades SET row_version = row_version + 1, updated_at = now() WHERE id = %s",
                    (financiacion_id,))
    despues = sesion.uno("SELECT row_to_json(e)::text FROM gapto.entidades e WHERE id = %s", (financiacion_id,))[0]
    auditoria.registrar(sesion, tabla="entidades", registro_id=financiacion_id, accion=auditoria.ACCION_ACTUALIZAR,
                        datos_antes_json=antes,
                        datos_despues_json=json.dumps({**json.loads(despues), "pago": {
                            "hecho_id": str(intencion), "numero_cuota": numero}}, ensure_ascii=False),
                        motivo=MOTIVO)
    return {"idempotente": False, "hecho_id": str(intencion), "hipoteca": lecturas.leer(sesion, financiacion_id, hoy)}
