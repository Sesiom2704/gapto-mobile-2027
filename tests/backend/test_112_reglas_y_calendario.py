# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_112_reglas_y_calendario.py
# Ruta: tests/backend/test_112_reglas_y_calendario.py
# Descripcion: F04-05. Reglas, versionado, pausa, excepciones y generacion
#   CALENDARIO. Incluye el caso canonico C-02 y el recalculo tras nueva
#   version.
#
#   La invariante que vigila casi toda esta suite es la inmutabilidad de
#   `fecha_objetivo_regla`: ni un override, ni un recalculo, ni una version
#   nueva pueden moverla. Es lo que permite reconocer la misma ocurrencia a lo
#   largo del tiempo.
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
from app.core.modelos_prevision import (
    ABIERTA,
    CALENDARIO,
    CANCELADA,
    Cadencia,
    DatosExcepcion,
    DatosPrevisionManual,
    DatosRegla,
    DatosVersionRegla,
    DatosVinculo,
    MENSUAL,
    RODANTE,
)
from app.services.hechos_service import HechosService
from app.services.previsiones_service import PrevisionesService
from app.services.reglas_service import ReglasService
from conftest import leer_fila

D = decimal.Decimal
F = dt.date.fromisoformat
MENSUAL_1 = Cadencia(MENSUAL, 1, CALENDARIO)


def version(**extra) -> DatosVersionRegla:
    base = {
        "version_id": uuid.uuid4(),
        "vigente_desde": F("2027-01-10"),
        "vigente_hasta": None,
        "tipo_hecho_codigo": "GASTO",
        "flujo_tesoreria_esperado": "SALIDA",
        "moneda": "EUR",
        "fecha_modo": "ANCLA",
        "importe_modo": "FIJO",
        "presupuestable": True,
        "cadencia": MENSUAL_1,
        "importe_fijo": D("800.0000"),
    }
    base.update(extra)
    return DatosVersionRegla(**base)


@pytest.fixture()
def regla(servicio_reglas: ReglasService, contexto: ContextoOperacion):
    identificador = uuid.uuid4()
    primera = version()
    resultado = servicio_reglas.crear_regla(
        contexto, DatosRegla(regla_id=identificador, nombre="Alquiler"), primera
    )
    return identificador, primera, resultado


def mapa_mensual(anio: int, meses: range, dia: int = 10) -> dict[dt.date, uuid.UUID]:
    return {dt.date(anio, m, dia): uuid.uuid4() for m in meses}


# ==================================================================
# Reglas y versionado
# ==================================================================

def test_alta_de_regla_con_primera_version(
    servicio_reglas: ReglasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    identificador = uuid.uuid4()
    primera = version()
    resultado = servicio_reglas.crear_regla(
        contexto, DatosRegla(regla_id=identificador, nombre="Luz"), primera
    )
    assert resultado.regla_row_version == 1

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT r.nombre, v.periodicidad, v.intervalo, v.anclaje_recurrencia, "
        "v.importe_modo FROM gapto.reglas_financieras r "
        "JOIN gapto.regla_versiones v ON v.regla_id = r.id WHERE r.id = %s",
        (identificador,),
    )
    assert fila == ("Luz", "MENSUAL", 1, "CALENDARIO", "FIJO")


def test_una_regla_no_tiene_enabled(admin: psycopg.Connection) -> None:
    """Esta operativa cuando tiene version vigente; no hay flag de lifecycle."""
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'gapto' AND table_name = 'reglas_financieras' "
            "AND column_name = 'enabled'"
        )
        assert cursor.fetchone()[0] == 0


def test_alta_idempotente(
    servicio_reglas: ReglasService, contexto: ContextoOperacion
) -> None:
    identificador = uuid.uuid4()
    primera = version()
    datos = DatosRegla(regla_id=identificador, nombre="Luz")
    uno = servicio_reglas.crear_regla(contexto, datos, primera)
    dos = servicio_reglas.crear_regla(contexto, datos, primera)
    assert uno.idempotente is False
    assert dos.idempotente is True
    assert dos.regla_row_version == uno.regla_row_version


def test_versionado_cierra_y_abre(
    servicio_reglas: ReglasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    regla,
) -> None:
    identificador, primera, creada = regla
    segunda = version(vigente_desde=F("2027-07-01"), importe_fijo=D("900.0000"))
    resultado = servicio_reglas.crear_version(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version,
        version=segunda,
        cerrar_version_id=primera.version_id,
        cerrar_vigente_hasta=F("2027-06-30"),
    )
    assert resultado.regla_row_version == creada.regla_row_version + 1

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT vigente_hasta FROM gapto.regla_versiones WHERE id = %s",
        (primera.version_id,),
    )
    assert fila == (F("2027-06-30"),)


def test_solapamiento_rechazado(
    servicio_reglas: ReglasService, contexto, regla
) -> None:
    """La autoridad es el EXCLUDE fisico; aqui solo se traduce."""
    identificador, _, creada = regla
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_reglas.crear_version(
            contexto,
            regla_id=identificador,
            regla_row_version_esperada=creada.regla_row_version,
            version=version(vigente_desde=F("2027-03-01")),
        )
    assert excinfo.value.codigo is CodigoError.VERSION_REGLA_SOLAPADA


def test_cierre_el_mismo_dia_que_inicia_la_nueva_rechazado(
    servicio_reglas: ReglasService, contexto, regla
) -> None:
    """La vigencia es INCLUSIVA: ese dia lo gobernarian las dos."""
    identificador, primera, creada = regla
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_reglas.crear_version(
            contexto,
            regla_id=identificador,
            regla_row_version_esperada=creada.regla_row_version,
            version=version(vigente_desde=F("2027-07-01")),
            cerrar_version_id=primera.version_id,
            cerrar_vigente_hasta=F("2027-07-01"),
        )
    assert excinfo.value.codigo is CodigoError.VERSION_REGLA_SOLAPADA


def test_version_desfasada_en_configuracion(
    servicio_reglas: ReglasService, contexto, regla
) -> None:
    identificador, _, _ = regla
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_reglas.crear_version(
            contexto,
            regla_id=identificador,
            regla_row_version_esperada=99,
            version=version(vigente_desde=F("2027-07-01")),
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_regla_cross_tenant(
    servicio_reglas: ReglasService, otro_owner: uuid.UUID, regla
) -> None:
    identificador, _, creada = regla
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_reglas.crear_version(
            ContextoOperacion.de_usuario(otro_owner),
            regla_id=identificador,
            regla_row_version_esperada=creada.regla_row_version,
            version=version(vigente_desde=F("2027-07-01")),
        )
    assert excinfo.value.codigo is CodigoError.REGLA_NO_ENCONTRADA


@pytest.mark.parametrize(
    "extra, codigo",
    [
        ({"cadencia": Cadencia(MENSUAL, 1, None)}, CodigoError.CADENCIA_INVALIDA),
        ({"cadencia": Cadencia(None, None, CALENDARIO)}, CodigoError.CADENCIA_INVALIDA),
        ({"cadencia": Cadencia(MENSUAL, 0, CALENDARIO)}, CodigoError.CADENCIA_INVALIDA),
        ({"cadencia": Cadencia("QUINCENAL", 1, CALENDARIO)}, CodigoError.CADENCIA_INVALIDA),
        (
            {"cadencia": Cadencia(MENSUAL, 1, RODANTE), "fecha_modo": "VENTANA",
             "dia_desde": 1, "dia_hasta": 5},
            CodigoError.ANCLAJE_INVALIDO,
        ),
        ({"importe_fijo": None}, CodigoError.IMPORTE_NO_POSITIVO),
        ({"moneda": "eur"}, CodigoError.MONEDA_INVALIDA),
        ({"presupuestable": None}, CodigoError.ENTRADA_INVALIDA),
        ({"importe_modo": "SALDO_OBJETIVO", "importe_fijo": None}, CodigoError.ENTRADA_INVALIDA),
        ({"meses_historico": 0}, CodigoError.ENTRADA_INVALIDA),
    ],
)
def test_validacion_de_version(
    servicio_reglas: ReglasService, contexto, contraparte, extra, codigo
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_reglas.crear_regla(
            contexto,
            DatosRegla(regla_id=uuid.uuid4(), nombre="X"),
            version(**extra),
        )
    assert excinfo.value.codigo is codigo


def test_nombre_en_blanco_rechazado(
    servicio_reglas: ReglasService, contexto
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_reglas.crear_regla(
            contexto, DatosRegla(regla_id=uuid.uuid4(), nombre="   "), version()
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


# ==================================================================
# Excepciones
# ==================================================================

def test_excepcion_omitida(
    servicio_reglas: ReglasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    regla,
) -> None:
    identificador, _, creada = regla
    excepcion = DatosExcepcion(
        excepcion_id=uuid.uuid4(),
        fecha_objetivo=F("2027-04-10"),
        omitida=True,
        motivo="vacaciones",
    )
    servicio_reglas.registrar_excepcion(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version,
        excepcion=excepcion,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT omitida, motivo FROM gapto.regla_excepciones WHERE id = %s",
        (excepcion.excepcion_id,),
    )
    assert fila == (True, "vacaciones")


def test_omitida_con_overrides_rechazada(
    servicio_reglas: ReglasService, contexto, regla
) -> None:
    """Si la ocurrencia no va a existir, no hay nada que ajustar."""
    identificador, _, creada = regla
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_reglas.registrar_excepcion(
            contexto,
            regla_id=identificador,
            regla_row_version_esperada=creada.regla_row_version,
            excepcion=DatosExcepcion(
                excepcion_id=uuid.uuid4(),
                fecha_objetivo=F("2027-04-10"),
                omitida=True,
                importe_override=D("5.0000"),
            ),
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_excepcion_vacia_rechazada(
    servicio_reglas: ReglasService, contexto, regla
) -> None:
    identificador, _, creada = regla
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_reglas.registrar_excepcion(
            contexto,
            regla_id=identificador,
            regla_row_version_esperada=creada.regla_row_version,
            excepcion=DatosExcepcion(
                excepcion_id=uuid.uuid4(), fecha_objetivo=F("2027-04-10")
            ),
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_una_sola_excepcion_por_identidad(
    servicio_reglas: ReglasService, contexto, regla
) -> None:
    identificador, _, creada = regla
    primera = DatosExcepcion(
        excepcion_id=uuid.uuid4(), fecha_objetivo=F("2027-04-10"), omitida=True
    )
    servicio_reglas.registrar_excepcion(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version,
        excepcion=primera,
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_reglas.registrar_excepcion(
            contexto,
            regla_id=identificador,
            regla_row_version_esperada=creada.regla_row_version + 1,
            excepcion=DatosExcepcion(
                excepcion_id=uuid.uuid4(),
                fecha_objetivo=F("2027-04-10"),
                omitida=True,
            ),
        )
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO


def test_correccion_de_excepcion_auditada(
    servicio_reglas: ReglasService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    regla,
) -> None:
    identificador, _, creada = regla
    excepcion = DatosExcepcion(
        excepcion_id=uuid.uuid4(), fecha_objetivo=F("2027-04-10"), omitida=True
    )
    servicio_reglas.registrar_excepcion(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version,
        excepcion=excepcion,
    )
    servicio_reglas.corregir_excepcion(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version + 1,
        excepcion_id=excepcion.excepcion_id,
        cambios={"omitida": False, "importe_override": D("120.0000")},
        motivo="al final si toca",
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT accion, datos_antes->>'omitida', datos_despues->>'omitida', motivo "
        "FROM gapto.auditoria WHERE registro_id = %s AND accion = 'ACTUALIZAR'",
        (excepcion.excepcion_id,),
    )
    assert fila == ("ACTUALIZAR", "true", "false", "al final si toca")


# ==================================================================
# Generacion CALENDARIO
# ==================================================================

def test_generacion_con_horizonte_por_fecha(
    servicio_previsiones: PrevisionesService, contexto, regla
) -> None:
    identificador, _, _ = regla
    mapa = mapa_mensual(2027, range(1, 5))
    resultado = servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-04-30"),
    )
    assert resultado.total_creadas == 4


def test_repetir_la_generacion_no_duplica(
    servicio_previsiones: PrevisionesService, contexto, regla
) -> None:
    identificador, _, _ = regla
    mapa = mapa_mensual(2027, range(1, 5))
    primera = servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-04-30"),
    )
    segunda = servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-04-30"),
    )
    assert primera.total_creadas == 4
    assert segunda.total_creadas == 0
    assert len(segunda.existentes) == 4


def test_la_generacion_exige_horizonte_finito(
    servicio_previsiones: PrevisionesService, contexto, regla
) -> None:
    identificador, _, _ = regla
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.generar_calendario(
            contexto, regla_id=identificador, uuids_por_objetivo={}
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_identidad_canonica_persistida(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    regla,
) -> None:
    identificador, _, _ = regla
    mapa = mapa_mensual(2027, range(1, 3))
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-02-28"),
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT fecha_objetivo_regla, estado, recalculo_automatico "
        "FROM gapto.previsiones WHERE id = %s",
        (mapa[F("2027-02-10")],),
    )
    assert fila == (F("2027-02-10"), ABIERTA, True)


def test_una_excepcion_omitida_no_materializa(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    regla,
) -> None:
    identificador, _, creada = regla
    servicio_reglas.registrar_excepcion(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version,
        excepcion=DatosExcepcion(
            excepcion_id=uuid.uuid4(), fecha_objetivo=F("2027-03-10"), omitida=True
        ),
    )
    mapa = mapa_mensual(2027, range(1, 5))
    resultado = servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-04-30"),
    )
    assert resultado.total_creadas == 3
    assert F("2027-03-10") in resultado.omitidas_por_excepcion
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.previsiones WHERE id = %s",
        (mapa[F("2027-03-10")],),
    )
    assert fila == (0,)


def test_override_de_fecha_no_mueve_el_objetivo(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    regla,
) -> None:
    """La ventana se desplaza; la identidad canonica NO."""
    identificador, _, creada = regla
    servicio_reglas.registrar_excepcion(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version,
        excepcion=DatosExcepcion(
            excepcion_id=uuid.uuid4(),
            fecha_objetivo=F("2027-02-10"),
            fecha_override=F("2027-02-22"),
        ),
    )
    mapa = mapa_mensual(2027, range(1, 3))
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-02-28"),
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT fecha_objetivo_regla, fecha_esperada_desde, fecha_esperada_hasta "
        "FROM gapto.previsiones WHERE id = %s",
        (mapa[F("2027-02-10")],),
    )
    assert fila == (F("2027-02-10"), F("2027-02-22"), F("2027-02-22"))


def test_override_de_importe_no_toca_las_demas(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    regla,
) -> None:
    identificador, _, creada = regla
    servicio_reglas.registrar_excepcion(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version,
        excepcion=DatosExcepcion(
            excepcion_id=uuid.uuid4(),
            fecha_objetivo=F("2027-02-10"),
            importe_override=D("111.0000"),
        ),
    )
    mapa = mapa_mensual(2027, range(1, 4))
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-03-31"),
    )
    assert servicio_previsiones.estado_de(
        contexto, mapa[F("2027-02-10")]
    ).importe_esperado == D("111.0000")
    assert servicio_previsiones.estado_de(
        contexto, mapa[F("2027-03-10")]
    ).importe_esperado == D("800.0000")


def test_una_pausa_no_genera_ni_acumula(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    regla,
) -> None:
    """Un hueco sin version no produce ocurrencias y no crea backlog.

    Y la reanudacion REINICIA el calendario en `vigente_desde`: la pausa rompe
    el segmento, de modo que el segmento nuevo genera el dia 1 de cada mes y no
    el dia 10 heredado. No se recuperan abril ni mayo, y tampoco se arrastra el
    ancla anterior.
    """
    identificador, primera, creada = regla
    # Se cierra en marzo y se reanuda en junio: abril y mayo quedan en pausa.
    servicio_reglas.crear_version(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version,
        version=version(vigente_desde=F("2027-06-01")),
        cerrar_version_id=primera.version_id,
        cerrar_vigente_hasta=F("2027-03-31"),
    )
    mapa = {
        **mapa_mensual(2027, range(1, 4)),
        F("2027-06-01"): uuid.uuid4(),
        F("2027-07-01"): uuid.uuid4(),
    }
    resultado = servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-07-31"),
    )
    creadas = {f for f, identidad in mapa.items() if identidad in resultado.creadas}
    # Enero a marzo del primer segmento.
    assert {F("2027-01-10"), F("2027-02-10"), F("2027-03-10")} <= creadas
    # Abril y mayo no existen en ningun segmento: la pausa no acumula.
    assert F("2027-04-10") not in creadas
    assert F("2027-05-10") not in creadas
    # El segmento reanudado empieza limpio en su propia fecha de vigencia.
    assert {F("2027-06-01"), F("2027-07-01")} <= creadas


def test_una_identidad_cancelada_no_se_regenera(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    regla,
) -> None:
    """Tombstone permanente: ni un retry la resucita."""
    identificador, _, _ = regla
    mapa = mapa_mensual(2027, range(1, 3))
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-02-28"),
    )
    objetivo = mapa[F("2027-02-10")]
    estado = servicio_previsiones.estado_de(contexto, objetivo)
    servicio_previsiones.cancelar(
        contexto,
        prevision_id=objetivo,
        row_version_esperada=estado.row_version,
        motivo="no aplica",
    )
    # Nueva generacion con OTRO uuid reservado para la misma identidad.
    nuevo = dict(mapa)
    nuevo[F("2027-02-10")] = uuid.uuid4()
    resultado = servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=nuevo,
        hasta_fecha=F("2027-02-28"),
    )
    assert nuevo[F("2027-02-10")] not in resultado.creadas
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.previsiones WHERE id = %s",
        (nuevo[F("2027-02-10")],),
    )
    assert fila == (0,)


def test_el_uuid_no_elude_una_identidad_ya_consumida(
    servicio_previsiones: PrevisionesService, contexto, regla
) -> None:
    """Si la identidad existe, se devuelve la existente aunque el llamante
    traiga otro UUID reservado."""
    identificador, _, _ = regla
    mapa = mapa_mensual(2027, range(1, 2))
    primera = servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-01-31"),
    )
    otro = {F("2027-01-10"): uuid.uuid4()}
    segunda = servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=otro,
        hasta_fecha=F("2027-01-31"),
    )
    assert segunda.total_creadas == 0
    assert segunda.existentes == primera.creadas


def test_regla_inexistente(
    servicio_previsiones: PrevisionesService, contexto
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.generar_calendario(
            contexto,
            regla_id=uuid.uuid4(),
            uuids_por_objetivo={},
            hasta_fecha=F("2027-12-31"),
        )
    assert excinfo.value.codigo is CodigoError.REGLA_NO_ENCONTRADA


def test_generacion_cross_tenant(
    servicio_previsiones: PrevisionesService, otro_owner: uuid.UUID, regla
) -> None:
    identificador, _, _ = regla
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.generar_calendario(
            ContextoOperacion.de_usuario(otro_owner),
            regla_id=identificador,
            uuids_por_objetivo={},
            hasta_fecha=F("2027-12-31"),
        )
    assert excinfo.value.codigo is CodigoError.REGLA_NO_ENCONTRADA


# ==================================================================
# Previsión manual
# ==================================================================

def manual(**extra) -> DatosPrevisionManual:
    base = {
        "prevision_id": uuid.uuid4(),
        "concepto": "Regalo puntual",
        "tipo_hecho_codigo": "GASTO",
        "fecha_esperada_desde": F("2027-05-01"),
        "fecha_esperada_hasta": F("2027-05-31"),
        "flujo_tesoreria_esperado": "SALIDA",
        "moneda": "EUR",
        "presupuestable": True,
        "importe_esperado": D("50.0000"),
    }
    base.update(extra)
    return DatosPrevisionManual(**base)


def test_prevision_manual_sin_regla(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    datos = manual()
    resultado = servicio_previsiones.crear_manual(contexto, datos)
    assert resultado.estado == ABIERTA
    assert resultado.recalculo_automatico is False

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT regla_version_id, fecha_objetivo_regla, recalculo_automatico "
        "FROM gapto.previsiones WHERE id = %s",
        (datos.prevision_id,),
    )
    assert fila == (None, None, False)


def test_importe_desconocido_es_null_no_cero(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    datos = manual(importe_esperado=None)
    servicio_previsiones.crear_manual(contexto, datos)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_esperado FROM gapto.previsiones WHERE id = %s",
        (datos.prevision_id,),
    )
    assert fila == (None,)


def test_importe_cero_rechazado(
    servicio_previsiones: PrevisionesService, contexto
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.crear_manual(contexto, manual(importe_esperado=D("0")))
    assert excinfo.value.codigo is CodigoError.IMPORTE_NO_POSITIVO


def test_ventana_invertida_rechazada(
    servicio_previsiones: PrevisionesService, contexto
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.crear_manual(
            contexto,
            manual(
                fecha_esperada_desde=F("2027-05-31"),
                fecha_esperada_hasta=F("2027-05-01"),
            ),
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_manual_idempotente(
    servicio_previsiones: PrevisionesService, contexto
) -> None:
    datos = manual()
    uno = servicio_previsiones.crear_manual(contexto, datos)
    dos = servicio_previsiones.crear_manual(contexto, datos)
    assert uno.idempotente is False
    assert dos.idempotente is True
    assert dos.row_version == uno.row_version


# ==================================================================
# C-02 — ALQUILER CON SUBIDA
# ==================================================================

def test_c02_alquiler_con_subida(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    servicio: HechosService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    regla,
) -> None:
    """800 mensual, subida a 900 desde julio.

    Lo que exige el caso: las futuras recalculables se regobiernan, las
    congeladas por realidad se respetan, el pasado no se reescribe y ninguna
    `fecha_objetivo_regla` se mueve.
    """
    identificador, primera, creada = regla
    mapa = mapa_mensual(2027, range(1, 13))
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-12-31"),
    )

    # Agosto recibe realidad: su expectativa queda congelada.
    agosto = mapa[F("2027-08-10")]
    estado = servicio_previsiones.estado_de(contexto, agosto)
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=F("2027-08-11"),
            moneda="EUR",
            presupuestable=True,
            estado_localizacion="NO_APLICA",
            tipo_hecho_codigo="GASTO",
            importe_total=D("800.0000"),
        ),
    )
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=agosto,
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=uuid.uuid4(),
            hecho_id=hecho_id,
            importe_asignado=D("800.0000"),
        ),
    )

    servicio_reglas.crear_version(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version,
        version=version(vigente_desde=F("2027-07-01"), importe_fijo=D("900.0000")),
        cerrar_version_id=primera.version_id,
        cerrar_vigente_hasta=F("2027-06-30"),
    )

    resultado = servicio_previsiones.recalcular_futuras(
        contexto,
        regla_id=identificador,
        desde_fecha=F("2027-07-01"),
        motivo="subida de alquiler",
    )

    # Julio, septiembre, octubre, noviembre y diciembre.
    assert len(resultado.regobernadas) == 5
    assert len(resultado.congeladas_respetadas) == 1
    assert resultado.canceladas_fuera_de_segmento == ()
    assert resultado.requieren_revision == ()

    assert servicio_previsiones.estado_de(
        contexto, mapa[F("2027-07-10")]
    ).importe_esperado == D("900.0000")
    # Congelada por realidad.
    assert servicio_previsiones.estado_de(
        contexto, agosto
    ).importe_esperado == D("800.0000")
    # El pasado no se reescribe.
    assert servicio_previsiones.estado_de(
        contexto, mapa[F("2027-06-10")]
    ).importe_esperado == D("800.0000")

    # Ninguna identidad se ha movido.
    for objetivo, identidad in mapa.items():
        fila = leer_fila(
            admin,
            contexto.owner_user_id,
            "SELECT fecha_objetivo_regla FROM gapto.previsiones WHERE id = %s",
            (identidad,),
        )
        assert fila == (objetivo,)


def test_cambio_de_cadencia_cancela_las_que_salen_del_segmento(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    regla,
) -> None:
    """Con intervalo 2, las identidades impares dejan de pertenecer.

    No se borran ni se reescriben: se CANCELAN explicitamente.
    """
    identificador, primera, creada = regla
    mapa = mapa_mensual(2027, range(1, 7))
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-06-30"),
    )
    servicio_reglas.crear_version(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version,
        version=version(
            vigente_desde=F("2027-03-01"),
            cadencia=Cadencia(MENSUAL, 2, CALENDARIO),
        ),
        cerrar_version_id=primera.version_id,
        cerrar_vigente_hasta=F("2027-02-28"),
    )
    resultado = servicio_previsiones.recalcular_futuras(
        contexto, regla_id=identificador, desde_fecha=F("2027-03-01")
    )
    assert len(resultado.canceladas_fuera_de_segmento) >= 1
    for identidad in resultado.canceladas_fuera_de_segmento:
        assert servicio_previsiones.estado_de(contexto, identidad).estado == CANCELADA


def test_una_futura_con_realidad_fuera_de_segmento_exige_revision(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    servicio: HechosService,
    contexto: ContextoOperacion,
    regla,
) -> None:
    """No se cancela ni se regobierna: se senala. Cancelarla destruiria
    realidad registrada."""
    identificador, primera, creada = regla
    mapa = mapa_mensual(2027, range(1, 7))
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-06-30"),
    )
    abril = mapa[F("2027-04-10")]
    estado = servicio_previsiones.estado_de(contexto, abril)
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=F("2027-04-12"),
            moneda="EUR",
            presupuestable=True,
            estado_localizacion="NO_APLICA",
            tipo_hecho_codigo="GASTO",
        ),
    )
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=abril,
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=uuid.uuid4(),
            hecho_id=hecho_id,
            importe_asignado=D("800.0000"),
        ),
    )
    # Cadencia bimensual desde marzo: abril queda fuera de la serie.
    servicio_reglas.crear_version(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version,
        version=version(
            vigente_desde=F("2027-03-01"),
            cadencia=Cadencia(MENSUAL, 2, CALENDARIO),
        ),
        cerrar_version_id=primera.version_id,
        cerrar_vigente_hasta=F("2027-02-28"),
    )
    resultado = servicio_previsiones.recalcular_futuras(
        contexto, regla_id=identificador, desde_fecha=F("2027-03-01")
    )
    assert abril in resultado.requieren_revision
    assert abril not in resultado.canceladas_fuera_de_segmento
    assert servicio_previsiones.estado_de(contexto, abril).estado == ABIERTA


def test_el_recalculo_no_mueve_la_identidad_con_ventana(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Con fecha_modo=VENTANA, ventana y objetivo NO coinciden.

    En modo ANCLA la ventana es un punto y vale lo mismo que el objetivo, de
    modo que un recalculo que escribiese la ventana sobre la identidad pasaria
    desapercibido. Aqui la ventana es 05-15 y el objetivo es el dia 10: si el
    recalculo tocase `fecha_objetivo_regla`, la identidad se moveria al dia 5 y
    la ocurrencia dejaria de ser reconocible.
    """
    identificador = uuid.uuid4()
    primera = version(
        fecha_modo="VENTANA", dia_desde=5, dia_hasta=15, importe_fijo=D("800.0000")
    )
    creada = servicio_reglas.crear_regla(
        contexto, DatosRegla(regla_id=identificador, nombre="Con ventana"), primera
    )
    mapa = mapa_mensual(2027, range(1, 5))
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=identificador,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-04-30"),
    )
    # La ventana es 05-15 y el objetivo el dia 10: son distintos.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT fecha_objetivo_regla, fecha_esperada_desde "
        "FROM gapto.previsiones WHERE id = %s",
        (mapa[F("2027-02-10")],),
    ) == (F("2027-02-10"), F("2027-02-05"))

    servicio_reglas.crear_version(
        contexto,
        regla_id=identificador,
        regla_row_version_esperada=creada.regla_row_version,
        version=version(
            vigente_desde=F("2027-03-01"),
            fecha_modo="VENTANA",
            dia_desde=5,
            dia_hasta=15,
            importe_fijo=D("900.0000"),
        ),
        cerrar_version_id=primera.version_id,
        cerrar_vigente_hasta=F("2027-02-28"),
    )
    resultado = servicio_previsiones.recalcular_futuras(
        contexto, regla_id=identificador, desde_fecha=F("2027-03-01")
    )
    assert len(resultado.regobernadas) == 2

    for objetivo in (F("2027-03-10"), F("2027-04-10")):
        assert leer_fila(
            admin,
            contexto.owner_user_id,
            "SELECT fecha_objetivo_regla, fecha_esperada_desde, importe_esperado "
            "FROM gapto.previsiones WHERE id = %s",
            (mapa[objetivo],),
        ) == (objetivo, objetivo.replace(day=5), D("900.0000"))
