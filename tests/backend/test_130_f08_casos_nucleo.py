# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_130_f08_casos_nucleo.py
# Ruta: tests/backend/test_130_f08_casos_nucleo.py
# Descripcion: F04-D042. Bateria integral, primer tramo: casos canonicos que
#   se apoyan en hechos, efectos, atribuciones, aportaciones y tesoreria.
#
#     C-01 supermercado          C-05 transferencia propia
#     C-07 intereses de poliza   C-14 nomina
#     C-17 conciliacion parcial  C-18 aportacion no vinculada
#     C-19 conciliaciones multiples
#     C-20 multidivisa
#
#   Cada escenario declara su cobertura con `@cubre` y su oraculo incluye
#   AUSENCIAS: lo que no debe haberse creado vale tanto como lo que si.
# Version: 0.3.0
#   0.3.0 (mandato F04 R1+R2 v0.3 + E01): OP-04 aporta `presupuestable` en la
#   transicion al primer GASTO/INGRESO (A08-bis generalizada); fixtures de
#   GASTO con localizacion DESCONOCIDA en vez de NO_APLICA cuando aplica. Sin
#   cambio de las propiedades probadas.
# Version: 0.2.0
#   0.2.0 (F04-D046 R1 · A19): signo canonico: supermercado, intereses, conciliaciones parciales/multiples,
#   aportacion tardia y multidivisa son GASTO +X con atribuciones +X. Tesoreria
#   y liquidez intactas. Mismas propiedades.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor  # noqa: F401
from app.core.unidad_trabajo import UnidadDeTrabajo
from f08_cobertura import cubre
from f08_motor import (
    D,
    FECHA,
    Motor,
    aportacion,
    atribucion,
    conciliacion,
    construir_motor,
    contar,
    efecto,
    efectos_de,
    exigir_ausencias,
    hecho,
    liquidez,
    movimiento,
    valor,
)


@pytest.fixture()
def motor(unidad: UnidadDeTrabajo) -> Motor:
    return construir_motor(unidad)


# ==================================================================
# C-01 · Supermercado
# ==================================================================

@cubre(
    casos=["C-01"],
    operaciones=["OP-01", "OP-04", "OP-05", "OP-08", "OP-09"],
    invariantes=["INV-01", "INV-11", "INV-18"],
    naturalezas=["GASTO"],
    dimensiones=["D1", "D2", "D3", "D6", "D7"],
    propiedades=["P-F08-02", "P-F08-03"],
)
def test_c01_supermercado(
    motor: Motor, contexto: ContextoOperacion, actor_a, cuenta, admin
) -> None:
    """Compra de 84,30 pagada con tarjeta, atribuida integramente al usuario.

    El caso mas simple del motor y aun asi cruza cinco operaciones. El oraculo
    comprueba las tres capas: realidad economica, caja y conciliacion, y que
    el saldo de la cuenta es DERIVADO de los movimientos, no una columna.
    """
    total = D("84.3000")
    datos = hecho(concepto="compra semanal", importe_total=total)
    creado = motor.hechos.crear_hecho(contexto, datos)

    tras_efectos = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", total, atribuciones=(atribucion(actor_a, total),))],
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    )

    pieza = movimiento(cuenta, -total, descripcion="cargo supermercado")
    resultado_mov = motor.tesoreria.registrar_movimiento(contexto, pieza)
    motor.tesoreria.conciliar(
        contexto,
        conciliacion(datos.hecho_id, pieza.movimiento_id, -total),
        hecho_row_version_esperada=tras_efectos.row_version,
        movimiento_row_version_esperada=resultado_mov.row_version,
    )

    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": total
    }
    assert liquidez(admin, contexto.owner_user_id, cuenta) == -total
    assert contar(
        admin,
        contexto.owner_user_id,
        "hecho_movimientos_tesoreria",
        "hecho_id = %s",
        (datos.hecho_id,),
    ) == 1
    # Un gasto ordinario no genera posicion ni relacion entre hechos.
    exigir_ausencias(admin, contexto, posiciones=0, relaciones=0, transferencias=0)


# ==================================================================
# C-05 · Transferencia propia
# ==================================================================

@cubre(
    casos=["C-05"],
    operaciones=["OP-10"],
    invariantes=["INV-15", "INV-18"],
    dimensiones=["D6", "D7"],
    propiedades=["P-F08-03", "P-F08-13"],
)
def test_c05_transferencia_propia_es_neutral(
    motor: Motor, contexto: ContextoOperacion, cuenta, cuenta_destino, admin
) -> None:
    """Mover 500 entre cuentas propias no es gasto ni ingreso.

    INV-15 se demuestra por AUSENCIA de efectos: la transferencia es neutral
    porque no genera ninguno, no porque genere dos que se anulen. La liquidez
    se desplaza y la suma de ambas cuentas no cambia.
    """
    from app.core.modelos_transferencia import DatosTransferencia

    importe = D("500.0000")
    datos = DatosTransferencia(
        transferencia_id=uuid.uuid4(),
        hecho_id=uuid.uuid4(),
        fecha_hecho=FECHA,
        concepto="traspaso a ahorro",
        cuenta_origen_id=cuenta,
        cuenta_destino_id=cuenta_destino,
        fecha_movimiento=FECHA,
        moneda="EUR",
        importe_salida=importe,
        importe_entrada=importe,
        movimiento_salida_id=uuid.uuid4(),
        movimiento_entrada_id=uuid.uuid4(),
        conciliacion_salida_id=uuid.uuid4(),
        conciliacion_entrada_id=uuid.uuid4(),
    )
    motor.transferencias.transferir(contexto, datos)

    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {}
    assert liquidez(admin, contexto.owner_user_id, cuenta) == -importe
    assert liquidez(admin, contexto.owner_user_id, cuenta_destino) == importe
    exigir_ausencias(admin, contexto, posiciones=0, transferencias=1)


# ==================================================================
# C-07 · Intereses de poliza · C-14 · Nomina
# ==================================================================

@cubre(
    casos=["C-07"],
    operaciones=["OP-01", "OP-04", "OP-08", "OP-09"],
    invariantes=["INV-12"],
    naturalezas=["GASTO"],
    dimensiones=["D2", "D6"],
)
def test_c07_intereses_de_poliza(
    motor: Motor, contexto: ContextoOperacion, cuenta, admin
) -> None:
    """Los intereses son gasto propio; el principal de la poliza no.

    El escenario registra SOLO los intereses. Si el motor hubiese contado
    tambien el dispuesto como gasto, el oraculo economico lo veria.
    """
    intereses = D("11.8100")
    datos = hecho(concepto="intereses de poliza", importe_total=intereses)
    creado = motor.hechos.crear_hecho(contexto, datos)
    tras = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", intereses)],
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    )
    pieza = movimiento(cuenta, -intereses, descripcion="intereses")
    mov = motor.tesoreria.registrar_movimiento(contexto, pieza)
    motor.tesoreria.conciliar(
        contexto,
        conciliacion(datos.hecho_id, pieza.movimiento_id, -intereses),
        hecho_row_version_esperada=tras.row_version,
        movimiento_row_version_esperada=mov.row_version,
    )
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": intereses
    }


@cubre(
    casos=["C-14"],
    operaciones=["OP-01", "OP-04", "OP-05", "OP-08", "OP-09"],
    invariantes=["INV-12", "INV-18"],
    naturalezas=["INGRESO"],
    dimensiones=["D1", "D2", "D3", "D6"],
)
def test_c14_nomina(
    motor: Motor, contexto: ContextoOperacion, actor_a, cuenta, admin
) -> None:
    """Nomina: ingreso real con entrada de caja, atribuido al usuario."""
    neto = D("1850.0000")
    datos = hecho(tipo="INGRESO", concepto="nomina junio", importe_total=neto)
    creado = motor.hechos.crear_hecho(contexto, datos)
    tras = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("INGRESO", neto, atribuciones=(atribucion(actor_a, neto),))],
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    )
    pieza = movimiento(cuenta, neto, descripcion="abono nomina")
    mov = motor.tesoreria.registrar_movimiento(contexto, pieza)
    motor.tesoreria.conciliar(
        contexto,
        conciliacion(datos.hecho_id, pieza.movimiento_id, neto),
        hecho_row_version_esperada=tras.row_version,
        movimiento_row_version_esperada=mov.row_version,
    )
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "INGRESO": neto
    }
    assert liquidez(admin, contexto.owner_user_id, cuenta) == neto
    exigir_ausencias(admin, contexto, posiciones=0)


# ==================================================================
# C-17 · Conciliacion parcial · C-19 · Conciliaciones multiples
# ==================================================================

@cubre(
    casos=["C-17"],
    operaciones=["OP-01", "OP-04", "OP-08", "OP-09"],
    invariantes=["INV-13", "INV-14"],
    dimensiones=["D1", "D6"],
    propiedades=["P-F08-04"],
)
def test_c17_conciliacion_parcial(
    motor: Motor, contexto: ContextoOperacion, cuenta, admin
) -> None:
    """Un gasto de 200 del que solo 120 aparecen todavia en el banco.

    La porcion conciliada es menor que el hecho y eso es un estado VALIDO, no
    un error: importe del hecho y tesoreria observada son dimensiones
    distintas.
    """
    total = D("200.0000")
    parcial = D("120.0000")
    datos = hecho(concepto="gasto conciliado a medias", importe_total=total)
    creado = motor.hechos.crear_hecho(contexto, datos)
    tras = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", total)],
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    )
    pieza = movimiento(cuenta, -parcial, descripcion="cargo parcial")
    mov = motor.tesoreria.registrar_movimiento(contexto, pieza)
    motor.tesoreria.conciliar(
        contexto,
        conciliacion(datos.hecho_id, pieza.movimiento_id, -parcial),
        hecho_row_version_esperada=tras.row_version,
        movimiento_row_version_esperada=mov.row_version,
    )
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": total
    }
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT sum(importe_asignado) FROM gapto.hecho_movimientos_tesoreria "
        "WHERE hecho_id = %s",
        (datos.hecho_id,),
    ) == (-parcial,)


@cubre(
    casos=["C-19"],
    operaciones=["OP-01", "OP-04", "OP-08", "OP-09", "OP-06", "OP-07"],
    invariantes=["INV-13", "INV-14"],
    dimensiones=["D1", "D5", "D6"],
)
def test_c19_conciliaciones_multiples(
    motor: Motor, contexto: ContextoOperacion, actor_a, cuenta, cuenta_destino, admin
) -> None:
    """Un gasto de 300 pagado en dos veces desde cuentas distintas.

    Dos movimientos, dos conciliaciones y una aportacion vinculada a una de
    ellas: el reparto de la financiacion real no se deduce del numero de
    movimientos.
    """
    total = D("300.0000")
    mitad = D("150.0000")
    datos = hecho(concepto="gasto en dos pagos", importe_total=total)
    creado = motor.hechos.crear_hecho(contexto, datos)
    version = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", total)],
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    ).row_version

    conciliaciones = []
    for cuenta_id in (cuenta, cuenta_destino):
        pieza = movimiento(cuenta_id, -mitad, descripcion="pago parcial")
        mov = motor.tesoreria.registrar_movimiento(contexto, pieza)
        datos_conc = conciliacion(datos.hecho_id, pieza.movimiento_id, -mitad)
        resultado = motor.tesoreria.conciliar(
            contexto,
            datos_conc,
            hecho_row_version_esperada=version,
            movimiento_row_version_esperada=mov.row_version,
        )
        version = resultado.hecho_row_version
        conciliaciones.append(datos_conc.conciliacion_id)

    motor.tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=datos.hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[
            aportacion(mitad, actor_id=actor_a, conciliacion_id=conciliaciones[0])
        ],
    )

    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe_asignado) "
        "FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
        (datos.hecho_id,),
    ) == (2, -total)
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), count(hecho_movimiento_tesoreria_id) "
        "FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
        (datos.hecho_id,),
    ) == (1, 1)


# ==================================================================
# C-18 · Aportacion no vinculada
# ==================================================================

@cubre(
    casos=["C-18"],
    operaciones=["OP-06", "OP-07"],
    invariantes=["INV-13", "INV-14"],
    dimensiones=["D5", "D6"],
    propiedades=["P-F08-04"],
)
def test_c18_aportacion_no_vinculada_y_vinculacion_posterior(
    motor: Motor, contexto: ContextoOperacion, actor_a, cuenta, admin
) -> None:
    """Se sabe quien puso el dinero antes de saber en que apunte aparece.

    La aportacion nace sin conciliacion y se vincula despues con OP-07. Es la
    operacion propia que el mandato §10 listaba y que C-18 ejercita: conocer
    la financiacion real no exige conocer todavia la caja.
    """
    total = D("90.0000")
    datos = hecho(concepto="gasto financiado por A", importe_total=total)
    creado = motor.hechos.crear_hecho(contexto, datos)
    version = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", total)],
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    ).row_version

    datos_aportacion = aportacion(total, actor_id=actor_a)
    version = motor.tesoreria.registrar_aportaciones(
        contexto,
        hecho_id=datos.hecho_id,
        hecho_row_version_esperada=version,
        aportaciones=[datos_aportacion],
    ).hecho_row_version
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT hecho_movimiento_tesoreria_id FROM gapto.hecho_aportaciones_pago "
        "WHERE id = %s",
        (datos_aportacion.aportacion_id,),
    ) == (None,)

    pieza = movimiento(cuenta, -total, descripcion="cargo tardio")
    mov = motor.tesoreria.registrar_movimiento(contexto, pieza)
    datos_conc = conciliacion(datos.hecho_id, pieza.movimiento_id, -total)
    resultado = motor.tesoreria.conciliar(
        contexto,
        datos_conc,
        hecho_row_version_esperada=version,
        movimiento_row_version_esperada=mov.row_version,
    )
    motor.tesoreria.vincular_aportacion(
        contexto,
        hecho_id=datos.hecho_id,
        hecho_row_version_esperada=resultado.hecho_row_version,
        aportacion_id=datos_aportacion.aportacion_id,
        destino=datos_conc.conciliacion_id,
    )
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT hecho_movimiento_tesoreria_id FROM gapto.hecho_aportaciones_pago "
        "WHERE id = %s",
        (datos_aportacion.aportacion_id,),
    ) == (datos_conc.conciliacion_id,)


# ==================================================================
# C-20 · Multidivisa
# ==================================================================

@cubre(
    casos=["C-20"],
    operaciones=["OP-01", "OP-04", "OP-08", "OP-09"],
    invariantes=["INV-14"],
    dimensiones=["D1", "D6"],
    propiedades=["P-F08-15"],
)
def test_c20_multidivisa_no_introduce_fx(
    motor: Motor, contexto: ContextoOperacion, cuenta, cuenta_usd, admin
) -> None:
    """Un gasto en USD se concilia contra la cuenta USD, nunca contra la EUR.

    El motor no convierte NUNCA. La demostracion es doble: el importe viaja
    en su propia moneda hasta la cuenta de esa moneda, y la cuenta EUR queda
    intacta. Si existiese conversion implicita, la liquidez en euros se
    habria movido.
    """
    total = D("60.0000")
    datos = hecho(concepto="compra en dolares", importe_total=total, moneda="USD")
    creado = motor.hechos.crear_hecho(contexto, datos)
    version = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", total)],
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    ).row_version

    # El hecho USD se concilia contra la cuenta USD. La cuenta EUR no se toca:
    # si el motor convirtiese, su liquidez se moveria.
    pieza_usd = movimiento(cuenta_usd, -total, descripcion="cargo en dolares")
    mov_usd = motor.tesoreria.registrar_movimiento(contexto, pieza_usd)
    motor.tesoreria.conciliar(
        contexto,
        conciliacion(datos.hecho_id, pieza_usd.movimiento_id, -total),
        hecho_row_version_esperada=version,
        movimiento_row_version_esperada=mov_usd.row_version,
    )
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
        (datos.hecho_id,),
    ) == (1,)
    assert liquidez(admin, contexto.owner_user_id, cuenta_usd) == -total
    assert liquidez(admin, contexto.owner_user_id, cuenta) == D("0")
    # La moneda del hecho y la de la cuenta permanecen separadas: nadie
    # convierte y nadie compara nominalmente 60 USD con 60 EUR.
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT h.moneda, c.moneda FROM gapto.hechos_financieros h "
        "JOIN gapto.hecho_movimientos_tesoreria v ON v.hecho_id = h.id "
        "JOIN gapto.movimientos_tesoreria m ON m.id = v.movimiento_tesoreria_id "
        "JOIN gapto.cuentas c ON c.id = m.cuenta_id WHERE h.id = %s",
        (datos.hecho_id,),
    ) == ("USD", "USD")
