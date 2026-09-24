# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_110_op14_reembolso_condonacion.py
# Ruta: tests/backend/test_110_op14_reembolso_condonacion.py
# Descripcion: F04-04 OP-14 y condonacion. Incluye los casos canonicos C-03 y
#   C-12 y los cuatro interleavings del mandato.
#
#   C-12 es el gate de INV-10: una obligacion de 15 y un derecho de 15 frente a
#   la misma contraparte conviven aunque su neto calculado sea cero. No se
#   extinguen, no se reescriben importes y no nace ningun hecho de
#   compensacion. El neteo es lectura, nunca realidad persistida.
# Version: 0.2.0
#   0.2.0 (mandato F04 R1+R2 v0.3 + E01): las condonaciones que declaran GASTO
#   aportan `presupuestable` (E01), preservando el discriminante
#   GASTO_DUPLICADO.
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
from app.core.modelos_posicion import (
    DatosCierre,
    DatosCondonacion,
    DatosReembolso,
    DatosTesoreriaReembolso,
    TIPO_OBLIGACION,
)
from app.core.modelos_tesoreria import DatosMovimiento
from app.services.posiciones_service import PosicionesService
from app.services.tesoreria_service import TesoreriaService
from conftest import leer_fila
from test_109_op12_posiciones import alta, delta

D = decimal.Decimal
FECHA = dt.date(2026, 6, 15)


@pytest.fixture()
def derecho(servicio_posiciones: PosicionesService, contexto, contraparte):
    datos = alta(contraparte)
    resultado = servicio_posiciones.crear_posicion(contexto, datos)
    return datos.entidad_id, resultado, datos


@pytest.fixture()
def derecho_indeterminado(
    servicio_posiciones: PosicionesService, contexto, contraparte
):
    datos = alta(contraparte, saldo_apertura=None, fecha_inicio_seguimiento=None)
    resultado = servicio_posiciones.crear_posicion(contexto, datos)
    return datos.entidad_id, resultado


def reembolso(importe: str, **extra) -> DatosReembolso:
    return DatosReembolso(delta=delta(importe), **extra)


# ==================================================================
# OP-14 — reembolso
# ==================================================================

def test_reembolso_parcial(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    entidad_id, creada, _ = derecho
    datos = reembolso("40.0000")
    resultado = servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    assert resultado.saldo.importe == D("60.0000")
    assert resultado.entidad_row_version == creada.entidad_row_version + 1

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tipo_efecto, importe_delta FROM gapto.hecho_efectos WHERE id = %s",
        (datos.delta.efecto_id,),
    )
    assert fila == ("DERECHO_COBRO", D("-40.0000"))


def test_reembolso_total_no_cierra_solo(
    servicio_posiciones: PosicionesService, contexto, derecho
) -> None:
    entidad_id, creada, _ = derecho
    resultado = servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=reembolso("100.0000"),
    )
    assert resultado.saldo.importe == D("0.0000")
    assert resultado.estado == "ACTIVA"


def test_reembolso_total_con_cierre_declarado(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    entidad_id, creada, _ = derecho
    datos = DatosReembolso(
        delta=delta(
            "100.0000",
            cierre=DatosCierre(
                motivo_cierre="LIQUIDADA", fecha_cierre=dt.date(2026, 7, 1)
            ),
        )
    )
    resultado = servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    assert resultado.estado == "CERRADA"
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT motivo_cierre FROM gapto.derechos_obligaciones_financieras "
        "WHERE entidad_id = %s",
        (entidad_id,),
    )
    assert fila == ("LIQUIDADA",)


def test_reembolso_nunca_es_ingreso_ni_gasto_negativo(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    """El dinero que vuelve de un derecho no es un ingreso nuevo."""
    entidad_id, creada, _ = derecho
    datos = reembolso("40.0000")
    servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos "
        "WHERE hecho_id = %s AND tipo_efecto IN ('INGRESO', 'GASTO', 'DEUDA')",
        (datos.delta.hecho_id,),
    )
    assert fila == (0,)


def test_exceso_sobre_saldo_conocido(
    servicio_posiciones: PosicionesService, contexto, derecho
) -> None:
    entidad_id, creada, _ = derecho
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reembolsar(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            datos=reembolso("101.0000"),
        )
    assert excinfo.value.codigo is CodigoError.EXCEDE_SALDO_DEL_DERECHO


def test_saldo_indeterminado_sigue_indeterminado(
    servicio_posiciones: PosicionesService, contexto, derecho_indeterminado
) -> None:
    """Se registra el importe cobrado; el saldo NO se vuelve conocido."""
    entidad_id, creada = derecho_indeterminado
    resultado = servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=reembolso("20.0000"),
    )
    assert resultado.saldo.conocido is False


def test_sin_derecho_previo(
    servicio_posiciones: PosicionesService, contexto
) -> None:
    """No se crea un derecho retroactivo porque haya llegado dinero."""
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reembolsar(
            contexto,
            entidad_id=uuid.uuid4(),
            entidad_row_version_esperada=1,
            datos=reembolso("10.0000"),
        )
    assert excinfo.value.codigo is CodigoError.SIN_DERECHO_PREVIO


def test_reembolso_sobre_obligacion_rechazado(
    servicio_posiciones: PosicionesService, contexto, contraparte
) -> None:
    creada = servicio_posiciones.crear_posicion(
        contexto, alta(contraparte, tipo=TIPO_OBLIGACION)
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reembolsar(
            contexto,
            entidad_id=creada.entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            datos=reembolso("10.0000"),
        )
    assert excinfo.value.codigo is CodigoError.NATURALEZA_INCOMPATIBLE


# ------------------------------------------------------------------
# Tesoreria del reembolso
# ------------------------------------------------------------------

def test_reembolso_con_movimiento_nuevo(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
    cuenta: uuid.UUID,
) -> None:
    entidad_id, creada, _ = derecho
    tesoreria = DatosTesoreriaReembolso(
        conciliacion_id=uuid.uuid4(),
        movimiento_id=uuid.uuid4(),
        cuenta_id=cuenta,
        fecha_movimiento=FECHA,
    )
    resultado = servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=DatosReembolso(delta=delta("40.0000"), tesoreria=tesoreria),
    )
    assert resultado.movimiento_row_version == 1
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe, estado FROM gapto.movimientos_tesoreria WHERE id = %s",
        (tesoreria.movimiento_id,),
    )
    assert fila == (D("40.0000"), "ACTIVO")
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_asignado FROM gapto.hecho_movimientos_tesoreria "
        "WHERE id = %s",
        (tesoreria.conciliacion_id,),
    )
    assert fila == (D("40.0000"),)


def test_reembolso_consumiendo_movimiento_existente(
    servicio_tesoreria: TesoreriaService,
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
    cuenta: uuid.UUID,
) -> None:
    """Modo B: no se crea un segundo movimiento."""
    entidad_id, creada, _ = derecho
    movimiento_id = uuid.uuid4()
    movimiento = servicio_tesoreria.registrar_movimiento(
        contexto,
        DatosMovimiento(
            movimiento_id=movimiento_id,
            cuenta_id=cuenta,
            fecha_movimiento=FECHA,
            importe=D("40.0000"),
            clase_movimiento="OPERACION",
        ),
    )
    tesoreria = DatosTesoreriaReembolso(
        conciliacion_id=uuid.uuid4(),
        movimiento_id=movimiento_id,
        movimiento_row_version_esperada=movimiento.row_version,
    )
    servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=DatosReembolso(delta=delta("40.0000"), tesoreria=tesoreria),
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE cuenta_id = %s",
        (cuenta,),
    )
    assert fila == (1,)


def test_reembolso_con_movimiento_negativo_rechazado(
    servicio_tesoreria: TesoreriaService,
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    derecho,
    cuenta: uuid.UUID,
) -> None:
    entidad_id, creada, _ = derecho
    movimiento_id = uuid.uuid4()
    movimiento = servicio_tesoreria.registrar_movimiento(
        contexto,
        DatosMovimiento(
            movimiento_id=movimiento_id,
            cuenta_id=cuenta,
            fecha_movimiento=FECHA,
            importe=D("-40.0000"),
            clase_movimiento="OPERACION",
        ),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reembolsar(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            datos=DatosReembolso(
                delta=delta("40.0000"),
                tesoreria=DatosTesoreriaReembolso(
                    conciliacion_id=uuid.uuid4(),
                    movimiento_id=movimiento_id,
                    movimiento_row_version_esperada=movimiento.row_version,
                ),
            ),
        )
    assert excinfo.value.codigo is CodigoError.SIGNO_INCOMPATIBLE


def test_sin_cuenta_registrada_no_se_inventa_movimiento(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    entidad_id, creada, _ = derecho
    datos = reembolso("40.0000")
    servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
        (datos.delta.hecho_id,),
    )
    assert fila == (0,)


# ------------------------------------------------------------------
# Relacion con el hecho causal
# ------------------------------------------------------------------

def test_relacion_reembolso_de(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    entidad_id, creada, datos_alta = derecho
    relacion_id = uuid.uuid4()
    datos = DatosReembolso(
        delta=delta("40.0000"),
        hecho_causal_id=datos_alta.hecho_id,
        relacion_id=relacion_id,
    )
    servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT hecho_origen_id, hecho_destino_id, tipo_relacion, importe_relacionado "
        "FROM gapto.hecho_relaciones WHERE id = %s",
        (relacion_id,),
    )
    assert fila == (
        datos.delta.hecho_id,
        datos_alta.hecho_id,
        "REEMBOLSO_DE",
        D("40.0000"),
    )


def test_origen_desconocido_no_inventa_relacion(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho_indeterminado,
) -> None:
    entidad_id, creada = derecho_indeterminado
    datos = reembolso("20.0000")
    servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_relaciones WHERE hecho_origen_id = %s",
        (datos.delta.hecho_id,),
    )
    assert fila == (0,)


# ------------------------------------------------------------------
# Idempotencia y version
# ------------------------------------------------------------------

def test_retry_tras_commit_incierto_con_version_antigua(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    """Mandato 32: el reintento exacto se reconoce ANTES de mirar la version.

    El COMMIT confirmo, el cliente perdio la respuesta y `entidades.row_version`
    ya avanzo. Comprobar la version primero convertiria un reintento legitimo
    en VERSION_DESFASADA, y el cliente acabaria duplicando la realidad con UUID
    nuevos.
    """
    entidad_id, creada, _ = derecho
    datos = reembolso("40.0000")
    primero = servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    segundo = servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    assert segundo.idempotente is True
    assert segundo.entidad_row_version == primero.entidad_row_version
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE id = %s",
        (datos.delta.efecto_id,),
    )
    assert fila == (1,)


def test_version_desfasada_con_uuid_nuevos(
    servicio_posiciones: PosicionesService, contexto, derecho
) -> None:
    """Si los UUID NO son los originales, una version vieja si es conflicto."""
    entidad_id, creada, _ = derecho
    servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=reembolso("40.0000"),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reembolsar(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            datos=reembolso("10.0000"),
        )
    assert excinfo.value.codigo is CodigoError.VERSION_DESFASADA


def test_lote_parcialmente_preexistente_es_conflicto(
    servicio_posiciones: PosicionesService, contexto, derecho
) -> None:
    entidad_id, creada, _ = derecho
    datos = reembolso("40.0000")
    servicio_posiciones.reembolsar(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    mezclado = DatosReembolso(
        delta=type(datos.delta)(
            hecho_id=datos.delta.hecho_id,
            efecto_id=uuid.uuid4(),
            vinculo_id=uuid.uuid4(),
            importe=D("40.0000"),
            fecha_hecho=datos.delta.fecha_hecho,
        )
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.reembolsar(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version + 1,
            datos=mezclado,
        )
    assert excinfo.value.codigo is CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION


def test_rollback_por_fallo_de_auditoria(
    unidad, contexto: ContextoOperacion, admin: psycopg.Connection, derecho
) -> None:
    from app.repositories import auditoria_repository as auditoria
    from app.repositories import posiciones_repository as repo_pos

    entidad_id, creada, _ = derecho

    def operacion(sesion):
        repo_pos.tocar_entidad(sesion, entidad_id, creada.entidad_row_version)
        auditoria.registrar(
            sesion,
            tabla=repo_pos.TABLA_POSICIONES,
            registro_id=entidad_id,
            accion=auditoria.ACCION_ACTUALIZAR,
            datos_despues_json='{"password": "x"}',
        )

    with pytest.raises(ErrorMotor):
        unidad.ejecutar(contexto, operacion, nombre="prueba-rollback-f0404")

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.entidades WHERE id = %s",
        (entidad_id,),
    )
    assert fila == (creada.entidad_row_version,)


# ==================================================================
# Condonacion (F04-D015)
# ==================================================================

def test_condonacion_parcial(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    entidad_id, creada, _ = derecho
    datos = DatosCondonacion(delta=delta("30.0000"))
    resultado = servicio_posiciones.condonar_derecho(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    assert resultado.saldo.importe == D("70.0000")
    assert resultado.estado == "ACTIVA"
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
        (datos.delta.hecho_id,),
    )
    assert fila == (0,)


def test_condonacion_total_con_cierre(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    entidad_id, creada, _ = derecho
    resultado = servicio_posiciones.condonar_derecho(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=DatosCondonacion(
            delta=delta(
                "100.0000",
                cierre=DatosCierre(
                    motivo_cierre="CONDONADA", fecha_cierre=dt.date(2026, 7, 1)
                ),
            )
        ),
    )
    assert resultado.estado == "CERRADA"
    assert resultado.saldo.importe == D("0.0000")
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT motivo_cierre FROM gapto.derechos_obligaciones_financieras "
        "WHERE entidad_id = %s",
        (entidad_id,),
    )
    assert fila == ("CONDONADA",)


def test_condonacion_no_genera_ingreso(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    entidad_id, creada, _ = derecho
    datos = DatosCondonacion(delta=delta("30.0000"))
    servicio_posiciones.condonar_derecho(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos "
        "WHERE hecho_id = %s AND tipo_efecto = 'INGRESO'",
        (datos.delta.hecho_id,),
    )
    assert fila == (0,)


@pytest.mark.parametrize(
    "soportado, no_reconocido",
    [(False, False), (True, False), (False, True)],
)
def test_sin_las_dos_declaraciones_no_hay_gasto(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
    soportado,
    no_reconocido,
) -> None:
    """El GASTO exige AMBAS declaraciones; con una sola, cero efecto."""
    entidad_id, creada, _ = derecho
    datos = DatosCondonacion(
        delta=delta("30.0000"),
        declara_gasto_soportado=soportado,
        declara_coste_no_reconocido=no_reconocido,
        efecto_gasto_id=uuid.uuid4(),
    )
    servicio_posiciones.condonar_derecho(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos "
        "WHERE hecho_id = %s AND tipo_efecto = 'GASTO'",
        (datos.delta.hecho_id,),
    )
    assert fila == (0,)


def test_gasto_explicito_permitido(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    entidad_id, creada, _ = derecho
    efecto_gasto_id = uuid.uuid4()
    datos = DatosCondonacion(
        delta=delta("30.0000"),
        declara_gasto_soportado=True,
        declara_coste_no_reconocido=True,
        presupuestable=True,  # mandato v0.3 §8: GASTO declarado
        efecto_gasto_id=efecto_gasto_id,
    )
    servicio_posiciones.condonar_derecho(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tipo_efecto, importe_delta FROM gapto.hecho_efectos WHERE id = %s",
        (efecto_gasto_id,),
    )
    assert fila == ("GASTO", D("30.0000"))


def test_doble_gasto_rechazado(
    servicio_posiciones: PosicionesService, contexto, derecho
) -> None:
    """INV-12: si el coste ya se reconocio, anadir otro es doble conteo."""
    entidad_id, creada, _ = derecho
    primera = servicio_posiciones.condonar_derecho(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=DatosCondonacion(
            delta=delta("30.0000"),
            declara_gasto_soportado=True,
            declara_coste_no_reconocido=True,
            presupuestable=True,  # mandato v0.3 §8: GASTO declarado
            efecto_gasto_id=uuid.uuid4(),
        ),
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.condonar_derecho(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=primera.entidad_row_version,
            datos=DatosCondonacion(
                delta=delta("20.0000"),
                declara_gasto_soportado=True,
                declara_coste_no_reconocido=True,
                presupuestable=True,  # mandato v0.3 §8: GASTO declarado
                efecto_gasto_id=uuid.uuid4(),
            ),
        )
    assert excinfo.value.codigo is CodigoError.GASTO_DUPLICADO


def test_condonacion_sobre_saldo_indeterminado(
    servicio_posiciones: PosicionesService, contexto, derecho_indeterminado
) -> None:
    entidad_id, creada = derecho_indeterminado
    resultado = servicio_posiciones.condonar_derecho(
        contexto,
        entidad_id=entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=DatosCondonacion(delta=delta("20.0000")),
    )
    assert resultado.saldo.conocido is False


def test_condonacion_de_obligacion_fail_closed(
    servicio_posiciones: PosicionesService, contexto, contraparte
) -> None:
    """Fuera de alcance: no se improvisa si la extincion supone INGRESO."""
    creada = servicio_posiciones.crear_posicion(
        contexto, alta(contraparte, tipo=TIPO_OBLIGACION)
    )
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_posiciones.condonar_derecho(
            contexto,
            entidad_id=creada.entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            datos=DatosCondonacion(delta=delta("10.0000")),
        )
    assert excinfo.value.codigo is CodigoError.CONDONACION_OBLIGACION_NO_SOPORTADA


def test_no_reclamar_no_cambia_la_posicion(
    servicio_posiciones: PosicionesService, contexto, derecho
) -> None:
    """Condonar es renuncia definitiva, no "todavia no he cobrado".

    Sin una llamada explicita, el saldo y el estado no se mueven solos por el
    paso del tiempo ni por la ausencia de cobro.
    """
    entidad_id, creada, _ = derecho
    actual = servicio_posiciones.saldo(contexto, entidad_id)
    assert actual.saldo.importe == D("100.0000")
    assert actual.estado == "ACTIVA"
    assert actual.entidad_row_version == creada.entidad_row_version


# ==================================================================
# C-03 — GASOIL REEMBOLSABLE
# ==================================================================

def test_c03_gasoil_reembolsable(
    servicio_tesoreria: TesoreriaService,
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    contraparte: uuid.UUID,
    cuenta: uuid.UUID,
) -> None:
    """Gasto real pagado, derecho de cobro explicito, reembolso posterior."""
    # 1-2. El derecho nace por DECISION_EXPLICITA, separado del gasto.
    datos_alta = alta(
        contraparte,
        nombre="Gasoil reembolsable",
        importe_inicial=D("100.0000"),
        concepto="derecho de reembolso de gasoil",
    )
    creada = servicio_posiciones.crear_posicion(contexto, datos_alta)

    # 3-4. Reembolso parcial con entrada real en cuenta Gapto.
    tesoreria = DatosTesoreriaReembolso(
        conciliacion_id=uuid.uuid4(),
        movimiento_id=uuid.uuid4(),
        cuenta_id=cuenta,
        fecha_movimiento=FECHA,
    )
    datos = DatosReembolso(
        delta=delta("60.0000"),
        tesoreria=tesoreria,
        hecho_causal_id=datos_alta.hecho_id,
        relacion_id=uuid.uuid4(),
    )
    resultado = servicio_posiciones.reembolsar(
        contexto,
        entidad_id=datos_alta.entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=datos,
    )

    # Saldo parcial, posicion todavia ACTIVA: el cierre es explicito.
    assert resultado.saldo.importe == D("40.0000")
    assert resultado.estado == "ACTIVA"

    # Cero INGRESO y cero GASTO negativo en el hecho del reembolso.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos "
        "WHERE hecho_id = %s AND tipo_efecto <> 'DERECHO_COBRO'",
        (datos.delta.hecho_id,),
    )
    assert fila == (0,)

    # Movimiento positivo real y conciliacion.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT m.importe, r.importe_asignado "
        "FROM gapto.movimientos_tesoreria m "
        "JOIN gapto.hecho_movimientos_tesoreria r "
        "  ON r.movimiento_tesoreria_id = m.id WHERE m.id = %s",
        (tesoreria.movimiento_id,),
    )
    assert fila == (D("60.0000"), D("60.0000"))

    # Trazabilidad con el hecho causal del derecho.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tipo_relacion FROM gapto.hecho_relaciones WHERE id = %s",
        (datos.relacion_id,),
    )
    assert fila == ("REEMBOLSO_DE",)


# ==================================================================
# C-12 — PELUQUERIA + CENA (gate de INV-10)
# ==================================================================

def test_c12_obligacion_y_derecho_conviven_sin_compensacion(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    contraparte: uuid.UUID,
) -> None:
    """Obligacion de 15 y derecho de 15 frente a la misma contraparte.

    El neto calculado es cero. F04-04 NO las extingue, NO reescribe importes y
    NO crea ningun hecho de compensacion: el neteo es lectura, nunca realidad
    persistida (INV-10). Las dos posiciones siguen vivas con su saldo.
    """
    # Peluqueria: 15 atribuibles al usuario, pagados integramente por la pareja.
    # La OBLIGACION nace por decision explicita, no porque el motor calcule
    # "atribucion 15 - pago 0".
    obligacion = alta(
        contraparte,
        tipo=TIPO_OBLIGACION,
        nombre="Obligacion peluqueria",
        importe_inicial=D("15.0000"),
        concepto="peluqueria pagada por la pareja",
    )
    r_obligacion = servicio_posiciones.crear_posicion(contexto, obligacion)

    # Cena: 44,50 pagados integramente por el usuario; parte de la pareja 15.
    derecho_cena = alta(
        contraparte,
        nombre="Derecho cena",
        importe_inicial=D("15.0000"),
        concepto="parte de la pareja en la cena",
    )
    r_derecho = servicio_posiciones.crear_posicion(contexto, derecho_cena)

    assert r_obligacion.saldo.importe == D("15.0000")
    assert r_derecho.saldo.importe == D("15.0000")

    # Las DOS posiciones existen y siguen ACTIVAS.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.derechos_obligaciones_financieras p "
        "JOIN gapto.entidades e ON e.id = p.entidad_id "
        "WHERE e.owner_user_id = %s AND p.estado = 'ACTIVA'",
        (contexto.owner_user_id,),
    )
    assert fila == (2,)

    # Ningun hecho de compensacion, ninguna relacion COMPENSA_A.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_relaciones r "
        "JOIN gapto.hechos_financieros h ON h.id = r.hecho_origen_id "
        "WHERE h.owner_user_id = %s",
        (contexto.owner_user_id,),
    )
    assert fila == (0,)

    # Los importes no se han reescrito: 15 y 15, no 0 y 0.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT sum(abs(ef.importe_delta)) FROM gapto.hecho_efectos ef "
        "JOIN gapto.hechos_financieros h ON h.id = ef.hecho_id "
        "WHERE h.owner_user_id = %s",
        (contexto.owner_user_id,),
    )
    assert fila == (D("30.0000"),)


# ==================================================================
# Interleavings (mandato 47)
# ==================================================================

def _competir(objetivo, veces: int = 2) -> list[Any]:
    """Lanza `veces` intentos sincronizados por barrera, sin sleeps."""
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


DEFENSAS_VALIDAS = (
    CodigoError.VERSION_DESFASADA,
    CodigoError.CONFLICTO_CONCURRENCIA,
    CodigoError.EXCEDE_SALDO_DEL_DERECHO,
    CodigoError.EXCEDE_SALDO_POSICION,
    CodigoError.VIOLACION_INVARIANTE_FISICA,
)


def test_c1_dos_reembolsos_concurrentes_de_setenta(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    """Derecho 100. Dos reembolsos de 70 a la vez. Solo uno confirma.

    No existe constraint fisico agregado que impida 140: lo unico que lo
    impide es la guarda SQL de `entidades.row_version`.
    """
    entidad_id, creada, _ = derecho
    intentos = [reembolso("70.0000"), reembolso("70.0000")]

    def intentar(indice: int) -> None:
        servicio_posiciones.reembolsar(
            ContextoOperacion.de_usuario(contexto.owner_user_id),
            entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            datos=intentos[indice],
        )

    resultados = _competir(intentar)
    assert resultados.count("OK") == 1, resultados
    assert [r for r in resultados if r != "OK"][0] in DEFENSAS_VALIDAS

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.entidades WHERE id = %s",
        (entidad_id,),
    )
    assert fila == (creada.entidad_row_version + 1,)
    assert servicio_posiciones.saldo(contexto, entidad_id).saldo.importe == D(
        "30.0000"
    )


def test_c2_dos_pagos_concurrentes_de_obligacion(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    contraparte: uuid.UUID,
) -> None:
    creada = servicio_posiciones.crear_posicion(
        contexto, alta(contraparte, tipo=TIPO_OBLIGACION)
    )
    intentos = [delta("70.0000"), delta("70.0000")]

    def intentar(indice: int) -> None:
        servicio_posiciones.reducir_obligacion(
            ContextoOperacion.de_usuario(contexto.owner_user_id),
            entidad_id=creada.entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            delta=intentos[indice],
        )

    resultados = _competir(intentar)
    assert resultados.count("OK") == 1, resultados
    assert servicio_posiciones.saldo(
        contexto, creada.entidad_id
    ).saldo.importe == D("30.0000")


def test_c3_cierre_frente_a_delta_concurrente(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    """Cerrar y anadir delta sobre la MISMA version: no confirman las dos."""
    entidad_id, creada, _ = derecho
    datos = reembolso("10.0000")

    def intentar(indice: int) -> None:
        contexto_propio = ContextoOperacion.de_usuario(contexto.owner_user_id)
        if indice == 0:
            servicio_posiciones.cerrar_posicion(
                contexto_propio,
                entidad_id=entidad_id,
                entidad_row_version_esperada=creada.entidad_row_version,
                cierre=DatosCierre(
                    motivo_cierre="CANCELADA", fecha_cierre=dt.date(2026, 7, 1)
                ),
            )
        else:
            servicio_posiciones.reembolsar(
                contexto_propio,
                entidad_id=entidad_id,
                entidad_row_version_esperada=creada.entidad_row_version,
                datos=datos,
            )

    resultados = _competir(intentar)
    assert resultados.count("OK") == 1, resultados

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.entidades WHERE id = %s",
        (entidad_id,),
    )
    assert fila == (creada.entidad_row_version + 1,)


def test_c4_retry_concurrente_no_duplica_deltas_ni_auditoria(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    derecho,
) -> None:
    """Dos reintentos simultaneos con LOS MISMOS UUID no duplican nada."""
    entidad_id, creada, _ = derecho
    datos = reembolso("40.0000")

    def intentar(indice: int) -> None:
        servicio_posiciones.reembolsar(
            ContextoOperacion.de_usuario(contexto.owner_user_id),
            entidad_id=entidad_id,
            entidad_row_version_esperada=creada.entidad_row_version,
            datos=datos,
        )

    resultados = _competir(intentar)
    assert "OK" in resultados

    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.hecho_efectos WHERE id = %s), "
        "(SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s)",
        (datos.delta.efecto_id, datos.delta.efecto_id),
    )
    assert fila == (1, 1)
    assert servicio_posiciones.saldo(contexto, entidad_id).saldo.importe == D(
        "60.0000"
    )
