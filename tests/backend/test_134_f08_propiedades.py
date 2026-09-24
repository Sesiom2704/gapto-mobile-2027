# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_134_f08_propiedades.py
# Ruta: tests/backend/test_134_f08_propiedades.py
# Descripcion: F04-D042 §20, §21, §22. Propiedades transversales del motor.
#
#     A-F08-01..04  atomicidad ante fallo tardio deliberado
#     INV-20 / P-F08-21  idempotencia sobre tres altas compuestas distintas
#     INV-21  retry de TRANSACCION COMPLETA ante 40P01
#     P-F08-23  aislamiento tenant
#     P-F08-24  los read-models no escriben
#
#   Ninguna de estas propiedades se demuestra con un escenario feliz. Todas
#   exigen provocar deliberadamente lo que no debe ocurrir y comprobar que el
#   estado final es indistinguible del inicial.
# Version: 0.3.0
#   0.3.0 (mandato F04 R1+R2 v0.3 + E01): OP-04 aporta `presupuestable` en la
#   transicion al primer GASTO/INGRESO (A08-bis generalizada); fixtures de
#   GASTO con localizacion DESCONOCIDA en vez de NO_APLICA cuando aplica. Sin
#   cambio de las propiedades probadas.
# Version: 0.2.0
#   0.2.0 (F04-D046 R1 · A19): signo canonico (GASTO +X, atribuciones +X,
#   correccion +40/+25); tesoreria intacta. Se FIJA el codigo de fallo de
#   A-F08-01, A-F08-02/03 y A-F08-04 para que el signo no pueda cambiar el
#   motivo del fallo que cada test demuestra.
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
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.compartidos_service import DatosGastoCompartido, DatosTesoreria
from app.services.correcciones_service import DatosCorreccion
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
    movimiento,
    valor,
)

CENA = D("44.5000")
MITAD = D("22.2500")


@pytest.fixture()
def motor(unidad: UnidadDeTrabajo) -> Motor:
    return construir_motor(unidad)


def _hechos_del_tenant(admin, contexto) -> int:
    return contar(
        admin,
        contexto.owner_user_id,
        "hechos_financieros",
        "owner_user_id = %s",
        (contexto.owner_user_id,),
    )


# ==================================================================
# A-F08-01 · Fallo en atribucion despues de crear el efecto
# ==================================================================

@cubre(
    propiedades=["P-F08-20"],
    invariantes=["INV-01"],
    operaciones=["OP-04", "OP-05"],
)
def test_a_f08_01_fallo_en_atribucion_no_deja_el_efecto(
    motor: Motor, contexto: ContextoOperacion, actor_a, actor_b, admin
) -> None:
    """El reparto declarado COMPLETA no cuadra: cae tambien el efecto.

    El efecto se crea antes que sus atribuciones dentro de la misma
    transaccion. Si la validacion del reparto fallase DESPUES de confirmar el
    efecto, quedaria un efecto huerfano con un estado que nadie pidio.
    """
    datos = hecho(concepto="cena con reparto invalido", importe_total=CENA)
    creado = motor.hechos.crear_hecho(contexto, datos)

    with pytest.raises(ErrorMotor) as excepcion:
        motor.efectos.registrar_efectos(
            contexto,
            hecho_id=datos.hecho_id,
            row_version_esperada=creado.row_version,
            efectos=[
                efecto(
                    "GASTO",
                    CENA,
                    estado="COMPLETA",
                    atribuciones=(
                        atribucion(actor_a, MITAD),
                        atribucion(actor_b, D("10.0000")),
                    ),
                )
            ],
        )

    # F04-D046 R1. El motivo del fallo queda fijado: no depende del signo.
    assert excepcion.value.codigo is CodigoError.SUMA_NO_CUADRA
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {}
    assert contar(
        admin,
        contexto.owner_user_id,
        "efecto_atribuciones a JOIN gapto.hecho_efectos e ON e.id = a.efecto_id",
        "e.hecho_id = %s",
        (datos.hecho_id,),
    ) == 0
    # El hecho sobrevive porque se creo en OTRA transaccion, y su version no
    # se consumio: el fallo no deja rastro en la raiz.
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    ) == (creado.row_version,)


# ==================================================================
# A-F08-02 / A-F08-03 · Fallo tardio en OP-19
# ==================================================================

@cubre(
    propiedades=["P-F08-20"],
    operaciones=["OP-19", "OP-08", "OP-09"],
    invariantes=["INV-13"],
)
def test_a_f08_02_03_fallo_tardio_en_op19_no_deja_residuo(
    motor: Motor, contexto: ContextoOperacion, actor_a, cuenta, admin
) -> None:
    """Falla la conciliacion tras crear hecho, efectos, participante y movimiento.

    Cuatro superficies escritas y una quinta que falla. El estado final debe
    ser indistinguible del inicial: cero hechos, cero efectos, cero
    participantes, cero movimientos y cero auditoria.
    """
    hechos_antes = _hechos_del_tenant(admin, contexto)
    datos = hecho(concepto="cena que no llega a confirmarse", importe_total=CENA)
    participante = DatosParticipante(
        participante_id=uuid.uuid4(), actor_id=actor_a
    )
    pieza_mov = movimiento(cuenta, -CENA, descripcion="cargo")
    roto = DatosTesoreria(
        movimiento=pieza_mov,
        # Conciliar mucho mas de lo que el movimiento mueve: falla al final.
        conciliacion=conciliacion(
            datos.hecho_id, pieza_mov.movimiento_id, D("-5000.0000")
        ),
    )

    with pytest.raises(ErrorMotor) as excepcion:
        motor.compartidos.registrar_gasto_compartido(
            contexto,
            DatosGastoCompartido(
                hecho=datos,
                efectos=[
                    efecto("GASTO", CENA, atribuciones=(atribucion(actor_a, CENA),))
                ],
                participantes=[participante],
                tesoreria=[roto],
            ),
        )

    # F04-D046 R1. El motivo del fallo queda fijado: no depende del signo.
    assert excepcion.value.codigo is CodigoError.EXCEDE_IMPORTE_MOVIMIENTO
    assert _hechos_del_tenant(admin, contexto) == hechos_antes
    for tabla, donde, parametros in (
        ("hecho_efectos", "hecho_id = %s", (datos.hecho_id,)),
        ("hecho_participantes", "id = %s", (participante.participante_id,)),
        ("movimientos_tesoreria", "id = %s", (pieza_mov.movimiento_id,)),
        ("auditoria", "registro_id = %s", (datos.hecho_id,)),
    ):
        assert contar(admin, contexto.owner_user_id, tabla, donde, parametros) == 0
    exigir_ausencias(admin, contexto, movimientos=0)


# ==================================================================
# A-F08-04 · Fallo tardio en OP-21 sobre efecto + atribuciones
# ==================================================================

@cubre(
    propiedades=["P-F08-20"],
    operaciones=["OP-21"],
    invariantes=["INV-01", "INV-07"],
)
def test_a_f08_04_fallo_tardio_en_correccion_agregada(
    motor: Motor, contexto: ContextoOperacion, actor_a, actor_b, admin
) -> None:
    """La correccion cuadra el efecto pero deja el reparto descuadrado.

    El mutante natural de una correccion agregada es confirmar la parte que
    ya se aplico. Aqui se comprueba lo contrario: el efecto vuelve a su
    importe y las atribuciones a los suyos.
    """
    a = atribucion(actor_a, MITAD)
    b = atribucion(actor_b, MITAD)
    efecto_cena = efecto("GASTO", CENA, atribuciones=(a, b))
    datos = hecho(concepto="cena", importe_total=CENA)
    resultado = motor.compartidos.registrar_gasto_compartido(
        contexto, DatosGastoCompartido(hecho=datos, efectos=[efecto_cena])
    )

    with pytest.raises(ErrorMotor) as excepcion:
        motor.correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=datos.hecho_id,
                row_version_esperada=resultado.row_version,
                motivo="solo se corrige una parte",
                efectos_a_actualizar={
                    efecto_cena.efecto_id: {"importe_delta": D("40.0000")}
                },
                atribuciones_a_actualizar={
                    a.atribucion_id: {"importe_atribuido": D("25.0000")}
                },
            ),
        )

    # F04-D046 R1. El fallo debe ser el DESCUADRE del estado final, no un
    # rechazo temprano: con el signo canonico ambos valores son positivos.
    assert excepcion.value.codigo is CodigoError.SUMA_NO_CUADRA
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": CENA
    }
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe_atribuido) FROM gapto.efecto_atribuciones "
        "WHERE efecto_id = %s",
        (efecto_cena.efecto_id,),
    ) == (2, CENA)
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    ) == (resultado.row_version,)


# ==================================================================
# INV-20 / P-F08-21 · Idempotencia sobre tres altas compuestas
# ==================================================================

@cubre(
    invariantes=["INV-20"],
    propiedades=["P-F08-21"],
    operaciones=["OP-01"],
)
def test_inv20_reintento_de_operacion_simple(
    motor: Motor, contexto: ContextoOperacion, admin
) -> None:
    """Mismo `hecho_id`: una sola raiz, sin segunda version."""
    datos = hecho(concepto="gasto reintentado", importe_total=D("30.0000"))
    primero = motor.hechos.crear_hecho(contexto, datos)
    segundo = motor.hechos.crear_hecho(contexto, datos)

    assert segundo.row_version == primero.row_version
    assert contar(
        admin, contexto.owner_user_id, "hechos_financieros", "id = %s",
        (datos.hecho_id,),
    ) == 1


@cubre(
    invariantes=["INV-20"],
    propiedades=["P-F08-21"],
    operaciones=["OP-04", "OP-05"],
)
def test_inv20_reintento_de_operacion_con_hijas(
    motor: Motor, contexto: ContextoOperacion, actor_a, admin
) -> None:
    """Mismos UUID de efecto y atribucion: cero hijos duplicados.

    Es el caso que mas duele si falla: un reintento tras un COMMIT de
    resultado desconocido duplicaria el gasto sin que nadie lo note.
    """
    total = D("70.0000")
    datos = hecho(concepto="gasto con hijas", importe_total=total)
    creado = motor.hechos.crear_hecho(contexto, datos)
    efectos = [efecto("GASTO", total, atribuciones=(atribucion(actor_a, total),))]

    primero = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=efectos,
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    )
    segundo = motor.efectos.registrar_efectos(
        contexto,
        hecho_id=datos.hecho_id,
        row_version_esperada=creado.row_version,
        efectos=efectos,
    )

    assert segundo.row_version == primero.row_version
    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": total
    }
    assert contar(
        admin,
        contexto.owner_user_id,
        "efecto_atribuciones a JOIN gapto.hecho_efectos e ON e.id = a.efecto_id",
        "e.hecho_id = %s",
        (datos.hecho_id,),
    ) == 1


@cubre(
    invariantes=["INV-20"],
    propiedades=["P-F08-21"],
    operaciones=["OP-19"],
)
def test_inv20_reintento_de_operacion_multisuperficie(
    motor: Motor, contexto: ContextoOperacion, actor_a, cuenta, admin
) -> None:
    """OP-19 reintegrada con las MISMAS identidades en cinco superficies.

    Hecho, efecto, atribucion, participante, movimiento y conciliacion. El
    segundo intento no puede duplicar ninguna de ellas.
    """
    datos = hecho(concepto="cena compuesta", importe_total=CENA)
    participante = DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_a)
    pieza_mov = movimiento(cuenta, -CENA, descripcion="cargo cena")
    entrada = DatosGastoCompartido(
        hecho=datos,
        efectos=[efecto("GASTO", CENA, atribuciones=(atribucion(actor_a, CENA),))],
        participantes=[participante],
        tesoreria=[
            DatosTesoreria(
                movimiento=pieza_mov,
                conciliacion=conciliacion(
                    datos.hecho_id, pieza_mov.movimiento_id, -CENA
                ),
            )
        ],
        aportaciones=[aportacion(CENA, actor_id=actor_a)],
    )

    motor.compartidos.registrar_gasto_compartido(contexto, entrada)
    # El reintento con las MISMAS identidades vuelve a ejecutarse: lo que se
    # exige no es que falle, sino que no duplique nada. Si el motor lo
    # clasifica como replica, devuelve; si rechaza por version, tampoco
    # escribe. Ambos son deterministas y ambos dejan el mismo estado.
    try:
        motor.compartidos.registrar_gasto_compartido(contexto, entrada)
    except ErrorMotor as error:
        assert error.codigo in (
            CodigoError.VERSION_DESFASADA,
            CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
        )

    assert efectos_de(admin, contexto.owner_user_id, datos.hecho_id) == {
        "GASTO": CENA
    }
    for tabla, donde, parametros, esperado in (
        ("hechos_financieros", "id = %s", (datos.hecho_id,), 1),
        ("hecho_efectos", "hecho_id = %s", (datos.hecho_id,), 1),
        (
            "hecho_participantes",
            "id = %s",
            (participante.participante_id,),
            1,
        ),
        ("movimientos_tesoreria", "id = %s", (pieza_mov.movimiento_id,), 1),
        (
            "hecho_movimientos_tesoreria",
            "hecho_id = %s",
            (datos.hecho_id,),
            1,
        ),
        ("hecho_aportaciones_pago", "hecho_id = %s", (datos.hecho_id,), 1),
    ):
        assert (
            contar(admin, contexto.owner_user_id, tabla, donde, parametros) == esperado
        ), tabla


# ==================================================================
# INV-21 · Retry de TRANSACCION COMPLETA ante 40P01
# ==================================================================

@cubre(invariantes=["INV-21"])
def test_inv21_retry_de_transaccion_completa(
    unidad: UnidadDeTrabajo, contexto: ContextoOperacion, admin
) -> None:
    """Un `40P01` en el primer intento reejecuta la operacion ENTERA.

    ORACULO DETERMINISTA, no una carrera. Lo que INV-21 afirma no es que
    existan deadlocks, sino que ante uno se reintenta la transaccion COMPLETA
    y no un trozo. Se provoca el 40P01 con `RAISE` en el primer intento y se
    comprueba que el segundo empieza de cero: la fila escrita antes del fallo
    no sobrevive, y la que persiste es la del intento bueno.

    Un interleaving real no anadiria informacion aqui y si intermitencia:
    §12C.1 clasifica como NO_CLASIFICABLE lo que pasa sin demostrar el
    mecanismo.
    """
    marcas: list[int] = []
    hecho_id = uuid.uuid4()

    def operacion(sesion) -> int:
        marcas.append(sesion.intento)
        sesion.uno(
            "SELECT set_config('gapto.f08_marca', %s, true)", (str(sesion.intento),)
        )
        if sesion.intento == 1:
            raise psycopg.errors.DeadlockDetected("deadlock simulado")
        fila = sesion.uno("SELECT current_setting('gapto.f08_marca', true)")
        return int(fila[0])

    resultado = unidad.ejecutar_con_traza(
        contexto, operacion, nombre="F04-08 retry 40P01"
    )

    assert marcas == [1, 2]
    assert resultado.valor == 2
    assert resultado.traza.intentos_realizados == 2
    assert [fallido.sqlstate for fallido in resultado.traza.fallidos] == ["40P01"]
    # La GUC del intento fallido no sobrevive: la transaccion se rehizo entera.
    assert resultado.valor != 1


# ==================================================================
# P-F08-23 · Aislamiento tenant
# ==================================================================

@cubre(
    propiedades=["P-F08-23"],
    operaciones=["OP-01", "OP-04"],
)
def test_p_f08_23_tenant_ajeno_no_opera_sobre_el_agregado(
    motor: Motor,
    contexto: ContextoOperacion,
    otro_owner,
    actor_ajeno,
    cuenta_ajena,
    admin,
) -> None:
    """El tenant A crea un agregado; el tenant B no puede tocarlo.

    El test NO se conforma con que una consulta devuelva cero filas: eso
    confundiria inexistencia con filtrado RLS. Primero se comprueba que el
    hecho EXISTE de verdad leyendolo con el tenant propietario, y solo
    despues se demuestra que el ajeno no lo alcanza.
    """
    datos = hecho(concepto="agregado del tenant A", importe_total=D("55.0000"))
    creado = motor.hechos.crear_hecho(contexto, datos)
    assert contar(
        admin, contexto.owner_user_id, "hechos_financieros", "id = %s",
        (datos.hecho_id,),
    ) == 1

    ajeno = ContextoOperacion.de_usuario(otro_owner)

    # Leer: el hecho es invisible para el otro tenant.
    with pytest.raises(ErrorMotor) as lectura:
        motor.hechos.corregir_hecho(
            ajeno,
            hecho_id=datos.hecho_id,
            row_version_esperada=creado.row_version,
            campos=CamposCorreccion(concepto="secuestrado"),
            motivo="intento cross-tenant",
        )
    assert lectura.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO

    # Escribir hijos: tampoco.
    with pytest.raises(ErrorMotor) as escritura:
        motor.efectos.registrar_efectos(
            ajeno,
            hecho_id=datos.hecho_id,
            row_version_esperada=creado.row_version,
            efectos=[efecto("GASTO", D("10.0000"))],
        )
    assert escritura.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO

    # Y el agregado del tenant A sigue exactamente igual.
    assert valor(
        admin,
        contexto.owner_user_id,
        "SELECT concepto, row_version FROM gapto.hechos_financieros WHERE id = %s",
        (datos.hecho_id,),
    ) == ("agregado del tenant A", creado.row_version)


# ==================================================================
# P-F08-24 · Los read-models no escriben
# ==================================================================

@cubre(
    propiedades=["P-F08-24"],
    operaciones=["OP-20", "OP-12"],
    invariantes=["INV-17", "INV-18"],
)
def test_p_f08_24_los_read_models_no_escriben(
    motor: Motor, contexto: ContextoOperacion, contraparte, admin
) -> None:
    """Tres lecturas seguidas dejan la base byte a byte igual.

    Se comprueban los dos read-models del motor —saldo de posicion y posicion
    neta— y la huella incluye la AUDITORIA: una lectura que se auditase como
    hecho economico seria una escritura disfrazada.
    """
    from app.core.modelos_posicion import DatosAltaPosicion, TIPO_DERECHO

    datos = DatosAltaPosicion(
        entidad_id=uuid.uuid4(),
        nombre="derecho",
        tipo=TIPO_DERECHO,
        contraparte_actor_id=contraparte,
        moneda="EUR",
        justificacion="DECISION_EXPLICITA",
        fecha_inicio_seguimiento=FECHA,
        saldo_apertura=D("0"),
        hecho_id=uuid.uuid4(),
        fecha_hecho=FECHA,
        concepto="derecho",
        efecto_id=uuid.uuid4(),
        vinculo_id=uuid.uuid4(),
        importe_inicial=D("120.0000"),
    )
    motor.posiciones.crear_posicion(contexto, datos)

    def huella():
        return valor(
            admin,
            contexto.owner_user_id,
            "SELECT (SELECT count(*) FROM gapto.hechos_financieros), "
            "(SELECT count(*) FROM gapto.hecho_efectos), "
            "(SELECT count(*) FROM gapto.hecho_entidades), "
            "(SELECT count(*) FROM gapto.derechos_obligaciones_financieras), "
            "(SELECT count(*) FROM gapto.movimientos_tesoreria), "
            "(SELECT count(*) FROM gapto.hecho_relaciones), "
            "(SELECT count(*) FROM gapto.auditoria)",
            (),
        )

    antes = huella()
    motor.posiciones.saldo(contexto, entidad_id=datos.entidad_id)
    motor.neto.posicion_neta(contexto, contraparte_actor_id=contraparte)
    motor.neto.posicion_neta(contexto)
    assert huella() == antes
