# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_121_coherencia_posicion.py
# Ruta: tests/backend/test_121_coherencia_posicion.py
# Descripcion: F04-D036. Coherencia posicion <-> efecto en los tres caminos
#   que pueden romperla y en la lectura que debe detectarla.
#
#   Cada prohibicion viene acompanada de su POSITIVO. Una guarda que solo se
#   prueba por el lado que rechaza acaba siendo demasiado ancha: `moneda` no
#   pasa a ser inmutable, `tipo_efecto` sigue siendo corregible y un importe
#   falso se sigue corrigiendo aunque mueva el saldo derivado.
# Version: 0.2.0
#   0.2.0 (mandato F04 R1+R2 v0.3 + E01): el caso que anade GASTO a un hecho
#   de posicion lo crea DESCONOCIDA y aporta la decision; el resto conserva
#   NO_APLICA.
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
from app.core.modelos import CamposCorreccion, DatosCreacionHecho
from app.core.modelos_efectos import DatosEfecto
from app.core.modelos_posicion import DatosAltaPosicion, TIPO_DERECHO
from app.services.correcciones_service import CorreccionesService, DatosCorreccion
from app.services.efectos_service import EfectosService
from app.services.hechos_service import HechosService
from app.services.posiciones_service import PosicionesService
from conftest import leer_fila

D = decimal.Decimal
FECHA = dt.date(2026, 6, 1)
TIPO_POSICION = "GENERACION_DERECHO_OBLIGACION"


def alta(contraparte: uuid.UUID, **extra) -> DatosAltaPosicion:
    base = {
        "entidad_id": uuid.uuid4(),
        "nombre": "Posicion F04-D036",
        "tipo": TIPO_DERECHO,
        "contraparte_actor_id": contraparte,
        "moneda": "EUR",
        "justificacion": "DECISION_EXPLICITA",
        "fecha_inicio_seguimiento": FECHA,
        "saldo_apertura": D("0"),
        "hecho_id": uuid.uuid4(),
        "fecha_hecho": FECHA,
        "concepto": "alta de posicion",
        "efecto_id": uuid.uuid4(),
        "vinculo_id": uuid.uuid4(),
        "importe_inicial": D("100.0000"),
    }
    base.update(extra)
    return DatosAltaPosicion(**base)


def _crear_hecho(
    servicio: HechosService, contexto, moneda: str, estado_localizacion: str = "NO_APLICA"
):
    hecho_id = uuid.uuid4()
    resultado = servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=FECHA,
            moneda=moneda,
            presupuestable=True,
            estado_localizacion=estado_localizacion,
            tipo_hecho_codigo=TIPO_POSICION,
            concepto=f"hecho en {moneda}",
        ),
    )
    return hecho_id, resultado.row_version


@pytest.fixture()
def derecho(servicio_posiciones: PosicionesService, contexto, contraparte):
    datos = alta(contraparte)
    resultado = servicio_posiciones.crear_posicion(contexto, datos)
    assert resultado.saldo.conocido and resultado.saldo.importe == D("100.0000")
    return datos


def _version_hecho(admin, contexto, hecho_id: uuid.UUID) -> tuple:
    return leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT row_version, moneda FROM gapto.hechos_financieros WHERE id = %s",
        (hecho_id,),
    )


# ==================================================================
# Camino 1 - nacimiento del vinculo
# ==================================================================

def test_alta_sobre_hecho_de_otra_moneda_rechazada(
    servicio: HechosService,
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    contraparte: uuid.UUID,
    admin: psycopg.Connection,
) -> None:
    """Una posicion EUR no puede nacer alimentada por un hecho USD."""
    hecho_id, version = _crear_hecho(servicio, contexto, "USD")
    datos = alta(contraparte, hecho_id=hecho_id, hecho_row_version_esperada=version)

    with pytest.raises(ErrorMotor) as excepcion:
        servicio_posiciones.crear_posicion(contexto, datos)
    assert excepcion.value.codigo is CodigoError.MONEDA_POSICION_INCOMPATIBLE

    # Cero mutaciones: la transaccion entera se deshace, incluida la entidad.
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.entidades WHERE id = %s",
        (datos.entidad_id,),
    )
    assert fila == (0,)


def test_alta_sobre_hecho_de_la_misma_moneda_permitida(
    servicio: HechosService,
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    contraparte: uuid.UUID,
) -> None:
    """El positivo: engancharse a un hecho preexistente sigue siendo legitimo."""
    hecho_id, version = _crear_hecho(servicio, contexto, "EUR")
    datos = alta(contraparte, hecho_id=hecho_id, hecho_row_version_esperada=version)

    resultado = servicio_posiciones.crear_posicion(contexto, datos)
    assert resultado.saldo.conocido and resultado.saldo.importe == D("100.0000")


# ==================================================================
# Camino 2 - OP-02 corrige la moneda del hecho
# ==================================================================

def test_op02_no_puede_cambiar_la_moneda_de_un_hecho_vinculado(
    servicio: HechosService,
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    derecho: DatosAltaPosicion,
    admin: psycopg.Connection,
) -> None:
    """La guarda de nacimiento sola no basta: el hecho podia mutar despues."""
    version, moneda = _version_hecho(admin, contexto, derecho.hecho_id)
    assert moneda == "EUR"

    with pytest.raises(ErrorMotor) as excepcion:
        servicio.corregir_hecho(
            contexto,
            hecho_id=derecho.hecho_id,
            row_version_esperada=version,
            campos=CamposCorreccion(moneda="USD"),
            motivo="la moneda capturada era falsa",
        )
    assert excepcion.value.codigo is CodigoError.MONEDA_POSICION_INCOMPATIBLE

    # Ni mutacion, ni version consumida, ni auditoria de algo que no ocurrio.
    assert _version_hecho(admin, contexto, derecho.hecho_id) == (version, "EUR")
    auditado = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s "
        "AND accion = 'ACTUALIZAR'",
        (derecho.hecho_id,),
    )
    assert auditado == (0,)
    saldo = servicio_posiciones.saldo(contexto, entidad_id=derecho.entidad_id)
    assert saldo.saldo.conocido and saldo.saldo.importe == D("100.0000")


def test_op02_corrige_la_moneda_de_un_hecho_sin_posicion(
    servicio: HechosService, contexto: ContextoOperacion, admin: psycopg.Connection
) -> None:
    """`moneda` NO pasa a ser inmutable: sin dependencia, se corrige."""
    hecho_id, version = _crear_hecho(servicio, contexto, "EUR")

    resultado = servicio.corregir_hecho(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(moneda="USD"),
        motivo="la moneda capturada era falsa",
    )
    assert resultado.row_version == version + 1
    assert _version_hecho(admin, contexto, hecho_id)[1] == "USD"


def test_op02_corrige_otros_campos_de_un_hecho_vinculado(
    servicio: HechosService,
    contexto: ContextoOperacion,
    derecho: DatosAltaPosicion,
    admin: psycopg.Connection,
) -> None:
    """La guarda es de moneda, no un candado sobre el hecho entero."""
    version, _ = _version_hecho(admin, contexto, derecho.hecho_id)

    resultado = servicio.corregir_hecho(
        contexto,
        hecho_id=derecho.hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(concepto="concepto corregido"),
        motivo="el concepto estaba mal escrito",
    )
    assert resultado.row_version == version + 1


def test_op02_moneda_identica_no_dispara_la_guarda(
    servicio: HechosService,
    contexto: ContextoOperacion,
    derecho: DatosAltaPosicion,
    admin: psycopg.Connection,
) -> None:
    """Reafirmar la misma moneda no cambia nada y no puede fallar."""
    version, _ = _version_hecho(admin, contexto, derecho.hecho_id)

    resultado = servicio.corregir_hecho(
        contexto,
        hecho_id=derecho.hecho_id,
        row_version_esperada=version,
        campos=CamposCorreccion(moneda="EUR"),
        motivo="se reafirma la moneda",
    )
    assert resultado.row_version == version + 1


# ==================================================================
# Camino 3 - OP-21 y el estado final
# ==================================================================

def test_op21_no_puede_cambiar_la_naturaleza_de_un_efecto_vinculado(
    servicio_correcciones: CorreccionesService,
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    derecho: DatosAltaPosicion,
    admin: psycopg.Connection,
) -> None:
    """Un derecho no se extingue corrigiendo el tipo de su efecto.

    Sin esta guarda el saldo pasaba de 100,0000 a 0,0000 CONOCIDO: no
    indeterminado, sino la afirmacion positiva de que no queda nada por
    cobrar, sin cobro, sin condonacion y sin cierre.
    """
    version, _ = _version_hecho(admin, contexto, derecho.hecho_id)

    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=derecho.hecho_id,
                row_version_esperada=version,
                motivo="el tipo de efecto estaba mal capturado",
                efectos_a_actualizar={derecho.efecto_id: {"tipo_efecto": "GASTO"}},
            ),
        )
    assert excepcion.value.codigo is CodigoError.NATURALEZA_INCOMPATIBLE

    saldo = servicio_posiciones.saldo(contexto, entidad_id=derecho.entidad_id)
    assert saldo.saldo.conocido and saldo.saldo.importe == D("100.0000")
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tipo_efecto FROM gapto.hecho_efectos WHERE id = %s",
        (derecho.efecto_id,),
    )
    assert fila == ("DERECHO_COBRO",)


def test_op21_corrige_el_importe_de_un_efecto_vinculado(
    servicio_correcciones: CorreccionesService,
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    derecho: DatosAltaPosicion,
    admin: psycopg.Connection,
) -> None:
    """Un importe falso SI se corrige, y el saldo derivado se mueve con el.

    Es la frontera de la guarda: el saldo es derivado por diseno, de modo
    que cambiarlo corrigiendo el dato origen es exactamente lo que OP-21
    debe poder hacer.
    """
    version, _ = _version_hecho(admin, contexto, derecho.hecho_id)

    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=derecho.hecho_id,
            row_version_esperada=version,
            motivo="el importe capturado era falso",
            efectos_a_actualizar={derecho.efecto_id: {"importe_delta": D("80.0000")}},
        ),
    )
    saldo = servicio_posiciones.saldo(contexto, entidad_id=derecho.entidad_id)
    assert saldo.saldo.conocido and saldo.saldo.importe == D("80.0000")


def test_op21_corrige_la_naturaleza_de_un_efecto_no_vinculado(
    servicio: HechosService,
    servicio_efectos: EfectosService,
    servicio_correcciones: CorreccionesService,
    contexto: ContextoOperacion,
    admin: psycopg.Connection,
) -> None:
    """Sin posicion alcanzada, `tipo_efecto` sigue siendo corregible.

    F04-D046 R2 (mandato v0.3 §9): el hecho recibe un GASTO, asi que su
    localizacion es aplicable (DESCONOCIDA) y OP-04 exige la decision
    `presupuestable` al nacer el primer GASTO.
    """
    hecho_id, version = _crear_hecho(
        servicio, contexto, "EUR", estado_localizacion="DESCONOCIDA"
    )
    efecto_id = uuid.uuid4()
    resultado = servicio_efectos.registrar_efectos(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=version,
        efectos=[
            DatosEfecto(
                efecto_id=efecto_id,
                tipo_efecto="GASTO",
                importe_delta=D("50.0000"),
                estado_atribucion="NO_DISPONIBLE",
            )
        ],
        presupuestable=True,
    )

    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=resultado.row_version,
            motivo="el tipo de efecto estaba mal capturado",
            efectos_a_actualizar={efecto_id: {"tipo_efecto": "INGRESO"}},
        ),
    )
    fila = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT tipo_efecto FROM gapto.hecho_efectos WHERE id = %s",
        (efecto_id,),
    )
    assert fila == ("INGRESO",)


# ==================================================================
# Lectura - defensa en profundidad
# ==================================================================

def test_la_lectura_falla_cerrada_ante_un_estado_incoherente(
    servicio_posiciones: PosicionesService,
    contexto: ContextoOperacion,
    derecho: DatosAltaPosicion,
    admin: psycopg.Connection,
) -> None:
    """El estado se corrompe por fuera del motor y la lectura lo denuncia.

    Los write-paths ya no pueden producirlo, asi que se fabrica por via
    administrativa: es la unica forma de demostrar que la lectura no se
    limita a confiar en ellos. Ignorar la fila devolveria 0,00 y sumarla
    devolveria una suma de EUR y USD; ambas cosas son peores que fallar.
    """
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)",
                (str(contexto.owner_user_id),),
            )
            cursor.execute(
                "UPDATE gapto.hechos_financieros SET moneda = 'USD' WHERE id = %s",
                (derecho.hecho_id,),
            )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")

    with pytest.raises(ErrorMotor) as excepcion:
        servicio_posiciones.saldo(contexto, entidad_id=derecho.entidad_id)
    assert (
        excepcion.value.codigo
        is CodigoError.INVARIANTE_MONETARIA_POSICION_VIOLADA
    )
