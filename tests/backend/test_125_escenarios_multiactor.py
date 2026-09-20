# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_125_escenarios_multiactor.py
# Ruta: tests/backend/test_125_escenarios_multiactor.py
# Descripcion: F04-D038 §27. Escenarios obligatorios donde se cruzan las
#   piezas: C-10, C-13, C-21 y los adversariales A1, A8, A9, A16, A18 y A19.
#
#   Lo que se busca aqui no es que cada operacion funcione —eso ya lo prueban
#   sus suites— sino que la combinacion no produzca una conclusion que nadie
#   decidio: una atribucion nacida de un porcentaje de cuenta, una deuda
#   nacida de una diferencia, un residual completado para cuadrar.
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
from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
from app.core.modelos_suplemento import DatosSuplemento
from app.core.modelos_tesoreria import (
    DatosAportacion,
    DatosConciliacion,
    DatosMovimiento,
)
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.compartidos_service import (
    DatosGastoCompartido,
    DatosTesoreria,
    GastosCompartidosService,
)
from app.services.correcciones_service import DatosCorreccion
from app.services.participantes_service import DatosParticipante
from conftest import leer_fila

D = decimal.Decimal
FECHA = dt.date(2026, 6, 1)
TOTAL = D("44.5000")
MITAD = D("22.2500")


@pytest.fixture()
def servicio_neto(unidad: UnidadDeTrabajo):
    from app.services.neto_service import NetoService

    return NetoService(unidad)


@pytest.fixture()
def servicio_participantes(unidad: UnidadDeTrabajo):
    from app.services.participantes_service import ParticipantesService

    return ParticipantesService(unidad)


@pytest.fixture()
def servicio_compartidos(unidad: UnidadDeTrabajo) -> GastosCompartidosService:
    from app.services.previsiones_service import impacto_correccion_ancla

    return GastosCompartidosService(unidad, impacto_ancla=impacto_correccion_ancla)


def _admin(admin: psycopg.Connection, owner: uuid.UUID):
    """Contexto administrativo para montar datos que el motor no escribe."""

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


def _hecho(**extra) -> DatosCreacionHecho:
    base = dict(
        hecho_id=uuid.uuid4(),
        fecha_hecho=FECHA,
        moneda="EUR",
        presupuestable=True,
        estado_localizacion="NO_APLICA",
        tipo_hecho_codigo="GASTO",
        concepto="gasto compartido",
        importe_total=TOTAL,
    )
    base.update(extra)
    return DatosCreacionHecho(**base)


def _gasto(importe=TOTAL, atribuciones=(), estado=None) -> DatosEfecto:
    return DatosEfecto(
        efecto_id=uuid.uuid4(),
        tipo_efecto="GASTO",
        importe_delta=-importe,
        estado_atribucion=estado or ("COMPLETA" if atribuciones else "NO_DISPONIBLE"),
        atribuciones=tuple(atribuciones),
    )


def _atribucion(actor_id, importe, criterio="MANUAL") -> DatosAtribucion:
    return DatosAtribucion(
        atribucion_id=uuid.uuid4(),
        actor_id=actor_id,
        importe_atribuido=-importe,
        criterio_atribucion=criterio,
    )


def _tesoreria(hecho_id, cuenta_id, importe=TOTAL) -> DatosTesoreria:
    movimiento_id = uuid.uuid4()
    return DatosTesoreria(
        movimiento=DatosMovimiento(
            movimiento_id=movimiento_id,
            cuenta_id=cuenta_id,
            fecha_movimiento=FECHA,
            importe=-importe,
            clase_movimiento="OPERACION",
            descripcion="cargo",
        ),
        conciliacion=DatosConciliacion(
            conciliacion_id=uuid.uuid4(),
            hecho_id=hecho_id,
            movimiento_tesoreria_id=movimiento_id,
            importe_asignado=-importe,
        ),
    )


def _aportacion(importe, actor_id=None, criterio="MANUAL"):
    return DatosAportacion(
        aportacion_id=uuid.uuid4(),
        importe=importe,
        criterio_aportacion=criterio,
        actor_id=actor_id,
    )


def _propiedad_compartida(admin, owner, actor_a, actor_b, reparto=(50, 50)):
    """Una vivienda con dos propietarios al 50 %."""
    entidad_id = uuid.uuid4()
    with _admin(admin, owner) as cursor:
        # La entidad y su subtipo viajan en UNA transaccion: el control de
        # subtipo unico es un constraint trigger diferido y se valida al
        # confirmar.
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
        for actor, porcentaje in zip((actor_a, actor_b), reparto):
            cursor.execute(
                "INSERT INTO gapto.entidad_participaciones "
                "(id, entidad_id, actor_id, porcentaje, vigente_desde) "
                "VALUES (%s, %s, %s, %s, CURRENT_DATE)",
                (uuid.uuid4(), entidad_id, actor, porcentaje),
            )
        cursor.execute("COMMIT")
    return entidad_id


def _cuenta_compartida(admin, owner, cuenta, actor_a, actor_b):
    with _admin(admin, owner) as cursor:
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


# ==================================================================
# C-10 — propiedad compartida
# ==================================================================

def test_c10_propiedad_compartida_propone_pero_no_decide(
    servicio_compartidos, contexto, owner, actor_a, actor_b, admin
) -> None:
    """§12. La participacion sugiere el reparto; la atribucion la decide quien registra.

    Se acepta el 50/50 que propone la propiedad y se persiste como atribucion
    real con criterio `PARTICIPACION_ENTIDAD`. Lo que NO ocurre es que el
    motor lea la tabla de participaciones y reparta solo.
    """
    _propiedad_compartida(admin, owner, actor_a, actor_b)
    hecho = _hecho(concepto="derrama de la comunidad")

    servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[
                _gasto(
                    atribuciones=[
                        _atribucion(actor_a, MITAD, criterio="PARTICIPACION_ENTIDAD"),
                        _atribucion(actor_b, MITAD, criterio="PARTICIPACION_ENTIDAD"),
                    ]
                )
            ],
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(a.importe_atribuido) "
        "FROM gapto.efecto_atribuciones a "
        "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s",
        (hecho.hecho_id,),
    ) == (2, -TOTAL)


def test_n3_la_participacion_no_materializa_atribuciones_por_si_sola(
    servicio_compartidos, contexto, owner, actor_a, actor_b, admin
) -> None:
    """N3. Existe la propiedad al 50/50 y NO se pide reparto: cero atribuciones."""
    _propiedad_compartida(admin, owner, actor_a, actor_b, reparto=(70, 30))
    hecho = _hecho()

    servicio_compartidos.registrar_gasto_compartido(
        contexto, DatosGastoCompartido(hecho=hecho, efectos=[_gasto()])
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.efecto_atribuciones a "
        "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s",
        (hecho.hecho_id,),
    ) == (0,)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado_atribucion FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho.hecho_id,),
    ) == ("NO_DISPONIBLE",)


# ==================================================================
# C-13 — cuenta compartida
# ==================================================================

def test_c13_cuenta_compartida_no_reparte_el_gasto(
    servicio_compartidos, contexto, owner, actor_a, actor_b, cuenta, admin
) -> None:
    """La cuenta es de dos; el gasto sigue siendo de quien se le atribuya.

    Participacion de cuenta y atribucion economica son dimensiones
    independientes: que el dinero salga de una cuenta compartida no reparte
    el gasto, y el hecho conserva el 100 %.
    """
    _cuenta_compartida(admin, owner, cuenta, actor_a, actor_b)
    hecho = _hecho(concepto="compra pagada desde cuenta comun")

    servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[_gasto(atribuciones=[_atribucion(actor_a, TOTAL)])],
            tesoreria=[_tesoreria(hecho.hecho_id, cuenta)],
            aportaciones=[
                _aportacion(MITAD, actor_id=actor_a, criterio="PARTICIPACION_CUENTA"),
                _aportacion(MITAD, actor_id=actor_b, criterio="PARTICIPACION_CUENTA"),
            ],
        ),
    )
    # Todo el gasto es de A, aunque la mitad del dinero la puso B.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(a.importe_atribuido) FROM gapto.efecto_atribuciones a "
        "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s",
        (hecho.hecho_id,),
    ) == (1, -TOTAL)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe) FROM gapto.hecho_aportaciones_pago "
        "WHERE hecho_id = %s",
        (hecho.hecho_id,),
    ) == (2, TOTAL)
    # N4: la diferencia entre atribucion y aportacion NO crea posicion.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.derechos_obligaciones_financieras p "
        "JOIN gapto.entidades e ON e.id = p.entidad_id WHERE e.owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == (0,)


# ==================================================================
# C-21 — aportaciones multi-actor
# ==================================================================

def test_c21_varios_aportantes_incluido_uno_desconocido(
    servicio_compartidos, contexto, actor_a, actor_b, cuenta, admin
) -> None:
    """Tres aportaciones: A, B y alguien que no se sabe quien fue."""
    hecho = _hecho()
    servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[_gasto()],
            tesoreria=[_tesoreria(hecho.hecho_id, cuenta)],
            aportaciones=[
                _aportacion(D("20.0000"), actor_id=actor_a),
                _aportacion(D("20.0000"), actor_id=actor_b),
                _aportacion(D("4.5000"), actor_id=None),
            ],
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), count(actor_id), sum(importe) "
        "FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s",
        (hecho.hecho_id,),
    ) == (3, 2, TOTAL)


# ==================================================================
# A1 — atribucion parcial con residual desconocido
# ==================================================================

def test_a1_atribucion_parcial_con_residual_desconocido(
    servicio_compartidos, contexto, actor_a, admin
) -> None:
    """Se conoce la parte de A y nada mas. El resto NO se completa."""
    hecho = _hecho()
    servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[
                _gasto(
                    atribuciones=[_atribucion(actor_a, MITAD)],
                    estado="PARCIAL",
                )
            ],
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT e.estado_atribucion, count(a.id), sum(a.importe_atribuido) "
        "FROM gapto.hecho_efectos e "
        "LEFT JOIN gapto.efecto_atribuciones a ON a.efecto_id = e.id "
        "WHERE e.hecho_id = %s GROUP BY e.estado_atribucion",
        (hecho.hecho_id,),
    ) == ("PARCIAL", 1, -MITAD)


def test_atribucion_completa_que_no_suma_el_efecto_se_rechaza(
    servicio_compartidos, contexto, actor_a, admin
) -> None:
    """Declarar COMPLETA con la mitad conocida es inventar el residual."""
    hecho = _hecho()
    with pytest.raises(ErrorMotor):
        servicio_compartidos.registrar_gasto_compartido(
            contexto,
            DatosGastoCompartido(
                hecho=hecho,
                efectos=[
                    _gasto(atribuciones=[_atribucion(actor_a, MITAD)], estado="COMPLETA")
                ],
            ),
        )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
        (hecho.hecho_id,),
    ) == (0,)


# ==================================================================
# A8 / A9 — propiedad y cuenta son independientes
# ==================================================================

def test_a8_propiedad_compartida_con_cuenta_individual(
    servicio_compartidos, contexto, owner, actor_a, actor_b, cuenta, admin
) -> None:
    """La vivienda es de dos; la cuenta que paga es de uno."""
    _propiedad_compartida(admin, owner, actor_a, actor_b)
    hecho = _hecho(concepto="IBI de la vivienda compartida")

    servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[
                _gasto(
                    atribuciones=[
                        _atribucion(actor_a, MITAD, criterio="PARTICIPACION_ENTIDAD"),
                        _atribucion(actor_b, MITAD, criterio="PARTICIPACION_ENTIDAD"),
                    ]
                )
            ],
            tesoreria=[_tesoreria(hecho.hecho_id, cuenta)],
            aportaciones=[_aportacion(TOTAL, actor_id=actor_a)],
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.cuenta_participaciones WHERE cuenta_id = %s",
        (cuenta,),
    ) == (0,)
    # A soporta la mitad y pone todo el dinero. Sigue sin haber posicion.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.derechos_obligaciones_financieras p "
        "JOIN gapto.entidades e ON e.id = p.entidad_id WHERE e.owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == (0,)


def test_a9_propiedad_individual_con_cuenta_compartida(
    servicio_compartidos, contexto, owner, actor_a, actor_b, cuenta, admin
) -> None:
    """El gasto es entero de A; el dinero sale de una cuenta de A y B."""
    _cuenta_compartida(admin, owner, cuenta, actor_a, actor_b)
    hecho = _hecho(concepto="gasto propio pagado desde cuenta comun")

    servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[_gasto(atribuciones=[_atribucion(actor_a, TOTAL)])],
            tesoreria=[_tesoreria(hecho.hecho_id, cuenta)],
            aportaciones=[
                _aportacion(MITAD, actor_id=actor_a, criterio="PARTICIPACION_CUENTA"),
                _aportacion(MITAD, actor_id=actor_b, criterio="PARTICIPACION_CUENTA"),
            ],
        ),
    )
    atribuidos = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(DISTINCT a.actor_id) FROM gapto.efecto_atribuciones a "
        "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s",
        (hecho.hecho_id,),
    )
    aportantes = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(DISTINCT actor_id) FROM gapto.hecho_aportaciones_pago "
        "WHERE hecho_id = %s",
        (hecho.hecho_id,),
    )
    assert (atribuidos, aportantes) == ((1,), (2,))


# ==================================================================
# A16 — participante identificado despues
# ==================================================================

def test_a16_participante_identificado_posteriormente(
    servicio_compartidos, servicio_participantes, contexto, actor_a, actor_b, admin
) -> None:
    """Enriquecimiento descriptivo: ni hecho nuevo, ni efecto, ni OP-18."""
    hecho = _hecho(numero_participantes_total=4)
    resultado = servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[_gasto()],
            participantes=[
                DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_a)
            ],
        ),
    )
    hechos_antes = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE owner_user_id = %s",
        (contexto.owner_user_id,),
    )

    posterior = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho.hecho_id,
        row_version_esperada=resultado.row_version,
        participantes=[
            DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_b)
        ],
    )
    assert posterior.identificados == 2
    assert posterior.total_declarado == 4
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == hechos_antes
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho.hecho_id,),
    ) == (1,)


# ==================================================================
# A18 / A19 — dato falso frente a realidad posterior
# ==================================================================

def test_a18_importe_falso_se_corrige_sin_crear_hecho(
    servicio_compartidos, servicio_correcciones, contexto, actor_a, admin
) -> None:
    """Dato que nunca fue cierto: se corrige el efecto, no se inventa realidad.

    El reparto aqui esta `NO_DISPONIBLE`, que es el unico escenario en el que
    hoy se puede corregir el importe de un efecto: con atribuciones COMPLETA
    la suma debe cuadrar exactamente y las filas de atribucion no son
    corregibles por ninguna via (ver el hallazgo elevado con este bloque).
    """
    hecho = _hecho()
    efecto = _gasto()
    resultado = servicio_compartidos.registrar_gasto_compartido(
        contexto, DatosGastoCompartido(hecho=hecho, efectos=[efecto])
    )
    hechos_antes = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE owner_user_id = %s",
        (contexto.owner_user_id,),
    )

    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho.hecho_id,
            row_version_esperada=resultado.row_version,
            motivo="el importe del ticket estaba mal leido",
            efectos_a_actualizar={efecto.efecto_id: {"importe_delta": D("-40.0000")}},
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == hechos_antes
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s "
        "AND accion = 'ACTUALIZAR'",
        (efecto.efecto_id,),
    ) == (1,)


def test_a19_realidad_posterior_distinta_es_un_hecho_nuevo(
    servicio_compartidos, servicio_suplementos, contexto, actor_a, admin
) -> None:
    """El camarero cobro un recargo despues: realidad nueva, no correccion."""
    hecho = _hecho()
    servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[_gasto(atribuciones=[_atribucion(actor_a, TOTAL)])],
        ),
    )

    suplemento_id = uuid.uuid4()
    servicio_suplementos.registrar(
        contexto,
        DatosSuplemento(
            hecho_id=suplemento_id,
            efecto_id=uuid.uuid4(),
            tipo_efecto="GASTO",
            importe_delta=D("-3.5000"),
            fecha_hecho=dt.date(2026, 6, 5),
            moneda="EUR",
            fecha_demostrada=True,
            concepto="recargo de terraza",
            relacion_id=uuid.uuid4(),
            hecho_ajustado_id=hecho.hecho_id,
        ),
    )
    # Dos hechos vivos, cada uno con su importe. El original NO se toca.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT sum(importe_delta) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho.hecho_id,),
    ) == (-TOTAL,)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_relaciones "
        "WHERE hecho_origen_id = %s AND tipo_relacion = 'CORRIGE_A'",
        (suplemento_id,),
    ) == (1,)


# ==================================================================
# A10 / A11 / A12 — el gasto compartido cruzado con el resto del motor
# ==================================================================

def test_a10_devolucion_posterior_sobre_gasto_compartido(
    servicio_compartidos,
    servicio_devoluciones,
    contexto,
    actor_a,
    actor_b,
    cuenta,
    admin,
) -> None:
    """A10. El restaurante devuelve 10,00 de la cena de cuatro manos.

    La devolucion NO es un ingreso: es un GASTO negativo que conserva la
    naturaleza del original. Y NO reescribe la cena: el gasto compartido sigue
    valiendo 44,50 con su reparto intacto.
    """
    from app.core.modelos_devolucion import DatosDevolucion

    hecho = _hecho()
    servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[
                _gasto(
                    atribuciones=[
                        _atribucion(actor_a, MITAD),
                        _atribucion(actor_b, MITAD),
                    ]
                )
            ],
            tesoreria=[_tesoreria(hecho.hecho_id, cuenta)],
            aportaciones=[_aportacion(TOTAL, actor_id=actor_a)],
        ),
    )

    devolucion_id = uuid.uuid4()
    servicio_devoluciones.devolver(
        contexto,
        DatosDevolucion(
            hecho_id=devolucion_id,
            efecto_id=uuid.uuid4(),
            relacion_id=uuid.uuid4(),
            hecho_original_id=hecho.hecho_id,
            tipo_efecto="GASTO",
            importe=D("10.0000"),
            fecha_hecho=dt.date(2026, 6, 10),
            moneda="EUR",
            concepto="devolucion parcial del restaurante",
        ),
    )

    # La cena original no se toca.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT sum(importe_delta) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho.hecho_id,),
    ) == (-TOTAL,)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe_atribuido) FROM gapto.efecto_atribuciones a "
        "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s",
        (hecho.hecho_id,),
    ) == (2, -TOTAL)

    # La devolucion es GASTO positivo, no INGRESO, y cuelga por DEVOLUCION_DE.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tipo_efecto, importe_delta FROM gapto.hecho_efectos "
        "WHERE hecho_id = %s",
        (devolucion_id,),
    ) == ("GASTO", D("10.0000"))
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_relaciones WHERE hecho_origen_id = %s "
        "AND hecho_destino_id = %s AND tipo_relacion = 'DEVOLUCION_DE'",
        (devolucion_id, hecho.hecho_id),
    ) == (1,)
    # Y no ha fabricado tesoreria: devolver no es cobrar.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
        (devolucion_id,),
    ) == (0,)


def test_a11_reembolso_parcial_deja_saldo_vivo(
    servicio_posiciones, servicio_neto, contexto, contraparte, admin
) -> None:
    """A11. Me devuelven 40 de los 100 que me debian: quedan 60 vivos.

    El derecho NO se cierra solo, y el neto lo refleja de inmediato porque es
    derivado: nadie tiene que acordarse de actualizar un total.
    """
    from test_109_op12_posiciones import alta, delta
    from app.core.modelos_posicion import DatosReembolso

    datos = alta(contraparte)
    creada = servicio_posiciones.crear_posicion(contexto, datos)

    resultado = servicio_posiciones.reembolsar(
        contexto,
        entidad_id=datos.entidad_id,
        entidad_row_version_esperada=creada.entidad_row_version,
        datos=DatosReembolso(delta=delta("40.0000")),
    )
    assert resultado.saldo.importe == D("60.0000")
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado FROM gapto.derechos_obligaciones_financieras "
        "WHERE entidad_id = %s",
        (datos.entidad_id,),
    ) == ("ACTIVA",)

    segmento = servicio_neto.posicion_neta(
        contexto, contraparte_actor_id=contraparte
    ).segmento(contraparte, "EUR")
    assert segmento.neto == D("60.0000")


def test_a12_prevision_materializada_en_gasto_compartido(
    servicio_compartidos,
    servicio_previsiones,
    contexto,
    actor_a,
    actor_b,
    cuenta,
    admin,
) -> None:
    """A12. Se preveia la cena mensual y llego. Vincular no crea realidad.

    OP-17 solo anade la fila de `prevision_hechos`: no duplica el gasto, no
    crea efectos, no mueve liquidez. Antes de vincular, la previsión tampoco
    la habia movido (INV-16).
    """
    from app.core.modelos_prevision import DatosPrevisionManual, DatosVinculo

    prevision_id = uuid.uuid4()
    servicio_previsiones.crear_manual(
        contexto,
        DatosPrevisionManual(
            prevision_id=prevision_id,
            concepto="Cena mensual del grupo",
            tipo_hecho_codigo="GASTO",
            fecha_esperada_desde=dt.date(2026, 6, 1),
            fecha_esperada_hasta=dt.date(2026, 6, 30),
            flujo_tesoreria_esperado="SALIDA",
            moneda="EUR",
            presupuestable=True,
            importe_esperado=D("40.0000"),
            cuenta_salida_esperada_id=cuenta,
        ),
    )
    # INV-16: una previsión no mueve liquidez.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.movimientos_tesoreria m "
        "JOIN gapto.cuentas c ON c.id = m.cuenta_id WHERE c.owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == (0,)

    hecho = _hecho(concepto="cena del grupo de junio")
    servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[
                _gasto(
                    atribuciones=[
                        _atribucion(actor_a, MITAD),
                        _atribucion(actor_b, MITAD),
                    ]
                )
            ],
            tesoreria=[_tesoreria(hecho.hecho_id, cuenta)],
        ),
    )
    efectos_antes = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho.hecho_id,),
    )

    estado = servicio_previsiones.estado_de(contexto, prevision_id)
    servicio_previsiones.vincular_realidad(
        contexto,
        prevision_id=prevision_id,
        row_version_esperada=estado.row_version,
        datos=DatosVinculo(
            vinculo_id=uuid.uuid4(),
            hecho_id=hecho.hecho_id,
            importe_asignado=D("40.0000"),
            marcar_realizada=True,
        ),
    )

    # Vincular no duplica la realidad: mismos efectos, un solo hecho.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho.hecho_id,),
    ) == efectos_antes
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.prevision_hechos WHERE prevision_id = %s "
        "AND hecho_id = %s",
        (prevision_id, hecho.hecho_id),
    ) == (1,)
    # La desviacion 44,50 frente a 40,00 esperados es desviacion, no error.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_total FROM gapto.hechos_financieros WHERE id = %s",
        (hecho.hecho_id,),
    ) == (TOTAL,)


def test_n12_ningun_writer_emite_relaciones_reservadas() -> None:
    """N12. Auditoria estatica: `PARTE_DE`, `REPERCUSION_DE` y `REVERSA_A`
    no se emiten desde ningun servicio.

    Se inspecciona el codigo, no el comportamiento: una relacion reservada no
    se emite hoy, y el riesgo es que alguien la introduzca manana creyendo que
    representa un gasto compartido. El catalogo fisico las admite; lo que no
    existe es writer, y eso debe seguir siendo cierto.
    """
    import pathlib

    reservadas = ("PARTE_DE", "REPERCUSION_DE", "REVERSA_A")
    servicios = pathlib.Path(__file__).resolve().parents[2] / "backend/app/services"
    emisiones: list[str] = []
    for fichero in sorted(servicios.glob("*.py")):
        for numero, linea in enumerate(
            fichero.read_text(encoding="utf-8").splitlines(), start=1
        ):
            desnuda = linea.strip()
            if desnuda.startswith("#"):
                continue
            for token in reservadas:
                if f'"{token}"' in desnuda or f"'{token}'" in desnuda:
                    emisiones.append(f"{fichero.name}:{numero} {desnuda}")
    assert emisiones == []
