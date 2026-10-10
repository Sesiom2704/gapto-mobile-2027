# ============================================================
# GAPTO MOBILE 2027
# Fichero: traductor_registro.py
# Ruta: backend/app/api/traductor_registro.py
# Descripcion: Traduccion de las intenciones de F05-04 (J2 §1.7) a los
#   contratos F04 certificados, SOLO desde el payload sellado y sin
#   reimplementar reglas financieras. API DE INTEGRACION F05, PENDIENTE DE
#   CONSOLIDACION F10.
#
#   Ingreso cobrado (C-14 via OP-22; F05 §46.3 A3):
#     hecho INGRESO        fecha_hecho = fecha de cobro, concepto = nota
#                          canonica (o NULL), importe_total = X, EUR,
#                          presupuestable = decision explicita,
#                          estado_localizacion = DESCONOCIDA;
#     efecto INGRESO +X    SOLO_MIO -> COMPLETA, atribucion self MANUAL 100 %;
#                          SIN_INDICAR -> NO_DISPONIBLE, sin filas (A01);
#     movimiento +X        en «Cobrado en», fecha = fecha_hecho, descripcion =
#                          nota canonica (o NULL);
#     conciliacion +X      signo del movimiento (OP-09);
#     SIN aportaciones     (no hay financiacion en un cobro; OP-06 lo rechaza).
#     tercero              -> hecho_terceros rol OTRO, principal = true;
#     contexto             -> hecho_entidades RELACIONADO_CON, efecto NULL,
#                             principal = false;
#     magnitudes           -> como VS-01 (las «No lo se» no generan fila).
#   Entre cuentas (OP-10; A4): seis identidades, concepto y descripciones de
#     ambas patas = nota canonica (o NULL), importe_salida = importe_entrada =
#     X, fecha_movimiento = fecha_hecho, sin comision.
#   Identidad: hecho_id = intencion_id; el resto con uuid5(intencion_id,
#   prefijo propio + rol): «gapto.f05.ingreso_cobrado.» y
#   «gapto.f05.transferencia.» (distintos del de VS-01).
#   Hecho y vinculos de contexto del gasto: ver contexto_hecho().
# Version: 0.1.0 (F05-03/F05-04 J2 §1.7)
# ============================================================

from __future__ import annotations

import decimal
import uuid

from app.api.dto_registro import IntencionIngresoCobrado, IntencionTransferencia
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_compuesto import (
    DatosContextoHecho,
    DatosEntidadHecho,
    DatosHechoCompuesto,
    DatosMagnitudHecho,
    DatosPagoCompuesto,
    DatosTerceroHecho,
)
from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
from app.core.modelos_transferencia import DatosTransferencia

CIEN = decimal.Decimal("100")
ESCALA = decimal.Decimal("0.0001")
PREFIJO_INGRESO = "gapto.f05.ingreso_cobrado."
PREFIJO_TRANSFERENCIA = "gapto.f05.transferencia."

#: Rol del tercero por tipo (A5): GASTO -> VENDEDOR; INGRESO -> OTRO.
ROL_TERCERO = {"GASTO": "VENDEDOR", "INGRESO": "OTRO"}


def _id(intencion: uuid.UUID, prefijo: str, rol: str) -> uuid.UUID:
    return uuid.uuid5(intencion, f"{prefijo}{rol}")


def contexto_hecho(intencion_id: uuid.UUID, prefijo: str, tipo: str, *, tercero_id, contexto_id,
                   magnitudes=()) -> DatosContextoHecho:
    """Vinculos del hecho: tercero (rol por tipo, principal), contexto
    (RELACIONADO_CON, a nivel de hecho, no principal) y magnitudes conocidas.
    Sin tercero ni contexto no se crea ninguna fila (nunca vinculos vacios)."""
    terceros = () if tercero_id is None else (
        DatosTerceroHecho(registro_id=_id(intencion_id, prefijo, "tercero"), tercero_id=tercero_id,
                          rol_en_hecho=ROL_TERCERO[tipo], principal=True),
    )
    entidades = () if contexto_id is None else (
        DatosEntidadHecho(registro_id=_id(intencion_id, prefijo, "contexto"), entidad_id=contexto_id,
                          tipo_relacion="RELACIONADO_CON", principal=False, efecto_id=None),
    )
    return DatosContextoHecho(terceros=terceros, entidades=entidades, magnitudes=tuple(magnitudes))


def componer_ingreso(intencion: IntencionIngresoCobrado, actor_self_id: uuid.UUID) -> DatosHechoCompuesto:
    x = intencion.importe.quantize(ESCALA)
    iid = intencion.intencion_id
    p = PREFIJO_INGRESO

    hecho = DatosCreacionHecho(
        hecho_id=iid, fecha_hecho=intencion.fecha_hecho, moneda=intencion.moneda,
        presupuestable=intencion.presupuestable, estado_localizacion="DESCONOCIDA",
        tipo_hecho_codigo="INGRESO", concepto=intencion.nota, importe_total=x,
    )
    if intencion.atribucion == "SOLO_MIO":
        efecto = DatosEfecto(
            efecto_id=_id(iid, p, "efecto"), tipo_efecto="INGRESO", importe_delta=x, estado_atribucion="COMPLETA",
            categoria_id=intencion.categoria_id,
            atribuciones=(DatosAtribucion(atribucion_id=_id(iid, p, "atribucion.self"), actor_id=actor_self_id,
                                          importe_atribuido=x, criterio_atribucion="MANUAL",
                                          porcentaje_aplicado=CIEN),),
        )
    else:  # SIN_INDICAR -> NO_DISPONIBLE (A01)
        efecto = DatosEfecto(efecto_id=_id(iid, p, "efecto"), tipo_efecto="INGRESO", importe_delta=x,
                             estado_atribucion="NO_DISPONIBLE", categoria_id=intencion.categoria_id)
    movimiento = DatosMovimiento(
        movimiento_id=_id(iid, p, "movimiento"), cuenta_id=intencion.cuenta_id, fecha_movimiento=intencion.fecha_hecho,
        importe=x, clase_movimiento="OPERACION", descripcion=intencion.nota,
    )
    conciliacion = DatosConciliacion(conciliacion_id=_id(iid, p, "conciliacion"), hecho_id=iid,
                                     movimiento_tesoreria_id=movimiento.movimiento_id, importe_asignado=x)
    magnitudes = tuple(
        DatosMagnitudHecho(registro_id=uuid.uuid5(iid, f"magnitud:{m.magnitud_id}"), magnitud_id=m.magnitud_id,
                           valor=decimal.Decimal(m.valor), unidad=None)
        for m in sorted(intencion.magnitudes, key=lambda m: m.magnitud_id)
    )
    return DatosHechoCompuesto(
        hecho=hecho, efectos=[efecto], pagos=[DatosPagoCompuesto(movimiento=movimiento, conciliacion=conciliacion)],
        aportaciones=[],
        contexto=contexto_hecho(iid, p, "INGRESO", tercero_id=intencion.tercero_id,
                                contexto_id=intencion.contexto_id, magnitudes=magnitudes),
    )


def componer_transferencia(intencion: IntencionTransferencia) -> DatosTransferencia:
    x = intencion.importe.quantize(ESCALA)
    iid = intencion.intencion_id
    p = PREFIJO_TRANSFERENCIA
    return DatosTransferencia(
        transferencia_id=_id(iid, p, "transferencia"), hecho_id=iid,
        movimiento_salida_id=_id(iid, p, "movimiento.salida"), movimiento_entrada_id=_id(iid, p, "movimiento.entrada"),
        conciliacion_salida_id=_id(iid, p, "conciliacion.salida"),
        conciliacion_entrada_id=_id(iid, p, "conciliacion.entrada"),
        cuenta_origen_id=intencion.cuenta_origen_id, cuenta_destino_id=intencion.cuenta_destino_id,
        fecha_hecho=intencion.fecha_hecho, fecha_movimiento=intencion.fecha_hecho, moneda=intencion.moneda,
        importe_salida=x, importe_entrada=x, concepto=intencion.nota, notas=None,
        descripcion_salida=intencion.nota, descripcion_entrada=intencion.nota, comision=None,
    )
