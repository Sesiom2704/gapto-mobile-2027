# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_102_op02_corregir_hecho.py
# Ruta: tests/backend/test_102_op02_corregir_hecho.py
# Descripcion: F04-01 OP-02. Correccion auditada de un error de captura:
#   optimistic locking con row_version, motivo obligatorio, campos que NO son
#   corregibles porque expresarian una realidad posterior, idempotencia
#   estricta, aislamiento tenant y atomicidad.
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
from app.core.modelos import CamposCorreccion
from app.repositories import auditoria_repository as auditoria
from app.repositories import hechos_repository as repo
from app.services.hechos_service import HechosService
from conftest import leer_fila
from test_101_op01_crear_hecho import datos_minimos


@pytest.fixture()
def hecho(servicio: HechosService, contexto: ContextoOperacion):
    datos = datos_minimos(
        concepto="concepto mal capturado",
        importe_total=decimal.Decimal("50.0000"),
    )
    resultado = servicio.crear_hecho(contexto, datos)
    return datos.hecho_id, resultado.row_version


# ------------------------------------------------------------------
# Camino correcto
# ------------------------------------------------------------------

def test_correccion_valida_incrementa_version(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    resultado = servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(concepto="concepto correcto"),
        motivo="se tecleo mal el concepto en el alta",
    )

    assert resultado.row_version == version + 1
    assert resultado.idempotente is False

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT concepto, row_version, updated_at > created_at "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila[0] == "concepto correcto"
    assert fila[1] == version + 1


def test_correccion_puede_poner_un_campo_a_null(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    """NULL solicitado explicitamente no es lo mismo que campo no enviado."""
    hecho_id, version = hecho
    servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(importe_total=None),
        motivo="el importe nunca se conocio",
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_total, concepto FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (None, "concepto mal capturado")


def test_auditoria_conserva_estado_anterior_y_posterior(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(concepto="corregido"),
        motivo="error de captura",
    )

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT accion, datos_antes->>'concepto', datos_despues->>'concepto', motivo "
        "FROM gapto.auditoria WHERE registro_id = %s AND accion = 'ACTUALIZAR'",
        (hecho_id,),
    )
    assert fila == (
        "ACTUALIZAR",
        "concepto mal capturado",
        "corregido",
        "error de captura",
    )


def test_el_owner_no_cambia_con_una_correccion(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    hecho_id, version = hecho
    servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(notas="nota"),
        motivo="faltaba la nota original",
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT owner_user_id FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == (contexto.owner_user_id,)


# ------------------------------------------------------------------
# Motivo
# ------------------------------------------------------------------

@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_motivo_obligatorio(
    servicio: HechosService, contexto: ContextoOperacion, hecho, motivo
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            campos=CamposCorreccion(concepto="x"),
            motivo=motivo,
        )
    assert excinfo.value.codigo is CodigoError.MOTIVO_AUSENTE


# ------------------------------------------------------------------
# Frontera semantica: correccion frente a realidad nueva
# ------------------------------------------------------------------

@pytest.mark.parametrize("campo", ["estado", "anulado_at", "motivo_anulacion"])
def test_no_se_puede_representar_realidad_posterior_como_correccion(campo) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        CamposCorreccion.desde_dict({campo: "ANULADO"})
    assert (
        excinfo.value.codigo
        is CodigoError.CORRECCION_IMPROCEDENTE_ES_REALIDAD_NUEVA
    )


@pytest.mark.parametrize("campo", ["id", "owner_user_id", "row_version", "created_at"])
def test_campos_inmutables_rechazados(campo) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        CamposCorreccion.desde_dict({campo: uuid.uuid4()})
    assert excinfo.value.codigo is CodigoError.CAMPO_INMUTABLE


def test_campo_desconocido_rechazado() -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        CamposCorreccion.desde_dict({"campo_inventado": 1})
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_correccion_vacia_rechazada(
    servicio: HechosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            campos=CamposCorreccion(),
            motivo="sin campos",
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


# ------------------------------------------------------------------
# Optimistic locking
# ------------------------------------------------------------------

def test_row_version_desfasada(
    servicio: HechosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(concepto="primera"),
        motivo="primera correccion",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            campos=CamposCorreccion(concepto="segunda"),
            motivo="segunda correccion",
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_dos_correcciones_sobre_la_misma_version_solo_una_gana(
    servicio: HechosService, owner: uuid.UUID, hecho
) -> None:
    """Equivalente determinista de dos editores concurrentes."""
    hecho_id, version = hecho
    a = ContextoOperacion.de_usuario(owner)
    b = ContextoOperacion.de_usuario(owner)

    servicio.corregir_hecho(
        contexto=a,
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(concepto="editor A"),
        motivo="A corrige",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            contexto=b,
            hecho_id=hecho_id,
            row_version_esperada=version,
            campos=CamposCorreccion(concepto="editor B"),
            motivo="B corrige",
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_repeticion_exacta_del_mismo_request_es_idempotente(
    servicio: HechosService, owner: uuid.UUID, admin: psycopg.Connection, hecho
) -> None:
    hecho_id, version = hecho
    ctx = ContextoOperacion.de_usuario(owner)

    primero = servicio.corregir_hecho(
        contexto=ctx,
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(concepto="corregido"),
        motivo="error de captura",
    )
    segundo = servicio.corregir_hecho(
        contexto=ctx,
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(concepto="corregido"),
        motivo="error de captura",
    )

    assert primero.idempotente is False
    assert segundo.idempotente is True
    assert segundo.row_version == primero.row_version

    fila = leer_fila(
        admin,
        owner,
        "SELECT count(*) FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ACTUALIZAR'",
        (hecho_id,),
    )
    assert fila == (1,)


def test_version_consumida_con_otro_request_no_es_idempotente(
    servicio: HechosService, owner: uuid.UUID, hecho
) -> None:
    """row_version NO es clave de idempotencia (enmienda de F04-00-C)."""
    hecho_id, version = hecho
    servicio.corregir_hecho(
        contexto=ContextoOperacion.de_usuario(owner),
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(concepto="corregido"),
        motivo="error de captura",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            contexto=ContextoOperacion.de_usuario(owner),
            hecho_id=hecho_id,
            row_version_esperada=version,
            campos=CamposCorreccion(concepto="corregido"),
            motivo="error de captura",
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


# ------------------------------------------------------------------
# Estado, tenant y tipo de hecho
# ------------------------------------------------------------------

def test_hecho_inexistente(
    servicio: HechosService, contexto: ContextoOperacion
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            contexto,
            hecho_id=uuid.uuid4(),
            row_version_esperada=1,
            campos=CamposCorreccion(concepto="x"),
            motivo="motivo",
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_aislamiento_tenant_en_correccion(
    servicio: HechosService, otro_owner: uuid.UUID, hecho
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            ContextoOperacion.de_usuario(otro_owner),
            hecho_id=hecho_id,
            row_version_esperada=version,
            campos=CamposCorreccion(concepto="ajeno"),
            motivo="intento cross-tenant",
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


def test_hecho_anulado_no_admite_correccion(
    servicio: HechosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    anulado = servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        motivo_anulacion="nunca debio existir",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=anulado.row_version,
            campos=CamposCorreccion(concepto="x"),
            motivo="motivo",
        )
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO


def test_tipo_hecho_es_corregible_sin_efectos_dependientes(
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    hecho,
) -> None:
    """F04-01 NO declara tipo_hecho_id globalmente inmutable."""
    hecho_id, version = hecho
    fila = leer_fila(
        admin, contexto.owner_user_id,
        "SELECT id FROM gapto.tipos_hecho WHERE codigo = 'INGRESO'", (),
    )
    tipo_ingreso = fila[0]

    resultado = servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(tipo_hecho_id=tipo_ingreso),
        motivo="se selecciono el arquetipo equivocado al capturar",
    )
    assert resultado.snapshot["tipo_hecho_id"] == str(tipo_ingreso)


def test_tipo_hecho_inexistente_en_correccion(
    servicio: HechosService, contexto: ContextoOperacion, hecho
) -> None:
    hecho_id, version = hecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            campos=CamposCorreccion(tipo_hecho_id=uuid.uuid4()),
            motivo="motivo",
        )
    assert excinfo.value.codigo is CodigoError.TIPO_HECHO_DESCONOCIDO


# ------------------------------------------------------------------
# Atomicidad
# ------------------------------------------------------------------

def test_rollback_completo_si_falla_la_auditoria_de_correccion(
    unidad, contexto: ContextoOperacion, admin: psycopg.Connection, hecho
) -> None:
    hecho_id, version = hecho

    def operacion(sesion):
        repo.exigir_contexto(sesion)
        repo.actualizar_campos(
            sesion, hecho_id, version, {"concepto": "no debe persistir"}
        )
        auditoria.registrar(
            sesion,
            tabla=repo.TABLA,
            registro_id=hecho_id,
            accion=auditoria.ACCION_ACTUALIZAR,
            datos_despues_json='{"api_key": "x"}',
        )

    with pytest.raises(ErrorMotor):
        unidad.ejecutar(contexto, operacion, nombre="prueba-rollback-op02")

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT concepto, row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == ("concepto mal capturado", version)


def test_la_guarda_sql_de_row_version_protege_la_carrera_real(
    unidad, contexto: ContextoOperacion, admin: psycopg.Connection, hecho
) -> None:
    """Interleaving real entre la lectura y el UPDATE.

    La comprobacion en Python de `row_version` NO basta: entre leer y escribir
    cabe otra transaccion. Quien impide la perdida de actualizacion es la
    clausula `AND h.row_version = %s` del propio UPDATE. Este test intercala
    una escritura ajena YA CONFIRMADA entre ambos pasos y exige que el UPDATE
    no case ninguna fila. Sin esa clausula el test falla: es su mutante.
    """
    hecho_id, version = hecho
    interferido: dict = {}

    def operacion(sesion):
        repo.exigir_contexto(sesion)
        actual = repo.leer_estado(sesion, hecho_id)
        assert actual is not None and actual[0] == version

        # Otra transaccion, ya confirmada, mueve la fila mientras la nuestra
        # sigue abierta.
        with admin.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("SET ROLE gapto_owner")
            try:
                cursor.execute(
                    "SELECT set_config('gapto.owner_user_id', %s, false)",
                    (str(contexto.owner_user_id),),
                )
                cursor.execute(
                    "UPDATE gapto.hechos_financieros "
                    "SET notas = 'ajena', row_version = row_version + 1 "
                    "WHERE id = %s",
                    (hecho_id,),
                )
            finally:
                cursor.execute("RESET ROLE")
                cursor.execute("RESET ALL")

        interferido["resultado"] = repo.actualizar_campos(
            sesion, hecho_id, version, {"concepto": "no debe ganar"}
        )

    unidad.ejecutar(contexto, operacion, nombre="prueba-carrera")

    assert interferido["resultado"] is None

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT concepto, notas, row_version "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    assert fila == ("concepto mal capturado", "ajena", version + 1)
