# ============================================================
# GAPTO MOBILE 2027
# Fichero: ejecucion_reparto.py
# Ruta: backend/app/api/ejecucion_reparto.py
# Descripcion: Adaptador de F05-06 M3 · Reparto, pagador real y posiciones
#   (lamina REP v0.2; F05 §51.2 fila M3, §51.4 M3, §57 F05-D043; M3-PRE2).
#   API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10.
#
#   Cada escritura es UNA transaccion de UnidadDeTrabajo (retry completo ante
#   40P01/40001) y entra al motor por servicios certificados ADSCRITOS a ella
#   (UnidadDeTrabajoAdscrita), sin tocar su codigo:
#     - gasto compartido: OP-22 de una sola llamada (efecto y reparto,
#       participantes, pagador real -movimiento propio o aportacion de un
#       tercero-, aportaciones y posiciones EXPLICITAS);
#     - cobro OP-14, pago OP-12B y perdon (condonacion de derecho u
#       obligacion) de una posicion, con cuenta Gapto y su capacidad (M4);
#     - «Corregir reparto»: OP-21 con WHITELIST (AJ-M3-DEC-09) y la guarda (i)
#       REPARTO_CAMBIA_POSICIONES del motor; su lectura previa
#       (`reparto_de_hecho`) no toma locks ni escribe.
#
#   ORDEN DE LOCKS (R-M3PRE2-01; AJ-M3-DEC-05; M3-PRE2 P2), vinculante:
#     advisory INVERSIONES (SIEMPRE que la operacion escriba posiciones o
#     hecho_entidades, aunque no haya contexto) -> cuentas FNKU por UUID ->
#     capacidad FS -> categoria FS -> C07 FS -> terceros FS por UUID ->
#     writer de actor (actores/servicio.py) -> hecho -> posiciones -> hijas.
#   El advisory va ANTES de la cuenta: con la cuenta primero, el servicio
#   pediria el advisory despues (OP-22 paso 1, adquirir_raiz de OP-12B/14) y
#   reproduciria el ciclo del candidato A de R2-B-PRE.
#
#   NADA SE INFIERE (INV-04): una posicion solo nace con un «SI» explicito;
#   pagar por otro no crea deuda y pagar de mas no crea derecho. G3: lo que no
#   se conoce queda «sin indicar» (PARCIAL); nunca a cero, nunca completo
#   solo. Los rechazos de capa F05 se devuelven como valor SIN escritura
#   previa: todas las comprobaciones van antes del writer de actor.
#
#   Identidad: hecho_id = intencion_id y el resto de UUID se derivan con
#   uuid5(intencion_id, prefijo M3 + rol). Un reintento de la MISMA intencion
#   reproduce el mismo agregado (OP-22 idempotente); con otro contenido,
#   IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION.
# Version: 0.1.0 (F05-06 M3 §A2, §A4, §A5)
# Version: 0.2.0 (F05-06 M5 §A6 D-M5-11; F05 §59 F05-D044 decision 10): el gasto
#   compartido SOLO transporta el bloque opcional `prevision` a la misma OP-22
#   (vinculo por importe_total, sucesor si marcar_realizada; prevision de tipo
#   GASTO para una intencion nueva). Sin el bloque, nada cambia.
# ============================================================

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.actores import servicio as actores
from app.api.dto_reparto import (
    IntencionCobroPago,
    IntencionCorregirReparto,
    IntencionGastoCompartido,
    IntencionPerdon,
    PagadoConCuenta,
    PagadoPorPersona,
    RepartoEntrePersonas,
)
from app.api.ejecucion_registro import (
    RechazoRegistro,
    bloquear_cuentas,
    con_rechazo_capacidad,
    rechazo_cuenta,
    tomar_inversiones,
    validar_categoria_y_magnitudes,
    validar_tercero,
    validar_tipo_prevision,
)
from app.api.traductor_gasto_pagado import id_magnitud_hecho, leer_actor_self
from app.api.traductor_registro import ESCALA, contexto_hecho, prevision_compuesta
from app.comun.fecha_funcional import CODIGO_FECHA_FUTURA, Reloj, es_futura, reloj_sistema
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_compuesto import DatosHechoCompuesto, DatosMagnitudHecho, DatosPagoCompuesto
from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
from app.core.modelos_posicion import (
    CausaReduccion,
    DatosAltaPosicion,
    DatosCierre,
    DatosCondonacion,
    DatosCondonacionObligacion,
    DatosDeltaPosicion,
    DatosReembolso,
    DatosTesoreriaReembolso,
    JUSTIFICACION_DECISION,
    TIPO_DERECHO,
    TIPO_OBLIGACION,
)
from app.core.modelos_tesoreria import DatosAportacion, DatosConciliacion, DatosMovimiento
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.repositories import hechos_repository as repo_hechos
from app.services import integridad_posicion
from app.services.compuesto_service import HechosCompuestosService
from app.services.correcciones_service import CorreccionesService, DatosCorreccion
from app.services.neto_service import DETERMINADO, NetoService
from app.services.participantes_service import DatosParticipante
from app.services.posiciones_service import PosicionesService
from app.services.previsiones_service import impacto_correccion_ancla

ESCALA = decimal.Decimal("0.0001")
CERO = decimal.Decimal("0")
PREFIJO = "gapto.f0506.m3."
MONEDA = "EUR"
#: Nombre de la posicion si el gasto no trae nota (la entidad exige nombre).
NOMBRE_POSICION = "Gasto compartido"

# Rechazos de capa F05 (sin escritura).
POSICION_NO_ENCONTRADA = "POSICION_NO_ENCONTRADA"
POSICION_NO_ADMITE_OPERACION = "POSICION_NO_ADMITE_OPERACION"
REPARTO_NO_CORREGIBLE = "REPARTO_NO_CORREGIBLE"
REPARTO_NO_DEMOSTRABLE = "REPARTO_NO_DEMOSTRABLE"
HECHO_NO_ENCONTRADO = "HECHO_NO_ENCONTRADO"


def _id(intencion_id: uuid.UUID, rol: str) -> uuid.UUID:
    return uuid.uuid5(intencion_id, PREFIJO + rol)


# ==================================================================
# Gasto compartido (OP-22 de una sola llamada)
# ==================================================================
@dataclass(frozen=True, slots=True)
class PosicionCreada:
    entidad_id: uuid.UUID
    tipo: str
    tercero_id: uuid.UUID
    importe: decimal.Decimal


@dataclass(frozen=True, slots=True)
class GastoCompartidoRegistrado:
    hecho_id: uuid.UUID
    idempotente: bool
    estado_atribucion: str
    tu_parte: decimal.Decimal | None
    movimiento: decimal.Decimal | None
    posiciones: list[PosicionCreada] = field(default_factory=list)


def _personas(intencion: IntencionGastoCompartido) -> list[uuid.UUID]:
    """Terceros PERSONA del gasto: los del reparto y quien pago, si fue otro."""
    personas = [p.tercero_id for p in intencion.partes]
    if isinstance(intencion.pagado_por, PagadoPorPersona) and intencion.pagado_por.tercero_id not in personas:
        personas.append(intencion.pagado_por.tercero_id)
    return personas


def _estado_atribucion(intencion: IntencionGastoCompartido) -> str:
    """G3: COMPLETA solo si todo se conoce y suma el total; con algo conocido,
    PARCIAL; sin nada, NO_DISPONIBLE. Nunca se completa ni se pone a cero."""
    if not isinstance(intencion.reparto, RepartoEntrePersonas):
        return "COMPLETA"
    conocidas = [p.importe for p in intencion.partes if p.importe is not None]
    if intencion.reparto.mi_parte is not None:
        conocidas.append(intencion.reparto.mi_parte)
    total = sum(conocidas, CERO)
    todas = intencion.reparto.mi_parte is not None and all(p.importe is not None for p in intencion.partes)
    if todas and total == intencion.importe:
        return "COMPLETA"
    return "PARCIAL" if conocidas else "NO_DISPONIBLE"


def posiciones_declaradas(intencion: IntencionGastoCompartido) -> list[tuple[str, uuid.UUID, decimal.Decimal]]:
    """(tipo, tercero, importe) de cada posicion con «SI» explicito (INV-04)."""
    declaradas: list[tuple[str, uuid.UUID, decimal.Decimal]] = []
    if isinstance(intencion.pagado_por, PagadoConCuenta):
        for parte in intencion.partes:
            if parte.me_debe == "SI":
                declaradas.append((TIPO_DERECHO, parte.tercero_id, parte.importe))
    elif intencion.pagado_por.le_debo == "SI":
        declaradas.append((TIPO_OBLIGACION, intencion.pagado_por.tercero_id, intencion.mi_parte))
    return declaradas


def componer_gasto_compartido(
    intencion: IntencionGastoCompartido, actor_self: uuid.UUID, actores_de: dict[uuid.UUID, uuid.UUID]
) -> DatosHechoCompuesto:
    iid = intencion.intencion_id
    x = intencion.importe.quantize(ESCALA)
    reparte = isinstance(intencion.reparto, RepartoEntrePersonas)
    hecho = DatosCreacionHecho(
        hecho_id=iid, fecha_hecho=intencion.fecha_hecho, moneda=intencion.moneda,
        presupuestable=intencion.presupuestable, estado_localizacion="DESCONOCIDA",
        tipo_hecho_codigo="GASTO", concepto=intencion.nota, importe_total=x,
        numero_participantes_total=(1 + len(intencion.partes)) if reparte else None,
    )
    atribuciones: list[DatosAtribucion] = []
    if intencion.mi_parte is not None:
        atribuciones.append(DatosAtribucion(
            atribucion_id=_id(iid, "atribucion.self"), actor_id=actor_self,
            importe_atribuido=intencion.mi_parte.quantize(ESCALA), criterio_atribucion="MANUAL"))
    for parte in intencion.partes:
        if parte.importe is not None:
            atribuciones.append(DatosAtribucion(
                atribucion_id=_id(iid, f"atribucion.{parte.tercero_id}"), actor_id=actores_de[parte.tercero_id],
                importe_atribuido=parte.importe.quantize(ESCALA), criterio_atribucion="MANUAL"))
    efecto = DatosEfecto(
        efecto_id=_id(iid, "efecto"), tipo_efecto="GASTO", importe_delta=x,
        estado_atribucion=_estado_atribucion(intencion), categoria_id=intencion.categoria_id,
        atribuciones=tuple(atribuciones),
    )
    participantes = []
    if reparte:
        participantes.append(DatosParticipante(participante_id=_id(iid, "participante.self"), actor_id=actor_self))
        for parte in intencion.partes:
            participantes.append(DatosParticipante(participante_id=_id(iid, f"participante.{parte.tercero_id}"),
                                                   actor_id=actores_de[parte.tercero_id]))
    pagos: list[DatosPagoCompuesto] = []
    if isinstance(intencion.pagado_por, PagadoConCuenta):
        movimiento = DatosMovimiento(
            movimiento_id=_id(iid, "movimiento"), cuenta_id=intencion.pagado_por.cuenta_id,
            fecha_movimiento=intencion.fecha_hecho, importe=-x, clase_movimiento="OPERACION",
            descripcion=intencion.nota)
        conciliacion = DatosConciliacion(
            conciliacion_id=_id(iid, "conciliacion"), hecho_id=iid,
            movimiento_tesoreria_id=movimiento.movimiento_id, importe_asignado=-x)
        pagos.append(DatosPagoCompuesto(movimiento=movimiento, conciliacion=conciliacion))
        aportacion = DatosAportacion(
            aportacion_id=_id(iid, "aportacion.self"), importe=x, criterio_aportacion="MANUAL",
            actor_id=actor_self, hecho_movimiento_tesoreria_id=conciliacion.conciliacion_id)
    else:
        # D-REP-01: pago otra persona; no sale dinero de mis cuentas.
        aportacion = DatosAportacion(
            aportacion_id=_id(iid, "aportacion.pagador"), importe=x, criterio_aportacion="MANUAL",
            actor_id=actores_de[intencion.pagado_por.tercero_id])
    posiciones = [
        DatosAltaPosicion(
            entidad_id=_id(iid, f"posicion.{tercero}"), nombre=intencion.nota or NOMBRE_POSICION, tipo=tipo,
            contraparte_actor_id=actores_de[tercero], moneda=MONEDA, justificacion=JUSTIFICACION_DECISION,
            fecha_inicio_seguimiento=intencion.fecha_hecho, saldo_apertura=CERO, hecho_id=iid,
            fecha_hecho=intencion.fecha_hecho, concepto=intencion.nota,
            efecto_id=_id(iid, f"posicion.{tercero}.efecto"), vinculo_id=_id(iid, f"posicion.{tercero}.vinculo"),
            importe_inicial=importe.quantize(ESCALA),
        )
        for tipo, tercero, importe in posiciones_declaradas(intencion)
    ]
    magnitudes = tuple(
        DatosMagnitudHecho(registro_id=id_magnitud_hecho(iid, m.magnitud_id), magnitud_id=m.magnitud_id,
                           valor=decimal.Decimal(m.valor), unidad=None)
        for m in sorted(intencion.magnitudes, key=lambda m: m.magnitud_id)
    )
    return DatosHechoCompuesto(
        hecho=hecho, efectos=[efecto], participantes=participantes, posiciones=posiciones, pagos=pagos,
        aportaciones=[aportacion],
        contexto=contexto_hecho(iid, PREFIJO, "GASTO", tercero_id=intencion.tercero_id, contexto_id=None,
                                magnitudes=magnitudes),
    )


def _actores_existentes(sesion: SesionMotor, terceros: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID] | None:
    """Replay: actores ya creados por la intencion original (sin crear nada)."""
    from app.actores import repositorio as repo_actores

    encontrados: dict[uuid.UUID, uuid.UUID] = {}
    for tercero in terceros:
        actor = repo_actores.leer_actor_de_tercero(sesion, tercero)
        if actor is None:
            return None
        encontrados[tercero] = actor
    return encontrados


def registrar_gasto_compartido(
    unidad: UnidadDeTrabajo, contexto: ContextoOperacion, intencion: IntencionGastoCompartido,
    reloj: Reloj = reloj_sistema,
) -> GastoCompartidoRegistrado | RechazoRegistro:
    declaradas = posiciones_declaradas(intencion)
    personas = _personas(intencion)

    def operacion(sesion: SesionMotor) -> GastoCompartidoRegistrado | RechazoRegistro:
        # 0. Advisory INVERSIONES ANTES de la cuenta si habra posiciones
        #    (hecho_entidades GENERADO_POR): R-M3PRE2-01.
        if declaradas:
            tomar_inversiones(sesion)
        # 1. Cuenta FNKU (solo si pague yo).
        if isinstance(intencion.pagado_por, PagadoConCuenta):
            bloquear_cuentas(sesion, intencion.pagado_por.cuenta_id)
        actor_self = leer_actor_self(sesion)
        # 2. Identidad antes que cualquier revalidacion contextual: un reintento
        #    no revalida (un hecho valido no se rechaza retrospectivamente).
        ya_materializada = repo_hechos.leer_estado(sesion, intencion.intencion_id) is not None
        if ya_materializada:
            actores_de = _actores_existentes(sesion, personas)
            if actores_de is None:
                raise ErrorMotor(CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                                 "La intencion ya existe con otras personas.")
        if not ya_materializada:
            if es_futura(sesion, intencion.fecha_hecho, reloj):
                return RechazoRegistro(CODIGO_FECHA_FUTURA)
            if isinstance(intencion.pagado_por, PagadoConCuenta):
                rechazo_cuenta(sesion, intencion.pagado_por.cuenta_id, "GASTO", intencion.fecha_hecho)
            rechazo = validar_categoria_y_magnitudes(
                sesion, intencion.categoria_id, "GASTO", intencion.magnitudes, intencion.magnitudes_desconocidas)
            if rechazo is not None:
                return RechazoRegistro(rechazo)
            # 3. Terceros FOR SHARE por UUID: el comercio (owner y habilitado)
            #    y las personas (owner, PERSONA y habilitadas), todos antes de
            #    escribir nada; despues, el writer de actor (orden canonico).
            for tercero in sorted({intencion.tercero_id, *personas} - {None}, key=str):
                if tercero == intencion.tercero_id:
                    codigo = validar_tercero(sesion, tercero)
                    if codigo is not None:
                        return RechazoRegistro(codigo, {"tercero_id": str(tercero)})
                else:
                    try:
                        actores.validar_tercero_persona(sesion, tercero)
                    except actores.RechazoActor as exc:
                        return RechazoRegistro(exc.codigo, {"tercero_id": str(exc.tercero_id)})
            rechazo = validar_tipo_prevision(sesion, intencion.prevision, "GASTO")  # F05-06 M5
            if rechazo is not None:
                return RechazoRegistro(rechazo)
            actores_de = {t: actores.actor_de_tercero(sesion, t) for t in sorted(personas, key=str)}
        # 4. OP-22 adscrito: hecho -> efectos/atribuciones -> participantes ->
        #    posiciones -> pago -> aportaciones -> contexto, todo o nada.
        datos = componer_gasto_compartido(intencion, actor_self, actores_de)
        if intencion.prevision is not None:  # F05-06 M5: ... -> regla -> prevision (OP-17 al final)
            datos = dataclasses.replace(datos, prevision=prevision_compuesta(
                intencion.intencion_id, intencion.prevision, intencion.importe.quantize(ESCALA)))
        op22 = HechosCompuestosService(UnidadDeTrabajoAdscrita(sesion), impacto_ancla=impacto_correccion_ancla)
        resultado = op22.registrar_hecho_compuesto(contexto, datos)
        return GastoCompartidoRegistrado(
            hecho_id=resultado.hecho_id, idempotente=resultado.idempotente,
            estado_atribucion=datos.efectos[0].estado_atribucion, tu_parte=intencion.mi_parte,
            movimiento=(-intencion.importe if isinstance(intencion.pagado_por, PagadoConCuenta) else None),
            posiciones=[PosicionCreada(entidad_id=_id(intencion.intencion_id, f"posicion.{t}"), tipo=tipo,
                                       tercero_id=t, importe=imp) for tipo, t, imp in declaradas],
        )

    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoRegistro),
                           nombre="F05-06 M3 gasto_compartido (locks + writer de actor + OP-22)")


# ==================================================================
# Cobro (OP-14), pago (OP-12B) y perdon (condonacion) de una posicion
# ==================================================================
@dataclass(frozen=True, slots=True)
class PosicionAplicada:
    hecho_id: uuid.UUID
    entidad_id: uuid.UUID
    idempotente: bool
    saldo: decimal.Decimal | None
    estado: str


def leer_posicion(sesion: SesionMotor, entidad_id: uuid.UUID) -> dict[str, Any] | None:
    """Posicion del owner (RLS) con su version, tipo y hecho de origen."""
    fila = sesion.uno(
        "SELECT p.tipo, e.row_version, p.estado, p.contraparte_actor_id FROM gapto.derechos_obligaciones_financieras p "
        "JOIN gapto.entidades e ON e.id = p.entidad_id WHERE p.entidad_id = %s",
        (entidad_id,),
    )
    if fila is None:
        return None
    origen = sesion.uno(
        "SELECT v.hecho_id FROM gapto.hecho_entidades v "
        "JOIN gapto.hechos_financieros h ON h.id = v.hecho_id JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id "
        "WHERE v.entidad_id = %s AND v.efecto_id IS NOT NULL AND t.codigo NOT IN ('REEMBOLSO', 'CONDONACION') "
        "ORDER BY h.fecha_hecho, h.id LIMIT 1",
        (entidad_id,),
    )
    return {"tipo": fila[0], "row_version": fila[1], "estado": fila[2], "contraparte": fila[3],
            "origen": None if origen is None else origen[0]}


def _saldo_conocido(sesion: SesionMotor, contexto: ContextoOperacion, entidad_id) -> decimal.Decimal | None:
    resultado = PosicionesService(UnidadDeTrabajoAdscrita(sesion)).saldo(contexto, entidad_id)
    return resultado.saldo.importe if resultado.saldo.conocido else None


def _aplicar_reduccion(
    unidad: UnidadDeTrabajo, contexto: ContextoOperacion, entidad_id: uuid.UUID, intencion_id: uuid.UUID,
    importe: decimal.Decimal, fecha: dt.date, *, operacion_motor: str, cuenta_id: uuid.UUID | None,
    reloj: Reloj, nombre: str,
) -> PosicionAplicada | RechazoRegistro:
    """operacion_motor: COBRO (OP-14, derecho), PAGO (OP-12B, obligacion) o
    PERDON (condonacion de derecho u obligacion)."""
    hecho_id = _id(intencion_id, f"{operacion_motor.lower()}.hecho")
    x = importe.quantize(ESCALA)

    def operacion(sesion: SesionMotor) -> PosicionAplicada | RechazoRegistro:
        # Advisory ANTES de la cuenta: el servicio lo pide en adquirir_raiz.
        tomar_inversiones(sesion)
        if cuenta_id is not None:
            bloquear_cuentas(sesion, cuenta_id)
        posicion = leer_posicion(sesion, entidad_id)
        if posicion is None:
            return RechazoRegistro(POSICION_NO_ENCONTRADA)
        if (operacion_motor == "COBRO" and posicion["tipo"] != TIPO_DERECHO) or (
                operacion_motor == "PAGO" and posicion["tipo"] != TIPO_OBLIGACION):
            return RechazoRegistro(POSICION_NO_ADMITE_OPERACION)
        nueva = repo_hechos.leer_estado(sesion, hecho_id) is None
        if nueva:
            if es_futura(sesion, fecha, reloj):
                return RechazoRegistro(CODIGO_FECHA_FUTURA)
            if cuenta_id is not None:
                rechazo_cuenta(sesion, cuenta_id, "INGRESO" if operacion_motor == "COBRO" else "GASTO", fecha)
        saldo = _saldo_conocido(sesion, contexto, entidad_id)
        motivo_cierre = "CONDONADA" if operacion_motor == "PERDON" else "LIQUIDADA"
        cierre = DatosCierre(motivo_cierre=motivo_cierre, fecha_cierre=fecha) if saldo is not None and x == saldo else None
        causa = {"COBRO": CausaReduccion.COBRO, "PAGO": CausaReduccion.PAGO,
                 "PERDON": CausaReduccion.CONDONACION}[operacion_motor]
        delta = DatosDeltaPosicion(
            hecho_id=hecho_id, efecto_id=_id(intencion_id, f"{operacion_motor.lower()}.efecto"),
            vinculo_id=_id(intencion_id, f"{operacion_motor.lower()}.vinculo"), importe=x, fecha_hecho=fecha,
            concepto=None, causa=causa, cierre=cierre)
        tesoreria = None if cuenta_id is None else DatosTesoreriaReembolso(
            conciliacion_id=_id(intencion_id, f"{operacion_motor.lower()}.conciliacion"),
            movimiento_id=_id(intencion_id, f"{operacion_motor.lower()}.movimiento"),
            cuenta_id=cuenta_id, fecha_movimiento=fecha)
        servicio = PosicionesService(UnidadDeTrabajoAdscrita(sesion))
        version = posicion["row_version"]
        if operacion_motor == "COBRO":
            r = servicio.reembolsar(contexto, entidad_id=entidad_id, entidad_row_version_esperada=version,
                                    datos=DatosReembolso(delta=delta, tesoreria=tesoreria,
                                                         hecho_causal_id=posicion["origen"],
                                                         relacion_id=(None if posicion["origen"] is None else
                                                                      _id(intencion_id, "cobro.relacion"))))
        elif operacion_motor == "PAGO":
            r = servicio.reducir_obligacion(contexto, entidad_id=entidad_id, entidad_row_version_esperada=version,
                                            delta=delta, movimiento=tesoreria)
        elif posicion["tipo"] == TIPO_DERECHO:
            r = servicio.condonar_derecho(contexto, entidad_id=entidad_id, entidad_row_version_esperada=version,
                                          datos=DatosCondonacion(delta=delta))
        else:
            r = servicio.condonar_obligacion(contexto, entidad_id=entidad_id, entidad_row_version_esperada=version,
                                             datos=DatosCondonacionObligacion(delta=delta))
        return PosicionAplicada(hecho_id=hecho_id, entidad_id=entidad_id, idempotente=r.idempotente,
                                saldo=r.saldo.importe if r.saldo.conocido else None, estado=r.estado)

    return unidad.ejecutar(contexto, con_rechazo_capacidad(operacion, RechazoRegistro), nombre=nombre)


def cobrar(unidad, contexto, entidad_id, intencion: IntencionCobroPago, reloj: Reloj = reloj_sistema):
    return _aplicar_reduccion(unidad, contexto, entidad_id, intencion.intencion_id, intencion.importe,
                              intencion.fecha, operacion_motor="COBRO", cuenta_id=intencion.cuenta_id,
                              reloj=reloj, nombre="F05-06 M3 cobro (OP-14)")


def pagar(unidad, contexto, entidad_id, intencion: IntencionCobroPago, reloj: Reloj = reloj_sistema):
    return _aplicar_reduccion(unidad, contexto, entidad_id, intencion.intencion_id, intencion.importe,
                              intencion.fecha, operacion_motor="PAGO", cuenta_id=intencion.cuenta_id,
                              reloj=reloj, nombre="F05-06 M3 pago (OP-12B)")


def perdonar(unidad, contexto, entidad_id, intencion: IntencionPerdon, reloj: Reloj = reloj_sistema):
    return _aplicar_reduccion(unidad, contexto, entidad_id, intencion.intencion_id, intencion.importe,
                              intencion.fecha, operacion_motor="PERDON", cuenta_id=None,
                              reloj=reloj, nombre="F05-06 M3 perdon (condonacion)")


# ==================================================================
# «Pendiente con <persona>» (OP-20, lectura) y elegibilidad de anulacion
# ==================================================================
def pendiente_con(sesion: SesionMotor, contexto: ContextoOperacion, tercero_id: uuid.UUID) -> dict | None:
    """D-REP-07/09. None si el tercero no es visible. Sin actor: sin posiciones."""
    from app.actores import repositorio as repo_actores

    tercero = sesion.uno("SELECT nombre FROM gapto.terceros WHERE id = %s", (tercero_id,))
    if tercero is None:
        return None
    vacio = {"tercero_id": tercero_id, "nombre": tercero[0], "te_debe": None, "le_debes": None, "neto": None,
             "neto_estado": "SIN_POSICIONES", "posiciones": []}
    actor = repo_actores.leer_actor_de_tercero(sesion, tercero_id)
    if actor is None:
        return vacio
    neto = NetoService(UnidadDeTrabajoAdscrita(sesion)).posicion_neta(contexto, contraparte_actor_id=actor)
    segmento = neto.segmento(actor, MONEDA)
    if segmento is None or not segmento.posiciones:
        return vacio
    posiciones, te_debe, le_debes = [], [], []
    for detalle in segmento.posiciones:
        info = leer_posicion(sesion, detalle.entidad_id)
        origen = None if info["origen"] is None else sesion.uno(
            "SELECT h.fecha_hecho, h.concepto, "
            "(SELECT t.nombre FROM gapto.hecho_terceros ht JOIN gapto.terceros t ON t.id = ht.tercero_id "
            " WHERE ht.hecho_id = h.id ORDER BY ht.principal DESC, t.id LIMIT 1) "
            "FROM gapto.hechos_financieros h WHERE h.id = %s", (info["origen"],))
        saldo = detalle.saldo.importe if detalle.saldo.conocido else None
        (te_debe if detalle.tipo == TIPO_DERECHO else le_debes).append(saldo)
        posiciones.append({
            "entidad_id": detalle.entidad_id, "entidad_row_version": info["row_version"], "tipo": detalle.tipo,
            "nombre": detalle.nombre, "saldo": None if saldo is None else _texto(saldo), "estado": info["estado"],
            "origen_hecho_id": info["origen"], "origen_fecha": None if origen is None else origen[0],
            "origen_concepto": None if origen is None else origen[1],
            "origen_tercero": None if origen is None else origen[2],  # el comercio del gasto (C1)
        })

    def _suma(valores):
        if not valores:
            return _texto(CERO)
        return None if any(v is None for v in valores) else _texto(sum(valores, CERO))

    return {
        "tercero_id": tercero_id, "nombre": tercero[0], "te_debe": _suma(te_debe), "le_debes": _suma(le_debes),
        "neto": None if segmento.estado != DETERMINADO or segmento.neto is None else _texto(segmento.neto),
        "neto_estado": "DETERMINADO" if segmento.estado == DETERMINADO else "INDETERMINADO",
        "posiciones": posiciones,
    }


def elegibilidad_anulacion(sesion: SesionMotor, hecho_id: uuid.UUID) -> dict | None:
    """(iii) AJ-M3-DEC-04: lo que OP-03 rechazaria, SIN locks ni escritura.
    Solo sirve para mostrar; la operacion revalida bajo lock."""
    estado = sesion.uno("SELECT estado FROM gapto.hechos_financieros WHERE id = %s", (hecho_id,))
    if estado is None:
        return None
    motivos = []
    if estado[0] != "ACTIVO":
        motivos.append("NO_ACTIVO")
    if sesion.uno("SELECT EXISTS (SELECT 1 FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s) "
                  "OR EXISTS (SELECT 1 FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s)",
                  (hecho_id, hecho_id))[0]:
        motivos.append("TESORERIA")
    if repo_hechos.dependencias_activas(sesion, hecho_id):
        motivos.append("DEPENDENCIAS_ACTIVAS")
    if sesion.uno("SELECT EXISTS (SELECT 1 FROM gapto.hecho_entidades v JOIN gapto.derechos_obligaciones_financieras p "
                  "ON p.entidad_id = v.entidad_id WHERE v.hecho_id = %s)", (hecho_id,))[0]:
        motivos.append("POSICIONES")
    if sesion.uno("SELECT EXISTS (SELECT 1 FROM gapto.mapeos_importacion WHERE tabla_destino = 'hechos_financieros' "
                  "AND registro_destino_id = %s)", (hecho_id,))[0]:
        motivos.append("ORIGEN_IMPORTADO")
    return {"hecho_id": hecho_id, "elegible": not motivos, "motivos": motivos}


# ==================================================================
# «Corregir reparto» (OP-21 con whitelist; §57.1.1)
# ==================================================================
@dataclass(frozen=True, slots=True)
class RepartoCorregido:
    hecho_id: uuid.UUID
    row_version: int
    tu_parte: decimal.Decimal | None
    posiciones: list[PosicionCreada]


def _estado_reparto(sesion: SesionMotor, hecho_id: uuid.UUID) -> dict[str, Any] | None:
    hecho = sesion.uno(
        "SELECT h.estado, t.codigo, h.importe_total FROM gapto.hechos_financieros h "
        "JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id WHERE h.id = %s", (hecho_id,))
    if hecho is None:
        return None
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT id, tipo_efecto, importe_delta, estado_atribucion FROM gapto.hecho_efectos "
                    "WHERE hecho_id = %s", (hecho_id,))
        efectos = cur.fetchall()
        cur.execute("SELECT a.id, a.efecto_id, a.actor_id, a.importe_atribuido, a.porcentaje_aplicado "
                    "FROM gapto.efecto_atribuciones a JOIN gapto.hecho_efectos e ON e.id = a.efecto_id "
                    "WHERE e.hecho_id = %s", (hecho_id,))
        atribuciones = cur.fetchall()
        cur.execute("SELECT v.efecto_id, p.tipo, p.contraparte_actor_id, p.entidad_id FROM gapto.hecho_entidades v "
                    "JOIN gapto.derechos_obligaciones_financieras p ON p.entidad_id = v.entidad_id "
                    "WHERE v.hecho_id = %s AND v.efecto_id IS NOT NULL", (hecho_id,))
        vinculos = cur.fetchall()
    es_devolucion = sesion.uno("SELECT EXISTS (SELECT 1 FROM gapto.hecho_relaciones WHERE hecho_origen_id = %s "
                               "AND tipo_relacion = 'DEVOLUCION_DE')", (hecho_id,))[0]
    importado = sesion.uno("SELECT EXISTS (SELECT 1 FROM gapto.mapeos_importacion WHERE tabla_destino = "
                           "'hechos_financieros' AND registro_destino_id = %s)", (hecho_id,))[0]
    return {"estado": hecho[0], "tipo": hecho[1], "importe_total": hecho[2], "efectos": efectos,
            "atribuciones": atribuciones, "vinculos": vinculos, "es_devolucion": es_devolucion,
            "importado": importado}


def corregir_reparto(
    unidad: UnidadDeTrabajo, contexto: ContextoOperacion, hecho_id: uuid.UUID, intencion: IntencionCorregirReparto,
) -> RepartoCorregido | RechazoRegistro:
    def operacion(sesion: SesionMotor) -> RepartoCorregido | RechazoRegistro:
        owner = repo_hechos.exigir_contexto(sesion)
        # Orden global: advisory -> hecho -> posiciones (los mismos locks que
        # OP-21 tomara; reentrantes). La whitelist se evalua bajo ellos.
        integridad_posicion.adquirir_raiz(sesion, owner, hechos=[hecho_id], advisory=True)
        estado = _estado_reparto(sesion, hecho_id)
        if estado is None:
            return RechazoRegistro(HECHO_NO_ENCONTRADO)
        actor_self = leer_actor_self(sesion)
        gastos = [e for e in estado["efectos"] if e[1] == "GASTO"]
        # Whitelist (AJ-M3-DEC-09): solo un gasto activo de un unico efecto
        # GASTO con reparto; nunca devoluciones, ingresos, V3 ni transferencias.
        if (estado["estado"] != "ACTIVO" or estado["tipo"] != "GASTO" or estado["es_devolucion"]
                or len(gastos) != 1 or any(e[1] == "INGRESO" for e in estado["efectos"])):
            return RechazoRegistro(REPARTO_NO_CORREGIBLE, {"motivo": "TIPO_NO_ADMITIDO"})
        if estado["importado"]:
            return RechazoRegistro(REPARTO_NO_CORREGIBLE, {"motivo": "ORIGEN_IMPORTADO"})
        efecto_id, _, importe_gasto, estado_atr = gastos[0]
        propias = {a[0]: a for a in estado["atribuciones"] if a[1] == efecto_id}
        nuevas = {p.atribucion_id: p.importe.quantize(ESCALA) for p in intencion.partes}
        if not set(nuevas) <= set(propias):
            return RechazoRegistro(REPARTO_NO_CORREGIBLE, {"motivo": "PARTE_AJENA"})
        final = {aid: nuevas.get(aid, a[3]) for aid, a in propias.items()}
        total = sum(final.values(), CERO)
        # G3: COMPLETA sigue sumando el total; PARCIAL nunca se completa solo.
        if (estado_atr == "COMPLETA" and total != importe_gasto) or (
                estado_atr == "PARCIAL" and total >= importe_gasto) or estado_atr == "NO_DISPONIBLE":
            return RechazoRegistro(REPARTO_NO_CORREGIBLE, {"motivo": "SUMA_NO_CUADRA"})
        # Coherencia efecto <-> posicion (AJ-M3-DEC-03): el efecto de cada
        # posicion debe ser DEMOSTRABLEMENTE la parte que se corrige; si no,
        # rechazo. Derecho: la parte de su contraparte; obligacion: la mia.
        efectos_a_actualizar: dict[uuid.UUID, dict[str, Any]] = {}
        importes_efecto = {e[0]: e[2] for e in estado["efectos"]}
        por_actor = {a[2]: a for a in propias.values()}
        posiciones: list[PosicionCreada] = []
        for efecto_pos, tipo, contraparte, entidad in estado["vinculos"]:
            deudor = contraparte if tipo == TIPO_DERECHO else actor_self
            atr = por_actor.get(deudor)
            if atr is None or atr[0] not in nuevas or nuevas[atr[0]] == atr[3]:
                continue
            if abs(importes_efecto[efecto_pos]) != atr[3]:
                return RechazoRegistro(REPARTO_NO_DEMOSTRABLE)
            efectos_a_actualizar[efecto_pos] = {"importe_delta": nuevas[atr[0]]}
            # El wire habla de terceros, no de actores (como en el gasto compartido).
            from app.actores import repositorio as repo_actores
            posiciones.append(PosicionCreada(entidad_id=entidad, tipo=tipo,
                                             tercero_id=repo_actores.tercero_de_actor(sesion, contraparte),
                                             importe=nuevas[atr[0]]))
        datos = DatosCorreccion(
            hecho_id=hecho_id, row_version_esperada=intencion.row_version, motivo=intencion.motivo.strip(),
            efectos_a_actualizar=efectos_a_actualizar,
            atribuciones_a_actualizar={
                aid: {"importe_atribuido": v, "porcentaje_aplicado": None}
                for aid, v in nuevas.items() if v != propias[aid][3]},
        )
        resultado = CorreccionesService(UnidadDeTrabajoAdscrita(sesion)).corregir(contexto, datos)
        mia = next((final[a[0]] for a in propias.values() if a[2] == actor_self), None)
        return RepartoCorregido(hecho_id=hecho_id, row_version=resultado.hecho_row_version, tu_parte=mia,
                                posiciones=posiciones)

    return unidad.ejecutar(contexto, operacion, nombre="F05-06 M3 corregir_reparto (OP-21 whitelist)")


def reparto_de_hecho(sesion: SesionMotor, contexto: ContextoOperacion, hecho_id: uuid.UUID) -> dict | None:
    """Lectura del reparto para «Corregir reparto» (E6), SIN locks ni escritura.
    `corregible` solo sirve para mostrar; la correccion revalida la whitelist
    bajo lock. None si el hecho no es visible."""
    estado = _estado_reparto(sesion, hecho_id)
    if estado is None:
        return None
    actor_self = leer_actor_self(sesion)
    gastos = [e for e in estado["efectos"] if e[1] == "GASTO"]
    motivo = None
    if estado["estado"] != "ACTIVO":
        motivo = "NO_ACTIVO"
    elif (estado["tipo"] != "GASTO" or estado["es_devolucion"] or len(gastos) != 1
          or any(e[1] == "INGRESO" for e in estado["efectos"])):
        motivo = "TIPO_NO_ADMITIDO"
    elif estado["importado"]:
        motivo = "ORIGEN_IMPORTADO"
    partes: list[dict[str, Any]] = []
    estado_atr = gastos[0][3] if len(gastos) == 1 else "NO_DISPONIBLE"
    if len(gastos) == 1:
        efecto_id = gastos[0][0]
        # Deudor de cada posicion: la contraparte en un derecho; yo en una obligacion.
        posicion_de = {(contraparte if tipo == TIPO_DERECHO else actor_self): (tipo, entidad)
                       for _, tipo, contraparte, entidad in estado["vinculos"]}
        saldos: dict[uuid.UUID, str | None] = {}
        neto = NetoService(UnidadDeTrabajoAdscrita(sesion))
        for _, _, contraparte, entidad in estado["vinculos"]:
            segmento = neto.posicion_neta(contexto, contraparte_actor_id=contraparte).segmento(contraparte, MONEDA)
            for detalle in (segmento.posiciones if segmento is not None else ()):
                if detalle.entidad_id == entidad:
                    saldos[entidad] = _texto(detalle.saldo.importe) if detalle.saldo.conocido else None
        propias = [a for a in estado["atribuciones"] if a[1] == efecto_id]
        for aid, _, actor, importe, _ in sorted(propias, key=lambda a: (a[2] != actor_self, str(a[2]))):
            tercero = None if actor == actor_self else sesion.uno(
                "SELECT t.id, t.nombre FROM gapto.actores_financieros a JOIN gapto.terceros t ON t.id = a.tercero_id "
                "WHERE a.id = %s", (actor,))
            pos = posicion_de.get(actor)
            partes.append({
                "atribucion_id": aid, "es_yo": actor == actor_self,
                "tercero_id": None if tercero is None else tercero[0],
                "nombre": "Tú" if actor == actor_self else (tercero[1] if tercero else "Sin nombre"),
                "importe": _texto(importe),
                "posicion": None if pos is None else {"entidad_id": pos[1], "tipo": pos[0],
                                                      "saldo": saldos.get(pos[1])},
            })
    if motivo is None and (estado_atr == "NO_DISPONIBLE" or len(partes) < 2):
        motivo = "SIN_REPARTO"
    version = sesion.uno("SELECT row_version FROM gapto.hechos_financieros WHERE id = %s", (hecho_id,))[0]
    return {"hecho_id": hecho_id, "row_version": version, "importe": _texto(estado["importe_total"]),
            "estado_atribucion": estado_atr, "corregible": motivo is None, "motivo": motivo, "partes": partes}


def _texto(valor: decimal.Decimal) -> str:
    return str(decimal.Decimal(valor).quantize(decimal.Decimal("0.01")))
