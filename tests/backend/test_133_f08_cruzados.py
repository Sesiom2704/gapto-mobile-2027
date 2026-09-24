# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_133_f08_cruzados.py
# Ruta: tests/backend/test_133_f08_cruzados.py
# Descripcion: F04-D042 §15. Escenarios cruzados X-01..X-12.
#
#   Aqui vive el objeto real de F04-08. Cada capacidad se certifico por
#   separado y pasa sus pruebas; lo que estos escenarios buscan es el fallo
#   que solo aparece cuando dos capacidades cerradas se tocan: una operacion
#   valida que deja un estado que otra operacion valida ya no sabe leer.
#
#   El precedente es reciente y caro: F04-07 descubrio que un efecto con
#   reparto COMPLETA tenia el importe inmutable. Ni F04-02 ni F04-06 fallaban
#   por separado. El hueco vivia entre ambas.
# Version: 0.3.0
#   0.3.0 (mandato F04 R1+R2 v0.3 + E01): OP-04 aporta `presupuestable` en la
#   transicion al primer GASTO/INGRESO (A08-bis generalizada); fixtures de
#   GASTO con localizacion DESCONOCIDA en vez de NO_APLICA cuando aplica. Sin
#   cambio de las propiedades probadas.
# Version: 0.2.0
#   0.2.0 (F04-D046 R1 · A19): signo canonico en X-01..X-12 (GASTO +X, atribuciones +X, correccion de
#   reparto +40/+25/+15). X-08: la devolucion declara `presupuestable` (R2).
#   X-12: el recargo es GASTO +12,40 y declara `presupuestable`. Tesoreria intacta.
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
from app.core.modelos_tesoreria import DatosReversion
from app.core.modelos_transferencia import DatosTransferencia
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.compartidos_service import DatosGastoCompartido, DatosTesoreria
from app.services.correcciones_service import DatosAtribucionNueva, DatosCorreccion
from app.services.neto_service import DETERMINADO
from app.services.participantes_service import DatosParticipante
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
    sin_naturaleza,
    valor,
)

CENA = D("44.5000")
MITAD = D("22.2500")


@pytest.fixture()
def motor(unidad: UnidadDeTrabajo) -> Motor:
    return construir_motor(unidad)


def _posicion(motor: Motor, contexto, *, tipo, contraparte, importe, concepto):
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


def _delta(importe, fecha=dt.date(2026, 7, 1)) -> DatosDeltaPosicion:
    return DatosDeltaPosicion(
        hecho_id=uuid.uuid4(),
        efecto_id=uuid.uuid4(),
        vinculo_id=uuid.uuid4(),
        importe=importe,
        fecha_hecho=fecha,
    )


def _gasto_simple(motor: Motor, contexto, importe, concepto="gasto"):
    datos = hecho(concepto=concepto, importe_total=importe)
    creado = motor.hechos.crear_hecho(contexto, datos)
    version = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", importe)],
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    ).row_version
    return datos, version


def _laboratorio(admin: psycopg.Connection, owner: uuid.UUID):
    class _Ctx:
        def __enter__(self):
            self.cursor = admin.cursor()
            self.cursor.execute("RESET ROLE")
            self.cursor.execute("SET ROLE gapto_owner")
            self.cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),)
            )
            return self.cursor

        def __exit__(self, *_):
            self.cursor.execute("RESET ROLE")
            self.cursor.execute("RESET ALL")
            self.cursor.close()
            return False

    return _Ctx()


# ==================================================================
# X-01 · Prevision -> realidad -> movimiento -> conciliacion
# ==================================================================

@cubre(
    cruzados=["X-01"],
    operaciones=["OP-17", "OP-08", "OP-09"],
    invariantes=["INV-16", "INV-12"],
    propiedades=["P-F08-01", "P-F08-02"],
)
def test_x01_prevision_realidad_movimiento_conciliacion(
    motor: Motor, contexto: ContextoOperacion, cuenta, admin
) -> None:
    """La cadena completa de una recurrencia, de la expectativa a la caja.

    Se comprueban las tres fronteras a la vez: la prevision no mueve caja, el
    hecho no implica movimiento, y el movimiento no duplica el gasto.
    """
    importe = D("38.0000")
    prevision_id = uuid.uuid4()
    motor.previsiones.crear_manual(
        contexto,
        DatosPrevisionManual(
            prevision_id=prevision_id,
            concepto="Cuota gimnasio",
            tipo_hecho_codigo="GASTO",
            fecha_esperada_desde=dt.date(2026, 6, 1),
            fecha_esperada_hasta=dt.date(2026, 6, 30),
            flujo_tesoreria_esperado="SALIDA",
            moneda="EUR",
            presupuestable=True,
            importe_esperado=importe,
            cuenta_salida_esperada_id=cuenta,
        ),
    )
    exigir_ausencias(admin, contexto, movimientos=0)

    datos, version = _gasto_simple(motor, contexto, importe, "cuota del gimnasio")
    # El hecho existe y la caja sigue quieta: P-F08-02.
    assert liquidez(admin, contexto.owner_user_id, cuenta) == D("0")

    pieza = movimiento(cuenta, -importe, descripcion="recibo gimnasio")
    mov = motor.tesoreria.registrar_movimiento(contexto, pieza)
    motor.tesoreria.conciliar(
        contexto,
        conciliacion(datos.hecho_id, pieza.movimiento_id, -importe),
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
            importe_asignado=importe,
            marcar_realizada=True,
        ),
    )
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": importe
    }
    assert liquidez(admin, contexto.owner_user_id, cuenta) == -importe


# ==================================================================
# X-02 · Reembolso parcial con saldo vivo
# ==================================================================

@cubre(
    cruzados=["X-02"],
    operaciones=["OP-12", "OP-14", "OP-20"],
    invariantes=["INV-05", "INV-17"],
    propiedades=["P-F08-08", "P-F08-27"],
)
def test_x02_reembolso_parcial_deja_saldo_vivo(
    motor: Motor, contexto: ContextoOperacion, contraparte, cuenta, admin
) -> None:
    """Me devuelven 60 de los 100 que adelantr. Quedan 40 vivos.

    P-F08-27: saldo cero y posicion cerrada son cosas distintas. Aqui el
    saldo baja pero la posicion sigue ACTIVA, y el neto lo refleja sin que
    nadie actualice un total.
    """
    total = D("100.0000")
    cobrado = D("60.0000")
    posicion, alta = _posicion(
        motor,
        contexto,
        tipo=TIPO_DERECHO,
        contraparte=contraparte,
        importe=total,
        concepto="adelanto reembolsable",
    )
    resultado = motor.posiciones.reembolsar(
        contexto,
        entidad_id=posicion.entidad_id,
        entidad_row_version_esperada=alta.entidad_row_version,
        datos=DatosReembolso(
            delta=_delta(cobrado),
            tesoreria=DatosTesoreriaReembolso(
                conciliacion_id=uuid.uuid4(),
                movimiento_id=uuid.uuid4(),
                cuenta_id=cuenta,
                fecha_movimiento=dt.date(2026, 7, 1),
            ),
        ),
    )
    assert resultado.saldo.importe == total - cobrado
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT estado FROM gapto.derechos_obligaciones_financieras "
        "WHERE entidad_id = %s",
        (posicion.entidad_id,),
    ) == ("ACTIVA",)
    segmento = motor.neto.posicion_neta(
        contexto, contraparte_actor_id=contraparte
    ).segmento(contraparte, "EUR")
    assert segmento.neto == D("40.0000")
    assert liquidez(admin, contexto.owner_user_id, cuenta) == cobrado


# ==================================================================
# X-03 · Compra financiada -> deuda -> pago sin gasto nuevo
# ==================================================================

@cubre(
    cruzados=["X-03"],
    operaciones=["OP-15", "OP-16", "OP-12"],
    invariantes=["INV-12"],
    propiedades=["P-F08-09"],
)
def test_x03_compra_financiada_y_pagos_sucesivos(
    motor: Motor, contexto: ContextoOperacion, contraparte, cuenta, admin
) -> None:
    """Tres cuotas seguidas. El gasto total no se mueve ni un euro.

    Una sola cuota podria pasar por casualidad; tres consecutivas demuestran
    que el motor no acumula gasto al amortizar.
    """
    total = D("600.0000")
    cuota = D("100.0000")
    datos = hecho(
        tipo="COMPRA_FINANCIADA", concepto="portatil financiado", importe_total=total
    )
    creado = motor.hechos.crear_hecho(contexto, datos)
    motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", total)],
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    )
    posicion, alta = _posicion(
        motor,
        contexto,
        tipo=TIPO_OBLIGACION,
        contraparte=contraparte,
        importe=total,
        concepto="financiacion del portatil",
    )

    version = alta.entidad_row_version
    for numero in range(3):
        pago = _delta(cuota, fecha=dt.date(2026, 7, 1 + numero))
        resultado = motor.posiciones.reducir_obligacion(
            contexto,
            entidad_id=posicion.entidad_id,
            entidad_row_version_esperada=version,
            delta=pago,
        )
        version = resultado.entidad_row_version
        sin_naturaleza(admin, contexto.owner_user_id, pago.hecho_id, "GASTO")

    assert resultado.saldo.importe == total - 3 * cuota
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT sum(e.importe_delta) FROM gapto.hecho_efectos e "
        "JOIN gapto.hechos_financieros h ON h.id = e.hecho_id "
        "WHERE h.owner_user_id = %s AND e.tipo_efecto = 'GASTO'",
        (contexto.owner_user_id,),
    ) == (total,)


# ==================================================================
# X-04 y X-05 · Gasto compartido y posicion
# ==================================================================

@cubre(
    cruzados=["X-04"],
    operaciones=["OP-19"],
    invariantes=["INV-03", "INV-04"],
    propiedades=["P-F08-07"],
)
def test_x04_diferencia_atribucion_aportacion_no_crea_posicion(
    motor: Motor, contexto: ContextoOperacion, actor_a, actor_b, cuenta, admin
) -> None:
    """Pago 44,50 y soporto 22,25. Nadie me debe nada por eso.

    La diferencia entre lo que pago y lo que soporto puede ser un regalo, un
    acuerdo previo o nada. Convertirla en deuda seria inventar una decision
    economica que nadie tomo.
    """
    datos = hecho(concepto="cena pagada por A", importe_total=CENA)
    pieza_mov = movimiento(cuenta, -CENA, descripcion="cena")
    motor.compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=datos,
            efectos=[
                efecto(
                    "GASTO",
                    CENA,
                    atribuciones=(
                        atribucion(actor_a, MITAD),
                        atribucion(actor_b, MITAD),
                    ),
                )
            ],
            tesoreria=[
                DatosTesoreria(
                    movimiento=pieza_mov,
                    conciliacion=conciliacion(
                        datos.hecho_id, pieza_mov.movimiento_id, -CENA
                    ),
                )
            ],
            aportaciones=[aportacion(CENA, actor_id=actor_a)],
        ),
    )
    exigir_ausencias(admin, contexto, posiciones=0)


@cubre(
    cruzados=["X-05"],
    operaciones=["OP-19", "OP-12", "OP-20"],
    invariantes=["INV-04", "INV-10"],
    propiedades=["P-F08-07", "P-F08-26"],
)
def test_x05_posicion_explicita_posterior_al_gasto_compartido(
    motor: Motor, contexto: ContextoOperacion, actor_a, actor_b, contraparte, admin
) -> None:
    """Despues de la cena se ACUERDA que B devuelve su parte.

    La posicion nace de una decision explicita con su justificacion, no de la
    resta. El neto la lee y no la extingue.
    """
    datos = hecho(concepto="cena compartida", importe_total=CENA)
    motor.compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=datos,
            efectos=[
                efecto(
                    "GASTO",
                    CENA,
                    atribuciones=(
                        atribucion(actor_a, MITAD),
                        atribucion(actor_b, MITAD),
                    ),
                )
            ],
            aportaciones=[aportacion(CENA, actor_id=actor_a)],
        ),
    )
    exigir_ausencias(admin, contexto, posiciones=0)

    posicion, alta = _posicion(
        motor,
        contexto,
        tipo=TIPO_DERECHO,
        contraparte=contraparte,
        importe=MITAD,
        concepto="parte de la cena acordada",
    )
    segmento = motor.neto.posicion_neta(
        contexto, contraparte_actor_id=contraparte
    ).segmento(contraparte, "EUR")
    assert segmento.estado == DETERMINADO and segmento.neto == MITAD
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": CENA
    }


# ==================================================================
# X-06 · Correccion agregada y read-model posterior
# ==================================================================

@cubre(
    cruzados=["X-06"],
    operaciones=["OP-19", "OP-21"],
    invariantes=["INV-01", "INV-07"],
    propiedades=["P-F08-11"],
)
def test_x06_correccion_de_reparto_y_lectura_posterior(
    motor: Motor, contexto: ContextoOperacion, actor_a, actor_b, admin
) -> None:
    """El importe y el reparto eran falsos; se corrigen juntos y se relee.

    El cruce que importa: tras una correccion agregada, el estado que queda
    debe seguir siendo legible por el resto del motor. Un efecto corregido a
    medias dejaria el agregado en un estado que nadie sabe interpretar.
    """
    a = atribucion(actor_a, MITAD)
    b = atribucion(actor_b, MITAD)
    efecto_cena = efecto("GASTO", CENA, atribuciones=(a, b))
    datos = hecho(concepto="cena mal leida", importe_total=CENA)
    resultado = motor.compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(hecho=datos, efectos=[efecto_cena]),
    )

    motor.correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=datos.hecho_id,
            row_version_esperada=resultado.row_version,
            motivo="el ticket eran 40,00 con reparto 25/15",
            efectos_a_actualizar={efecto_cena.efecto_id: {"importe_delta": D("40.0000")}},
            atribuciones_a_actualizar={
                a.atribucion_id: {"importe_atribuido": D("25.0000")},
                b.atribucion_id: {"importe_atribuido": D("15.0000")},
            },
        ),
    )

    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": D("40.0000")
    }
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT e.estado_atribucion, count(a.id), sum(a.importe_atribuido) "
        "FROM gapto.hecho_efectos e "
        "JOIN gapto.efecto_atribuciones a ON a.efecto_id = e.id "
        "WHERE e.hecho_id = %s GROUP BY e.estado_atribucion",
        (datos.hecho_id,),
    ) == ("COMPLETA", 2, D("40.0000"))
    # Un solo hecho: corregir no crea realidad nueva.
    assert contar(
        admin,
        contexto.owner_user_id,
        "hechos_financieros",
        "owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == 1


# ==================================================================
# X-07 · Participante falso retirado
# ==================================================================

@cubre(
    cruzados=["X-07"],
    operaciones=["OP-19"],
    invariantes=["INV-02"],
    propiedades=["P-F08-16", "P-F08-19", "P-F08-22"],
)
def test_x07_retirar_participante_no_toca_el_total(
    motor: Motor, contexto: ContextoOperacion, actor_a, actor_b, admin
) -> None:
    """Pedro nunca estuvo en la cena de ocho. Siguen siendo ocho.

    Retirar a quien nunca estuvo no demuestra que hubiese menos gente: Pedro
    pudo ocupar erroneamente el hueco de uno de los desconocidos.
    """
    participante_b = DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_b)
    datos = hecho(concepto="cena de ocho", importe_total=CENA, participantes_total=8)
    resultado = motor.compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=datos,
            efectos=[efecto("GASTO", CENA)],
            participantes=[
                DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_a),
                participante_b,
            ],
        ),
    )
    retirada = motor.participantes.retirar_participante(
        contexto,
        hecho_id=datos.hecho_id,
        participante_id=participante_b.participante_id,
        row_version_esperada=resultado.row_version,
        motivo="Pedro nunca estuvo en esa cena",
    )
    assert retirada.identificados == 1
    assert retirada.total_declarado == 8
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT accion, datos_antes->>'actor_id' FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ANULAR'",
        (participante_b.participante_id,),
    ) == ("ANULAR", str(actor_b))


# ==================================================================
# X-08 · Devolucion sobre gasto compartido
# ==================================================================

@cubre(
    cruzados=["X-08"],
    operaciones=["OP-19", "OP-13"],
    invariantes=["INV-05", "INV-12"],
    propiedades=["P-F08-10", "P-F08-18"],
)
def test_x08_devolucion_sobre_gasto_compartido(
    motor: Motor, contexto: ContextoOperacion, actor_a, actor_b, admin
) -> None:
    """El restaurante devuelve 10 de la cena repartida al 50 %.

    El gasto compartido conserva sus 44,50 y su reparto intacto; la
    devolucion es un hecho nuevo de naturaleza GASTO, jamas INGRESO.
    """
    datos = hecho(concepto="cena compartida", importe_total=CENA)
    motor.compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=datos,
            efectos=[
                efecto(
                    "GASTO",
                    CENA,
                    atribuciones=(
                        atribucion(actor_a, MITAD),
                        atribucion(actor_b, MITAD),
                    ),
                )
            ],
        ),
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
            importe=D("10.0000"),
            fecha_hecho=dt.date(2026, 6, 10),
            moneda="EUR",
            concepto="devolucion del restaurante",
            presupuestable=True,
        ),
    )
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": CENA
    }
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(a.importe_atribuido) FROM gapto.efecto_atribuciones a "
        "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s",
        (datos.hecho_id,),
    ) == (2, CENA)
    sin_naturaleza(admin, contexto.owner_user_id, devolucion_id, "INGRESO")


# ==================================================================
# X-09 · Transferencia prevista y reversion de una pata
# ==================================================================

@cubre(
    cruzados=["X-09"],
    operaciones=["OP-10", "OP-11", "OP-17"],
    invariantes=["INV-15", "INV-18"],
    propiedades=["P-F08-13", "P-F08-22"],
)
def test_x09_reversion_de_una_pata_no_reescribe_la_transferencia(
    motor: Motor, contexto: ContextoOperacion, cuenta, cuenta_destino, admin
) -> None:
    """El banco devuelve la salida de una transferencia ya registrada.

    La transferencia historica permanece: existio y su rastro no se edita. La
    reversion es un movimiento nuevo, y la transferencia sigue sin efectos
    economicos, antes y despues.
    """
    importe = D("250.0000")
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
        concepto="traspaso",
    )
    motor.transferencias.transferir(contexto, datos)
    assert liquidez(admin, contexto.owner_user_id, cuenta) == -importe

    motor.tesoreria.revertir_movimiento(
        contexto,
        DatosReversion(
            reversion_id=uuid.uuid4(),
            movimiento_original_id=datos.movimiento_salida_id,
            cuenta_id=cuenta,
            fecha_movimiento=dt.date(2026, 6, 3),
            importe=importe,
            descripcion="devolucion de la salida",
        ),
    )

    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT importe, estado FROM gapto.movimientos_tesoreria WHERE id = %s",
        (datos.movimiento_salida_id,),
    ) == (-importe, "ACTIVO")
    assert contar(
        admin,
        contexto.owner_user_id,
        "transferencias t JOIN gapto.movimientos_tesoreria m "
        "ON m.id = t.movimiento_salida_id JOIN gapto.cuentas c ON c.id = m.cuenta_id",
        "c.owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == 1
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {}
    assert liquidez(admin, contexto.owner_user_id, cuenta) == D("0")


# ==================================================================
# X-10 · Multidivisa y posicion: lectura fail-closed
# ==================================================================

@cubre(
    cruzados=["X-10"],
    operaciones=["OP-12", "OP-20"],
    invariantes=["INV-14", "INV-17"],
    propiedades=["P-F08-15"],
)
def test_x10_lectura_fail_closed_ante_incoherencia_monetaria(
    motor: Motor, contexto: ContextoOperacion, contraparte, admin
) -> None:
    """Se corrompe el estado por LABORATORIO y la lectura lo denuncia.

    Los write-paths ya no pueden producir esta incoherencia desde F04-D036,
    de modo que se monta por SQL de laboratorio: es la unica forma de
    demostrar que la lectura no se limita a confiar en ellos. Ignorar la fila
    devolveria 0,00 y sumarla mezclaria EUR con USD; ambas cosas son peores
    que fallar.
    """
    posicion, _ = _posicion(
        motor,
        contexto,
        tipo=TIPO_DERECHO,
        contraparte=contraparte,
        importe=D("100.0000"),
        concepto="derecho en euros",
    )
    with _laboratorio(admin, contexto.owner_user_id) as cursor:
        cursor.execute(
            "UPDATE gapto.hechos_financieros SET moneda = 'USD' WHERE id = %s",
            (posicion.hecho_id,),
        )

    with pytest.raises(ErrorMotor) as excepcion:
        motor.neto.posicion_neta(contexto, contraparte_actor_id=contraparte)
    assert (
        excepcion.value.codigo
        is CodigoError.INVARIANTE_MONETARIA_POSICION_VIOLADA
    )


# ==================================================================
# X-11 · Prevision materializada y correccion posterior
# ==================================================================

@cubre(
    cruzados=["X-11"],
    operaciones=["OP-17", "OP-02"],
    invariantes=["INV-07", "INV-16"],
    propiedades=["P-F08-11"],
)
def test_x11_correccion_posterior_a_la_materializacion(
    motor: Motor, contexto: ContextoOperacion, cuenta, admin
) -> None:
    """Se vinculo la prevision y despues se corrige el hecho.

    El cruce peligroso: corregir un hecho YA vinculado podria tentar al motor
    a crear una segunda realidad o a romper el vinculo. Ni una cosa ni la
    otra: mismo hecho, mismo vinculo, dato corregido.
    """
    importe = D("38.0000")
    prevision_id = uuid.uuid4()
    motor.previsiones.crear_manual(
        contexto,
        DatosPrevisionManual(
            prevision_id=prevision_id,
            concepto="Cuota mensual",
            tipo_hecho_codigo="GASTO",
            fecha_esperada_desde=dt.date(2026, 6, 1),
            fecha_esperada_hasta=dt.date(2026, 6, 30),
            flujo_tesoreria_esperado="SALIDA",
            moneda="EUR",
            presupuestable=True,
            importe_esperado=importe,
            cuenta_salida_esperada_id=cuenta,
        ),
    )
    datos, version = _gasto_simple(motor, contexto, importe, "cuota")
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
    fila = valor(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    )

    motor.hechos.corregir_hecho(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=fila[0],
        campos=CamposCorreccion(concepto="cuota del gimnasio"),
        motivo="el concepto estaba incompleto",
    )

    assert contar(
        admin,
        contexto.owner_user_id,
        "hechos_financieros",
        "owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == 1
    assert contar(
        admin,
        contexto.owner_user_id,
        "prevision_hechos",
        "prevision_id = %s AND hecho_id = %s",
        (prevision_id, datos.hecho_id),
    ) == 1


# ==================================================================
# X-12 · Realidad suplementaria retroactiva
# ==================================================================

@cubre(
    cruzados=["X-12"],
    operaciones=["OP-18"],
    invariantes=["INV-07", "INV-08"],
    propiedades=["P-F08-12"],
)
def test_x12_realidad_suplementaria_con_fecha_economica_propia(
    motor: Motor, contexto: ContextoOperacion, admin
) -> None:
    """Aparece un recargo cuya fecha economica es ANTERIOR al descubrimiento.

    INV-08: la fecha economica es la del acontecimiento, no la de la captura.
    Y OP-18 no exige que la realidad suplementaria sea cronologicamente
    posterior al hecho que ajusta: exige que su fecha este demostrada.
    """
    datos, _ = _gasto_simple(motor, contexto, D("200.0000"), "suministro de junio")
    suplemento_id = uuid.uuid4()
    fecha_economica = dt.date(2026, 5, 28)

    motor.suplementos.registrar(
        contexto,
        DatosSuplemento(
            hecho_id=suplemento_id,
            efecto_id=uuid.uuid4(),
            tipo_efecto="GASTO",
            importe_delta=D("12.4000"),  # recargo: aumenta el gasto
            presupuestable=True,
            fecha_hecho=fecha_economica,
            moneda="EUR",
            fecha_demostrada=True,
            concepto="recargo con fecha anterior",
            relacion_id=uuid.uuid4(),
            hecho_ajustado_id=datos.hecho_id,
        ),
    )

    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s",
        (suplemento_id,),
    ) == (fecha_economica,)
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": D("200.0000")
    }
    assert contar(
        admin,
        contexto.owner_user_id,
        "hecho_relaciones",
        "hecho_origen_id = %s AND hecho_destino_id = %s "
        "AND tipo_relacion = 'CORRIGE_A'",
        (suplemento_id, datos.hecho_id),
    ) == 1
