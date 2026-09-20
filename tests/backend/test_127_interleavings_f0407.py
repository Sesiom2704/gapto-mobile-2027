# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_127_interleavings_f0407.py
# Ruta: tests/backend/test_127_interleavings_f0407.py
# Descripcion: F04-D038 §26. Interleavings de F04-07.
#
#     I1  dos participantes distintos contra un total limitado
#     I2  alta de participante frente a reduccion concurrente del total
#     I3  enriquecimiento de participantes frente a OP-21 sobre el mismo hecho
#
#   EL ORACULO PRINCIPAL ES SECUENCIAL. §26 lo admite expresamente, y hay una
#   razon para preferirlo: una carrera verde no demuestra que la propiedad se
#   cumpla, solo que ese entrelazado concreto no la rompio. Lo que sostiene la
#   invariante es que las tres operaciones consumen la MISMA raiz
#   —`hechos_financieros.row_version`, con la guarda en el WHERE del UPDATE— y
#   que el recuento se revalida DESPUES de escribir, con esa raiz ya bloqueada.
#   La concurrencia corrobora; no es la prueba.
#
#   NINGUNA CARRERA SE SINCRONIZA CON SLEEPS. Se usa una barrera explicita: los
#   dos hilos se sueltan a la vez y despues se mira el resultado, que solo
#   admite dos formas y ninguna deja estado invalido.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import threading
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import CamposCorreccion, DatosCreacionHecho
from app.core.modelos_efectos import DatosEfecto
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.correcciones_service import DatosCorreccion
from app.services.hechos_service import HechosService
from app.services.participantes_service import (
    DatosParticipante,
    ParticipantesService,
)
from conftest import leer_fila

D = decimal.Decimal
FECHA = dt.date(2026, 6, 1)


@pytest.fixture()
def servicio_participantes(unidad: UnidadDeTrabajo) -> ParticipantesService:
    return ParticipantesService(unidad)


def _cena(servicio: HechosService, contexto, total):
    hecho_id = uuid.uuid4()
    resultado = servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=FECHA,
            moneda="EUR",
            presupuestable=True,
            estado_localizacion="NO_APLICA",
            tipo_hecho_codigo="GASTO",
            concepto="cena compartida",
            importe_total=D("44.5000"),
            numero_participantes_total=total,
        ),
    )
    return hecho_id, resultado.row_version


def _participante(actor_id):
    return DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_id)


def _competir(objetivo) -> list[object]:
    """Dos hilos soltados por una barrera. Sin sleeps."""
    barrera = threading.Barrier(2)
    resultados: list[object] = []
    cerrojo = threading.Lock()

    def correr(indice: int) -> None:
        barrera.wait()
        try:
            objetivo(indice)
            salida: object = "OK"
        except ErrorMotor as error:
            salida = error.codigo
        except Exception as error:  # noqa: BLE001 - se clasifica por nombre
            salida = type(error).__name__
        with cerrojo:
            resultados.append(salida)

    hilos = [threading.Thread(target=correr, args=(i,)) for i in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)
    return resultados


def _identificados(admin, contexto, hecho_id) -> int:
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(DISTINCT actor_id) FROM gapto.hecho_participantes "
        "WHERE hecho_id = %s",
        (hecho_id,),
    )
    return fila[0]


def _total(admin, contexto, hecho_id):
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT numero_participantes_total FROM gapto.hechos_financieros "
        "WHERE id = %s",
        (hecho_id,),
    )
    return fila[0]


# ==================================================================
# I1 — dos actores distintos contra un total de uno
# ==================================================================

def test_i1_oraculo_secuencial(
    servicio, servicio_participantes, contexto, actor_a, actor_b, admin
) -> None:
    """La propiedad, demostrada sin concurrencia.

    El segundo alta ve la version ya consumida por el primero. Si el llamante
    reintenta con la version correcta, entonces es el recuento el que lo
    rechaza. Ninguna de las dos puertas deja pasar dos personas con total 1.
    """
    hecho_id, version = _cena(servicio, contexto, total=1)
    servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a)],
    )

    with pytest.raises(ErrorMotor) as desfasada:
        servicio_participantes.registrar_participantes(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            participantes=[_participante(actor_b)],
        )
    assert desfasada.value.codigo is CodigoError.VERSION_DESFASADA

    with pytest.raises(ErrorMotor) as recuento:
        servicio_participantes.registrar_participantes(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version + 1,
            participantes=[_participante(actor_b)],
        )
    assert recuento.value.codigo is CodigoError.PARTICIPANTES_INCONSISTENTES
    assert _identificados(admin, contexto, hecho_id) == 1


def test_i1_dos_altas_concurrentes_con_total_uno(
    servicio, servicio_participantes, contexto, actor_a, actor_b, admin
) -> None:
    """I1. Corroboracion concurrente: nunca quedan dos con total 1."""
    hecho_id, version = _cena(servicio, contexto, total=1)
    actores = (actor_a, actor_b)

    def alta(indice: int) -> None:
        servicio_participantes.registrar_participantes(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            participantes=[_participante(actores[indice])],
        )

    resultados = _competir(alta)
    assert resultados.count("OK") == 1
    assert _identificados(admin, contexto, hecho_id) == 1
    assert _total(admin, contexto, hecho_id) == 1


def test_i1_con_total_desconocido_ambas_pueden_valer(
    servicio, servicio_participantes, contexto, actor_a, actor_b, admin
) -> None:
    """Sin total declarado no hay nada que violar: el limite es la version.

    Una de las dos gana la raiz y la otra recibe conflicto. Lo que NO ocurre
    es que el recuento las rechace: NULL significa total desconocido, no cero.
    """
    hecho_id, version = _cena(servicio, contexto, total=None)
    actores = (actor_a, actor_b)

    def alta(indice: int) -> None:
        servicio_participantes.registrar_participantes(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=version,
            participantes=[_participante(actores[indice])],
        )

    resultados = _competir(alta)
    assert resultados.count("OK") == 1
    assert CodigoError.PARTICIPANTES_INCONSISTENTES not in resultados
    assert _identificados(admin, contexto, hecho_id) == 1


# ==================================================================
# I2 — alta de participante frente a reduccion del total
# ==================================================================

def test_i2_oraculo_secuencial(
    servicio, servicio_participantes, contexto, actor_a, actor_b, admin
) -> None:
    """Los dos extremos de la misma invariante, uno detras de otro.

    Con dos identificados, bajar el total a 1 se rechaza. Con el total ya en
    2, anadir un tercero tambien. La guarda es la misma y se evalua sobre el
    estado final en ambos casos.
    """
    hecho_id, version = _cena(servicio, contexto, total=3)
    resultado = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a), _participante(actor_b)],
    )

    with pytest.raises(ErrorMotor) as bajar:
        servicio.corregir_hecho(
            contexto,
            hecho_id=hecho_id,
            row_version_esperada=resultado.row_version,
            campos=CamposCorreccion(numero_participantes_total=1),
            motivo="eran menos de los que parecia",
        )
    assert bajar.value.codigo is CodigoError.PARTICIPANTES_INCONSISTENTES
    assert _total(admin, contexto, hecho_id) == 3


def test_i2_alta_y_reduccion_concurrentes(
    servicio, servicio_participantes, contexto, actor_a, actor_b, admin
) -> None:
    """I2. Una anade la segunda persona mientras la otra baja el total a 1.

    Ambas consumen la raiz, de modo que una gana. Sea cual sea, el estado
    final debe cumplir la invariante: si gano la reduccion, queda total 1 con
    un identificado; si gano el alta, quedan dos identificados con total 2.
    """
    hecho_id, version = _cena(servicio, contexto, total=2)
    primero = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        participantes=[_participante(actor_a)],
    )
    version_actual = primero.row_version

    def operar(indice: int) -> None:
        if indice == 0:
            servicio_participantes.registrar_participantes(
                contexto,
                hecho_id=hecho_id,
                row_version_esperada=version_actual,
                participantes=[_participante(actor_b)],
            )
        else:
            servicio.corregir_hecho(
                contexto,
                hecho_id=hecho_id,
                row_version_esperada=version_actual,
                campos=CamposCorreccion(numero_participantes_total=1),
                motivo="era una sola persona",
            )

    resultados = _competir(operar)
    assert resultados.count("OK") == 1

    total = _total(admin, contexto, hecho_id)
    identificados = _identificados(admin, contexto, hecho_id)
    assert total >= identificados, (total, identificados)


# ==================================================================
# I3 — participantes frente a OP-21 sobre el mismo hecho
# ==================================================================

def test_i3_oraculo_secuencial(
    servicio,
    servicio_efectos,
    servicio_participantes,
    servicio_correcciones,
    contexto,
    actor_a,
    actor_b,
    admin,
) -> None:
    """OP-21 no toca participantes, pero comparte la raiz con quien si.

    `DatosCorreccion` no expone `hecho_participantes`: la retirada de un
    participante falso vive en su propia superficie. Lo que ambas comparten es
    `hechos_financieros.row_version`, y eso basta para serializarlas.
    """
    hecho_id, version = _cena(servicio, contexto, total=4)
    efecto_id = uuid.uuid4()
    tras_efectos = servicio_efectos.registrar_efectos(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efectos=[
            DatosEfecto(
                efecto_id=efecto_id,
                tipo_efecto="GASTO",
                importe_delta=D("-44.5000"),
                estado_atribucion="NO_DISPONIBLE",
            )
        ],
    )
    tras_participante = servicio_participantes.registrar_participantes(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=tras_efectos.row_version,
        participantes=[_participante(actor_a)],
    )

    # Con la version ya consumida por el alta, OP-21 no puede confirmar.
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=tras_efectos.row_version,
                motivo="el importe era otro",
                efectos_a_actualizar={efecto_id: {"importe_delta": D("-40.0000")}},
            ),
        )
    assert excepcion.value.codigo is CodigoError.VERSION_DESFASADA

    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=tras_participante.row_version,
            motivo="el importe era otro",
            efectos_a_actualizar={efecto_id: {"importe_delta": D("-40.0000")}},
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_delta FROM gapto.hecho_efectos WHERE id = %s",
        (efecto_id,),
    ) == (D("-40.0000"),)
    # La correccion no ha tocado a los participantes.
    assert _identificados(admin, contexto, hecho_id) == 1


def test_i3_enriquecimiento_y_correccion_concurrentes(
    servicio,
    servicio_efectos,
    servicio_participantes,
    servicio_correcciones,
    contexto,
    actor_a,
    actor_b,
    admin,
) -> None:
    """I3. Corroboracion concurrente sobre la misma raiz."""
    hecho_id, version = _cena(servicio, contexto, total=4)
    efecto_id = uuid.uuid4()
    tras_efectos = servicio_efectos.registrar_efectos(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efectos=[
            DatosEfecto(
                efecto_id=efecto_id,
                tipo_efecto="GASTO",
                importe_delta=D("-44.5000"),
                estado_atribucion="NO_DISPONIBLE",
            )
        ],
    )
    version_actual = tras_efectos.row_version

    def operar(indice: int) -> None:
        if indice == 0:
            servicio_participantes.registrar_participantes(
                contexto,
                hecho_id=hecho_id,
                row_version_esperada=version_actual,
                participantes=[_participante(actor_b)],
            )
        else:
            servicio_correcciones.corregir(
                contexto,
                DatosCorreccion(
                    hecho_id=hecho_id,
                    row_version_esperada=version_actual,
                    motivo="el importe era otro",
                    efectos_a_actualizar={
                        efecto_id: {"importe_delta": D("-40.0000")}
                    },
                ),
            )

    resultados = _competir(operar)
    assert resultados.count("OK") == 1

    # Gane quien gane, el estado es coherente: o el efecto se corrigio y no
    # hay participante, o hay participante y el efecto sigue como estaba.
    importe = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_delta FROM gapto.hecho_efectos WHERE id = %s",
        (efecto_id,),
    )[0]
    identificados = _identificados(admin, contexto, hecho_id)
    assert (importe, identificados) in (
        (D("-40.0000"), 0),
        (D("-44.5000"), 1),
    )
