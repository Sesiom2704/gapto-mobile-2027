# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_118_op18_suplemento.py
# Ruta: tests/backend/test_118_op18_suplemento.py
# Descripcion: F04-06 / B4. OP-18 realidad suplementaria / fecha economica.
#
#   LA FRONTERA QUE VIGILA ESTA SUITE:
#
#     OP-02   corrige lo que NUNCA fue cierto. No crea hecho.
#     OP-13   DESHACE un efecto anterior, con signo contrario.
#     OP-18   AÑADE realidad que si ocurrio, con su propia fecha.
#
#   Ninguna garantia fisica las separa: las tres producen filas validas. Por
#   eso los tres errores de OP-18 son SRV puros y por eso el mutante N8 —usar
#   CORRIGE_A para tapar un error de captura— es el que de verdad importa aqui.
#
#   INV-07 · CORRIGE_A no representa un error de captura. Pero la frontera es
#            de OPERACION, no de fechas: un suplemento puede ser ANTERIOR,
#            igual o posterior al hecho con el que se relaciona.
#   INV-08 · Un efecto no tiene fecha propia: la toma de su hecho, de modo que
#            varios periodos economicos exigen varios hechos.
# Version: 0.2.0
#   0.2.0 (iteracion correctiva): se retiran los dos casos que exigian fecha
#   posterior —regla inventada, contraria a F04-D002/INV-08— y se anaden los
#   de retroactividad legitima.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_suplemento import DatosSuplemento
from app.services.hechos_service import HechosService
from app.services.suplementos_service import SuplementosService
from conftest import leer_fila

D = decimal.Decimal
F = dt.date.fromisoformat


def crear_anterior(
    servicio: HechosService,
    contexto: ContextoOperacion,
    fecha: dt.date = F("2027-01-05"),
) -> uuid.UUID:
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=fecha,
            moneda="EUR",
            presupuestable=True,
            estado_localizacion="NO_APLICA",
            tipo_hecho_codigo="GASTO",
            importe_total=D("800.0000"),
            concepto="Alquiler enero",
        ),
    )
    return hecho_id


def datos_suplemento(**extra) -> DatosSuplemento:
    base = {
        "hecho_id": uuid.uuid4(),
        "efecto_id": uuid.uuid4(),
        "tipo_efecto": "GASTO",
        "importe_delta": D("50.0000"),
        "fecha_hecho": F("2027-06-01"),
        "moneda": "EUR",
        "fecha_demostrada": True,
        "concepto": "Revision de alquiler",
    }
    base.update(extra)
    return DatosSuplemento(**base)


# ==================================================================
# Camino correcto
# ==================================================================

def test_realidad_suplementaria_autonoma(
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Una realidad que aparece sola no necesita relacionarse con nada.

    CORRIGE_A se emite solo cuando existe un hecho anterior identificable al
    que esta ajusta de verdad. Forzar una relacion siempre obligaria a inventar
    un vinculo donde no lo hay.
    """
    datos = datos_suplemento()
    resultado = servicio_suplementos.registrar(contexto, datos)
    assert resultado.relacion_id is None
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.hecho_relaciones "
        "          WHERE hecho_origen_id = %s), "
        "       (SELECT tipo_efecto FROM gapto.hecho_efectos WHERE id = %s)",
        (datos.hecho_id, datos.efecto_id),
    ) == (0, "GASTO")


def test_el_suplemento_tiene_su_propia_fecha_economica(
    servicio: HechosService,
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """No hereda la del hecho ajustado: ocurrio en su propio momento."""
    anterior = crear_anterior(servicio, contexto)
    datos = datos_suplemento(
        relacion_id=uuid.uuid4(), hecho_ajustado_id=anterior
    )
    servicio_suplementos.registrar(contexto, datos)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s), "
        "       (SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s)",
        (datos.hecho_id, anterior),
    ) == (F("2027-06-01"), F("2027-01-05"))


def test_corrige_a_va_del_ajuste_al_hecho_ajustado(
    servicio: HechosService,
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    anterior = crear_anterior(servicio, contexto)
    datos = datos_suplemento(
        relacion_id=uuid.uuid4(), hecho_ajustado_id=anterior
    )
    servicio_suplementos.registrar(contexto, datos)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT hecho_origen_id, hecho_destino_id, tipo_relacion "
        "FROM gapto.hecho_relaciones WHERE id = %s",
        (datos.relacion_id,),
    ) == (datos.hecho_id, anterior, "CORRIGE_A")


def test_el_hecho_ajustado_no_se_modifica(
    servicio: HechosService,
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """OP-18 anade realidad; no edita la anterior. El original conserva su
    estado, su version y su importe."""
    anterior = crear_anterior(servicio, contexto)
    antes = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado, row_version, importe_total, fecha_hecho "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (anterior,),
    )
    servicio_suplementos.registrar(
        contexto,
        datos_suplemento(relacion_id=uuid.uuid4(), hecho_ajustado_id=anterior),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado, row_version, importe_total, fecha_hecho "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (anterior,),
    ) == antes


def test_un_delta_negativo_tambien_es_realidad_suplementaria(
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Un ajuste posterior puede reducir. No por ello es una devolucion:
    OP-13 DESHACE una porcion del efecto anterior y se relaciona con
    DEVOLUCION_DE; OP-18 registra un acontecimiento propio.
    """
    datos = datos_suplemento(importe_delta=D("-20.0000"))
    servicio_suplementos.registrar(contexto, datos)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_delta FROM gapto.hecho_efectos WHERE id = %s",
        (datos.efecto_id,),
    ) == (D("-20.0000"),)


def test_varios_periodos_exigen_varios_hechos(
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """INV-08. Un efecto no tiene fecha propia: la toma de su hecho.

    Una revision que afecta a tres meses no es un efecto con tres fechas: son
    tres hechos, uno por periodo economico.
    """
    creados = []
    for mes in (1, 2, 3):
        datos = datos_suplemento(fecha_hecho=dt.date(2027, mes, 28))
        servicio_suplementos.registrar(contexto, datos)
        creados.append(datos.hecho_id)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(DISTINCT fecha_hecho) FROM gapto.hechos_financieros "
        "WHERE id = ANY(%s::uuid[])",
        (creados,),
    ) == (3,)


# ==================================================================
# La frontera: lo que NUNCA fue cierto no pasa por aqui
# ==================================================================

def test_fecha_economica_no_demostrada(
    servicio_suplementos: SuplementosService, contexto: ContextoOperacion
) -> None:
    """Sin fecha demostrada no se retrodata nada.

    Es la puerta que impide que OP-18 se convierta en un mecanismo para
    colocar realidad en cualquier momento del pasado.
    """
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_suplementos.registrar(
            contexto, datos_suplemento(fecha_demostrada=False)
        )
    assert excinfo.value.codigo is CodigoError.FECHA_ECONOMICA_NO_DEMOSTRADA


def test_intento_de_editar_el_original(
    servicio_suplementos: SuplementosService, contexto: ContextoOperacion
) -> None:
    """Lo que nunca fue cierto se corrige con OP-02, no se tapa con un hecho
    nuevo."""
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_suplementos.registrar(
            contexto, datos_suplemento(editar_original=True)
        )
    assert excinfo.value.codigo is CodigoError.EDICION_DE_ORIGINAL_NO_PERMITIDA


def test_periodo_cerrado_sin_politica(
    servicio_suplementos: SuplementosService, contexto: ContextoOperacion
) -> None:
    """F04-06 no inventa la politica de periodos cerrados."""
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_suplementos.registrar(
            contexto, datos_suplemento(periodo_cerrado=True)
        )
    assert excinfo.value.codigo is CodigoError.PERIODO_CERRADO_SIN_POLITICA


def test_periodo_cerrado_con_politica_declarada(
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
) -> None:
    """Con politica aplicable declarada, la operacion procede.

    Sin este caso el anterior solo demostraria que el servicio rechaza, no que
    DISCRIMINA.
    """
    resultado = servicio_suplementos.registrar(
        contexto,
        datos_suplemento(
            periodo_cerrado=True, politica_periodo_cerrado="APERTURA_AUTORIZADA"
        ),
    )
    assert resultado.importe_delta == D("50.0000")


# ==================================================================
# Rechazos ordinarios
# ==================================================================

def test_delta_cero(
    servicio_suplementos: SuplementosService, contexto: ContextoOperacion
) -> None:
    """Un efecto de importe cero es ademas fisicamente imposible."""
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_suplementos.registrar(
            contexto, datos_suplemento(importe_delta=D("0"))
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_moneda_invalida(
    servicio_suplementos: SuplementosService, contexto: ContextoOperacion
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_suplementos.registrar(contexto, datos_suplemento(moneda="eur"))
    assert excinfo.value.codigo is CodigoError.MONEDA_INVALIDA


def test_relacion_sin_identidad_reservada(
    servicio: HechosService,
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
) -> None:
    anterior = crear_anterior(servicio, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_suplementos.registrar(
            contexto, datos_suplemento(hecho_ajustado_id=anterior)
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_hecho_ajustado_inexistente(
    servicio_suplementos: SuplementosService, contexto: ContextoOperacion
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_suplementos.registrar(
            contexto,
            datos_suplemento(
                relacion_id=uuid.uuid4(), hecho_ajustado_id=uuid.uuid4()
            ),
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_cross_tenant(
    servicio: HechosService,
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
    otro_owner: uuid.UUID,
) -> None:
    anterior = crear_anterior(servicio, contexto)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_suplementos.registrar(
            ContextoOperacion.de_usuario(otro_owner),
            datos_suplemento(
                relacion_id=uuid.uuid4(), hecho_ajustado_id=anterior
            ),
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


# ==================================================================
# Idempotencia
# ==================================================================

def test_retry_idempotente(
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    datos = datos_suplemento()
    primero = servicio_suplementos.registrar(contexto, datos)
    segundo = servicio_suplementos.registrar(contexto, datos)
    assert primero.idempotente is False
    assert segundo.idempotente is True
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (datos.hecho_id,),
    ) == (1,)


def test_misma_identidad_con_otra_fecha_es_conflicto(
    servicio_suplementos: SuplementosService, contexto: ContextoOperacion
) -> None:
    """La fecha economica forma parte de la identidad de la intencion: el
    mismo ajuste en otro periodo es otra realidad."""
    primera = datos_suplemento()
    servicio_suplementos.registrar(contexto, primera)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_suplementos.registrar(
            contexto,
            datos_suplemento(
                hecho_id=primera.hecho_id,
                efecto_id=primera.efecto_id,
                fecha_hecho=F("2027-07-01"),
            ),
        )
    assert (
        excinfo.value.codigo
        is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION
    )


# ==================================================================
# Retroactividad legitima (F04-D002 / INV-08)
# ==================================================================

def test_suplemento_retroactivo_anterior_al_hecho_relacionado(
    servicio: HechosService,
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """El 20 de septiembre se descubre un gasto atribuible al 31 de agosto.

    `fecha_hecho` es la fecha ECONOMICA demostrada; cuando se registro lo dice
    `created_at`. Que el hecho relacionado sea posterior no convierte esto en
    una reescritura del pasado: la relacion expresa significado economico, no
    secuencia temporal.
    """
    relacionado = crear_anterior(servicio, contexto, F("2027-09-10"))
    datos = datos_suplemento(
        fecha_hecho=F("2027-08-31"),
        relacion_id=uuid.uuid4(),
        hecho_ajustado_id=relacionado,
        concepto="Gasto de agosto descubierto en septiembre",
    )
    resultado = servicio_suplementos.registrar(contexto, datos)
    assert resultado.fecha_hecho == F("2027-08-31")
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s), "
        "       (SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s), "
        "       (SELECT tipo_relacion FROM gapto.hecho_relaciones WHERE id = %s)",
        (datos.hecho_id, relacionado, datos.relacion_id),
    ) == (F("2027-08-31"), F("2027-09-10"), "CORRIGE_A")


def test_suplemento_con_la_misma_fecha_que_el_hecho_relacionado(
    servicio: HechosService,
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Dos realidades economicas del mismo dia son legitimas.

    Un recargo que se descubre despues y pertenece al mismo periodo que el
    hecho original no deja de haber ocurrido por compartir fecha.
    """
    relacionado = crear_anterior(servicio, contexto, F("2027-03-10"))
    datos = datos_suplemento(
        fecha_hecho=F("2027-03-10"),
        relacion_id=uuid.uuid4(),
        hecho_ajustado_id=relacionado,
    )
    resultado = servicio_suplementos.registrar(contexto, datos)
    assert resultado.fecha_hecho == F("2027-03-10")
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE id IN (%s, %s)",
        (datos.hecho_id, relacionado),
    ) == (2,)


def test_op18_crea_realidad_nueva_y_no_edita_el_original(
    servicio: HechosService,
    servicio_suplementos: SuplementosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """LA FRONTERA, comprobada por IDENTIDAD y PERSISTENCIA.

    OP-18 crea un hecho NUEVO con su propia identidad; el hecho relacionado
    permanece intacto en estado, version, importe y fecha. Corregir un dato
    falso es otra operacion —OP-02 u OP-21— y NO produce un hecho sustitutorio.

    Es el oraculo determinista del mutante N8: no mira fechas, mira si nacio
    una realidad nueva y si la anterior sobrevivio sin tocarse.
    """
    relacionado = crear_anterior(servicio, contexto, F("2027-03-10"))
    antes = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado, row_version, importe_total, fecha_hecho "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (relacionado,),
    )
    datos = datos_suplemento(
        relacion_id=uuid.uuid4(), hecho_ajustado_id=relacionado
    )
    servicio_suplementos.registrar(contexto, datos)

    # 1. Nacio una realidad NUEVA, con identidad propia.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    ) == (1,)
    assert datos.hecho_id != relacionado
    # 2. El original sobrevivio sin un solo cambio.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado, row_version, importe_total, fecha_hecho "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (relacionado,),
    ) == antes
    # 3. Coexisten los dos, no hay sustitucion.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE id IN (%s, %s)",
        (datos.hecho_id, relacionado),
    ) == (2,)
