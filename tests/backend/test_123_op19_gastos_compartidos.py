# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_123_op19_gastos_compartidos.py
# Ruta: tests/backend/test_123_op19_gastos_compartidos.py
# Descripcion: F04-D038 §3, §4, §5, §6. OP-19 como operacion compuesta y
#   atomica.
#
#   Lo que estas pruebas vigilan no es que OP-19 escriba: es que escriba TODO
#   o NADA, que no invente posiciones y que no duplique ninguna capacidad ya
#   certificada. El caso C-11 completo y los adversariales A4, A5, A6 y A7
#   viven aqui.
# Version: 0.2.0
#   0.2.0 (F04-D046 R1 · A19): GASTO de la cena con signo canonico +X (y sus
#   atribuciones, F04-D007). La tesoreria no cambia: la salida sigue siendo
#   -X. Las propiedades demostradas se conservan.
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
from app.services.participantes_service import DatosParticipante
from conftest import leer_fila

D = decimal.Decimal
FECHA = dt.date(2026, 6, 1)
TOTAL_CENA = D("44.5000")
MITAD = D("22.2500")


@pytest.fixture()
def servicio_compartidos(unidad: UnidadDeTrabajo) -> GastosCompartidosService:
    from app.services.previsiones_service import impacto_correccion_ancla

    return GastosCompartidosService(unidad, impacto_ancla=impacto_correccion_ancla)


def _hecho(total_participantes=None, hecho_id=None) -> DatosCreacionHecho:
    return DatosCreacionHecho(
        hecho_id=hecho_id or uuid.uuid4(),
        fecha_hecho=FECHA,
        moneda="EUR",
        presupuestable=True,
        estado_localizacion="NO_APLICA",
        tipo_hecho_codigo="GASTO",
        concepto="cena compartida",
        importe_total=TOTAL_CENA,
        numero_participantes_total=total_participantes,
    )


def _gasto(importe=TOTAL_CENA, atribuciones=()) -> DatosEfecto:
    return DatosEfecto(
        efecto_id=uuid.uuid4(),
        tipo_efecto="GASTO",
        # F04-D046 R1. GASTO +X aumenta el gasto (DB Schema §34).
        importe_delta=importe,
        estado_atribucion="COMPLETA" if atribuciones else "NO_DISPONIBLE",
        atribuciones=tuple(atribuciones),
    )


def _atribucion(actor_id, importe) -> DatosAtribucion:
    return DatosAtribucion(
        atribucion_id=uuid.uuid4(),
        actor_id=actor_id,
        # F04-D007: la atribucion hereda el signo del efecto (GASTO +X).
        importe_atribuido=importe,
        criterio_atribucion="PARTES_IGUALES",
    )


def _tesoreria(hecho_id, cuenta_id, importe=TOTAL_CENA) -> DatosTesoreria:
    movimiento_id = uuid.uuid4()
    return DatosTesoreria(
        movimiento=DatosMovimiento(
            movimiento_id=movimiento_id,
            cuenta_id=cuenta_id,
            fecha_movimiento=FECHA,
            importe=-importe,
            clase_movimiento="OPERACION",
            descripcion="cargo restaurante",
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


# ==================================================================
# C-11 — la cena compartida completa, en una sola invocacion
# ==================================================================

def test_c11_cena_compartida_completa(
    servicio_compartidos, contexto, actor_a, actor_b, cuenta, admin
) -> None:
    hecho = _hecho(total_participantes=2)
    datos = DatosGastoCompartido(
        hecho=hecho,
        efectos=[
            _gasto(
                atribuciones=[
                    _atribucion(actor_a, MITAD),
                    _atribucion(actor_b, MITAD),
                ]
            )
        ],
        participantes=[
            DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_a),
            DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_b),
        ],
        tesoreria=[_tesoreria(hecho.hecho_id, cuenta)],
        aportaciones=[_aportacion(TOTAL_CENA, actor_id=actor_a)],
    )

    resultado = servicio_compartidos.registrar_gasto_compartido(contexto, datos)

    assert resultado.efectos_creados == 1
    assert resultado.atribuciones_creadas == 2
    assert resultado.participantes_creados == 2
    assert resultado.aportaciones_creadas == 1
    assert resultado.movimientos_creados == 1
    assert resultado.conciliaciones_creadas == 1
    assert resultado.posiciones_creadas == 0

    # El hecho conserva el 100 %: un solo hecho, no dos mitades.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), max(importe_total) FROM gapto.hechos_financieros "
        "WHERE id = %s",
        (hecho.hecho_id,),
    ) == (1, TOTAL_CENA)


def test_una_sola_transaccion(
    servicio_compartidos, contexto, actor_a, cuenta
) -> None:
    """§3. Una llamada OP-19 es UNA transaccion, no cuatro encadenadas."""
    hecho = _hecho()
    servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[_gasto()],
            tesoreria=[_tesoreria(hecho.hecho_id, cuenta)],
        ),
    )
    traza = servicio_compartidos.ultima_traza
    assert traza.intentos_realizados == 1
    assert traza.operacion == "OP-19 registrar_gasto_compartido"


# ==================================================================
# §4 — atomicidad: el mutante N1 vive aqui
# ==================================================================

def test_n1_fallo_en_tesoreria_deshace_el_hecho_entero(
    servicio_compartidos, contexto, actor_a, actor_b, cuenta, admin
) -> None:
    """Falla la conciliacion y NO puede sobrevivir nada de lo anterior."""
    hecho = _hecho(total_participantes=2)
    pieza = _tesoreria(hecho.hecho_id, cuenta)
    # Conciliar mas de lo que el movimiento mueve: falla al confirmar.
    roto = DatosTesoreria(
        movimiento=pieza.movimiento,
        conciliacion=DatosConciliacion(
            conciliacion_id=pieza.conciliacion.conciliacion_id,
            hecho_id=hecho.hecho_id,
            movimiento_tesoreria_id=pieza.movimiento.movimiento_id,
            importe_asignado=D("-500.0000"),
        ),
    )
    participante = DatosParticipante(
        participante_id=uuid.uuid4(), actor_id=actor_a
    )

    with pytest.raises(ErrorMotor):
        servicio_compartidos.registrar_gasto_compartido(
            contexto,
            DatosGastoCompartido(
                hecho=hecho,
                efectos=[_gasto(atribuciones=[_atribucion(actor_a, TOTAL_CENA)])],
                participantes=[participante],
                tesoreria=[roto],
            ),
        )

    for consulta, parametros in (
        ("SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (hecho.hecho_id,)),
        ("SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s", (hecho.hecho_id,)),
        (
            "SELECT count(*) FROM gapto.hecho_participantes WHERE id = %s",
            (participante.participante_id,),
        ),
        (
            "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE id = %s",
            (roto.movimiento.movimiento_id,),
        ),
        (
            "SELECT count(*) FROM gapto.auditoria WHERE registro_id = %s",
            (hecho.hecho_id,),
        ),
    ):
        assert leer_fila(admin, contexto.owner_user_id, consulta, parametros) == (0,)


def test_fallo_en_participantes_deshace_hecho_y_efectos(
    servicio_compartidos, contexto, actor_a, actor_b, admin
) -> None:
    """El total declarado no admite dos identificados: cae todo."""
    hecho = _hecho(total_participantes=1)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_compartidos.registrar_gasto_compartido(
            contexto,
            DatosGastoCompartido(
                hecho=hecho,
                efectos=[_gasto()],
                participantes=[
                    DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_a),
                    DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_b),
                ],
            ),
        )
    assert excepcion.value.codigo is CodigoError.PARTICIPANTES_INCONSISTENTES
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
        (hecho.hecho_id,),
    ) == (0,)


def test_captura_parcial_voluntaria_es_valida(
    servicio_compartidos, contexto, actor_a, actor_b, admin
) -> None:
    """§4. Hoy el hecho y el reparto; la tesoreria cuando aparezca el banco."""
    hecho = _hecho(total_participantes=2)
    resultado = servicio_compartidos.registrar_gasto_compartido(
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
        ),
    )
    assert resultado.movimientos_creados == 0
    assert resultado.aportaciones_creadas == 0
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
        (hecho.hecho_id,),
    ) == (1,)


# ==================================================================
# §5 — OP-19 no crea posiciones
# ==================================================================

def test_a5_pagador_unico_con_atribucion_mitad_y_mitad_sin_posicion(
    servicio_compartidos, contexto, actor_a, actor_b, cuenta, admin
) -> None:
    """A5. Pago 44,50 y me atribuyo 22,25. Nadie me debe nada por eso."""
    hecho = _hecho(total_participantes=2)
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
            aportaciones=[_aportacion(TOTAL_CENA, actor_id=actor_a)],
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.derechos_obligaciones_financieras p "
        "JOIN gapto.entidades e ON e.id = p.entidad_id "
        "WHERE e.owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == (0,)


# ==================================================================
# Adversariales de financiacion y caja
# ==================================================================

def test_a4_aportante_no_identificado(
    servicio_compartidos, contexto, actor_a, cuenta, admin
) -> None:
    """A4. Alguien puso el dinero y no se sabe quien. NULL, no un actor falso."""
    hecho = _hecho()
    servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[_gasto()],
            tesoreria=[_tesoreria(hecho.hecho_id, cuenta)],
            aportaciones=[_aportacion(TOTAL_CENA, actor_id=None)],
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), count(actor_id) FROM gapto.hecho_aportaciones_pago "
        "WHERE hecho_id = %s",
        (hecho.hecho_id,),
    ) == (1, 0)


def test_a6_financiacion_externa(
    servicio_compartidos, contexto, actor_a, actor_b, admin
) -> None:
    """A6. Lo pago un tercero por su canal: hay gasto y no hay caja propia."""
    hecho = _hecho()
    servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[_gasto()],
            aportaciones=[
                _aportacion(TOTAL_CENA, actor_id=actor_b, criterio="EXTERNA")
            ],
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
        (hecho.hecho_id,),
    ) == (0,)


def test_a7_varios_movimientos_para_un_mismo_hecho(
    servicio_compartidos, contexto, cuenta, admin
) -> None:
    """A7. Mitad en efectivo y mitad con tarjeta: dos realidades de caja."""
    hecho = _hecho()
    resultado = servicio_compartidos.registrar_gasto_compartido(
        contexto,
        DatosGastoCompartido(
            hecho=hecho,
            efectos=[_gasto()],
            tesoreria=[
                _tesoreria(hecho.hecho_id, cuenta, importe=MITAD),
                _tesoreria(hecho.hecho_id, cuenta, importe=MITAD),
            ],
        ),
    )
    assert resultado.movimientos_creados == 2
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), sum(importe_asignado) "
        "FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s",
        (hecho.hecho_id,),
    ) == (2, -TOTAL_CENA)


# ==================================================================
# Entrada
# ==================================================================

def test_exige_al_menos_un_efecto(servicio_compartidos, contexto) -> None:
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_compartidos.registrar_gasto_compartido(
            contexto, DatosGastoCompartido(hecho=_hecho(), efectos=[])
        )
    assert excepcion.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_conciliacion_de_otro_hecho_se_rechaza(
    servicio_compartidos, contexto, cuenta
) -> None:
    hecho = _hecho()
    ajena = _tesoreria(uuid.uuid4(), cuenta)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_compartidos.registrar_gasto_compartido(
            contexto,
            DatosGastoCompartido(
                hecho=hecho, efectos=[_gasto()], tesoreria=[ajena]
            ),
        )
    assert excepcion.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_ningun_writer_emite_relaciones_reservadas(admin, contexto) -> None:
    """N12. `PARTE_DE`, `REPERCUSION_DE` y `REVERSA_A` siguen sin writer.

    Auditoria estatica sobre el codigo de servicios mas comprobacion dinamica
    de que la suite no ha dejado ni una fila con esos tokens. El estatico
    impide que alguien los escriba; el dinamico, que lleguen por otra via.
    """
    import pathlib
    import re as _re

    servicios = pathlib.Path(__file__).resolve().parents[2] / "backend" / "app"
    # El token entrecomillado, no la subcadena: `CONTRAPARTE_DESCONOCIDA`
    # contiene `PARTE_DE` y no tiene nada que ver.
    emision = _re.compile(r"""['"](PARTE_DE|REPERCUSION_DE|REVERSA_A)['"]""")
    emisores = [
        ruta.name
        for ruta in servicios.rglob("*.py")
        if emision.search(ruta.read_text(encoding="utf-8"))
    ]
    assert emisores == []

    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hecho_relaciones "
        "WHERE tipo_relacion IN ('PARTE_DE', 'REPERCUSION_DE', 'REVERSA_A')",
        (),
    ) == (0,)
