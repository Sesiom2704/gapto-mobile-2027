# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_131_f08_casos_posiciones.py
# Ruta: tests/backend/test_131_f08_casos_posiciones.py
# Descripcion: F04-D042. Bateria integral, segundo tramo: casos canonicos que
#   cruzan posiciones, financiacion, devolucion, prevision, inversion y
#   patrimonio.
#
#     C-02 luz recurrente        C-03 gasoil reembolsable
#     C-04 devolucion parcial    C-06 hipoteca
#     C-08 compra financiada     C-09 alquiler con revision
#     C-15 inversion             C-16 activo patrimonial
#     C-22 transferencia prevista
#
#   Este tramo concentra la mayor parte del riesgo de DOBLE CONTEO: pagar una
#   deuda, cobrar un derecho, materializar una prevision y reconocer una
#   compra financiada son las cuatro situaciones donde el motor podria contar
#   dos veces la misma realidad. Cada oraculo lo comprueba explicitamente.
# Version: 0.2.0
#   0.2.0 (F04-D046 R1 · A19): signo canonico. Compras, gasoil, luz, intereses,
#   alquiler y revision IPC son GASTO +X; la devolucion de C-04 es GASTO -30.
#   Tesoreria y liquidez intactas. R2: devolucion y suplemento declaran
#   `presupuestable`.
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
from app.core.modelos_devolucion import DatosDevolucion
from app.core.modelos_posicion import (
    DatosAltaPosicion,
    DatosDeltaPosicion,
    DatosReembolso,
    DatosTesoreriaReembolso,
    TIPO_DERECHO,
    TIPO_OBLIGACION,
)
from app.core.modelos_prevision import DatosPrevisionManual, DatosVinculo
from app.core.modelos_suplemento import DatosSuplemento
from app.core.modelos_transferencia import DatosTransferencia
from app.core.unidad_trabajo import UnidadDeTrabajo
from f08_cobertura import cubre
from f08_motor import (
    D,
    FECHA,
    Motor,
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
    sin_naturaleza,
    valor,
)


@pytest.fixture()
def motor(unidad: UnidadDeTrabajo) -> Motor:
    return construir_motor(unidad)


def _alta_posicion(
    motor: Motor,
    contexto: ContextoOperacion,
    *,
    tipo: str,
    contraparte: uuid.UUID,
    importe: decimal.Decimal,
    concepto: str,
):
    datos = DatosAltaPosicion(
        entidad_id=uuid.uuid4(),
        nombre=concepto,
        tipo=tipo,
        contraparte_actor_id=contraparte,
        moneda="EUR",
        justificacion="DECISION_EXPLICITA",
        fecha_inicio_seguimiento=FECHA,
        saldo_apertura=D("0"),
        hecho_id=uuid.uuid4(),
        fecha_hecho=FECHA,
        concepto=concepto,
        efecto_id=uuid.uuid4(),
        vinculo_id=uuid.uuid4(),
        importe_inicial=importe,
    )
    return datos, motor.posiciones.crear_posicion(contexto, datos)


def _delta(importe: decimal.Decimal) -> DatosDeltaPosicion:
    return DatosDeltaPosicion(
        hecho_id=uuid.uuid4(),
        efecto_id=uuid.uuid4(),
        vinculo_id=uuid.uuid4(),
        importe=importe,
        fecha_hecho=dt.date(2026, 7, 1),
    )


# ==================================================================
# C-02 · Luz recurrente
# ==================================================================

@cubre(
    casos=["C-02"],
    operaciones=["OP-01", "OP-04", "OP-08", "OP-09", "OP-17"],
    invariantes=["INV-12", "INV-16"],
    naturalezas=["GASTO"],
    dimensiones=["D1", "D4", "D6"],
    propiedades=["P-F08-01"],
)
def test_c02_luz_recurrente_prevision_y_realidad(
    motor: Motor, contexto: ContextoOperacion, cuenta, admin
) -> None:
    """Se preveia la factura de la luz y llego.

    Dos comprobaciones de doble conteo. Antes de materializar, la prevision
    no ha movido ni un euro. Despues de vincular, existe UN solo gasto: la
    realidad no se suma a la expectativa, la explica.
    """
    esperado = D("62.0000")
    real = D("64.3500")
    prevision_id = uuid.uuid4()
    motor.previsiones.crear_manual(
        contexto,
        DatosPrevisionManual(
            prevision_id=prevision_id,
            concepto="Luz mensual",
            tipo_hecho_codigo="GASTO",
            fecha_esperada_desde=dt.date(2026, 6, 1),
            fecha_esperada_hasta=dt.date(2026, 6, 30),
            flujo_tesoreria_esperado="SALIDA",
            moneda="EUR",
            presupuestable=True,
            importe_esperado=esperado,
            cuenta_salida_esperada_id=cuenta,
        ),
    )
    # INV-16 / P-F08-01: una prevision no toca liquidez.
    assert liquidez(admin, contexto.owner_user_id, cuenta) == D("0")
    exigir_ausencias(admin, contexto, movimientos=0)

    datos = hecho(concepto="factura de la luz", importe_total=real)
    creado = motor.hechos.crear_hecho(contexto, datos)
    version = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", real)],
    ).row_version
    pieza = movimiento(cuenta, -real, descripcion="recibo luz")
    mov = motor.tesoreria.registrar_movimiento(contexto, pieza)
    motor.tesoreria.conciliar(
        contexto,
        conciliacion(datos.hecho_id, pieza.movimiento_id, -real),
        hecho_row_version_esperada=version,
        movimiento_row_version_esperada=mov.row_version,
    )

    estado = motor.previsiones.estado_de(contexto, prevision_id)
    motor.previsiones.vincular_realidad(
        contexto,
        prevision_id=prevision_id,
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=uuid.uuid4(),
            hecho_id=datos.hecho_id,
            importe_asignado=real,
            marcar_realizada=True,
        ),
    )

    # INV-12: un solo gasto, del importe REAL. La desviacion frente a los
    # 62,00 previstos es desviacion, no un segundo hecho.
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": real
    }
    assert contar(
        admin,
        contexto.owner_user_id,
        "hechos_financieros",
        "owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == 1
    assert liquidez(admin, contexto.owner_user_id, cuenta) == -real


# ==================================================================
# C-03 · Gasoil reembolsable
# ==================================================================

@cubre(
    casos=["C-03"],
    operaciones=["OP-01", "OP-04", "OP-05", "OP-08", "OP-09", "OP-12", "OP-14"],
    invariantes=["INV-05", "INV-12", "INV-17"],
    naturalezas=["GASTO", "DERECHO_COBRO"],
    dimensiones=["D2", "D3", "D6", "D7"],
    propiedades=["P-F08-08", "P-F08-10"],
)
def test_c03_gasoil_reembolsable(
    motor: Motor, contexto: ContextoOperacion, actor_a, contraparte, cuenta, admin
) -> None:
    """Adelanto 80 de gasoil que la empresa me reembolsara.

    El cobro del derecho NO es un INGRESO: reduce el derecho y aumenta la
    liquidez. Si el motor lo tratase como ingreso, el resultado del periodo
    subiria 80 sin que nadie haya ganado nada.
    """
    total = D("80.0000")
    datos = hecho(concepto="gasoil de trabajo", importe_total=total)
    creado = motor.hechos.crear_hecho(contexto, datos)
    version = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", total, atribuciones=(atribucion(actor_a, total),))],
    ).row_version
    pieza = movimiento(cuenta, -total, descripcion="gasolinera")
    mov = motor.tesoreria.registrar_movimiento(contexto, pieza)
    motor.tesoreria.conciliar(
        contexto,
        conciliacion(datos.hecho_id, pieza.movimiento_id, -total),
        hecho_row_version_esperada=version,
        movimiento_row_version_esperada=mov.row_version,
    )

    posicion, alta = _alta_posicion(
        motor,
        contexto,
        tipo=TIPO_DERECHO,
        contraparte=contraparte,
        importe=total,
        concepto="reembolso de gasoil",
    )
    assert alta.saldo.conocido and alta.saldo.importe == total

    cobro = _delta(total)
    resultado = motor.posiciones.reembolsar(
        contexto,
        entidad_id=posicion.entidad_id,
        entidad_row_version_esperada=alta.entidad_row_version,
        datos=DatosReembolso(
            delta=cobro,
            tesoreria=DatosTesoreriaReembolso(
                conciliacion_id=uuid.uuid4(),
                movimiento_id=uuid.uuid4(),
                cuenta_id=cuenta,
                fecha_movimiento=dt.date(2026, 7, 1),
            ),
        ),
    )
    assert resultado.saldo.conocido and resultado.saldo.importe == D("0")
    # P-F08-08: cobrar un derecho no crea INGRESO.
    sin_naturaleza(admin, contexto.owner_user_id, cobro.hecho_id, "INGRESO")
    assert liquidez(admin, contexto.owner_user_id, cuenta) == D("0")


# ==================================================================
# C-04 · Devolucion parcial
# ==================================================================

@cubre(
    casos=["C-04"],
    operaciones=["OP-01", "OP-04", "OP-08", "OP-09", "OP-13"],
    invariantes=["INV-05", "INV-06", "INV-12"],
    naturalezas=["GASTO"],
    dimensiones=["D1", "D2"],
    propiedades=["P-F08-10"],
)
def test_c04_devolucion_parcial(
    motor: Motor, contexto: ContextoOperacion, cuenta, admin
) -> None:
    """Devuelven 30 de una compra de 120. El gasto original no se toca.

    La devolucion es un GASTO positivo —reduce la misma naturaleza— y cuelga
    del original por DEVOLUCION_DE. Nunca es INGRESO: nadie ha ganado 30.
    """
    total = D("120.0000")
    devuelto = D("30.0000")
    datos = hecho(concepto="compra con devolucion", importe_total=total)
    creado = motor.hechos.crear_hecho(contexto, datos)
    version = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", total)],
    ).row_version
    pieza = movimiento(cuenta, -total, descripcion="compra")
    mov = motor.tesoreria.registrar_movimiento(contexto, pieza)
    motor.tesoreria.conciliar(
        contexto,
        conciliacion(datos.hecho_id, pieza.movimiento_id, -total),
        hecho_row_version_esperada=version,
        movimiento_row_version_esperada=mov.row_version,
    )

    devolucion_id = uuid.uuid4()
    motor.devoluciones.devolver(
        contexto,
        DatosDevolucion(
            hecho_id=devolucion_id,
            efecto_id=uuid.uuid4(),
            relacion_id=uuid.uuid4(),
            hecho_original_id=datos.hecho_id,
            tipo_efecto="GASTO",
            importe=devuelto,
            presupuestable=True,
            fecha_hecho=dt.date(2026, 6, 20),
            moneda="EUR",
            concepto="devolucion parcial",
        ),
    )

    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": total
    }
    assert efectos_de(admin, contexto.owner_user_id, devolucion_id) == {
        "GASTO": -devuelto
    }
    sin_naturaleza(admin, contexto.owner_user_id, devolucion_id, "INGRESO")
    assert contar(
        admin,
        contexto.owner_user_id,
        "hecho_relaciones",
        "hecho_origen_id = %s AND hecho_destino_id = %s "
        "AND tipo_relacion = 'DEVOLUCION_DE'",
        (devolucion_id, datos.hecho_id),
    ) == 1
    # Reconocer la devolucion no mueve caja por si sola.
    assert liquidez(admin, contexto.owner_user_id, cuenta) == -total


# ==================================================================
# C-06 · Hipoteca · C-08 · Compra financiada
# ==================================================================

@cubre(
    casos=["C-06"],
    operaciones=["OP-01", "OP-04", "OP-08", "OP-09", "OP-12", "OP-16"],
    invariantes=["INV-12"],
    naturalezas=["GASTO", "DEUDA"],
    dimensiones=["D2", "D6", "D7"],
    propiedades=["P-F08-09"],
)
def test_c06_hipoteca_cuota_separa_capital_e_intereses(
    motor: Motor, contexto: ContextoOperacion, contraparte, cuenta, admin
) -> None:
    """Cuota de 400: 340 de capital y 60 de intereses.

    OP-16 no tiene servicio propio: es la composicion de reducir la
    obligacion por el capital mas reconocer el gasto por los intereses. Lo
    que el oraculo vigila es que el CAPITAL no vuelva a ser gasto: ese gasto
    ya se reconocio cuando nacio la deuda.
    """
    principal = D("1000.0000")
    capital = D("340.0000")
    intereses = D("60.0000")

    posicion, alta = _alta_posicion(
        motor,
        contexto,
        tipo=TIPO_OBLIGACION,
        contraparte=contraparte,
        importe=principal,
        concepto="hipoteca",
    )

    pago = _delta(capital)
    resultado = motor.posiciones.reducir_obligacion(
        contexto,
        entidad_id=posicion.entidad_id,
        entidad_row_version_esperada=alta.entidad_row_version,
        delta=pago,
    )
    assert resultado.saldo.importe == principal - capital
    sin_naturaleza(admin, contexto.owner_user_id, pago.hecho_id, "GASTO")

    datos = hecho(concepto="intereses de la cuota", importe_total=intereses)
    creado = motor.hechos.crear_hecho(contexto, datos)
    version = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", intereses)],
    ).row_version
    pieza = movimiento(cuenta, -(capital + intereses), descripcion="cuota hipoteca")
    mov = motor.tesoreria.registrar_movimiento(contexto, pieza)
    motor.tesoreria.conciliar(
        contexto,
        conciliacion(datos.hecho_id, pieza.movimiento_id, -intereses),
        hecho_row_version_esperada=version,
        movimiento_row_version_esperada=mov.row_version,
    )

    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": intereses
    }
    assert liquidez(admin, contexto.owner_user_id, cuenta) == -(capital + intereses)


@cubre(
    casos=["C-08"],
    operaciones=["OP-01", "OP-04", "OP-15", "OP-16", "OP-12"],
    invariantes=["INV-12"],
    naturalezas=["GASTO", "DEUDA"],
    dimensiones=["D1", "D2", "D6"],
    propiedades=["P-F08-09"],
)
def test_c08_compra_financiada_reconoce_el_gasto_una_sola_vez(
    motor: Motor, contexto: ContextoOperacion, contraparte, cuenta, admin
) -> None:
    """Movil de 1.349 financiado en 24 cuotas.

    OP-15 es un hecho `COMPRA_FINANCIADA` con el gasto integro; la deuda vive
    en su propia posicion. Las cuotas posteriores reducen deuda y liquidez
    con CERO gasto nuevo: si cada cuota volviese a ser gasto, el movil habria
    costado el doble.
    """
    total = D("1349.0400")
    cuota = D("56.2100")

    datos = hecho(
        tipo="COMPRA_FINANCIADA", concepto="movil financiado", importe_total=total
    )
    creado = motor.hechos.crear_hecho(contexto, datos)
    motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", total)],
    )
    posicion, alta = _alta_posicion(
        motor,
        contexto,
        tipo=TIPO_OBLIGACION,
        contraparte=contraparte,
        importe=total,
        concepto="financiacion del movil",
    )

    pago = _delta(cuota)
    resultado = motor.posiciones.reducir_obligacion(
        contexto,
        entidad_id=posicion.entidad_id,
        entidad_row_version_esperada=alta.entidad_row_version,
        delta=pago,
    )

    assert resultado.saldo.importe == total - cuota
    sin_naturaleza(admin, contexto.owner_user_id, pago.hecho_id, "GASTO")
    # El gasto total del tenant sigue siendo el de la compra, ni un euro mas.
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT sum(e.importe_delta) FROM gapto.hecho_efectos e "
        "JOIN gapto.hechos_financieros h ON h.id = e.hecho_id "
        "WHERE h.owner_user_id = %s AND e.tipo_efecto = 'GASTO'",
        (contexto.owner_user_id,),
    ) == (total,)


# ==================================================================
# C-09 · Alquiler con revision
# ==================================================================

@cubre(
    casos=["C-09"],
    operaciones=["OP-01", "OP-04", "OP-18"],
    invariantes=["INV-07", "INV-08"],
    naturalezas=["GASTO"],
    dimensiones=["D1", "D2"],
    propiedades=["P-F08-11", "P-F08-12"],
)
def test_c09_alquiler_con_revision_es_realidad_nueva(
    motor: Motor, contexto: ContextoOperacion, admin
) -> None:
    """La revision del IPC llega despues y se cobra aparte.

    INV-07: esto NO es corregir el alquiler de junio, que fue exactamente lo
    que se pago. Es una realidad posterior con su propia fecha economica, y
    por eso nace como hecho nuevo relacionado, no como edicion del anterior.
    """
    renta = D("650.0000")
    revision = D("18.5000")

    datos = hecho(concepto="alquiler de junio", importe_total=renta)
    creado = motor.hechos.crear_hecho(contexto, datos)
    motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", renta)],
    )

    suplemento_id = uuid.uuid4()
    motor.suplementos.registrar(
        contexto,
        DatosSuplemento(
            hecho_id=suplemento_id,
            efecto_id=uuid.uuid4(),
            tipo_efecto="GASTO",
            importe_delta=revision,  # revision IPC: aumenta el coste
            presupuestable=True,
            fecha_hecho=dt.date(2026, 7, 15),
            moneda="EUR",
            fecha_demostrada=True,
            concepto="revision IPC del alquiler",
            relacion_id=uuid.uuid4(),
            hecho_ajustado_id=datos.hecho_id,
        ),
    )

    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": renta
    }
    assert efectos_de(admin, contexto.owner_user_id, suplemento_id) == {
        "GASTO": revision
    }
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s",
        (suplemento_id,),
    ) == (dt.date(2026, 7, 15),)
    assert contar(
        admin,
        contexto.owner_user_id,
        "hecho_relaciones",
        "hecho_origen_id = %s AND tipo_relacion = 'CORRIGE_A'",
        (suplemento_id,),
    ) == 1


# ==================================================================
# C-15 · Inversion · C-16 · Activo patrimonial
# ==================================================================

@cubre(
    casos=["C-15"],
    operaciones=["OP-01", "OP-04"],
    invariantes=["INV-12"],
    naturalezas=["INVERSION"],
    dimensiones=["D2", "D6"],
)
def test_c15_aportacion_a_inversion_no_es_gasto(
    motor: Motor, contexto: ContextoOperacion, cuenta, admin
) -> None:
    """Aportar 184,13 a un fondo mueve caja y NO es gasto.

    El dinero cambia de sitio, no desaparece. Sin asignaciones a posiciones
    concretas D-080 no exige inversion principal, de modo que el efecto puede
    existir con el reparto pendiente.
    """
    aporte = D("184.1300")
    datos = hecho(
        tipo="APORTACION_INVERSION", concepto="aportacion al fondo",
        importe_total=aporte,
    )
    creado = motor.hechos.crear_hecho(contexto, datos)
    version = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("INVERSION", aporte)],
    ).row_version
    pieza = movimiento(cuenta, -aporte, descripcion="aportacion fondo")
    mov = motor.tesoreria.registrar_movimiento(contexto, pieza)
    motor.tesoreria.conciliar(
        contexto,
        conciliacion(datos.hecho_id, pieza.movimiento_id, -aporte),
        hecho_row_version_esperada=version,
        movimiento_row_version_esperada=mov.row_version,
    )

    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "INVERSION": aporte
    }
    sin_naturaleza(admin, contexto.owner_user_id, datos.hecho_id, "GASTO")
    assert liquidez(admin, contexto.owner_user_id, cuenta) == -aporte


@cubre(
    casos=["C-16"],
    operaciones=["OP-01", "OP-04"],
    invariantes=["INV-09"],
    naturalezas=["VALOR_ACTIVO"],
    dimensiones=["D2"],
)
def test_c16_valor_activo_solo_por_acontecimiento_real(
    motor: Motor, contexto: ContextoOperacion, admin
) -> None:
    """`VALOR_ACTIVO` registra una adquisicion, no una tasacion.

    INV-09: el efecto exige declarar el ACONTECIMIENTO real que produce el
    delta patrimonial —aqui `ADQUISICION`—. Una tasacion no es un
    acontecimiento y el motor la rechaza: se comprueba en el negativo, porque
    una invariante de este tipo se demuestra por lo que impide.
    """
    valor_compra = D("110000.0000")
    datos = hecho(concepto="compra de vivienda", importe_total=valor_compra)
    creado = motor.hechos.crear_hecho(contexto, datos)
    motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[
            efecto("VALOR_ACTIVO", valor_compra, acontecimiento="ADQUISICION")
        ],
    )
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "VALOR_ACTIVO": valor_compra
    }
    sin_naturaleza(admin, contexto.owner_user_id, datos.hecho_id, "GASTO")

    # El negativo: una revalorizacion no es acontecimiento y no puede entrar.
    tasacion = hecho(concepto="tasacion anual", importe_total=D("5000.0000"))
    creada = motor.hechos.crear_hecho(contexto, tasacion)
    with pytest.raises(ErrorMotor) as excepcion:
        motor.efectos.registrar_efectos(
            contexto,
            hecho_id=tasacion.hecho_id,
            row_version_esperada=creada.row_version,
            efectos=[efecto("VALOR_ACTIVO", D("5000.0000"))],
        )
    assert excepcion.value.codigo is CodigoError.VALOR_ACTIVO_SIN_ACONTECIMIENTO


# ==================================================================
# C-22 · Transferencia prevista
# ==================================================================

@cubre(
    casos=["C-22"],
    operaciones=["OP-10", "OP-17"],
    invariantes=["INV-15", "INV-16"],
    dimensiones=["D4", "D6"],
    propiedades=["P-F08-01", "P-F08-13"],
)
def test_c22_transferencia_prevista_sigue_sin_efectos_tras_vincular(
    motor: Motor, contexto: ContextoOperacion, cuenta, cuenta_destino, admin
) -> None:
    """Se preveia el traspaso mensual a ahorro y se hizo.

    Doble invariante en un solo escenario: la prevision no movio liquidez
    antes, y vincularla no le fabrica efectos despues. Una transferencia
    prevista y realizada sigue siendo economicamente neutra.
    """
    importe = D("500.0000")
    prevision_id = uuid.uuid4()
    motor.previsiones.crear_manual(
        contexto,
        DatosPrevisionManual(
            prevision_id=prevision_id,
            concepto="Traspaso mensual a ahorro",
            tipo_hecho_codigo="TRANSFERENCIA",
            fecha_esperada_desde=dt.date(2026, 6, 1),
            fecha_esperada_hasta=dt.date(2026, 6, 30),
            flujo_tesoreria_esperado="TRANSFERENCIA",
            moneda="EUR",
            presupuestable=False,
            importe_esperado=importe,
            cuenta_salida_esperada_id=cuenta,
            cuenta_entrada_esperada_id=cuenta_destino,
        ),
    )
    assert liquidez(admin, contexto.owner_user_id, cuenta) == D("0")

    datos = DatosTransferencia(
        transferencia_id=uuid.uuid4(),
        hecho_id=uuid.uuid4(),
        movimiento_salida_id=uuid.uuid4(),
        movimiento_entrada_id=uuid.uuid4(),
        conciliacion_salida_id=uuid.uuid4(),
        conciliacion_entrada_id=uuid.uuid4(),
        cuenta_origen_id=cuenta,
        cuenta_destino_id=cuenta_destino,
        fecha_hecho=FECHA,
        fecha_movimiento=FECHA,
        moneda="EUR",
        importe_salida=importe,
        importe_entrada=importe,
        concepto="traspaso mensual",
    )
    motor.transferencias.transferir(contexto, datos)

    estado = motor.previsiones.estado_de(contexto, prevision_id)
    motor.previsiones.vincular_realidad(
        contexto,
        prevision_id=prevision_id,
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=uuid.uuid4(),
            hecho_id=datos.hecho_id,
            importe_asignado=importe,
            marcar_realizada=True,
        ),
    )

    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {}
    assert liquidez(admin, contexto.owner_user_id, cuenta) == -importe
    assert liquidez(admin, contexto.owner_user_id, cuenta_destino) == importe
    assert contar(
        admin,
        contexto.owner_user_id,
        "prevision_hechos",
        "prevision_id = %s AND hecho_id = %s",
        (prevision_id, datos.hecho_id),
    ) == 1
