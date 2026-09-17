# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_101_op01_crear_hecho.py
# Ruta: tests/backend/test_101_op01_crear_hecho.py
# Descripcion: F04-01 OP-01. Creacion de hechos financieros: entrada minima,
#   desconocidos que permanecen NULL, triestado de localizacion, validaciones,
#   idempotencia por UUID reservado, aislamiento tenant, auditoria y
#   atomicidad.
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
from app.repositories import auditoria_repository as auditoria
from app.repositories import hechos_repository as repo
from app.services.hechos_service import HechosService
from conftest import leer_fila

FECHA = dt.date(2026, 2, 14)


def datos_minimos(**extra) -> DatosCreacionHecho:
    base = {
        "hecho_id": uuid.uuid4(),
        "fecha_hecho": FECHA,
        "moneda": "EUR",
        "presupuestable": True,
        "estado_localizacion": "DESCONOCIDA",
        "tipo_hecho_codigo": "GASTO",
    }
    base.update(extra)
    return DatosCreacionHecho(**base)


# ------------------------------------------------------------------
# Camino correcto
# ------------------------------------------------------------------

def test_creacion_valida_minima(
    servicio: HechosService, contexto: ContextoOperacion, admin: psycopg.Connection
) -> None:
    datos = datos_minimos()
    resultado = servicio.crear_hecho(contexto, datos)

    assert resultado.hecho_id == datos.hecho_id
    assert resultado.row_version == 1
    assert resultado.estado == "ACTIVO"
    assert resultado.idempotente is False

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT owner_user_id, estado, anulado_at, row_version "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    )
    assert fila == (contexto.owner_user_id, "ACTIVO", None, 1)


def test_creacion_con_campos_opcionales(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    localidad: uuid.UUID,
) -> None:
    datos = datos_minimos(
        estado_localizacion="CONOCIDA",
        localidad_id=localidad,
        concepto="Compra de prueba",
        importe_total=decimal.Decimal("123.4500"),
        numero_participantes_total=3,
        notas="nota libre",
    )
    servicio.crear_hecho(contexto, datos)

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT concepto, importe_total, numero_participantes_total, "
        "localidad_id, notas FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    )
    assert fila == (
        "Compra de prueba",
        decimal.Decimal("123.4500"),
        3,
        localidad,
        "nota libre",
    )


def test_dato_desconocido_permanece_null_y_no_se_convierte_en_cero(
    servicio: HechosService, contexto: ContextoOperacion, admin: psycopg.Connection
) -> None:
    datos = datos_minimos()
    servicio.crear_hecho(contexto, datos)

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_total, concepto, numero_participantes_total, notas, "
        "localidad_id FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    )
    assert fila == (None, None, None, None, None)


# ------------------------------------------------------------------
# Triestado de localizacion
# ------------------------------------------------------------------

def test_localizacion_no_aplica_es_admisible_y_distinta_de_desconocida(
    servicio: HechosService, contexto: ContextoOperacion, admin: psycopg.Connection
) -> None:
    no_aplica = datos_minimos(estado_localizacion="NO_APLICA")
    desconocida = datos_minimos(estado_localizacion="DESCONOCIDA")
    servicio.crear_hecho(contexto, no_aplica)
    servicio.crear_hecho(contexto, desconocida)

    for datos, esperado in ((no_aplica, "NO_APLICA"), (desconocida, "DESCONOCIDA")):
        fila = leer_fila(
            admin,
            contexto.owner_user_id,
            "SELECT estado_localizacion FROM gapto.hechos_financieros WHERE id = %s",
            (datos.hecho_id,),
        )
        assert fila == (esperado,)


def test_conocida_exige_localidad(
    servicio: HechosService, contexto: ContextoOperacion
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.crear_hecho(
            contexto, datos_minimos(estado_localizacion="CONOCIDA", localidad_id=None)
        )
    assert excinfo.value.codigo is CodigoError.VIOLACION_INVARIANTE_FISICA


def test_desconocida_no_admite_localidad(
    servicio: HechosService, contexto: ContextoOperacion, localidad: uuid.UUID
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.crear_hecho(
            contexto,
            datos_minimos(estado_localizacion="DESCONOCIDA", localidad_id=localidad),
        )
    assert excinfo.value.codigo is CodigoError.VIOLACION_INVARIANTE_FISICA


def test_estado_localizacion_invalido_no_se_sustituye_por_no_aplica(
    servicio: HechosService, contexto: ContextoOperacion
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.crear_hecho(contexto, datos_minimos(estado_localizacion=None))
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


# ------------------------------------------------------------------
# Validaciones canonicas
# ------------------------------------------------------------------

def test_tipo_hecho_desconocido(
    servicio: HechosService, contexto: ContextoOperacion
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.crear_hecho(
            contexto, datos_minimos(tipo_hecho_codigo="NO_EXISTE_ESTE_TIPO")
        )
    assert excinfo.value.codigo is CodigoError.TIPO_HECHO_DESCONOCIDO


def test_moneda_invalida(
    servicio: HechosService, contexto: ContextoOperacion
) -> None:
    for moneda in ("eur", "EURO", "", None):
        with pytest.raises(ErrorMotor) as excinfo:
            servicio.crear_hecho(contexto, datos_minimos(moneda=moneda))
        assert excinfo.value.codigo is CodigoError.MONEDA_INVALIDA


def test_fecha_economica_ausente(
    servicio: HechosService, contexto: ContextoOperacion
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.crear_hecho(contexto, datos_minimos(fecha_hecho=None))
    assert excinfo.value.codigo is CodigoError.FECHA_ECONOMICA_AUSENTE


def test_presupuestable_no_tiene_default(
    servicio: HechosService, contexto: ContextoOperacion
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.crear_hecho(contexto, datos_minimos(presupuestable=None))
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


# ------------------------------------------------------------------
# Idempotencia por identidad reservada
# ------------------------------------------------------------------

def test_retry_con_mismo_uuid_no_duplica_el_hecho(
    servicio: HechosService, contexto: ContextoOperacion, admin: psycopg.Connection
) -> None:
    datos = datos_minimos(concepto="idempotente", importe_total=decimal.Decimal("10.00"))
    primero = servicio.crear_hecho(contexto, datos)
    segundo = servicio.crear_hecho(contexto, datos)

    assert primero.idempotente is False
    assert segundo.idempotente is True
    assert segundo.hecho_id == primero.hecho_id
    assert segundo.row_version == primero.row_version

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    )
    assert fila == (1,)

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'CREAR'",
        (datos.hecho_id,),
    )
    assert fila == (1,)


def test_retry_idempotente_funciona_con_otro_request_id(
    servicio: HechosService, owner: uuid.UUID
) -> None:
    """La identidad idempotente es el UUID del hecho, no el request_id."""
    datos = datos_minimos()
    servicio.crear_hecho(ContextoOperacion.de_usuario(owner), datos)
    segundo = servicio.crear_hecho(ContextoOperacion.de_usuario(owner), datos)
    assert segundo.idempotente is True


def test_mismo_uuid_con_intencion_incompatible_es_conflicto(
    servicio: HechosService, contexto: ContextoOperacion
) -> None:
    datos = datos_minimos(concepto="original")
    servicio.crear_hecho(contexto, datos)

    otra_intencion = DatosCreacionHecho(
        hecho_id=datos.hecho_id,
        fecha_hecho=FECHA,
        moneda="EUR",
        presupuestable=True,
        estado_localizacion="DESCONOCIDA",
        tipo_hecho_codigo="GASTO",
        concepto="otra cosa distinta",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.crear_hecho(contexto, otra_intencion)
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION


def test_idempotencia_se_compara_contra_la_creacion_no_contra_el_estado_actual(
    servicio: HechosService, contexto: ContextoOperacion
) -> None:
    """Un alta corregida despues sigue siendo idempotente ante su propio retry."""
    from app.core.modelos import CamposCorreccion

    datos = datos_minimos(concepto="capturado mal")
    creado = servicio.crear_hecho(contexto, datos)
    servicio.corregir_hecho(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        campos=CamposCorreccion(concepto="capturado bien"),
        motivo="error de captura del concepto",
    )

    repetido = servicio.crear_hecho(contexto, datos)
    assert repetido.idempotente is True
    assert repetido.row_version == 2
    assert repetido.snapshot["concepto"] == "capturado bien"


# ------------------------------------------------------------------
# Tenant
# ------------------------------------------------------------------

def test_aislamiento_entre_tenants_en_la_creacion(
    servicio: HechosService, owner: uuid.UUID, otro_owner: uuid.UUID
) -> None:
    datos = datos_minimos()
    servicio.crear_hecho(ContextoOperacion.de_usuario(owner), datos)

    with pytest.raises(ErrorMotor) as excinfo:
        servicio.crear_hecho(ContextoOperacion.de_usuario(otro_owner), datos)
    # El otro tenant no ve la auditoria de creacion, de modo que no puede
    # demostrar la misma intencion; tampoco recibe informacion sobre a quien
    # pertenece el identificador.
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION


def test_el_owner_lo_fija_el_contexto_no_el_llamante(
    servicio: HechosService, contexto: ContextoOperacion, admin: psycopg.Connection
) -> None:
    assert not hasattr(datos_minimos(), "owner_user_id")
    datos = datos_minimos()
    servicio.crear_hecho(contexto, datos)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT owner_user_id FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    )
    assert fila == (contexto.owner_user_id,)


# ------------------------------------------------------------------
# Auditoria y atomicidad
# ------------------------------------------------------------------

def test_auditoria_de_creacion_en_la_misma_transaccion(
    servicio: HechosService, contexto: ContextoOperacion, admin: psycopg.Connection
) -> None:
    datos = datos_minimos(concepto="auditado")
    servicio.crear_hecho(contexto, datos)

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT accion, actor_tipo, actor_user_id, request_id, datos_antes, "
        "datos_despues->>'concepto' FROM gapto.auditoria WHERE registro_id = %s",
        (datos.hecho_id,),
    )
    assert fila is not None
    accion, actor_tipo, actor_user_id, request_id, antes, concepto = fila
    assert accion == "CREAR"
    assert actor_tipo == "USUARIO"
    assert actor_user_id == contexto.actor_user_id
    assert request_id == contexto.request_id
    assert antes is None
    assert concepto == "auditado"


def test_fallo_de_auditoria_revierte_el_hecho(
    unidad, contexto: ContextoOperacion, admin: psycopg.Connection
) -> None:
    """Si la auditoria falla, no puede quedar el hecho escrito."""
    datos = datos_minimos()

    def operacion(sesion):
        tipo_id = repo.resolver_tipo_hecho(sesion, codigo="GASTO", tipo_hecho_id=None)
        creado = repo.insertar_si_no_existe(sesion, datos, tipo_id)
        assert creado is not None
        # Snapshot con una clave prohibida por la minimizacion de D-068.
        auditoria.registrar(
            sesion,
            tabla=repo.TABLA,
            registro_id=datos.hecho_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json='{"password": "x"}',
        )

    with pytest.raises(ErrorMotor):
        unidad.ejecutar(contexto, operacion, nombre="prueba-rollback")

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    )
    assert fila == (0,)


def test_fallo_del_hecho_no_deja_auditoria_residual(
    servicio: HechosService, contexto: ContextoOperacion, admin: psycopg.Connection
) -> None:
    datos = datos_minimos(estado_localizacion="CONOCIDA", localidad_id=None)
    with pytest.raises(ErrorMotor):
        servicio.crear_hecho(contexto, datos)

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s",
        (datos.hecho_id,),
    )
    assert fila == (0,)
