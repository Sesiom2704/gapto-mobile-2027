# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_113_rodante_y_materializacion.py
# Ruta: tests/backend/test_113_rodante_y_materializacion.py
# Descripcion: F04-05. Cadenas RODANTE, lifecycle, OP-17, AMB-009 (F04-D018),
#   parcialidad derivada (F04-D019), correccion de vinculos (F04-D021),
#   correccion de estado terminal (F04-D024), algoritmos historicos, C-22 e
#   interleavings.
#
#   El nucleo de esta suite es que NADA se infiere: ni la cabeza siguiente, ni
#   el estado, ni la equivalencia de moneda, ni el hecho que satisface una
#   previsión. Y que una realidad anulada deja de contar sin degradar el estado.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import threading
import uuid
from typing import Any

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
    DatosRegla,
    DatosVersionRegla,
    DatosVinculo,
    MENSUAL,
    OMITIDA,
    REALIZADA,
    REALIZADA_SIN_REALIDAD_ACTIVA,
    REQUIERE_REVISION,
    RODANTE,
    SEMANAL,
)
from app.services.hechos_service import HechosService
from app.services.previsiones_service import PrevisionesService
from app.services.reglas_service import ReglasService
from conftest import leer_fila

D = decimal.Decimal
F = dt.date.fromisoformat

GIMNASIO = Cadencia(SEMANAL, 5, RODANTE)


def version_rodante(**extra) -> DatosVersionRegla:
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
        "cadencia": GIMNASIO,
        "importe_fijo": D("45.0000"),
    }
    base.update(extra)
    return DatosVersionRegla(**base)


@pytest.fixture()
def cadena(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
):
    """Regla RODANTE de 5 semanas con su cabeza inicial en 10/01."""
    regla_id = uuid.uuid4()
    primera = version_rodante()
    creada = servicio_reglas.crear_regla(
        contexto, DatosRegla(regla_id=regla_id, nombre="Gimnasio"), primera
    )
    cabeza = uuid.uuid4()
    servicio_previsiones.generar_rodante(
        contexto, regla_id=regla_id, uuid_nuevo=cabeza
    )
    return {"regla_id": regla_id, "version": primera, "cabeza": cabeza, "regla": creada}


def with_apertura(
    contexto: ContextoOperacion, cuenta_id: uuid.UUID, apertura: decimal.Decimal
) -> None:
    """Fija `saldo_apertura` de la cuenta para ejercitar SALDO_OBJETIVO.

    Se monta desde fixture, bajo gapto_owner: F04-05 no gestiona el ciclo de
    vida de las cuentas y no debe inventarse una operacion para ello.
    """
    import psycopg as _pg

    with _pg.connect(_DSN_FIXTURE[0]) as conexion, conexion.cursor() as cursor:
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute(
            "SELECT set_config('gapto.owner_user_id', %s, true)",
            (str(contexto.owner_user_id),),
        )
        cursor.execute(
            "UPDATE gapto.cuentas SET saldo_apertura = %s, "
            "fecha_inicio_ledger = DATE '2027-01-01' WHERE id = %s",
            (apertura, cuenta_id),
        )
        conexion.commit()


_DSN_FIXTURE: list[str] = []


@pytest.fixture(autouse=True)
def _capturar_dsn(dsn: str) -> None:
    if not _DSN_FIXTURE:
        _DSN_FIXTURE.append(dsn)


def crear_hecho(
    servicio: HechosService,
    contexto: ContextoOperacion,
    fecha: dt.date,
    *,
    moneda: str = "EUR",
    importe: decimal.Decimal | None = None,
) -> uuid.UUID:
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=fecha,
            moneda=moneda,
            presupuestable=True,
            estado_localizacion="NO_APLICA",
            tipo_hecho_codigo="GASTO",
            importe_total=importe,
        ),
    )
    return hecho_id


def vincular(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    prevision_id: uuid.UUID,
    hecho_id: uuid.UUID,
    importe: str,
    *,
    realizar: bool = False,
    sucesor: uuid.UUID | None = None,
    equivalencia: bool = False,
) -> Any:
    estado = servicio_previsiones.estado_de(contexto, prevision_id)
    return servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=prevision_id,
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=uuid.uuid4(),
            hecho_id=hecho_id,
            importe_asignado=D(importe),
            marcar_realizada=realizar,
            equivalencia_declarada=equivalencia,
        ),
        uuid_sucesor=sucesor,
    )


# ==================================================================
# Cadena RODANTE
# ==================================================================

def test_cabeza_inicial_en_vigente_desde(
    servicio_previsiones: PrevisionesService, contexto, cadena
) -> None:
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    assert estado.fecha_objetivo_regla == F("2027-01-10")
    assert estado.estado == ABIERTA


def test_con_cabeza_abierta_no_nace_sucesor(
    servicio_previsiones: PrevisionesService, contexto, cadena
) -> None:
    """Anticiparlo materializaria una expectativa que todavia puede cambiar."""
    resultado = servicio_previsiones.generar_rodante(
        contexto, regla_id=cadena["regla_id"], uuid_nuevo=uuid.uuid4()
    )
    assert resultado.total_creadas == 0
    assert resultado.existentes == (cadena["cabeza"],)


def test_una_sola_cabeza_abierta_a_la_vez(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    for _ in range(3):
        servicio_previsiones.generar_rodante(
            contexto, regla_id=cadena["regla_id"], uuid_nuevo=uuid.uuid4()
        )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.previsiones p "
        "JOIN gapto.regla_versiones v ON v.id = p.regla_version_id "
        "WHERE v.regla_id = %s AND p.estado = 'ABIERTA'",
        (cadena["regla_id"],),
    )
    assert fila == (1,)


def test_vector_gimnasio_d126(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    """Objetivo 10/01, realidad 02/02, cadencia 5 semanas -> sucesor 09/03.

    El ancla es la fecha REAL, no el objetivo: eso es lo que distingue RODANTE
    de CALENDARIO.
    """
    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    sucesor = uuid.uuid4()
    vincular(
        servicio_previsiones,
        contexto,
        cadena["cabeza"],
        hecho_id,
        "50.0000",
        realizar=True,
        sucesor=sucesor,
    )
    assert servicio_previsiones.estado_de(
        contexto, sucesor
    ).fecha_objetivo_regla == F("2027-03-09")


def test_omitida_ancla_en_el_objetivo_no_en_un_override(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    """La omision avanza desde la identidad canonica.

    Es la invariante que en el helper puro no se podia discriminar, porque
    `fecha_override` no es parametro suyo. Aqui si existe: se registra un
    override de fecha sobre la ocurrencia y, al omitirla, el sucesor debe
    anclarse en 10/01 —objetivo— y no en 25/01 —override—.
    """
    servicio_reglas.registrar_excepcion(
        contexto,
        regla_id=cadena["regla_id"],
        regla_row_version_esperada=cadena["regla"].regla_row_version,
        excepcion=DatosExcepcion(
            excepcion_id=uuid.uuid4(),
            fecha_objetivo=F("2027-01-10"),
            fecha_override=F("2027-01-25"),
        ),
    )
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    sucesor = uuid.uuid4()
    servicio_previsiones.omitir(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        motivo="no fui",
        uuid_sucesor=sucesor,
    )
    # 10/01 + 5 semanas = 14/02. Desde el override seria 29/02, inexistente.
    assert servicio_previsiones.estado_de(
        contexto, sucesor
    ).fecha_objetivo_regla == F("2027-02-14")


def test_cancelada_no_genera_sucesor(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    servicio_previsiones.cancelar(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        motivo="me doy de baja",
    )
    resultado = servicio_previsiones.generar_rodante(
        contexto, regla_id=cadena["regla_id"], uuid_nuevo=uuid.uuid4()
    )
    assert resultado.total_creadas == 0
    assert F("2027-01-10") in resultado.canceladas_encontradas


def test_una_excepcion_omitida_consume_la_ocurrencia_y_la_cadena_avanza(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
) -> None:
    """La identidad omitida por excepcion no se materializa, y la siguiente
    candidata avanza desde el objetivo canonico."""
    regla_id = uuid.uuid4()
    primera = version_rodante()
    creada = servicio_reglas.crear_regla(
        contexto, DatosRegla(regla_id=regla_id, nombre="Gym"), primera
    )
    servicio_reglas.registrar_excepcion(
        contexto,
        regla_id=regla_id,
        regla_row_version_esperada=creada.regla_row_version,
        excepcion=DatosExcepcion(
            excepcion_id=uuid.uuid4(), fecha_objetivo=F("2027-01-10"), omitida=True
        ),
    )
    cabeza = uuid.uuid4()
    resultado = servicio_previsiones.generar_rodante(
        contexto, regla_id=regla_id, uuid_nuevo=cabeza
    )
    assert F("2027-01-10") in resultado.omitidas_por_excepcion
    assert servicio_previsiones.estado_de(
        contexto, cabeza
    ).fecha_objetivo_regla == F("2027-02-14")


def test_la_regla_no_rodante_no_genera_cadena(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
) -> None:
    regla_id = uuid.uuid4()
    servicio_reglas.crear_regla(
        contexto,
        DatosRegla(regla_id=regla_id, nombre="Calendario"),
        version_rodante(cadencia=Cadencia(MENSUAL, 1, CALENDARIO)),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.generar_rodante(
            contexto, regla_id=regla_id, uuid_nuevo=uuid.uuid4()
        )
    assert excinfo.value.codigo is CodigoError.ANCLAJE_INVALIDO


# ==================================================================
# OP-17 y parcialidad derivada (F04-D019)
# ==================================================================

def test_primer_vinculo_no_realiza_pero_congela(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    resultado = vincular(
        servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "20.0000"
    )
    assert resultado.estado == ABIERTA
    assert resultado.recalculo_automatico is False


def test_parcialidad_no_es_un_estado(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """Previsto 45, realizado 20: sigue ABIERTA. No hay PARCIAL persistido."""
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    vincular(servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "20.0000")
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado, importe_esperado FROM gapto.previsiones WHERE id = %s",
        (cadena["cabeza"],),
    )
    assert fila == (ABIERTA, D("45.0000"))


def test_realizada_exige_declaracion_explicita(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    vincular(servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "45.0000")
    assert (
        servicio_previsiones.estado_de(contexto, cadena["cabeza"]).estado == ABIERTA
    )


def test_desviacion_no_es_error(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    """Previsto 45, realidad 50: se registra la desviacion sin reescribir la
    expectativa."""
    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    resultado = vincular(
        servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "50.0000"
    )
    assert resultado.importe_esperado == D("45.0000")


def test_pareja_duplicada_rechazada(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    vincular(servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "20.0000")
    with pytest.raises(ErrorMotor) as excinfo:
        vincular(servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "5.0000")
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO


def test_hecho_anulado_no_es_realidad(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=fila[0],
        motivo_anulacion="capturado por error",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        vincular(servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "20.0000")
    assert excinfo.value.codigo is CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO


def test_multidivisa_sin_equivalencia_declarada(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    """No se consulta FX, no se inventa tipo y no se copia el nominal."""
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"), moneda="USD")
    with pytest.raises(ErrorMotor) as excinfo:
        vincular(servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "20.0000")
    assert excinfo.value.codigo is CodigoError.ASIGNACION_MULTIDIVISA_NO_DEMOSTRADA


def test_multidivisa_con_equivalencia_declarada(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"), moneda="USD")
    resultado = vincular(
        servicio_previsiones,
        contexto,
        cadena["cabeza"],
        hecho_id,
        "20.0000",
        equivalencia=True,
    )
    assert resultado.estado == ABIERTA


def test_no_se_autoelige_el_hecho(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """Importe y fecha coincidentes con lo esperado: aun asi no se vincula solo."""
    crear_hecho(servicio, contexto, F("2027-01-10"), importe=D("45.0000"))
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.prevision_hechos WHERE prevision_id = %s",
        (cadena["cabeza"],),
    )
    assert fila == (0,)


def test_retry_idempotente_de_op17(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    datos = DatosVinculo(
        vinculo_id=uuid.uuid4(), hecho_id=hecho_id, importe_asignado=D("20.0000")
    )
    primero = servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        datos=datos,
    )
    segundo = servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        datos=datos,
    )
    assert segundo.idempotente is True
    assert segundo.row_version == primero.row_version
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.prevision_hechos WHERE id = %s",
        (datos.vinculo_id,),
    )
    assert fila == (1,)


def test_no_se_crea_realidad_al_vincular(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """INV-16: OP-17 solo vincula. Cero efectos, movimientos o posiciones."""
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    vincular(servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "20.0000")
    for consulta in (
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
        "SELECT count(*) FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
    ):
        assert leer_fila(admin, contexto.owner_user_id, consulta, (hecho_id,)) == (0,)


# ==================================================================
# AMB-009 / F04-D018
# ==================================================================

def test_amb009_realizada_sin_realidad_activa(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """Conserva REALIZADA y se expone como REALIZADA_SIN_REALIDAD_ACTIVA.

    No pasa a ABIERTA, ni a OMITIDA, ni a CANCELADA.
    """
    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    vincular(
        servicio_previsiones,
        contexto,
        cadena["cabeza"],
        hecho_id,
        "45.0000",
        realizar=True,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=fila[0],
        motivo_anulacion="capturado por error",
    )
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    assert estado.estado == REALIZADA
    assert estado.estado_derivado == REALIZADA_SIN_REALIDAD_ACTIVA

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado FROM gapto.previsiones WHERE id = %s",
        (cadena["cabeza"],),
    )
    assert fila == (REALIZADA,)


def test_amb009_bloquea_la_cadena(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
    admin: psycopg.Connection,
) -> None:
    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    vincular(
        servicio_previsiones,
        contexto,
        cadena["cabeza"],
        hecho_id,
        "45.0000",
        realizar=True,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=fila[0],
        motivo_anulacion="error",
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.generar_rodante(
            contexto, regla_id=cadena["regla_id"], uuid_nuevo=uuid.uuid4()
        )
    assert excinfo.value.codigo is CodigoError.CABEZA_RODANTE_BLOQUEADA


def test_amb009_se_desbloquea_reasignando_el_vinculo(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """F04-D021: se reasigna al hecho correcto conservando el id del vinculo.

    Nunca se anula un hecho verdadero para arreglar una asociacion falsa.
    """
    falso = crear_hecho(servicio, contexto, F("2027-02-02"))
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    vinculo_id = uuid.uuid4()
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=vinculo_id,
            hecho_id=falso,
            importe_asignado=D("45.0000"),
            marcar_realizada=True,
        ),
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (falso,),
    )
    servicio.anular_hecho(
        contexto,
        hecho_id=falso,
        row_version_esperada=fila[0],
        motivo_anulacion="no era este",
    )
    assert (
        servicio_previsiones.estado_de(contexto, cadena["cabeza"]).estado_derivado
        == REALIZADA_SIN_REALIDAD_ACTIVA
    )

    correcto = crear_hecho(servicio, contexto, F("2027-02-03"))
    actual = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    servicio_previsiones.corregir_vinculo(
        contexto,
        vinculo_id=vinculo_id,
        versiones_esperadas={cadena["cabeza"]: actual.row_version},
        nuevo_hecho_id=correcto,
        motivo="hecho equivocado",
    )
    reparada = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    assert reparada.estado == REALIZADA
    assert reparada.estado_derivado is None

    # El vinculo conserva su identidad.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT hecho_id FROM gapto.prevision_hechos WHERE id = %s",
        (vinculo_id,),
    )
    assert fila == (correcto,)


# ==================================================================
# F04-D021 — correccion de vinculos
# ==================================================================

def test_d021_correccion_de_importe_conserva_identidad(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    vinculo_id = uuid.uuid4()
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=vinculo_id, hecho_id=hecho_id, importe_asignado=D("20.0000")
        ),
    )
    antes = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT created_at FROM gapto.prevision_hechos WHERE id = %s",
        (vinculo_id,),
    )
    actual = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    servicio_previsiones.corregir_vinculo(
        contexto,
        vinculo_id=vinculo_id,
        versiones_esperadas={cadena["cabeza"]: actual.row_version},
        nuevo_importe=D("30.0000"),
        motivo="importe mal capturado",
    )
    despues = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_asignado, created_at FROM gapto.prevision_hechos "
        "WHERE id = %s",
        (vinculo_id,),
    )
    assert despues[0] == D("30.0000")
    assert despues[1] == antes[0]


def test_d021_reasignacion_entre_previsiones(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """P1 -> P2 con las dos versiones exigidas y ambas raices incrementadas."""
    manual_id = uuid.uuid4()
    from app.core.modelos_prevision import DatosPrevisionManual

    servicio_previsiones.crear_manual(
        contexto,
        DatosPrevisionManual(
            prevision_id=manual_id,
            concepto="Destino",
            tipo_hecho_codigo="GASTO",
            fecha_esperada_desde=F("2027-01-01"),
            fecha_esperada_hasta=F("2027-01-31"),
            flujo_tesoreria_esperado="SALIDA",
            moneda="EUR",
            presupuestable=True,
            importe_esperado=D("45.0000"),
        ),
    )
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    vinculo_id = uuid.uuid4()
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=vinculo_id, hecho_id=hecho_id, importe_asignado=D("20.0000")
        ),
    )
    origen = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    destino = servicio_previsiones.estado_de(contexto, manual_id)
    servicio_previsiones.corregir_vinculo(
        contexto,
        vinculo_id=vinculo_id,
        versiones_esperadas={
            cadena["cabeza"]: origen.row_version,
            manual_id: destino.row_version,
        },
        nueva_prevision_id=manual_id,
        motivo="pertenecia a la otra previsión",
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT prevision_id FROM gapto.prevision_hechos WHERE id = %s",
        (vinculo_id,),
    )
    assert fila == (manual_id,)
    assert (
        servicio_previsiones.estado_de(contexto, cadena["cabeza"]).row_version
        == origen.row_version + 1
    )
    assert (
        servicio_previsiones.estado_de(contexto, manual_id).row_version
        == destino.row_version + 1
    )


def test_d021_reasignacion_exige_las_dos_versiones(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    from app.core.modelos_prevision import DatosPrevisionManual

    manual_id = uuid.uuid4()
    servicio_previsiones.crear_manual(
        contexto,
        DatosPrevisionManual(
            prevision_id=manual_id,
            concepto="Destino",
            tipo_hecho_codigo="GASTO",
            fecha_esperada_desde=F("2027-01-01"),
            fecha_esperada_hasta=F("2027-01-31"),
            flujo_tesoreria_esperado="SALIDA",
            moneda="EUR",
            presupuestable=True,
        ),
    )
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    vinculo_id = uuid.uuid4()
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=vinculo_id, hecho_id=hecho_id, importe_asignado=D("20.0000")
        ),
    )
    actual = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.corregir_vinculo(
            contexto,
            vinculo_id=vinculo_id,
            versiones_esperadas={cadena["cabeza"]: actual.row_version},
            nueva_prevision_id=manual_id,
        )
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_d021_retirada_de_vinculo_sin_sustituto(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """El hecho verdadero NO se anula: solo desaparece la asociacion."""
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    vinculo_id = uuid.uuid4()
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=vinculo_id, hecho_id=hecho_id, importe_asignado=D("20.0000")
        ),
    )
    actual = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    servicio_previsiones.retirar_vinculo(
        contexto,
        vinculo_id=vinculo_id,
        prevision_row_version_esperada=actual.row_version,
        motivo="nunca debio existir",
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.prevision_hechos WHERE id = %s",
        (vinculo_id,),
    ) == (0,)
    # El hecho sigue ACTIVO.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    ) == ("ACTIVO",)
    # Y la retirada queda auditada con el snapshot eliminado.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT accion, datos_antes->>'importe_asignado' FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ANULAR'",
        (vinculo_id,),
    ) == ("ANULAR", "20.0000")


def test_d021_no_se_puede_reasignar_a_una_cancelada(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    from app.core.modelos_prevision import DatosPrevisionManual

    destino_id = uuid.uuid4()
    servicio_previsiones.crear_manual(
        contexto,
        DatosPrevisionManual(
            prevision_id=destino_id,
            concepto="Destino",
            tipo_hecho_codigo="GASTO",
            fecha_esperada_desde=F("2027-01-01"),
            fecha_esperada_hasta=F("2027-01-31"),
            flujo_tesoreria_esperado="SALIDA",
            moneda="EUR",
            presupuestable=True,
        ),
    )
    estado_destino = servicio_previsiones.estado_de(contexto, destino_id)
    servicio_previsiones.cancelar(
        contexto,
        prevision_id=destino_id,
        row_version_esperada=estado_destino.row_version,
        motivo="no aplica",
    )
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    vinculo_id = uuid.uuid4()
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=vinculo_id, hecho_id=hecho_id, importe_asignado=D("20.0000")
        ),
    )
    actual = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    cancelada = servicio_previsiones.estado_de(contexto, destino_id)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.corregir_vinculo(
            contexto,
            vinculo_id=vinculo_id,
            versiones_esperadas={
                cadena["cabeza"]: actual.row_version,
                destino_id: cancelada.row_version,
            },
            nueva_prevision_id=destino_id,
        )
    assert excinfo.value.codigo is CodigoError.ESTADO_PREVISION_INCOMPATIBLE


def test_d022_omitida_con_realidad_requiere_revision(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    """La incoherencia se detecta por LECTURA, sin degradar el estado."""
    from app.core.modelos_prevision import DatosPrevisionManual

    destino_id = uuid.uuid4()
    servicio_previsiones.crear_manual(
        contexto,
        DatosPrevisionManual(
            prevision_id=destino_id,
            concepto="Destino",
            tipo_hecho_codigo="GASTO",
            fecha_esperada_desde=F("2027-01-01"),
            fecha_esperada_hasta=F("2027-01-31"),
            flujo_tesoreria_esperado="SALIDA",
            moneda="EUR",
            presupuestable=True,
        ),
    )
    estado_destino = servicio_previsiones.estado_de(contexto, destino_id)
    servicio_previsiones.omitir(
        contexto,
        prevision_id=destino_id,
        row_version_esperada=estado_destino.row_version,
        motivo="no toca",
    )
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    vinculo_id = uuid.uuid4()
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=vinculo_id, hecho_id=hecho_id, importe_asignado=D("20.0000")
        ),
    )
    # Reasignar a la OMITIDA se rechaza en el write-path.
    actual = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    omitida = servicio_previsiones.estado_de(contexto, destino_id)
    with pytest.raises(ErrorMotor):
        servicio_previsiones.corregir_vinculo(
            contexto,
            vinculo_id=vinculo_id,
            versiones_esperadas={
                cadena["cabeza"]: actual.row_version,
                destino_id: omitida.row_version,
            },
            nueva_prevision_id=destino_id,
        )
    assert servicio_previsiones.estado_de(contexto, destino_id).estado == OMITIDA


# ==================================================================
# Lifecycle
# ==================================================================

def test_omitir_exige_cero_realidad_activa(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    hecho_id = crear_hecho(servicio, contexto, F("2027-01-12"))
    vincular(servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "20.0000")
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.omitir(
            contexto,
            prevision_id=cadena["cabeza"],
            row_version_esperada=estado.row_version,
            motivo="no fui",
        )
    assert excinfo.value.codigo is CodigoError.ESTADO_PREVISION_INCOMPATIBLE


def test_una_terminal_no_admite_transicion_ordinaria(
    servicio_previsiones: PrevisionesService, contexto, cadena
) -> None:
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    servicio_previsiones.cancelar(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        motivo="baja",
    )
    actual = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.omitir(
            contexto,
            prevision_id=cadena["cabeza"],
            row_version_esperada=actual.row_version,
            motivo="tarde",
        )
    assert excinfo.value.codigo is CodigoError.ESTADO_PREVISION_INCOMPATIBLE


def test_version_desfasada_en_lifecycle(
    servicio_previsiones: PrevisionesService, contexto, cadena
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.cancelar(
            contexto,
            prevision_id=cadena["cabeza"],
            row_version_esperada=99,
            motivo="x",
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_prevision_cross_tenant(
    servicio_previsiones: PrevisionesService, otro_owner: uuid.UUID, cadena
) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.cancelar(
            ContextoOperacion.de_usuario(otro_owner),
            prevision_id=cadena["cabeza"],
            row_version_esperada=1,
            motivo="x",
        )
    assert excinfo.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO


# ==================================================================
# F04-D024 — correccion de estado terminal
# ==================================================================

def test_d024_realizada_a_abierta_cancela_el_sucesor(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    sucesor = uuid.uuid4()
    vincular(
        servicio_previsiones,
        contexto,
        cadena["cabeza"],
        hecho_id,
        "45.0000",
        realizar=True,
        sucesor=sucesor,
    )
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    estado_sucesor = servicio_previsiones.estado_de(contexto, sucesor)
    resultado = servicio_previsiones.corregir_estado_terminal(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        motivo="marcada por error",
        sucesor_row_version_esperada=estado_sucesor.row_version,
    )
    assert resultado.estado == ABIERTA
    assert resultado.recalculo_automatico is False
    assert servicio_previsiones.estado_de(contexto, sucesor).estado == CANCELADA


def test_d024_los_vinculos_se_conservan(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """Si el error fue marcar REALIZADA demasiado pronto, la realidad
    vinculada sigue siendo verdadera."""
    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    sucesor = uuid.uuid4()
    vincular(
        servicio_previsiones,
        contexto,
        cadena["cabeza"],
        hecho_id,
        "30.0000",
        realizar=True,
        sucesor=sucesor,
    )
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    estado_sucesor = servicio_previsiones.estado_de(contexto, sucesor)
    servicio_previsiones.corregir_estado_terminal(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        motivo="marcada por error",
        sucesor_row_version_esperada=estado_sucesor.row_version,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe_asignado) FROM gapto.prevision_hechos "
        "WHERE prevision_id = %s",
        (cadena["cabeza"],),
    )
    assert fila == (1, D("30.0000"))


def test_d024_cancelada_nunca_se_reabre(
    servicio_previsiones: PrevisionesService, contexto, cadena
) -> None:
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    servicio_previsiones.cancelar(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        motivo="baja",
    )
    actual = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.corregir_estado_terminal(
            contexto,
            prevision_id=cadena["cabeza"],
            row_version_esperada=actual.row_version,
            motivo="me equivoque",
        )
    assert excinfo.value.codigo is CodigoError.REAPERTURA_NO_PERMITIDA


def test_d024_sucesor_con_realidad_exige_revision(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    """Cancelar un sucesor con realidad destruiria algo verdadero."""
    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    sucesor = uuid.uuid4()
    vincular(
        servicio_previsiones,
        contexto,
        cadena["cabeza"],
        hecho_id,
        "45.0000",
        realizar=True,
        sucesor=sucesor,
    )
    otro = crear_hecho(servicio, contexto, F("2027-03-10"))
    vincular(servicio_previsiones, contexto, sucesor, otro, "45.0000")
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    estado_sucesor = servicio_previsiones.estado_de(contexto, sucesor)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.corregir_estado_terminal(
            contexto,
            prevision_id=cadena["cabeza"],
            row_version_esperada=estado.row_version,
            motivo="x",
            sucesor_row_version_esperada=estado_sucesor.row_version,
        )
    assert excinfo.value.codigo is CodigoError.REVISION_DERIVADA_REQUERIDA


def test_d024_exige_motivo(
    servicio_previsiones: PrevisionesService, contexto, cadena
) -> None:
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    servicio_previsiones.omitir(
        contexto,
        prevision_id=cadena["cabeza"],
        row_version_esperada=estado.row_version,
        motivo="no fui",
    )
    actual = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.corregir_estado_terminal(
            contexto,
            prevision_id=cadena["cabeza"],
            row_version_esperada=actual.row_version,
            motivo="   ",
        )
    assert excinfo.value.codigo is CodigoError.MOTIVO_AUSENTE


def test_d024_abierta_no_tiene_nada_que_corregir(
    servicio_previsiones: PrevisionesService, contexto, cadena
) -> None:
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.corregir_estado_terminal(
            contexto,
            prevision_id=cadena["cabeza"],
            row_version_esperada=estado.row_version,
            motivo="x",
        )
    assert excinfo.value.codigo is CodigoError.ESTADO_PREVISION_INCOMPATIBLE


# ==================================================================
# C-22 — GIMNASIO RODANTE COMPLETO
# ==================================================================

def test_c22_gimnasio_rodante(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """Cadena de tres eslabones con desviacion y anclaje en realidad.

    Objetivo 10/01 -> realidad 02/02 (50,00) -> sucesor 09/03 -> realidad
    15/03 (45,00) -> sucesor 19/04. Cada ancla es la fecha REAL anterior, y
    ninguna identidad se mueve despues de nacer.
    """
    primero = cadena["cabeza"]
    h1 = crear_hecho(servicio, contexto, F("2027-02-02"))
    segundo = uuid.uuid4()
    vincular(
        servicio_previsiones, contexto, primero, h1, "50.0000",
        realizar=True, sucesor=segundo,
    )
    assert servicio_previsiones.estado_de(
        contexto, segundo
    ).fecha_objetivo_regla == F("2027-03-09")

    h2 = crear_hecho(servicio, contexto, F("2027-03-15"))
    tercero = uuid.uuid4()
    vincular(
        servicio_previsiones, contexto, segundo, h2, "45.0000",
        realizar=True, sucesor=tercero,
    )
    # 15/03 + 5 semanas = 19/04.
    assert servicio_previsiones.estado_de(
        contexto, tercero
    ).fecha_objetivo_regla == F("2027-04-19")

    # Exactamente una cabeza abierta y dos realizadas.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FILTER (WHERE p.estado = 'ABIERTA'), "
        "       count(*) FILTER (WHERE p.estado = 'REALIZADA') "
        "  FROM gapto.previsiones p "
        "  JOIN gapto.regla_versiones v ON v.id = p.regla_version_id "
        " WHERE v.regla_id = %s",
        (cadena["regla_id"],),
    )
    assert fila == (1, 2)

    # Las identidades no se han movido pese a las desviaciones.
    for identidad, objetivo in (
        (primero, F("2027-01-10")),
        (segundo, F("2027-03-09")),
        (tercero, F("2027-04-19")),
    ):
        assert leer_fila(
            admin,
            contexto.owner_user_id,
            "SELECT fecha_objetivo_regla FROM gapto.previsiones WHERE id = %s",
            (identidad,),
        ) == (objetivo,)


# ==================================================================
# Algoritmos historicos
# ==================================================================

def test_media_historica_sobre_ocurrencias_de_la_misma_regla(
    servicio: HechosService,
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
) -> None:
    """La fuente son ocurrencias anteriores de LA MISMA regla, y el importe
    real es la suma de `importe_asignado`, no `importe_total` del hecho."""
    regla_id = uuid.uuid4()
    primera = version_rodante(
        cadencia=Cadencia(MENSUAL, 1, CALENDARIO),
        importe_modo="MEDIA_HISTORICA",
        importe_fijo=None,
    )
    servicio_reglas.crear_regla(
        contexto, DatosRegla(regla_id=regla_id, nombre="Luz variable"), primera
    )
    mapa = {dt.date(2027, m, 10): uuid.uuid4() for m in range(1, 5)}
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=regla_id,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-04-30"),
    )
    # Sin historico, la primera queda en NULL: desconocido, no cero.
    assert (
        servicio_previsiones.estado_de(contexto, mapa[F("2027-01-10")]).importe_esperado
        is None
    )

    # Se realizan enero (60) y febrero (80). El hecho lleva otro importe_total
    # a proposito: lo que cuenta es el importe asignado.
    for objetivo, asignado in ((F("2027-01-10"), "60.0000"), (F("2027-02-10"), "80.0000")):
        hecho_id = crear_hecho(
            servicio, contexto, objetivo, importe=D("999.0000")
        )
        vincular(
            servicio_previsiones, contexto, mapa[objetivo], hecho_id, asignado,
            realizar=True,
        )

    resultado = servicio_previsiones.recalcular_futuras(
        contexto, regla_id=regla_id, desde_fecha=F("2027-03-01")
    )
    assert len(resultado.regobernadas) == 2
    assert servicio_previsiones.estado_de(
        contexto, mapa[F("2027-03-10")]
    ).importe_esperado == D("70")


# ==================================================================
# Interleavings
# ==================================================================

def _competir(objetivo, veces: int = 2) -> list[Any]:
    barrera = threading.Barrier(veces)
    resultados: list[Any] = []
    cerrojo = threading.Lock()

    def correr(indice: int) -> None:
        barrera.wait()
        try:
            objetivo(indice)
            salida: Any = "OK"
        except ErrorMotor as error:
            salida = error.codigo
        with cerrojo:
            resultados.append(salida)

    hilos = [threading.Thread(target=correr, args=(i,)) for i in range(veces)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)
    return resultados


def test_c1_dos_generaciones_rodantes_concurrentes(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """No hay UNIQUE fisico: la unica defensa es el lock de regla.

    Las dos generaciones ven la misma cabeza ABIERTA y ninguna crea sucesor;
    lo que NO puede pasar es que nazcan dos cabezas.
    """
    identificadores = [uuid.uuid4(), uuid.uuid4()]

    def intentar(indice: int) -> None:
        servicio_previsiones.generar_rodante(
            ContextoOperacion.de_usuario(contexto.owner_user_id),
            regla_id=cadena["regla_id"],
            uuid_nuevo=identificadores[indice],
        )

    resultados = _competir(intentar)
    assert resultados.count("OK") == 2, resultados
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.previsiones p "
        "JOIN gapto.regla_versiones v ON v.id = p.regla_version_id "
        "WHERE v.regla_id = %s AND p.estado = 'ABIERTA'",
        (cadena["regla_id"],),
    )
    assert fila == (1,)


def test_c2_dos_sucesores_concurrentes_tras_realizar(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """Cabeza terminada y dos generaciones a la vez: una sola cabeza nueva."""
    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    vincular(
        servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "45.0000",
        realizar=True,
    )
    identificadores = [uuid.uuid4(), uuid.uuid4()]

    def intentar(indice: int) -> None:
        servicio_previsiones.generar_rodante(
            ContextoOperacion.de_usuario(contexto.owner_user_id),
            regla_id=cadena["regla_id"],
            uuid_nuevo=identificadores[indice],
        )

    _competir(intentar)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.previsiones p "
        "JOIN gapto.regla_versiones v ON v.id = p.regla_version_id "
        "WHERE v.regla_id = %s AND p.estado = 'ABIERTA'",
        (cadena["regla_id"],),
    )
    assert fila == (1,)


def test_c3_dos_generaciones_calendario_concurrentes(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Mismo horizonte desde dos hilos: cada identidad se materializa una vez."""
    regla_id = uuid.uuid4()
    servicio_reglas.crear_regla(
        contexto,
        DatosRegla(regla_id=regla_id, nombre="Luz"),
        version_rodante(cadencia=Cadencia(MENSUAL, 1, CALENDARIO)),
    )
    mapa = {dt.date(2027, m, 10): uuid.uuid4() for m in range(1, 5)}

    def intentar(indice: int) -> None:
        servicio_previsiones.generar_calendario(
            ContextoOperacion.de_usuario(contexto.owner_user_id),
            regla_id=regla_id,
            uuids_por_objetivo=mapa,
            hasta_fecha=F("2027-04-30"),
        )

    _competir(intentar)
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), count(DISTINCT p.fecha_objetivo_regla) "
        "  FROM gapto.previsiones p "
        "  JOIN gapto.regla_versiones v ON v.id = p.regla_version_id "
        " WHERE v.regla_id = %s",
        (regla_id,),
    )
    assert fila == (4, 4)


def test_c4_dos_realizaciones_concurrentes(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    """Solo una puede consumir la version esperada."""
    h1 = crear_hecho(servicio, contexto, F("2027-02-02"))
    h2 = crear_hecho(servicio, contexto, F("2027-02-03"))
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    hechos = [h1, h2]

    def intentar(indice: int) -> None:
        servicio_previsiones.vincular_realidad(
            ContextoOperacion.de_usuario(contexto.owner_user_id),
            prevision_id=cadena["cabeza"],
            row_version_esperada=estado.row_version,
            datos=DatosVinculo(
                vinculo_id=uuid.uuid4(),
                hecho_id=hechos[indice],
                importe_asignado=D("45.0000"),
                marcar_realizada=True,
            ),
        )

    resultados = _competir(intentar)
    assert resultados.count("OK") == 1, resultados


def test_c5_omision_y_realizacion_concurrentes(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])

    def intentar(indice: int) -> None:
        propio = ContextoOperacion.de_usuario(contexto.owner_user_id)
        if indice == 0:
            servicio_previsiones.omitir(
                propio,
                prevision_id=cadena["cabeza"],
                row_version_esperada=estado.row_version,
                motivo="no fui",
            )
        else:
            servicio_previsiones.vincular_realidad(
                propio,
                prevision_id=cadena["cabeza"],
                row_version_esperada=estado.row_version,
                datos=DatosVinculo(
                    vinculo_id=uuid.uuid4(),
                    hecho_id=hecho_id,
                    importe_asignado=D("45.0000"),
                    marcar_realizada=True,
                ),
            )

    resultados = _competir(intentar)
    assert resultados.count("OK") == 1, resultados


def test_c6_configuracion_y_generacion_concurrentes(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """Nadie genera desde una configuracion a medio cambiar.

    El versionado toma el mismo lock que la generacion, de modo que las dos se
    serializan y el resultado es coherente en cualquier orden.
    """
    def intentar(indice: int) -> None:
        propio = ContextoOperacion.de_usuario(contexto.owner_user_id)
        if indice == 0:
            servicio_reglas.crear_version(
                propio,
                regla_id=cadena["regla_id"],
                regla_row_version_esperada=cadena["regla"].regla_row_version,
                version=version_rodante(
                    vigente_desde=F("2027-07-01"), importe_fijo=D("60.0000")
                ),
                cerrar_version_id=cadena["version"].version_id,
                cerrar_vigente_hasta=F("2027-06-30"),
            )
        else:
            servicio_previsiones.generar_rodante(
                propio, regla_id=cadena["regla_id"], uuid_nuevo=uuid.uuid4()
            )

    resultados = _competir(intentar)
    assert "OK" in resultados
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.previsiones p "
        "JOIN gapto.regla_versiones v ON v.id = p.regla_version_id "
        "WHERE v.regla_id = %s AND p.estado = 'ABIERTA'",
        (cadena["regla_id"],),
    )
    assert fila == (1,)


def test_c7_retry_concurrente_del_mismo_vinculo(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """Dos reintentos simultaneos con los MISMOS UUID: un vinculo, una
    auditoria."""
    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    estado = servicio_previsiones.estado_de(contexto, cadena["cabeza"])
    datos = DatosVinculo(
        vinculo_id=uuid.uuid4(), hecho_id=hecho_id, importe_asignado=D("45.0000")
    )

    def intentar(indice: int) -> None:
        servicio_previsiones.vincular_realidad(
            ContextoOperacion.de_usuario(contexto.owner_user_id),
            prevision_id=cadena["cabeza"],
            row_version_esperada=estado.row_version,
            datos=datos,
        )

    resultados = _competir(intentar)
    assert "OK" in resultados
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.prevision_hechos WHERE id = %s), "
        "       (SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s)",
        (datos.vinculo_id, datos.vinculo_id),
    )
    assert fila == (1, 1)


# ==================================================================
# Impacto de OP-02 sobre el ancla (mandato 82)
# ==================================================================

def test_op02_no_puede_mover_el_ancla_de_una_cadena_con_sucesor(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """Falla cerrado en vez de propagar (F04-D022).

    Mover la fecha economica del hecho ancla dejaria el sucesor calculado
    desde una fecha que ya no es cierta, y su identidad NO puede moverse.
    """
    from app.core.modelos import CamposCorreccion

    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    sucesor = uuid.uuid4()
    vincular(
        servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "45.0000",
        realizar=True, sucesor=sucesor,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=fila[0],
            campos=CamposCorreccion(fecha_hecho=F("2027-02-20")),
            motivo="fecha mal capturada",
        )
    assert excinfo.value.codigo is CodigoError.REVISION_DERIVADA_REQUERIDA

    # Ni el hecho ni la identidad del sucesor se han movido.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT fecha_hecho, row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    ) == (F("2027-02-02"), fila[0])
    assert servicio_previsiones.estado_de(
        contexto, sucesor
    ).fecha_objetivo_regla == F("2027-03-09")


def test_op02_sigue_corrigiendo_otros_campos_del_hecho_ancla(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """El bloqueo es SOLO de la fecha economica: el resto de OP-02 no cambia."""
    from app.core.modelos import CamposCorreccion

    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    vincular(
        servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "45.0000",
        realizar=True, sucesor=uuid.uuid4(),
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=fila[0],
        campos=CamposCorreccion(concepto="cuota corregida"),
        motivo="concepto mal capturado",
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT concepto FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    ) == ("cuota corregida",)


def test_op02_puede_mover_la_fecha_si_la_cadena_no_avanzo(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """Sin sucesor no hay nada que quede descolgado: la correccion procede."""
    from app.core.modelos import CamposCorreccion

    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    vincular(
        servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "45.0000",
        realizar=True,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=fila[0],
        campos=CamposCorreccion(fecha_hecho=F("2027-02-04")),
        motivo="fecha mal capturada",
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    ) == (F("2027-02-04"),)


def test_con_cabeza_abierta_la_cadena_no_esta_bloqueada(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
    admin: psycopg.Connection,
) -> None:
    """AMB-009 bloquea la cadena solo si NO hay cabeza con la que trabajar.

    Escenario: la primera ocurrencia queda REALIZADA_SIN_REALIDAD_ACTIVA, pero
    su sucesor ya existe y sigue ABIERTA. Generar debe devolver ese sucesor
    como existente, NO bloquear: hay cabeza operativa y nada que decidir.

    Es el caso que discrimina un motor que, teniendo cabeza abierta, se pone a
    recalcular el sucesor desde la ultima terminal.
    """
    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    sucesor = uuid.uuid4()
    vincular(
        servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "45.0000",
        realizar=True, sucesor=sucesor,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    servicio.anular_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=fila[0],
        motivo_anulacion="capturado por error",
    )
    assert (
        servicio_previsiones.estado_de(contexto, cadena["cabeza"]).estado_derivado
        == REALIZADA_SIN_REALIDAD_ACTIVA
    )

    resultado = servicio_previsiones.generar_rodante(
        contexto, regla_id=cadena["regla_id"], uuid_nuevo=uuid.uuid4()
    )
    assert resultado.total_creadas == 0
    assert resultado.existentes == (sucesor,)


def test_un_hecho_anulado_deja_de_contar_en_el_historico(
    servicio: HechosService,
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Solo participan ocurrencias con realidad ACTIVA.

    La muestra es {60, 80} y la media 70. Al anular el hecho de la segunda,
    esa ocurrencia pierde su realidad y queda fuera de la muestra: la media
    pasa a 60, no sigue en 70.

    Sin este caso, un motor que ignorase `h.estado` daria el mismo resultado
    en todos los demas tests, porque en ninguno hay hechos anulados dentro del
    historico.
    """
    regla_id = uuid.uuid4()
    primera = version_rodante(
        cadencia=Cadencia(MENSUAL, 1, CALENDARIO),
        importe_modo="MEDIA_HISTORICA",
        importe_fijo=None,
    )
    servicio_reglas.crear_regla(
        contexto, DatosRegla(regla_id=regla_id, nombre="Luz variable"), primera
    )
    mapa = {dt.date(2027, m, 10): uuid.uuid4() for m in range(1, 5)}
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=regla_id,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-04-30"),
    )

    hechos: dict[dt.date, uuid.UUID] = {}
    for objetivo, asignado in (
        (F("2027-01-10"), "60.0000"),
        (F("2027-02-10"), "80.0000"),
    ):
        hecho_id = crear_hecho(servicio, contexto, objetivo)
        hechos[objetivo] = hecho_id
        vincular(
            servicio_previsiones, contexto, mapa[objetivo], hecho_id, asignado,
            realizar=True,
        )

    servicio_previsiones.recalcular_futuras(
        contexto, regla_id=regla_id, desde_fecha=F("2027-03-01")
    )
    assert servicio_previsiones.estado_de(
        contexto, mapa[F("2027-03-10")]
    ).importe_esperado == D("70")

    # Se anula el hecho de febrero: su ocurrencia pierde la realidad ACTIVA.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hechos[F("2027-02-10")],),
    )
    servicio.anular_hecho(
        contexto,
        hecho_id=hechos[F("2027-02-10")],
        row_version_esperada=fila[0],
        motivo_anulacion="capturado por error",
    )
    assert (
        servicio_previsiones.estado_de(contexto, mapa[F("2027-02-10")]).estado_derivado
        == REALIZADA_SIN_REALIDAD_ACTIVA
    )

    servicio_previsiones.recalcular_futuras(
        contexto, regla_id=regla_id, desde_fecha=F("2027-03-01")
    )
    assert servicio_previsiones.estado_de(
        contexto, mapa[F("2027-03-10")]
    ).importe_esperado == D("60")


def test_version_desfasada_tiene_precedencia_sobre_la_guarda_de_ancla(
    servicio: HechosService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cadena,
) -> None:
    """F04-D022. La guarda se evalua DESPUES del control optimista.

    Con la version desfasada, el llamante debe recibir VERSION_DESFASADA como
    en cualquier otra correccion: alterar esa precedencia cambiaria el
    contrato de OP-02 cerrado en F04-01.
    """
    from app.core.modelos import CamposCorreccion

    hecho_id = crear_hecho(servicio, contexto, F("2027-02-02"))
    vincular(
        servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "45.0000",
        realizar=True, sucesor=uuid.uuid4(),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio.corregir_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=99,
            campos=CamposCorreccion(fecha_hecho=F("2027-02-20")),
            motivo="fecha mal capturada",
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_sin_colaborador_op02_se_comporta_como_en_f04_01(
    unidad,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cadena,
) -> None:
    """La guarda es un colaborador inyectado, no una dependencia del servicio.

    Un `HechosService` construido sin el se comporta exactamente como en
    F04-01: `hechos_service` no importa nada de F04-05.
    """
    from app.core.modelos import CamposCorreccion

    aislado = HechosService(unidad)
    hecho_id = crear_hecho(aislado, contexto, F("2027-02-02"))
    vincular(
        servicio_previsiones, contexto, cadena["cabeza"], hecho_id, "45.0000",
        realizar=True, sucesor=uuid.uuid4(),
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )
    aislado.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=fila[0],
        campos=CamposCorreccion(fecha_hecho=F("2027-02-04")),
        motivo="fecha mal capturada",
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    ) == (F("2027-02-04"),)


# ==================================================================
# E2E de los algoritmos de importe pendientes
# ==================================================================

def _regla_con_modo(
    servicio_reglas: ReglasService,
    contexto: ContextoOperacion,
    modo: str,
    **extra,
) -> uuid.UUID:
    regla_id = uuid.uuid4()
    servicio_reglas.crear_regla(
        contexto,
        DatosRegla(regla_id=regla_id, nombre=f"Regla {modo}"),
        version_rodante(
            cadencia=Cadencia(MENSUAL, 1, CALENDARIO),
            importe_modo=modo,
            importe_fijo=None,
            **extra,
        ),
    )
    return regla_id


def test_e2e_mediana_historica(
    servicio: HechosService,
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
) -> None:
    """Muestra {10, 100, 20}: la mediana es 20 y la media seria 43,33.

    Los valores estan elegidos para que las dos respuestas sean muy distintas:
    con una muestra simetrica, este test no distinguiria mediana de media.
    """
    regla_id = _regla_con_modo(servicio_reglas, contexto, "MEDIANA_HISTORICA")
    mapa = {dt.date(2027, m, 10): uuid.uuid4() for m in range(1, 6)}
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=regla_id,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-05-31"),
    )
    for objetivo, asignado in (
        (F("2027-01-10"), "10.0000"),
        (F("2027-02-10"), "100.0000"),
        (F("2027-03-10"), "20.0000"),
    ):
        hecho_id = crear_hecho(servicio, contexto, objetivo)
        vincular(
            servicio_previsiones, contexto, mapa[objetivo], hecho_id, asignado,
            realizar=True,
        )
    servicio_previsiones.recalcular_futuras(
        contexto, regla_id=regla_id, desde_fecha=F("2027-04-01")
    )
    assert servicio_previsiones.estado_de(
        contexto, mapa[F("2027-04-10")]
    ).importe_esperado == D("20")


def test_e2e_ultimo_real_ordena_por_identidad(
    servicio: HechosService,
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
) -> None:
    """Se realiza FEBRERO antes que ENERO, a proposito.

    El orden de captura contradice el orden por identidad. ULTIMO_REAL debe
    devolver el importe de la ocurrencia con mayor `fecha_objetivo_regla`
    —enero es anterior, asi que gana febrero— y no el ultimo capturado.
    """
    regla_id = _regla_con_modo(servicio_reglas, contexto, "ULTIMO_REAL")
    mapa = {dt.date(2027, m, 10): uuid.uuid4() for m in range(1, 5)}
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=regla_id,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-04-30"),
    )
    # Febrero primero, enero despues: la captura va al reves de la identidad.
    for objetivo, asignado in (
        (F("2027-02-10"), "80.0000"),
        (F("2027-01-10"), "60.0000"),
    ):
        hecho_id = crear_hecho(servicio, contexto, objetivo)
        vincular(
            servicio_previsiones, contexto, mapa[objetivo], hecho_id, asignado,
            realizar=True,
        )
    servicio_previsiones.recalcular_futuras(
        contexto, regla_id=regla_id, desde_fecha=F("2027-03-01")
    )
    assert servicio_previsiones.estado_de(
        contexto, mapa[F("2027-03-10")]
    ).importe_esperado == D("80.0000")


def test_e2e_saldo_objetivo_con_saldo_conocido(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    servicio_tesoreria,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
) -> None:
    """Cuenta con apertura 300 y objetivo 1.000: la necesidad es 700.

    Es el unico algoritmo con codigo propio end-to-end —lee
    `cuentas.saldo_apertura` y suma los movimientos ACTIVOS— y hasta ahora solo
    estaba probado en el helper puro.
    """
    from app.core.modelos_tesoreria import DatosMovimiento

    with_apertura(contexto, cuenta, D("300.0000"))
    regla_id = _regla_con_modo(
        servicio_reglas,
        contexto,
        "SALDO_OBJETIVO",
        flujo_tesoreria_esperado="ENTRADA",
        cuenta_calculo_id=cuenta,
        saldo_objetivo=D("1000.0000"),
    )
    mapa = {F("2027-01-10"): uuid.uuid4()}
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=regla_id,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-01-31"),
    )
    assert servicio_previsiones.estado_de(
        contexto, mapa[F("2027-01-10")]
    ).importe_esperado == D("700.0000")


def test_e2e_saldo_objetivo_cuenta_los_movimientos_activos(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    servicio_tesoreria,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
) -> None:
    """Apertura 300 mas una entrada real de 200: la necesidad baja a 500."""
    from app.core.modelos_tesoreria import DatosMovimiento

    with_apertura(contexto, cuenta, D("300.0000"))
    servicio_tesoreria.registrar_movimiento(
        contexto,
        DatosMovimiento(
            movimiento_id=uuid.uuid4(),
            cuenta_id=cuenta,
            fecha_movimiento=F("2027-01-05"),
            importe=D("200.0000"),
            clase_movimiento="OPERACION",
        ),
    )
    regla_id = _regla_con_modo(
        servicio_reglas,
        contexto,
        "SALDO_OBJETIVO",
        flujo_tesoreria_esperado="ENTRADA",
        cuenta_calculo_id=cuenta,
        saldo_objetivo=D("1000.0000"),
    )
    mapa = {F("2027-01-10"): uuid.uuid4()}
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=regla_id,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-01-31"),
    )
    assert servicio_previsiones.estado_de(
        contexto, mapa[F("2027-01-10")]
    ).importe_esperado == D("500.0000")


def test_e2e_saldo_objetivo_indeterminado_no_asume_cero(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
) -> None:
    """Sin `saldo_apertura`, el saldo es INDETERMINADO y el importe queda NULL.

    Asumir cero produciria una necesidad inventada de 1.000.
    """
    regla_id = _regla_con_modo(
        servicio_reglas,
        contexto,
        "SALDO_OBJETIVO",
        flujo_tesoreria_esperado="ENTRADA",
        cuenta_calculo_id=cuenta,
        saldo_objetivo=D("1000.0000"),
    )
    mapa = {F("2027-01-10"): uuid.uuid4()}
    servicio_previsiones.generar_calendario(
        contexto,
        regla_id=regla_id,
        uuids_por_objetivo=mapa,
        hasta_fecha=F("2027-01-31"),
    )
    assert (
        servicio_previsiones.estado_de(
            contexto, mapa[F("2027-01-10")]
        ).importe_esperado
        is None
    )


def test_e2e_saldo_objetivo_cumplido_no_materializa(
    servicio_reglas: ReglasService,
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    cuenta: uuid.UUID,
) -> None:
    """Objetivo ya alcanzado: omision determinista, no una previsión de 0."""
    with_apertura(contexto, cuenta, D("1000.0000"))
    regla_id = _regla_con_modo(
        servicio_reglas,
        contexto,
        "SALDO_OBJETIVO",
        flujo_tesoreria_esperado="ENTRADA",
        cuenta_calculo_id=cuenta,
        saldo_objetivo=D("1000.0000"),
    )
    resultado = servicio_previsiones.generar_calendario(
        contexto,
        regla_id=regla_id,
        uuids_por_objetivo={F("2027-01-10"): uuid.uuid4()},
        hasta_fecha=F("2027-01-31"),
    )
    assert resultado.total_creadas == 0
