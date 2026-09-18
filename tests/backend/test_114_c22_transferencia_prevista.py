# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_114_c22_transferencia_prevista.py
# Ruta: tests/backend/test_114_c22_transferencia_prevista.py
# Descripcion: F04-05. Caso canonico C-22 "transferencia prevista".
#
#   MATRIZ CANONICA: C-22 | OP-10 + OP-17 | INV-15 + INV-16.
#
#   ALCANCE DE F04-05. OP-10 pertenece a F04-06 y NO se implementa aqui. La
#   realidad de la transferencia se monta desde fixture con los contratos ya
#   cerrados —OP-01 para el hecho, OP-08 para los dos movimientos, OP-09 para
#   las dos conciliaciones— mas la fila de `transferencias`, que es la unica
#   pieza sin operacion propia todavia. Lo que F04-05 debe demostrar es lo
#   otro: que puede existir una previsión de transferencia, que esa previsión
#   NO mueve liquidez, y que OP-17 la vincula a la realidad sin volver a crear
#   movimientos ni otra transferencia.
#
#   INV-15. Una transferencia real es hecho `TRANSFERENCIA` + dos movimientos
#   + fila `transferencias` + dos conciliaciones, y es economicamente neutra
#   POR AUSENCIA de efectos. El efecto de importe cero no es que se evite: es
#   fisicamente imposible, porque `ck_hecho_efectos__importe_delta` exige
#   distinto de cero.
#
#   HALLAZGO DE CONTRATO. `ck_previsiones__cuentas_por_flujo` admite las DOS
#   cuentas esperadas unicamente cuando `flujo_tesoreria_esperado` vale
#   `TRANSFERENCIA`. El contrato fisico ya anticipaba este caso: una previsión
#   de transferencia no es una salida con destino, es su propio flujo.
#
#   INV-16. Una previsión nunca modifica liquidez. El saldo de la cuenta antes
#   y despues de crear la previsión debe ser identico.
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
    DatosPrevisionManual,
    DatosVinculo,
    REALIZADA,
)
from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
from app.services.hechos_service import HechosService
from app.services.previsiones_service import PrevisionesService
from app.services.tesoreria_service import TesoreriaService
from conftest import leer_fila

D = decimal.Decimal
F = dt.date.fromisoformat

IMPORTE = D("500.0000")


def saldo_de(
    admin: psycopg.Connection, owner: uuid.UUID, cuenta_id: uuid.UUID
) -> decimal.Decimal:
    """Saldo DERIVADO de la cuenta: solo movimientos ACTIVOS (INV-18)."""
    fila = leer_fila(
        admin,
        owner,
        "SELECT COALESCE(sum(importe), 0) FROM gapto.movimientos_tesoreria "
        "WHERE cuenta_id = %s AND estado = 'ACTIVO'",
        (cuenta_id,),
    )
    return decimal.Decimal(fila[0])


@pytest.fixture()
def transferencia_real(
    servicio: HechosService,
    servicio_tesoreria: TesoreriaService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> dict[str, uuid.UUID]:
    """Transferencia real completa conforme a INV-15.

    Se monta con operaciones cerradas salvo la fila `transferencias`, que se
    inserta desde el fixture porque OP-10 es de F04-06. No se inventa una
    operacion de F04-05 para crearla.
    """
    hecho_id = uuid.uuid4()
    servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=F("2027-03-15"),
            moneda="EUR",
            presupuestable=False,
            estado_localizacion="NO_APLICA",
            tipo_hecho_codigo="TRANSFERENCIA",
            importe_total=IMPORTE,
        ),
    )

    salida_id, entrada_id = uuid.uuid4(), uuid.uuid4()
    salida = servicio_tesoreria.registrar_movimiento(
        contexto,
        DatosMovimiento(
            movimiento_id=salida_id,
            cuenta_id=cuenta,
            fecha_movimiento=F("2027-03-15"),
            importe=-IMPORTE,
            clase_movimiento="OPERACION",
        ),
    )
    entrada = servicio_tesoreria.registrar_movimiento(
        contexto,
        DatosMovimiento(
            movimiento_id=entrada_id,
            cuenta_id=cuenta_destino,
            fecha_movimiento=F("2027-03-15"),
            importe=IMPORTE,
            clase_movimiento="OPERACION",
        ),
    )

    version = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )[0]
    version = servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=uuid.uuid4(),
            hecho_id=hecho_id,
            movimiento_tesoreria_id=salida_id,
            importe_asignado=-IMPORTE,
        ),
        hecho_row_version_esperada=version,
        movimiento_row_version_esperada=salida.row_version,
    ).hecho_row_version
    servicio_tesoreria.conciliar(
        contexto,
        DatosConciliacion(
            conciliacion_id=uuid.uuid4(),
            hecho_id=hecho_id,
            movimiento_tesoreria_id=entrada_id,
            importe_asignado=IMPORTE,
        ),
        hecho_row_version_esperada=version,
        movimiento_row_version_esperada=entrada.row_version,
    )

    transferencia_id = uuid.uuid4()
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        cursor.execute(
            "SELECT set_config('gapto.owner_user_id', %s, false)",
            (str(contexto.owner_user_id),),
        )
        cursor.execute(
            "INSERT INTO gapto.transferencias (id, movimiento_salida_id, "
            "movimiento_entrada_id) VALUES (%s, %s, %s)",
            (transferencia_id, salida_id, entrada_id),
        )
        admin.commit()

    return {
        "hecho": hecho_id,
        "salida": salida_id,
        "entrada": entrada_id,
        "transferencia": transferencia_id,
    }


def prevision_de_transferencia(**extra) -> DatosPrevisionManual:
    base = {
        "prevision_id": uuid.uuid4(),
        "concepto": "Traspaso mensual al ahorro",
        "tipo_hecho_codigo": "TRANSFERENCIA",
        "fecha_esperada_desde": F("2027-03-01"),
        "fecha_esperada_hasta": F("2027-03-31"),
        "flujo_tesoreria_esperado": "TRANSFERENCIA",
        "moneda": "EUR",
        "presupuestable": False,
        "importe_esperado": IMPORTE,
    }
    base.update(extra)
    return DatosPrevisionManual(**base)


# ==================================================================
# La realidad montada cumple INV-15
# ==================================================================

def test_la_transferencia_real_cumple_inv15(
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    transferencia_real,
) -> None:
    """Hecho + dos movimientos + fila transferencias + dos conciliaciones.

    Y CERO efectos: la neutralidad es por ausencia, nunca por efectos de
    importe cero, que ademas son fisicamente imposibles.
    """
    hecho_id = transferencia_real["hecho"]
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s), "
        "       (SELECT count(*) FROM gapto.hecho_movimientos_tesoreria "
        "          WHERE hecho_id = %s), "
        "       (SELECT count(*) FROM gapto.transferencias t "
        "          JOIN gapto.hecho_movimientos_tesoreria h "
        "            ON h.movimiento_tesoreria_id = t.movimiento_salida_id "
        "         WHERE h.hecho_id = %s)",
        (hecho_id, hecho_id, hecho_id),
    ) == (0, 2, 1)


# ==================================================================
# INV-16 — la previsión no mueve liquidez
# ==================================================================

def test_una_prevision_de_transferencia_no_mueve_liquidez(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
) -> None:
    """INV-16. El saldo derivado es identico antes y despues.

    Y no nace ningun movimiento: descontar del saldo disponible lo que solo se
    espera es exactamente el contraejemplo que INV-16 prohibe.
    """
    antes_origen = saldo_de(admin, contexto.owner_user_id, cuenta)
    antes_destino = saldo_de(admin, contexto.owner_user_id, cuenta_destino)
    movimientos_antes = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.movimientos_tesoreria m "
        "  JOIN gapto.cuentas c ON c.id = m.cuenta_id WHERE c.owner_user_id = %s",
        (contexto.owner_user_id,),
    )[0]

    datos = prevision_de_transferencia(
        cuenta_salida_esperada_id=cuenta, cuenta_entrada_esperada_id=cuenta_destino
    )
    resultado = servicio_previsiones.crear_manual(contexto, datos)
    assert resultado.estado == ABIERTA

    assert saldo_de(admin, contexto.owner_user_id, cuenta) == antes_origen
    assert saldo_de(admin, contexto.owner_user_id, cuenta_destino) == antes_destino
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.movimientos_tesoreria m "
        "  JOIN gapto.cuentas c ON c.id = m.cuenta_id WHERE c.owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == (movimientos_antes,)


def test_la_prevision_de_transferencia_no_crea_efectos(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Una expectativa de transferencia tampoco anticipa efectos economicos."""
    datos = prevision_de_transferencia()
    servicio_previsiones.crear_manual(contexto, datos)
    # Acotado por tenant: la conexion de verificacion tiene BYPASSRLS y un
    # recuento global veria los hechos de las demas suites.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.hecho_efectos e "
        "          JOIN gapto.hechos_financieros h ON h.id = e.hecho_id "
        "         WHERE h.owner_user_id = %s), "
        "       (SELECT count(*) FROM gapto.transferencias t "
        "          JOIN gapto.movimientos_tesoreria m ON m.id = t.movimiento_salida_id "
        "          JOIN gapto.cuentas c ON c.id = m.cuenta_id "
        "         WHERE c.owner_user_id = %s)",
        (contexto.owner_user_id, contexto.owner_user_id),
    ) == (0, 0)


# ==================================================================
# C-22 completo — OP-17 vincula sin recrear realidad
# ==================================================================

def test_c22_transferencia_prevista(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    cuenta: uuid.UUID,
    cuenta_destino: uuid.UUID,
    transferencia_real,
) -> None:
    """Caso canonico C-22.

    Existe una previsión de transferencia y existe la transferencia real.
    OP-17 las vincula: la unica fila que nace es `prevision_hechos`. No se
    crean movimientos nuevos, ni una segunda fila de `transferencias`, ni
    efectos, y la liquidez no cambia por el hecho de vincular.
    """
    datos = prevision_de_transferencia(
        cuenta_salida_esperada_id=cuenta, cuenta_entrada_esperada_id=cuenta_destino
    )
    servicio_previsiones.crear_manual(contexto, datos)

    antes = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.movimientos_tesoreria m "
        "          JOIN gapto.cuentas c ON c.id = m.cuenta_id "
        "         WHERE c.owner_user_id = %(o)s), "
        "       (SELECT count(*) FROM gapto.transferencias t "
        "          JOIN gapto.movimientos_tesoreria m ON m.id = t.movimiento_salida_id "
        "          JOIN gapto.cuentas c ON c.id = m.cuenta_id "
        "         WHERE c.owner_user_id = %(o)s), "
        "       (SELECT count(*) FROM gapto.hecho_efectos e "
        "          JOIN gapto.hechos_financieros h ON h.id = e.hecho_id "
        "         WHERE h.owner_user_id = %(o)s), "
        "       (SELECT count(*) FROM gapto.hecho_movimientos_tesoreria x "
        "          JOIN gapto.hechos_financieros h ON h.id = x.hecho_id "
        "         WHERE h.owner_user_id = %(o)s)",
        {"o": contexto.owner_user_id},
    )
    saldo_origen = saldo_de(admin, contexto.owner_user_id, cuenta)
    saldo_destino = saldo_de(admin, contexto.owner_user_id, cuenta_destino)

    estado = servicio_previsiones.estado_de(contexto, datos.prevision_id)
    resultado = servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=datos.prevision_id,
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=uuid.uuid4(),
            hecho_id=transferencia_real["hecho"],
            importe_asignado=IMPORTE,
            marcar_realizada=True,
        ),
    )
    assert resultado.estado == REALIZADA

    # Nada de la realidad se ha recreado.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT (SELECT count(*) FROM gapto.movimientos_tesoreria m "
        "          JOIN gapto.cuentas c ON c.id = m.cuenta_id "
        "         WHERE c.owner_user_id = %(o)s), "
        "       (SELECT count(*) FROM gapto.transferencias t "
        "          JOIN gapto.movimientos_tesoreria m ON m.id = t.movimiento_salida_id "
        "          JOIN gapto.cuentas c ON c.id = m.cuenta_id "
        "         WHERE c.owner_user_id = %(o)s), "
        "       (SELECT count(*) FROM gapto.hecho_efectos e "
        "          JOIN gapto.hechos_financieros h ON h.id = e.hecho_id "
        "         WHERE h.owner_user_id = %(o)s), "
        "       (SELECT count(*) FROM gapto.hecho_movimientos_tesoreria x "
        "          JOIN gapto.hechos_financieros h ON h.id = x.hecho_id "
        "         WHERE h.owner_user_id = %(o)s)",
        {"o": contexto.owner_user_id},
    ) == antes
    assert saldo_de(admin, contexto.owner_user_id, cuenta) == saldo_origen
    assert saldo_de(admin, contexto.owner_user_id, cuenta_destino) == saldo_destino

    # Lo unico que nace es el vinculo.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe_asignado) FROM gapto.prevision_hechos "
        "WHERE prevision_id = %s",
        (datos.prevision_id,),
    ) == (1, IMPORTE)


def test_c22_la_transferencia_sigue_sin_efectos_tras_vincular(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
    transferencia_real,
) -> None:
    """INV-15 sobrevive a OP-17: la existencia de previsión solo anade
    `prevision_hechos`."""
    datos = prevision_de_transferencia()
    servicio_previsiones.crear_manual(contexto, datos)
    estado = servicio_previsiones.estado_de(contexto, datos.prevision_id)
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=datos.prevision_id,
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=uuid.uuid4(),
            hecho_id=transferencia_real["hecho"],
            importe_asignado=IMPORTE,
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (transferencia_real["hecho"],),
    ) == (0,)


def test_c22_la_misma_transferencia_no_satisface_dos_veces_la_misma_prevision(
    servicio_previsiones: PrevisionesService,
    contexto: ContextoOperacion,
    transferencia_real,
) -> None:
    """Prohibido materializar dos veces la misma porcion de realidad."""
    datos = prevision_de_transferencia()
    servicio_previsiones.crear_manual(contexto, datos)
    estado = servicio_previsiones.estado_de(contexto, datos.prevision_id)
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=datos.prevision_id,
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=uuid.uuid4(),
            hecho_id=transferencia_real["hecho"],
            importe_asignado=IMPORTE,
        ),
    )
    actual = servicio_previsiones.estado_de(contexto, datos.prevision_id)
    with pytest.raises(ErrorMotor) as excinfo:
        servicio_previsiones.vincular_realidad(
            contexto,
            prevision_id=datos.prevision_id,
            row_version_esperada=actual.row_version,
            datos=DatosVinculo(
                vinculo_id=uuid.uuid4(),
                hecho_id=transferencia_real["hecho"],
                importe_asignado=IMPORTE,
            ),
        )
    assert excinfo.value.codigo is CodigoError.PREVISION_YA_MATERIALIZADA_POR_ESTA_REALIDAD
