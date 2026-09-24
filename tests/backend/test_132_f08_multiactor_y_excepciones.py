# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_132_f08_multiactor_y_excepciones.py
# Ruta: tests/backend/test_132_f08_multiactor_y_excepciones.py
# Descripcion: F04-D042. Bateria integral, tercer tramo.
#
#     C-10 propiedad compartida   C-11 cena compartida
#     C-12 neteo peluqueria+cena (GATE)
#     C-13 cuenta compartida      C-21 aportaciones multi-actor
#     E-01 correccion             E-02 anulacion
#     E-03 reversion de tesoreria
#
#   Los cinco casos multi-actor existen como unidad en las suites de F04-07,
#   pero el mandato §8 exige que el ESCENARIO INTEGRAL exista como tal: no
#   basta con que varias pruebas aisladas cubran sus piezas. Aqui se
#   construyen extremo a extremo y su oraculo mira el agregado completo.
#
#   E-01/E-02/E-03 cubren las tres operaciones que ningun caso canonico
#   ejercita: OP-02, OP-03 y OP-11.
# Version: 0.3.0
#   0.3.0 (mandato F04 R1+R2 v0.3 + E01): E-01 excluye la auditoria de
#   activacion A08-bis y aporta la decision en OP-04.
# Version: 0.2.0
#   0.2.0 (F04-D046 R1 · A19 + A19-bis): signo canonico en C-10/C-11/C-13/C-21
#   y E-01 (GASTO +X, atribuciones +X; tesoreria intacta). C-12 se SUSTITUYE
#   por el caso canonico de Project Memory: peluqueria 15 pagada por la pareja
#   con obligacion explicita; cena 44,50 pagada por el usuario con atribucion
#   explicita de la pareja 15, sin 29,50 por resta, y derecho explicito 15;
#   OP-20 neto 0 sin escribir nada. La version anterior modelaba solo
#   posiciones y con la direccion invertida.
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
from app.core.modelos_posicion import (
    DatosAltaPosicion,
    TIPO_DERECHO,
    TIPO_OBLIGACION,
)
from app.core.modelos_tesoreria import DatosReversion
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.compartidos_service import DatosGastoCompartido, DatosTesoreria
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
    valor,
)

CENA = D("44.5000")
MITAD = D("22.2500")
PELUQUERIA = D("15.0000")


@pytest.fixture()
def motor(unidad: UnidadDeTrabajo) -> Motor:
    return construir_motor(unidad)


def _laboratorio(admin: psycopg.Connection, owner: uuid.UUID):
    """Cursor administrativo para fixtures que el motor no escribe.

    Participaciones de cuenta y de entidad son configuracion, no operaciones
    del motor: ningun servicio las crea. Montarlas por SQL es fixture de
    infraestructura, no un atajo para hacer pasar un escenario.
    """

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


def _propiedad_compartida(admin, owner, actor_a, actor_b) -> uuid.UUID:
    entidad_id = uuid.uuid4()
    with _laboratorio(admin, owner) as cursor:
        cursor.execute("BEGIN")
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")
        cursor.execute(
            "INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
            "VALUES (%s, %s, 'PROPIEDAD', 'Vivienda compartida')",
            (entidad_id, owner),
        )
        cursor.execute(
            "INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad) "
            "VALUES (%s, 'VIVIENDA')",
            (entidad_id,),
        )
        for actor in (actor_a, actor_b):
            cursor.execute(
                "INSERT INTO gapto.entidad_participaciones "
                "(id, entidad_id, actor_id, porcentaje, vigente_desde) "
                "VALUES (%s, %s, %s, 50, CURRENT_DATE)",
                (uuid.uuid4(), entidad_id, actor),
            )
        cursor.execute("COMMIT")
    return entidad_id


def _cuenta_compartida(admin, owner, cuenta, actor_a, actor_b) -> None:
    with _laboratorio(admin, owner) as cursor:
        cursor.execute("BEGIN")
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")
        for actor in (actor_a, actor_b):
            cursor.execute(
                "INSERT INTO gapto.cuenta_participaciones "
                "(id, cuenta_id, actor_id, porcentaje, vigente_desde) "
                "VALUES (%s, %s, %s, 50, CURRENT_DATE)",
                (uuid.uuid4(), cuenta, actor),
            )
        cursor.execute("COMMIT")


def _posicion(
    motor: Motor, contexto, *, tipo: str, contraparte, importe, concepto: str
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


# ==================================================================
# C-10 · Propiedad compartida
# ==================================================================

@cubre(
    casos=["C-10"],
    operaciones=["OP-19", "OP-06", "OP-08", "OP-09"],
    invariantes=["INV-03", "INV-04", "INV-13"],
    naturalezas=["GASTO"],
    dimensiones=["D1", "D3", "D5", "D8"],
    propiedades=["P-F08-06", "P-F08-07", "P-F08-18"],
)
def test_c10_propiedad_compartida(
    motor: Motor, contexto: ContextoOperacion, owner, actor_a, actor_b, cuenta, admin
) -> None:
    """Derrama de 300 de una vivienda al 50 %, pagada entera por A.

    Tres dimensiones que no se deducen entre si: la propiedad es de dos, el
    gasto se atribuye mitad y mitad, y el dinero lo pone uno solo. Que A haya
    pagado 300 y soporte 150 NO crea ningun derecho frente a B: eso exige una
    decision economica explicita que aqui nadie ha tomado.
    """
    derrama = D("300.0000")
    mitad = D("150.0000")
    _propiedad_compartida(admin, owner, actor_a, actor_b)

    datos = hecho(concepto="derrama de la comunidad", importe_total=derrama)
    pieza_mov = movimiento(cuenta, -derrama, descripcion="derrama")
    pieza = DatosTesoreria(
        movimiento=pieza_mov,
        conciliacion=conciliacion(datos.hecho_id, pieza_mov.movimiento_id, -derrama),
    )
    motor.compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=datos,
            efectos=[
                efecto(
                    "GASTO",
                    derrama,
                    atribuciones=(
                        atribucion(actor_a, mitad, criterio="PARTICIPACION_ENTIDAD"),
                        atribucion(actor_b, mitad, criterio="PARTICIPACION_ENTIDAD"),
                    ),
                )
            ],
            tesoreria=[pieza],
            aportaciones=[aportacion(derrama, actor_id=actor_a)],
        ),
    )

    # El hecho conserva el 100 %: un solo hecho de 300, no dos de 150.
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": derrama
    }
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(a.importe_atribuido) FROM gapto.efecto_atribuciones a "
        "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s",
        (datos.hecho_id,),
    ) == (2, derrama)
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT count(DISTINCT actor_id) FROM gapto.hecho_aportaciones_pago "
        "WHERE hecho_id = %s",
        (datos.hecho_id,),
    ) == (1,)
    exigir_ausencias(admin, contexto, posiciones=0)


# ==================================================================
# C-11 · Cena compartida
# ==================================================================

@cubre(
    casos=["C-11"],
    operaciones=["OP-19"],
    invariantes=["INV-01", "INV-02"],
    naturalezas=["GASTO"],
    dimensiones=["D1", "D3"],
    propiedades=["P-F08-17", "P-F08-18", "P-F08-19"],
)
def test_c11_cena_compartida_con_reparto_desconocido(
    motor: Motor, contexto: ContextoOperacion, actor_a, actor_b, admin
) -> None:
    """Cena de cuatro de los que solo se conocen dos, y solo una parte.

    INV-02 en su forma pura: lo desconocido NO es cero. El efecto queda
    PARCIAL con las dos partes conocidas, el total declara cuatro comensales
    y nadie inventa el reparto de los otros dos ni crea actores ficticios.
    """
    datos = hecho(
        concepto="cena del grupo", importe_total=CENA, participantes_total=4
    )
    motor.compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=datos,
            efectos=[
                efecto(
                    "GASTO",
                    CENA,
                    estado="PARCIAL",
                    atribuciones=(
                        atribucion(actor_a, D("11.1250")),
                        atribucion(actor_b, D("11.1250")),
                    ),
                )
            ],
            participantes=[
                DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_a),
                DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_b),
            ],
        ),
    )

    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT e.estado_atribucion, count(a.id), sum(a.importe_atribuido) "
        "FROM gapto.hecho_efectos e "
        "LEFT JOIN gapto.efecto_atribuciones a ON a.efecto_id = e.id "
        "WHERE e.hecho_id = %s GROUP BY e.estado_atribucion",
        (datos.hecho_id,),
    ) == ("PARCIAL", 2, MITAD)
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT numero_participantes_total FROM gapto.hechos_financieros "
        "WHERE id = %s",
        (datos.hecho_id,),
    ) == (4,)
    # Participar no es soportar: dos identificados, dos atribuciones, cero
    # deuda entre ellos.
    assert contar(
        admin,
        contexto.owner_user_id,
        "hecho_participantes",
        "hecho_id = %s",
        (datos.hecho_id,),
    ) == 2
    exigir_ausencias(admin, contexto, posiciones=0)


# ==================================================================
# C-12 · GATE · neteo peluqueria + cena
# ==================================================================

@cubre(
    casos=["C-12"],
    operaciones=["OP-01", "OP-04", "OP-05", "OP-06", "OP-08", "OP-09", "OP-12", "OP-19", "OP-20"],
    invariantes=["INV-02", "INV-03", "INV-04", "INV-10", "INV-17"],
    naturalezas=["GASTO", "DERECHO_COBRO", "DEUDA"],
    dimensiones=["D1", "D2", "D3", "D5", "D7", "D8"],
    propiedades=["P-F08-14", "P-F08-26", "P-F08-27", "P-F08-28"],
)
def test_c12_gate_neteo_no_extingue_nada(
    motor: Motor, contexto: ContextoOperacion, actor_a, contraparte, cuenta, admin
) -> None:
    """C-12 canonico (Project Memory, caso gate; F04-D046 R1 · A19-bis).

    Hecho A · peluqueria 15,00: gasto del usuario (GASTO +15, atribucion self
    15 explicita) pagado integramente por la pareja (aportacion 15 sin
    vinculo). El usuario no mueve dinero. La obligacion de 15 frente a la
    pareja nace por DECISION EXPLICITA (INV-04), no por diferencia de importes.

    Hecho B · cena 44,50 con tres participantes, pagada por el usuario desde su
    cuenta (movimiento -44,50, aportacion self 44,50 vinculada). Solo consta
    explicitamente la parte de la pareja: 15. La parte del usuario NO se
    declara, asi que el reparto es PARCIAL y NUNCA aparece 29,50 por resta. El
    derecho de 15 frente a la pareja nace por decision explicita.

    Lectura OP-20: derecho 15 - obligacion 15 = neto 0. Leer no extingue, no
    compensa, no modifica hechos, atribuciones, aportaciones ni tesoreria, y no
    crea GASTO ni INGRESO. La compensacion extintiva sigue fuera de alcance
    (`F04-PEND-COMP-EXT`).
    """
    pareja = contraparte

    # ---------------- Hecho A: peluqueria pagada por la pareja ----------------
    peluqueria = hecho(concepto="peluqueria", importe_total=PELUQUERIA)
    alta_a = motor.compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=peluqueria,
            efectos=[
                efecto(
                    "GASTO",
                    PELUQUERIA,
                    atribuciones=(atribucion(actor_a, PELUQUERIA),),
                )
            ],
            aportaciones=[aportacion(PELUQUERIA, actor_id=pareja)],
        ),
    )
    obligacion = DatosAltaPosicion(
        entidad_id=uuid.uuid4(),
        nombre="peluqueria",
        tipo=TIPO_OBLIGACION,
        contraparte_actor_id=pareja,
        moneda="EUR",
        justificacion="DECISION_EXPLICITA",
        fecha_inicio_seguimiento=FECHA,
        saldo_apertura=D("0"),
        hecho_id=peluqueria.hecho_id,
        fecha_hecho=FECHA,
        concepto="peluqueria",
        hecho_row_version_esperada=alta_a.row_version,
        efecto_id=uuid.uuid4(),
        vinculo_id=uuid.uuid4(),
        importe_inicial=PELUQUERIA,
    )
    motor.posiciones.crear_posicion(contexto, obligacion)

    # ---------------- Hecho B: cena pagada por el usuario ---------------------
    cena = hecho(concepto="cena", importe_total=CENA, participantes_total=3)
    pieza = movimiento(cuenta, -CENA, descripcion="cena")
    puente = conciliacion(cena.hecho_id, pieza.movimiento_id, -CENA)
    alta_b = motor.compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=cena,
            efectos=[
                efecto(
                    "GASTO",
                    CENA,
                    estado="PARCIAL",
                    atribuciones=(atribucion(pareja, PELUQUERIA),),
                )
            ],
            participantes=[
                DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_a),
                DatosParticipante(participante_id=uuid.uuid4(), actor_id=pareja),
            ],
            tesoreria=[DatosTesoreria(movimiento=pieza, conciliacion=puente)],
            aportaciones=[
                aportacion(
                    CENA, actor_id=actor_a, conciliacion_id=puente.conciliacion_id
                )
            ],
        ),
    )
    derecho = DatosAltaPosicion(
        entidad_id=uuid.uuid4(),
        nombre="cena",
        tipo=TIPO_DERECHO,
        contraparte_actor_id=pareja,
        moneda="EUR",
        justificacion="DECISION_EXPLICITA",
        fecha_inicio_seguimiento=FECHA,
        saldo_apertura=D("0"),
        hecho_id=cena.hecho_id,
        fecha_hecho=FECHA,
        concepto="cena",
        hecho_row_version_esperada=alta_b.row_version,
        efecto_id=uuid.uuid4(),
        vinculo_id=uuid.uuid4(),
        importe_inicial=PELUQUERIA,
    )
    motor.posiciones.crear_posicion(contexto, derecho)

    # ---------------- Separacion de dimensiones, antes de leer ----------------
    # Efecto economico: gasto real conservado al 100 % y posicion explicita.
    assert efectos_de(admin, contexto.owner_user_id, peluqueria.hecho_id) == {
        "GASTO": PELUQUERIA,
        "DEUDA": PELUQUERIA,
    }
    assert efectos_de(admin, contexto.owner_user_id, cena.hecho_id) == {
        "GASTO": CENA,
        "DERECHO_COBRO": PELUQUERIA,
    }
    # Atribucion: A integra al usuario; B solo la parte explicita de la pareja.
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT e.estado_atribucion, count(a.id), sum(a.importe_atribuido), "
        "bool_or(a.actor_id = %s) "
        "FROM gapto.hecho_efectos e JOIN gapto.efecto_atribuciones a "
        "ON a.efecto_id = e.id WHERE e.hecho_id = %s AND e.tipo_efecto = 'GASTO' "
        "GROUP BY e.estado_atribucion",
        (actor_a, cena.hecho_id),
    ) == ("PARCIAL", 1, PELUQUERIA, False)
    # Nunca 29,50 por resta, en ninguna fila de ningun hecho.
    assert contar(
        admin,
        contexto.owner_user_id,
        "efecto_atribuciones a JOIN gapto.hecho_efectos e ON e.id = a.efecto_id",
        "e.hecho_id = ANY(%s) AND abs(a.importe_atribuido) = %s",
        ([peluqueria.hecho_id, cena.hecho_id], D("29.5000")),
    ) == 0
    # Pagador real: la pareja financio A sin caja del usuario; el usuario, B.
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT actor_id, importe, hecho_movimiento_tesoreria_id IS NULL "
        "FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
        (peluqueria.hecho_id,),
    ) == (pareja, PELUQUERIA, True)
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT actor_id, importe, hecho_movimiento_tesoreria_id IS NOT NULL "
        "FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
        (cena.hecho_id,),
    ) == (actor_a, CENA, True)
    # Tesoreria: A no tiene caja; B, exactamente -44,50.
    assert contar(
        admin,
        contexto.owner_user_id,
        "hecho_movimientos_tesoreria",
        "hecho_id = %s",
        (peluqueria.hecho_id,),
    ) == 0
    assert liquidez(admin, contexto.owner_user_id, cuenta) == -CENA

    huella = (
        "SELECT (SELECT count(*) FROM gapto.hechos_financieros), "
        "(SELECT count(*) FROM gapto.hecho_efectos), "
        "(SELECT coalesce(sum(importe_delta), 0) FROM gapto.hecho_efectos), "
        "(SELECT count(*) FROM gapto.efecto_atribuciones), "
        "(SELECT count(*) FROM gapto.hecho_aportaciones_pago), "
        "(SELECT count(*) FROM gapto.movimientos_tesoreria), "
        "(SELECT coalesce(sum(importe), 0) FROM gapto.movimientos_tesoreria), "
        "(SELECT count(*) FROM gapto.derechos_obligaciones_financieras), "
        "(SELECT count(*) FROM gapto.hecho_relaciones), "
        "(SELECT max(row_version) FROM gapto.hechos_financieros), "
        "(SELECT count(*) FROM gapto.auditoria)"
    )
    huella_antes = valor(admin, contexto.owner_user_id, huella, ())

    # ---------------- Lectura OP-20 -------------------------------------------
    segmento = motor.neto.posicion_neta(
        contexto, contraparte_actor_id=pareja
    ).segmento(pareja, "EUR")
    assert segmento is not None
    assert segmento.estado == DETERMINADO
    assert segmento.neto == D("0")
    assert len(segmento.posiciones) == 2
    saldos = {d.nombre: d.saldo.importe for d in segmento.posiciones}
    assert saldos == {"peluqueria": PELUQUERIA, "cena": PELUQUERIA}
    for alta in (obligacion, derecho):
        assert valor(
            admin,
            contexto.owner_user_id,
            "SELECT estado FROM gapto.derechos_obligaciones_financieras "
            "WHERE entidad_id = %s",
            (alta.entidad_id,),
        ) == ("ACTIVA",)

    # Leer no escribe: ni hechos, ni efectos, ni atribuciones, ni aportaciones,
    # ni tesoreria, ni posiciones, ni relaciones, ni versiones, ni auditoria.
    assert valor(admin, contexto.owner_user_id, huella, ()) == huella_antes
    # Ni INGRESO ni gasto adicional en los hechos del caso.
    assert efectos_de(admin, contexto.owner_user_id, peluqueria.hecho_id) == {
        "GASTO": PELUQUERIA,
        "DEUDA": PELUQUERIA,
    }
    assert efectos_de(admin, contexto.owner_user_id, cena.hecho_id) == {
        "GASTO": CENA,
        "DERECHO_COBRO": PELUQUERIA,
    }
    # Y no existe arquetipo de compensacion en ninguna forma.
    assert contar(
        admin,
        contexto.owner_user_id,
        "hecho_relaciones r JOIN gapto.hechos_financieros h "
        "ON h.id = r.hecho_origen_id",
        "h.owner_user_id = %s AND r.tipo_relacion = 'COMPENSA_A'",
        (contexto.owner_user_id,),
    ) == 0


# ==================================================================
# C-13 · Cuenta compartida · C-21 · Aportaciones multi-actor
# ==================================================================

@cubre(
    casos=["C-13"],
    operaciones=["OP-19", "OP-06", "OP-08", "OP-09"],
    invariantes=["INV-03", "INV-19"],
    dimensiones=["D3", "D5", "D7", "D8"],
    propiedades=["P-F08-05", "P-F08-07"],
)
def test_c13_cuenta_compartida_no_reparte_el_gasto(
    motor: Motor, contexto: ContextoOperacion, owner, actor_a, actor_b, cuenta, admin
) -> None:
    """Compra de 120 de A pagada desde la cuenta comun de A y B.

    P-F08-05: que el dinero salga de una cuenta al 50 % no reparte el gasto.
    Todo el gasto es de A; la financiacion real si se reparte. Y la liquidez
    atribuible de la cuenta es DERIVADA de la participacion, no una columna
    que alguien mantenga.
    """
    total = D("120.0000")
    mitad = D("60.0000")
    _cuenta_compartida(admin, owner, cuenta, actor_a, actor_b)

    datos = hecho(concepto="compra desde cuenta comun", importe_total=total)
    pieza_mov = movimiento(cuenta, -total, descripcion="cargo cuenta comun")
    motor.compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=datos,
            efectos=[
                efecto("GASTO", total, atribuciones=(atribucion(actor_a, total),))
            ],
            tesoreria=[
                DatosTesoreria(
                    movimiento=pieza_mov,
                    conciliacion=conciliacion(
                        datos.hecho_id, pieza_mov.movimiento_id, -total
                    ),
                )
            ],
            aportaciones=[
                aportacion(mitad, actor_id=actor_a, criterio="PARTICIPACION_CUENTA"),
                aportacion(mitad, actor_id=actor_b, criterio="PARTICIPACION_CUENTA"),
            ],
        ),
    )

    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(a.importe_atribuido) FROM gapto.efecto_atribuciones a "
        "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s",
        (datos.hecho_id,),
    ) == (1, total)
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe) FROM gapto.hecho_aportaciones_pago "
        "WHERE hecho_id = %s",
        (datos.hecho_id,),
    ) == (2, total)
    # INV-19: liquidez atribuible derivada, con precision completa.
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT sum(m.importe) * max(p.porcentaje) / 100 "
        "FROM gapto.movimientos_tesoreria m "
        "JOIN gapto.cuenta_participaciones p ON p.cuenta_id = m.cuenta_id "
        "WHERE m.cuenta_id = %s AND p.actor_id = %s",
        (cuenta, actor_a),
    ) == (-mitad,)
    exigir_ausencias(admin, contexto, posiciones=0)


@cubre(
    casos=["C-21"],
    operaciones=["OP-19", "OP-06"],
    invariantes=["INV-02", "INV-03", "INV-14"],
    dimensiones=["D5"],
    propiedades=["P-F08-16"],
)
def test_c21_aportaciones_multiactor_con_aportante_desconocido(
    motor: Motor, contexto: ContextoOperacion, actor_a, actor_b, cuenta, admin
) -> None:
    """Tres aportaciones: A, B y alguien que no se sabe quien fue.

    P-F08-16: el aportante desconocido se persiste como NULL. Ni se asigna a
    `self`, ni se reparte entre los conocidos, ni se inventa un actor.
    """
    total = D("90.0000")
    datos = hecho(concepto="gasto financiado entre varios", importe_total=total)
    pieza_mov = movimiento(cuenta, -total, descripcion="cargo")
    motor.compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=datos,
            efectos=[efecto("GASTO", total)],
            tesoreria=[
                DatosTesoreria(
                    movimiento=pieza_mov,
                    conciliacion=conciliacion(
                        datos.hecho_id, pieza_mov.movimiento_id, -total
                    ),
                )
            ],
            aportaciones=[
                aportacion(D("40.0000"), actor_id=actor_a),
                aportacion(D("30.0000"), actor_id=actor_b),
                aportacion(D("20.0000"), actor_id=None),
            ],
        ),
    )
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), count(actor_id), sum(importe) "
        "FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
        (datos.hecho_id,),
    ) == (3, 2, total)


# ==================================================================
# E-01 · Correccion
# ==================================================================

@cubre(
    excepciones=["E-01"],
    operaciones=["OP-02"],
    invariantes=["INV-07", "INV-08"],
    dimensiones=["D1"],
    propiedades=["P-F08-11", "P-F08-22"],
)
def test_e01_correccion_conserva_identidad_y_no_crea_realidad(
    motor: Motor, contexto: ContextoOperacion, cuenta, admin
) -> None:
    """El concepto y el importe total se capturaron mal y se corrigen.

    OP-02 conserva la IDENTIDAD del hecho porque la realidad sigue siendo la
    misma cena: lo que estaba mal era el dato, no el acontecimiento. El
    oraculo vigila que no nazca realidad economica nueva y que la auditoria
    conserve el valor anterior.
    """
    datos = hecho(concepto="cena", importe_total=D("40.0000"))
    creado = motor.hechos.crear_hecho(contexto, datos)
    version = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[efecto("GASTO", D("40.0000"))],
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    ).row_version
    hechos_antes = contar(
        admin,
        contexto.owner_user_id,
        "hechos_financieros",
        "owner_user_id = %s",
        (contexto.owner_user_id,),
    )

    corregido = motor.hechos.corregir_hecho(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(
            concepto="cena del viernes", importe_total=D("44.5000")
        ),
        motivo="el ticket decia 44,50 y el concepto estaba incompleto",
    )

    assert corregido.row_version == version + 1
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT concepto, importe_total FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    ) == ("cena del viernes", D("44.5000"))
    # Misma identidad, ninguna realidad nueva, ningun movimiento.
    assert contar(
        admin,
        contexto.owner_user_id,
        "hechos_financieros",
        "owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == hechos_antes
    exigir_ausencias(admin, contexto, movimientos=0, relaciones=0)
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT datos_antes->>'importe_total', motivo FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ACTUALIZAR' "
        # F04-D046 A08-bis: se excluye la auditoria de activacion de
        # `presupuestable` que deja OP-04 al nacer el primer GASTO.
        "AND motivo NOT LIKE 'F04-D046 A08-bis:%%'",
        (datos.hecho_id,),
    ) == (
        "40.0000",
        "el ticket decia 44,50 y el concepto estaba incompleto",
    )


# ==================================================================
# E-02 · Anulacion
# ==================================================================

@cubre(
    excepciones=["E-02"],
    operaciones=["OP-03"],
    invariantes=["INV-12"],
    dimensiones=["D1"],
    propiedades=["P-F08-22", "P-F08-25"],
)
def test_e02_anulacion_preserva_la_raiz_y_no_inventa_reversion(
    motor: Motor, contexto: ContextoOperacion, admin
) -> None:
    """Un hecho que nunca debio existir se ANULA; no se borra.

    P-F08-25: el hecho deja de ser realidad vigente pero su rastro permanece.
    Y anular NO fabrica una devolucion ni una reversion compensatoria: no ha
    ocurrido nada nuevo en el mundo, solo se reconoce que aquello nunca
    ocurrio.
    """
    datos = hecho(concepto="hecho duplicado por error", importe_total=D("25.0000"))
    creado = motor.hechos.crear_hecho(contexto, datos)

    anulado = motor.hechos.anular_hecho(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        motivo_anulacion="se registro dos veces la misma compra",
    )

    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT estado, motivo_anulacion IS NOT NULL, anulado_at IS NOT NULL "
        "FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    ) == ("ANULADO", True, True)
    assert anulado.row_version == creado.row_version + 1
    # Ni devolucion, ni reversion, ni movimiento compensatorio.
    exigir_ausencias(admin, contexto, movimientos=0, relaciones=0, posiciones=0)
    assert contar(
        admin,
        contexto.owner_user_id,
        "auditoria",
        "registro_id = %s",
        (datos.hecho_id,),
    ) >= 1


# ==================================================================
# E-03 · Reversion de tesoreria
# ==================================================================

@cubre(
    excepciones=["E-03"],
    operaciones=["OP-11", "OP-08"],
    invariantes=["INV-18"],
    dimensiones=["D6", "D7"],
    propiedades=["P-F08-03", "P-F08-22"],
)
def test_e03_reversion_de_tesoreria(
    motor: Motor, contexto: ContextoOperacion, cuenta, cuenta_destino, admin
) -> None:
    """El banco devuelve un cargo de 70 que nunca debio salir.

    La reversion es un movimiento NUEVO en la misma cuenta, no una edicion
    del original: el apunte erroneo existio y el extracto lo conserva. No
    crea efecto economico —no ha habido ingreso— y no emite `REVERSA_A`, que
    sigue siendo token reservado sin writer.
    """
    importe = D("70.0000")
    pieza = movimiento(cuenta, -importe, descripcion="cargo erroneo")
    original = motor.tesoreria.registrar_movimiento(contexto, pieza)
    assert liquidez(admin, contexto.owner_user_id, cuenta) == -importe

    reversion_id = uuid.uuid4()
    resultado = motor.tesoreria.revertir_movimiento(
        contexto,
        DatosReversion(
            reversion_id=reversion_id,
            movimiento_original_id=pieza.movimiento_id,
            cuenta_id=cuenta,
            fecha_movimiento=dt.date(2026, 6, 5),
            importe=importe,
            descripcion="devolucion del cargo",
        ),
    )
    assert resultado.pendiente == D("0")

    # Original intacto, reversion como movimiento propio, liquidez a cero.
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT importe, estado FROM gapto.movimientos_tesoreria WHERE id = %s",
        (pieza.movimiento_id,),
    ) == (-importe, "ACTIVO")
    assert liquidez(admin, contexto.owner_user_id, cuenta) == D("0")
    assert contar(
        admin,
        contexto.owner_user_id,
        "movimientos_tesoreria m JOIN gapto.cuentas c ON c.id = m.cuenta_id",
        "c.owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == 2

    # Same-account: una reversion no puede aterrizar en otra cuenta.
    with pytest.raises(ErrorMotor):
        motor.tesoreria.revertir_movimiento(
            contexto,
            DatosReversion(
                reversion_id=uuid.uuid4(),
                movimiento_original_id=pieza.movimiento_id,
                cuenta_id=cuenta_destino,
                fecha_movimiento=dt.date(2026, 6, 6),
                importe=importe,
            ),
        )
    # Cero efecto economico y cero REVERSA_A.
    assert efectos_de(admin, contexto.owner_user_id, pieza.movimiento_id) == {}
    assert contar(
        admin,
        contexto.owner_user_id,
        "hecho_relaciones r JOIN gapto.hechos_financieros h "
        "ON h.id = r.hecho_origen_id",
        "h.owner_user_id = %s AND r.tipo_relacion = 'REVERSA_A'",
        (contexto.owner_user_id,),
    ) == 0
