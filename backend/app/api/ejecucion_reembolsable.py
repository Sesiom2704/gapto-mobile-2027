# ============================================================
# GAPTO MOBILE 2027
# Fichero: ejecucion_reembolsable.py
# Ruta: backend/app/api/ejecucion_reembolsable.py
# Descripcion: Adaptador del gasto propio reembolsable C-03 «Mío, pero me lo
#   reembolsan» (F05 §66.A, contrato C-03 v1.0; F05-D052). API DE INTEGRACION
#   F05, PENDIENTE DE CONSOLIDACION F10.
#
#   UNA transaccion de UnidadDeTrabajo (retry completo ante 40P01/40001) y UNA
#   sola llamada a OP-22 adscrita (UnidadDeTrabajoAdscrita), sin segundo paso
#   de alta del derecho (§66.A.4):
#     actor de la contraparte (writer de actor, politica C-03) -> hecho GASTO
#     por el total -> efecto GASTO COMPLETA con UNA atribucion propia por el
#     total (ninguna fila de la contraparte) -> posicion DERECHO_COBRO (OP-12A:
#     contraparte = actor del tercero, saldo_apertura 0, inicio = fecha del
#     hecho, importe = reembolso.importe, vinculo GENERADO_POR, nombre
#     «Pendiente de cobro · <categoria>») -> movimiento -total en la cuenta
#     pagadora y su conciliacion -> aportacion segun el contrato vigente de
#     VS-01 (PROPUESTA_ACEPTADA: self 100 %; NO_DETERMINADA: ninguna) ->
#     contexto, comercio y magnitudes -> auditoria.
#
#   ORDEN DE LOCKS (§66.A.5, vinculante y completo):
#     1. advisory por raiz de OP-22 (F04-R3 il1b, primer recurso);
#     2. advisory INVERSIONES (siempre: la posicion escribe hecho_entidades);
#     3. cuenta pagadora FOR NO KEY UPDATE;
#     4. bajo FOR SHARE: capacidad de la cuenta (PAGAR_GASTO), categoria (C-a),
#        magnitudes (C07) y contexto;
#     5. terceros FOR SHARE ORDENADOS POR UUID (comercio y contraparte);
#     6. writer de actor;
#     7-9. OP-22: hecho -> posiciones -> tablas hijas.
#   Todas las validaciones van ANTES de cualquier escritura: un rechazo no deja
#   actor huerfano ni fila alguna.
#
#   POLITICA DE NATURALEZA fijada aqui, por ruta (nunca un parametro del
#   cliente): PERSONA o EMPRESA (actores.validar_tercero_reembolso). El reparto
#   conserva la suya (solo PERSONA).
#
#   IDENTIDAD E IDEMPOTENCIA (§66.A.6): hecho_id = intencion_id; los demas ids
#   uuid5(intencion_id, PREFIJO + rol). El PREFIJO es propio de esta ruta: la
#   ruta forma parte del agregado sellado, asi que reutilizar el intencion_id
#   desde el gasto pagado o el compartido (o a la inversa) no coincide con el
#   agregado persistido -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION. OP-22
#   compara hecho, efectos, atribuciones, posicion (tipo, contraparte),
#   vinculo, pagos, aportaciones y contexto; el importe recuperable vive en el
#   efecto causal de la posicion, que OP-22 no compara: este adaptador lo
#   compara en el replay. Un replay NO revalida la disponibilidad del tercero
#   ni su naturaleza, no recrea el actor y no duplica la posicion.
# Version: 0.1.0 (F05-D052 paso 2; F05 §66.A.1-§66.A.7)
# ============================================================

from __future__ import annotations

import decimal
import uuid
from dataclasses import dataclass, field

from app.actores import repositorio as repo_actores
from app.actores import servicio as actores
from app.api.dto_reembolsable import IntencionGastoReembolsable
from app.api.ejecucion_gasto_pagado import CODIGO_PROPUESTA_OBSOLETA
from app.api.ejecucion_registro import (
    RechazoRegistro,
    bloquear_cuentas,
    con_rechazo_capacidad,
    rechazo_cuenta,
    tomar_inversiones,
    validar_categoria_y_magnitudes,
    validar_contexto,
    validar_tercero,
)
from app.api.traductor_gasto_pagado import id_magnitud_hecho, leer_actor_self, participacion_self_100
from app.api.traductor_registro import contexto_hecho
from app.comun.fecha_funcional import CODIGO_FECHA_FUTURA, Reloj, es_futura, reloj_sistema
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_compuesto import DatosHechoCompuesto, DatosMagnitudHecho, DatosPagoCompuesto
from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
from app.core.modelos_posicion import JUSTIFICACION_DECISION, TIPO_DERECHO, DatosAltaPosicion
from app.core.modelos_tesoreria import DatosAportacion, DatosConciliacion, DatosMovimiento
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.repositories import compuesto_repository as repo_comp
from app.repositories import hechos_repository as repo_hechos
from app.services.compuesto_service import HechosCompuestosService
from app.services.posiciones_service import PosicionesService
from app.services.previsiones_service import impacto_correccion_ancla

ESCALA = decimal.Decimal("0.0001")
CERO = decimal.Decimal("0")
CIEN = decimal.Decimal("100")
MONEDA = "EUR"
#: Prefijo de identidad de ESTA ruta (sella la ruta en el agregado, §66.A.6).
PREFIJO = "gapto.f05d052.c03."
#: Nombre de la posicion (§66.2).
NOMBRE_POSICION = "Pendiente de cobro"


def _id(intencion_id: uuid.UUID, rol: str) -> uuid.UUID:
    return uuid.uuid5(intencion_id, PREFIJO + rol)


@dataclass(frozen=True, slots=True)
class PosicionReembolso:
    entidad_id: uuid.UUID
    contraparte_tercero_id: uuid.UUID
    nombre: str
    importe: decimal.Decimal
    saldo: decimal.Decimal | None
    estado: str
    apertura_indeterminada: bool


@dataclass(frozen=True, slots=True)
class GastoReembolsableRegistrado:
    hecho_id: uuid.UUID
    idempotente: bool
    total: decimal.Decimal
    movimiento_id: uuid.UUID
    cuenta_id: uuid.UUID
    posiciones: list[PosicionReembolso] = field(default_factory=list)


def nombre_posicion(sesion: SesionMotor, categoria_id: uuid.UUID | None) -> str:
    """«Pendiente de cobro · <categoria>» o «Pendiente de cobro» sin categoria (§66.2)."""
    if categoria_id is None:
        return NOMBRE_POSICION
    fila = sesion.uno("SELECT nombre FROM gapto.categorias_financieras WHERE id = %s", (categoria_id,))
    return NOMBRE_POSICION if fila is None else f"{NOMBRE_POSICION} · {fila[0]}"


def componer_gasto_reembolsable(intencion: IntencionGastoReembolsable, actor_self: uuid.UUID,
                                actor_contraparte: uuid.UUID, nombre: str) -> DatosHechoCompuesto:
    iid = intencion.intencion_id
    x = intencion.importe.quantize(ESCALA)
    hecho = DatosCreacionHecho(
        hecho_id=iid, fecha_hecho=intencion.fecha_hecho, moneda=intencion.moneda,
        presupuestable=intencion.presupuestable, estado_localizacion="DESCONOCIDA",
        tipo_hecho_codigo="GASTO", concepto=intencion.concepto, importe_total=x,
    )
    # §66.1: la atribucion propia es el TOTAL, nunca la diferencia gasto - derecho;
    # ninguna fila de la contraparte.
    efecto = DatosEfecto(
        efecto_id=_id(iid, "efecto"), tipo_efecto="GASTO", importe_delta=x, estado_atribucion="COMPLETA",
        categoria_id=intencion.categoria_id,
        atribuciones=(DatosAtribucion(atribucion_id=_id(iid, "atribucion.self"), actor_id=actor_self,
                                      importe_atribuido=x, criterio_atribucion="MANUAL", porcentaje_aplicado=CIEN),),
    )
    posicion = DatosAltaPosicion(
        entidad_id=_id(iid, "posicion"), nombre=nombre, tipo=TIPO_DERECHO, contraparte_actor_id=actor_contraparte,
        moneda=MONEDA, justificacion=JUSTIFICACION_DECISION, fecha_inicio_seguimiento=intencion.fecha_hecho,
        saldo_apertura=CERO, hecho_id=iid, fecha_hecho=intencion.fecha_hecho, concepto=intencion.concepto,
        efecto_id=_id(iid, "posicion.efecto"), vinculo_id=_id(iid, "posicion.vinculo"),
        importe_inicial=intencion.reembolso.importe.quantize(ESCALA),
    )
    movimiento = DatosMovimiento(
        movimiento_id=_id(iid, "movimiento"), cuenta_id=intencion.cuenta_id, fecha_movimiento=intencion.fecha_hecho,
        importe=-x, clase_movimiento="OPERACION", descripcion=intencion.concepto)
    conciliacion = DatosConciliacion(
        conciliacion_id=_id(iid, "conciliacion"), hecho_id=iid, movimiento_tesoreria_id=movimiento.movimiento_id,
        importe_asignado=-x)
    # Financiacion: el contrato vigente de VS-01 (§16.4), con su aceptacion visible.
    aportaciones = []
    if intencion.financiacion.estado == "PROPUESTA_ACEPTADA":
        aportaciones.append(DatosAportacion(
            aportacion_id=_id(iid, "aportacion.self"), importe=x, criterio_aportacion="PARTICIPACION_CUENTA",
            actor_id=actor_self, porcentaje_aplicado=CIEN, hecho_movimiento_tesoreria_id=conciliacion.conciliacion_id))
    magnitudes = tuple(
        DatosMagnitudHecho(registro_id=id_magnitud_hecho(iid, m.magnitud_id), magnitud_id=m.magnitud_id,
                           valor=decimal.Decimal(m.valor), unidad=None)
        for m in sorted(intencion.magnitudes, key=lambda m: m.magnitud_id)
    )
    return DatosHechoCompuesto(
        hecho=hecho, efectos=[efecto], posiciones=[posicion],
        pagos=[DatosPagoCompuesto(movimiento=movimiento, conciliacion=conciliacion)], aportaciones=aportaciones,
        contexto=contexto_hecho(iid, PREFIJO, "GASTO", tercero_id=intencion.tercero_id,
                                contexto_id=intencion.contexto_id, magnitudes=magnitudes),
    )


def _importe_recuperable_persistido(sesion: SesionMotor, iid: uuid.UUID) -> decimal.Decimal | None:
    """Importe del efecto causal de la posicion de ESTA intencion (vinculo propio de la ruta)."""
    fila = sesion.uno(
        "SELECT e.importe_delta FROM gapto.hecho_entidades v JOIN gapto.hecho_efectos e ON e.id = v.efecto_id "
        "WHERE v.id = %s AND v.hecho_id = %s AND v.entidad_id = %s",
        (_id(iid, "posicion.vinculo"), iid, _id(iid, "posicion")))
    return None if fila is None else decimal.Decimal(fila[0])


def registrar_gasto_reembolsable(
    unidad: UnidadDeTrabajo, contexto: ContextoOperacion, intencion: IntencionGastoReembolsable,
    reloj: Reloj = reloj_sistema,
) -> GastoReembolsableRegistrado | RechazoRegistro:
    iid = intencion.intencion_id
    contraparte = intencion.reembolso.tercero_id

    def operacion(sesion: SesionMotor) -> GastoReembolsableRegistrado | RechazoRegistro:
        # 1. F04-R3 il1b: advisory por raiz, primer recurso de la transaccion.
        repo_comp.tomar_advisory_raiz(sesion, iid)
        # 2. INVERSIONES siempre: la posicion escribe hecho_entidades (GENERADO_POR).
        tomar_inversiones(sesion)
        # 3. Cuenta pagadora FNKU.
        bloquear_cuentas(sesion, intencion.cuenta_id)
        actor_self = leer_actor_self(sesion)
        # Identidad antes que cualquier revalidacion: un replay no revalida.
        if repo_hechos.leer_estado(sesion, iid) is not None:
            actor_contraparte = repo_actores.leer_actor_de_tercero(sesion, contraparte)
            persistido = _importe_recuperable_persistido(sesion, iid)
            if (actor_contraparte is None or persistido is None
                    or persistido != intencion.reembolso.importe.quantize(ESCALA)):
                raise ErrorMotor(CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                                 "La intencion ya existe con otro contenido o desde otra ruta.")
        else:
            if es_futura(sesion, intencion.fecha_hecho, reloj):
                return RechazoRegistro(CODIGO_FECHA_FUTURA)
            # 4. Bajo FOR SHARE: capacidad, propuesta de financiacion, categoria, C07 y contexto.
            rechazo_cuenta(sesion, intencion.cuenta_id, "GASTO", intencion.fecha_hecho)
            if intencion.financiacion.estado == "PROPUESTA_ACEPTADA" and not participacion_self_100(
                    sesion, intencion.cuenta_id, actor_self, intencion.fecha_hecho):
                return RechazoRegistro(CODIGO_PROPUESTA_OBSOLETA)
            rechazo = validar_categoria_y_magnitudes(
                sesion, intencion.categoria_id, "GASTO", intencion.magnitudes, intencion.magnitudes_desconocidas)
            if rechazo is not None:
                return RechazoRegistro(rechazo)
            rechazo = validar_contexto(sesion, intencion.contexto_id)
            if rechazo is not None:
                return RechazoRegistro(rechazo)
            # 5. Terceros FOR SHARE por UUID: el comercio (owner y habilitado) y
            #    quien lo debe (owner, habilitado y PERSONA o EMPRESA).
            for tercero in sorted({intencion.tercero_id, contraparte} - {None}, key=str):
                if tercero == contraparte:
                    try:
                        actores.validar_tercero_reembolso(sesion, tercero)
                    except actores.RechazoActor as exc:
                        return RechazoRegistro(exc.codigo)
                else:
                    codigo = validar_tercero(sesion, tercero)
                    if codigo is not None:
                        return RechazoRegistro(codigo)
            # 6. Writer de actor (despues de TODAS las validaciones).
            actor_contraparte = actores.actor_de_tercero(sesion, contraparte, motivo=actores.MOTIVO_ALTA_REEMBOLSO)
        # 7-9. OP-22 adscrito, UNA sola llamada: hecho -> posicion -> hijas, todo o nada.
        nombre = nombre_posicion(sesion, intencion.categoria_id)
        datos = componer_gasto_reembolsable(intencion, actor_self, actor_contraparte, nombre)
        op22 = HechosCompuestosService(UnidadDeTrabajoAdscrita(sesion), impacto_ancla=impacto_correccion_ancla)
        resultado = op22.registrar_hecho_compuesto(contexto, datos)
        # Estado de la posicion, leido una vez (en un replay posterior a cobros refleja el actual).
        entidad = _id(iid, "posicion")
        r = PosicionesService(UnidadDeTrabajoAdscrita(sesion)).saldo(contexto, entidad)
        persistido = sesion.uno("SELECT nombre FROM gapto.entidades WHERE id = %s", (entidad,))
        return GastoReembolsableRegistrado(
            hecho_id=resultado.hecho_id, idempotente=resultado.idempotente,
            total=intencion.importe, movimiento_id=_id(iid, "movimiento"), cuenta_id=intencion.cuenta_id,
            posiciones=[PosicionReembolso(
                entidad_id=entidad, contraparte_tercero_id=contraparte,
                nombre=persistido[0] if persistido else nombre, importe=intencion.reembolso.importe,
                saldo=r.saldo.importe if r.saldo.conocido else None, estado=r.estado,
                apertura_indeterminada=r.apertura_indeterminada)],
        )

    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoRegistro),
                           nombre="F05-D052 C-03 gasto_reembolsable (locks + writer de actor + OP-22)")
