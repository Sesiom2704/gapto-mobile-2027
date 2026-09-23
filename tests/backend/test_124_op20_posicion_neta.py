# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_124_op20_posicion_neta.py
# Ruta: tests/backend/test_124_op20_posicion_neta.py
# Descripcion: F04-D038 §13 a §21. OP-20, lectura de posicion neta.
#
#   El caso gate C-12 vive aqui, y lo que vigila no es que el neto salga
#   -29,50: es que al leerlo no se toque nada. Un read-model que "arregla" los
#   saldos para que cuadren seria una compensacion extintiva disfrazada.
#   Ademas A13 (dos monedas), A14 (segmento indeterminado) y A15 (dos legacy
#   sin contraparte).
# Version: 0.2.0
#   0.2.0 (F04-D046 R1 · A19-bis): el test etiquetado C-12 modelaba otra cosa
#   (derecho 15 por la peluqueria, obligacion 44,50 por la cena). Se conserva
#   como aritmetica asimetrica de OP-20 con su nombre real y se anade el C-12
#   canonico: obligacion 15 (peluqueria) y derecho 15 (cena), neto 0.
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
from app.core.modelos_posicion import (
    DatosAltaPosicion,
    TIPO_DERECHO,
    TIPO_OBLIGACION,
)
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.neto_service import (
    DETERMINADO,
    INDETERMINADO,
    NO_COMPARABLE,
    NetoService,
)
from app.services.posiciones_service import PosicionesService
from conftest import leer_fila

D = decimal.Decimal
FECHA = dt.date(2026, 6, 1)


@pytest.fixture()
def servicio_neto(unidad: UnidadDeTrabajo) -> NetoService:
    return NetoService(unidad)


def _alta(
    servicio_posiciones: PosicionesService,
    contexto,
    *,
    tipo=TIPO_DERECHO,
    contraparte=None,
    moneda="EUR",
    importe=D("100.0000"),
    apertura=D("0"),
    concepto="posicion",
):
    datos = DatosAltaPosicion(
        entidad_id=uuid.uuid4(),
        nombre=concepto,
        tipo=tipo,
        contraparte_actor_id=contraparte,
        moneda=moneda,
        justificacion="DECISION_EXPLICITA",
        fecha_inicio_seguimiento=FECHA if apertura is not None else None,
        saldo_apertura=apertura,
        hecho_id=uuid.uuid4(),
        fecha_hecho=FECHA,
        concepto=concepto,
        efecto_id=uuid.uuid4(),
        vinculo_id=uuid.uuid4(),
        importe_inicial=importe,
    )
    servicio_posiciones.crear_posicion(contexto, datos)
    return datos


# ==================================================================
# C-12 — caso gate obligatorio (F04-D046 R1 · A19-bis)
# ==================================================================

def test_c12_peluqueria_y_cena(
    servicio_posiciones, servicio_neto, contexto, contraparte, admin
) -> None:
    """C-12 canonico a nivel de posiciones (Project Memory, caso gate).

    Peluqueria pagada por la pareja -> OBLIGACION del usuario de 15,00.
    Cena pagada por el usuario -> DERECHO de 15,00 por la parte explicita de
    la pareja (nunca el total del ticket). Neto 0, y ambas posiciones intactas.
    El caso integral con hechos, atribuciones, aportaciones y tesoreria vive
    en `test_132_f08_multiactor_y_excepciones.py::test_c12_gate_neteo_no_extingue_nada`.
    """
    peluqueria = _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_OBLIGACION,
        contraparte=contraparte,
        importe=D("15.0000"),
        concepto="peluqueria",
    )
    cena = _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_DERECHO,
        contraparte=contraparte,
        importe=D("15.0000"),
        concepto="cena",
    )
    segmento = servicio_neto.posicion_neta(
        contexto, contraparte_actor_id=contraparte
    ).segmento(contraparte, "EUR")
    assert segmento is not None
    assert segmento.estado == DETERMINADO
    assert segmento.neto == D("0")
    saldos = {d.nombre: d.saldo.importe for d in segmento.posiciones}
    assert saldos == {"peluqueria": D("15.0000"), "cena": D("15.0000")}
    for datos in (peluqueria, cena):
        assert leer_fila(
            admin,
            contexto.owner_user_id,
            "SELECT estado FROM gapto.derechos_obligaciones_financieras "
            "WHERE entidad_id = %s",
            (datos.entidad_id,),
        ) == ("ACTIVA",)


# ==================================================================
# OP-20 — aritmetica asimetrica del neto (antes etiquetada como C-12)
# ==================================================================

def test_op20_neto_asimetrico_derecho_menos_obligacion(
    servicio_posiciones, servicio_neto, contexto, contraparte, admin
) -> None:
    """Derecho 15,00 y obligacion 44,50 frente a la misma persona.

    NO es el caso C-12 (F04-D046 R1 · A19-bis): es la prueba aritmetica de
    OP-20 con importes asimetricos, que discrimina la direccion de cada
    posicion (neto -29,50) y conserva los importes originales. Se mantiene
    porque mata mutantes que el caso simetrico no puede distinguir.
    """
    peluqueria = _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_DERECHO,
        contraparte=contraparte,
        importe=D("15.0000"),
        concepto="peluqueria",
    )
    cena = _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_OBLIGACION,
        contraparte=contraparte,
        importe=D("44.5000"),
        concepto="cena",
    )

    resultado = servicio_neto.posicion_neta(
        contexto, contraparte_actor_id=contraparte
    )
    segmento = resultado.segmento(contraparte, "EUR")
    assert segmento is not None
    assert segmento.estado == DETERMINADO
    assert segmento.neto == D("-29.5000")
    assert len(segmento.posiciones) == 2

    # §21. Los importes originales permanecen INTACTOS: 15,00 y 44,50.
    saldos = {
        detalle.nombre: detalle.saldo.importe for detalle in segmento.posiciones
    }
    assert saldos == {"peluqueria": D("15.0000"), "cena": D("44.5000")}

    for datos, esperado in ((peluqueria, D("15.0000")), (cena, D("44.5000"))):
        assert leer_fila(
            admin,
            contexto.owner_user_id,
            "SELECT estado, saldo_apertura FROM "
            "gapto.derechos_obligaciones_financieras WHERE entidad_id = %s",
            (datos.entidad_id,),
        ) == ("ACTIVA", D("0.0000"))
        assert leer_fila(
            admin,
            contexto.owner_user_id,
            "SELECT sum(importe_delta) FROM gapto.hecho_efectos WHERE id = %s",
            (datos.efecto_id,),
        ) == (esperado,)


def test_op20_no_escribe_nada(
    servicio_posiciones, servicio_neto, contexto, contraparte, admin
) -> None:
    """N11. Snapshot antes y despues identico, auditoria incluida."""
    _alta(servicio_posiciones, contexto, contraparte=contraparte)

    def huella():
        return leer_fila(
            admin,
            contexto.owner_user_id,
            "SELECT (SELECT count(*) FROM gapto.derechos_obligaciones_financieras), "
            "(SELECT count(*) FROM gapto.hechos_financieros), "
            "(SELECT count(*) FROM gapto.hecho_efectos), "
            "(SELECT count(*) FROM gapto.movimientos_tesoreria), "
            "(SELECT count(*) FROM gapto.hecho_relaciones), "
            "(SELECT count(*) FROM gapto.auditoria)",
            (),
        )

    antes = huella()
    servicio_neto.posicion_neta(contexto, contraparte_actor_id=contraparte)
    servicio_neto.posicion_neta(contexto)
    assert huella() == antes


# ==================================================================
# §14 — signo canonico
# ==================================================================

def test_solo_derecho_aporta_positivo(
    servicio_posiciones, servicio_neto, contexto, contraparte
) -> None:
    _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_DERECHO,
        contraparte=contraparte,
        importe=D("300.0000"),
    )
    segmento = servicio_neto.posicion_neta(
        contexto, contraparte_actor_id=contraparte
    ).segmento(contraparte, "EUR")
    assert segmento.neto == D("300.0000")


def test_solo_obligacion_aporta_negativo(
    servicio_posiciones, servicio_neto, contexto, contraparte
) -> None:
    _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_OBLIGACION,
        contraparte=contraparte,
        importe=D("120.0000"),
    )
    segmento = servicio_neto.posicion_neta(
        contexto, contraparte_actor_id=contraparte
    ).segmento(contraparte, "EUR")
    assert segmento.neto == D("-120.0000")


# ==================================================================
# §15 y §17 — A13: monedas distintas
# ==================================================================

def test_a13_misma_contraparte_con_eur_y_usd(
    servicio_posiciones, servicio_neto, contexto, contraparte
) -> None:
    """Dos segmentos. No hay neto total que mezcle monedas."""
    _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_DERECHO,
        contraparte=contraparte,
        importe=D("300.0000"),
        moneda="EUR",
    )
    _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_OBLIGACION,
        contraparte=contraparte,
        importe=D("120.0000"),
        moneda="EUR",
    )
    _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_DERECHO,
        contraparte=contraparte,
        importe=D("50.0000"),
        moneda="USD",
    )

    resultado = servicio_neto.posicion_neta(
        contexto, contraparte_actor_id=contraparte
    )
    assert len(resultado.segmentos) == 2
    assert resultado.segmento(contraparte, "EUR").neto == D("180.0000")
    assert resultado.segmento(contraparte, "USD").neto == D("50.0000")


# ==================================================================
# §16 — A14: indeterminado es resultado, no error
# ==================================================================

def test_a14_segmento_con_saldo_indeterminado(
    servicio_posiciones, servicio_neto, contexto, contraparte
) -> None:
    _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_DERECHO,
        contraparte=contraparte,
        importe=D("300.0000"),
        concepto="conocida",
    )
    _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_OBLIGACION,
        contraparte=contraparte,
        apertura=None,
        importe=None,
        concepto="heredada",
    )

    segmento = servicio_neto.posicion_neta(
        contexto, contraparte_actor_id=contraparte
    ).segmento(contraparte, "EUR")
    assert segmento.estado == INDETERMINADO
    assert segmento.neto is None

    # El desglose conserva lo que SI se sabe, sin llamarlo neto.
    conocidas = [d for d in segmento.posiciones if d.saldo.conocido]
    assert len(conocidas) == 1
    assert conocidas[0].aporte == D("300.0000")
    assert any(not d.saldo.conocido for d in segmento.posiciones)


# ==================================================================
# §18 — A15: contrapartes desconocidas
# ==================================================================

def test_a15_dos_posiciones_sin_contraparte_no_se_agrupan(
    servicio_posiciones, servicio_neto, contexto, contraparte, admin
) -> None:
    """Dos NULL pueden ser dos personas distintas. Nunca se compensan."""
    # OP-12 EXIGE contraparte: `CONTRAPARTE_REQUERIDA`. Una posicion sin ella
    # solo puede venir de una importacion legacy, de modo que se construye por
    # via administrativa. Que el motor no pueda crearlas no significa que el
    # read-model pueda ignorarlas.
    una = _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_DERECHO,
        contraparte=contraparte,
        importe=D("40.0000"),
        concepto="legacy A",
    )
    otra = _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_OBLIGACION,
        contraparte=contraparte,
        importe=D("40.0000"),
        concepto="legacy B",
    )
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)",
                (str(contexto.owner_user_id),),
            )
            cursor.execute(
                "UPDATE gapto.derechos_obligaciones_financieras "
                "SET contraparte_actor_id = NULL WHERE entidad_id = ANY(%s)",
                ([una.entidad_id, otra.entidad_id],),
            )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")

    resultado = servicio_neto.posicion_neta(contexto)
    sueltas = [s for s in resultado.segmentos if s.estado == NO_COMPARABLE]
    assert len(sueltas) == 2
    assert all(segmento.neto is None for segmento in sueltas)
    assert {segmento.posiciones[0].entidad_id for segmento in sueltas} == {
        una.entidad_id,
        otra.entidad_id,
    }


# ==================================================================
# §19 — posiciones cerradas
# ==================================================================

def test_posicion_cerrada_fuera_del_neto_vivo(
    servicio_posiciones, servicio_neto, contexto, contraparte, admin
) -> None:
    viva = _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_DERECHO,
        contraparte=contraparte,
        importe=D("30.0000"),
        concepto="viva",
    )
    cerrada = _alta(
        servicio_posiciones,
        contexto,
        tipo=TIPO_OBLIGACION,
        contraparte=contraparte,
        importe=D("500.0000"),
        concepto="cerrada",
    )
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)",
                (str(contexto.owner_user_id),),
            )
            cursor.execute(
                "UPDATE gapto.derechos_obligaciones_financieras "
                "SET estado = 'CERRADA' WHERE entidad_id = %s",
                (cerrada.entidad_id,),
            )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")

    segmento = servicio_neto.posicion_neta(
        contexto, contraparte_actor_id=contraparte
    ).segmento(contraparte, "EUR")
    assert segmento.neto == D("30.0000")
    assert [d.entidad_id for d in segmento.posiciones] == [viva.entidad_id]


# ==================================================================
# §20 y F04-D036 — snapshot unico y fail-closed
# ==================================================================

def test_una_sola_sentencia_un_solo_snapshot(
    servicio_posiciones, servicio_neto, contexto, contraparte
) -> None:
    _alta(servicio_posiciones, contexto, contraparte=contraparte)
    servicio_neto.posicion_neta(contexto, contraparte_actor_id=contraparte)
    traza = servicio_neto.ultima_traza
    assert traza.operacion == "OP-20 posicion_neta"
    assert traza.intentos_realizados == 1


def test_falla_cerrado_ante_delta_de_otra_moneda(
    servicio_posiciones, servicio_neto, contexto, contraparte, admin
) -> None:
    """El estado se corrompe por fuera del motor y OP-20 lo denuncia."""
    datos = _alta(
        servicio_posiciones, contexto, contraparte=contraparte, importe=D("100.0000")
    )
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
                (datos.hecho_id,),
            )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")

    with pytest.raises(ErrorMotor) as excepcion:
        servicio_neto.posicion_neta(contexto, contraparte_actor_id=contraparte)
    assert (
        excepcion.value.codigo
        is CodigoError.INVARIANTE_MONETARIA_POSICION_VIOLADA
    )
