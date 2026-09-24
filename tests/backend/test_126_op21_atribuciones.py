# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_126_op21_atribuciones.py
# Ruta: tests/backend/test_126_op21_atribuciones.py
# Descripcion: F04-D039. Superficie de atribuciones de OP-21: A18 y R1..R11.
#
#   Lo que se corrige aqui son datos que NUNCA fueron ciertos. Por eso las
#   transiciones inversas de `estado_atribucion` son legitimas: no son una
#   perdida posterior de conocimiento, son la constatacion de que lo que se
#   creia saber era falso. OP-05 conserva su progresion ordinaria.
# Version: 0.3.0
#   0.3.0 (mandato F04 R1+R2 v0.3 + E01): OP-04 aporta `presupuestable` en la
#   transicion al primer GASTO/INGRESO (A08-bis generalizada); fixtures de
#   GASTO con localizacion DESCONOCIDA en vez de NO_APLICA cuando aplica. Sin
#   cambio de las propiedades probadas.
# Version: 0.2.0
#   0.2.0 (F04-D046 R1 · A19): signo canonico. La cena de 44,50 es GASTO +44,50
#   y todos los repartos, correcciones y oraculos (A18, R1..R11) son positivos
#   (F04-D007). Este fichero no toca tesoreria. Mismas propiedades.
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
from app.services.correcciones_service import (
    DatosAtribucionNueva,
    DatosCorreccion,
)
from conftest import leer_fila

D = decimal.Decimal
FECHA = dt.date(2026, 6, 1)
TOTAL = D("44.5000")
MITAD = D("22.2500")


def _cena(servicio, servicio_efectos, contexto, atribuciones, estado, importe=TOTAL):
    """Un gasto con su reparto, tal y como quedo registrado en su dia."""
    hecho_id = uuid.uuid4()
    efecto_id = uuid.uuid4()
    creado = servicio.crear_hecho(
        contexto,
        DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=FECHA,
            moneda="EUR",
            presupuestable=True,
            estado_localizacion="DESCONOCIDA",  # F04-D046 R2: GASTO aplicable, localidad no conocida
            tipo_hecho_codigo="GASTO",
            concepto="cena compartida",
            importe_total=importe,
        ),
    )
    resultado = servicio_efectos.registrar_efectos(
        contexto,
        hecho_id=hecho_id,
        row_version_esperada=creado.row_version,
        efectos=[
            DatosEfecto(
                efecto_id=efecto_id,
                tipo_efecto="GASTO",
                importe_delta=importe,  # F04-D046 R1: GASTO +X
                estado_atribucion=estado,
                atribuciones=tuple(atribuciones),
            )
        ],
        presupuestable=True,  # F04-D046 A08-bis: primer GASTO/INGRESO
    )
    return hecho_id, efecto_id, resultado.row_version


def _atribucion(actor_id, importe, criterio="MANUAL"):
    return DatosAtribucion(
        atribucion_id=uuid.uuid4(),
        actor_id=actor_id,
        importe_atribuido=importe,  # F04-D007: hereda el signo
        criterio_atribucion=criterio,
    )


def _reparto(admin, contexto, efecto_id):
    return leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), COALESCE(sum(importe_atribuido), 0) "
        "FROM gapto.efecto_atribuciones WHERE efecto_id = %s",
        (efecto_id,),
    )


# ==================================================================
# A18 — el caso minimo obligatorio
# ==================================================================

def test_a18_importe_y_reparto_falsos_se_corrigen_juntos(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    """44,50 con 22,25/22,25 pasa a 40,00 con 25,00/15,00 en una transaccion.

    Mismo hecho, mismo efecto, sin hecho nuevo. Antes de F04-D039 este estado
    final era inalcanzable: hacian falta dos mutaciones a la vez y solo una
    era posible.
    """
    a = _atribucion(actor_a, MITAD)
    b = _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a, b], "COMPLETA"
    )
    hechos_antes = leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE owner_user_id = %s",
        (contexto.owner_user_id,),
    )

    resultado = servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo="el ticket decia 40,00 y el reparto era 25/15",
            efectos_a_actualizar={efecto_id: {"importe_delta": D("40.0000")}},
            atribuciones_a_actualizar={
                a.atribucion_id: {"importe_atribuido": D("25.0000")},
                b.atribucion_id: {"importe_atribuido": D("15.0000")},
            },
        ),
    )
    assert resultado.atribuciones_actualizadas == 2
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT importe_delta, estado_atribucion FROM gapto.hecho_efectos "
        "WHERE id = %s",
        (efecto_id,),
    ) == (D("40.0000"), "COMPLETA")
    assert _reparto(admin, contexto, efecto_id) == (2, D("40.0000"))
    # Sin hecho nuevo y sin cambiar la identidad del efecto.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*) FROM gapto.hechos_financieros WHERE owner_user_id = %s",
        (contexto.owner_user_id,),
    ) == hechos_antes


def test_a18_auditoria_integra_bajo_el_mismo_motivo(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    """Efecto y atribuciones comparten motivo y request de la correccion."""
    a = _atribucion(actor_a, MITAD)
    b = _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a, b], "COMPLETA"
    )
    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo="reparto falso",
            efectos_a_actualizar={efecto_id: {"importe_delta": D("40.0000")}},
            atribuciones_a_actualizar={
                a.atribucion_id: {"importe_atribuido": D("25.0000")},
                b.atribucion_id: {"importe_atribuido": D("15.0000")},
            },
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), count(DISTINCT motivo), count(DISTINCT request_id) "
        "FROM gapto.auditoria WHERE registro_id = ANY(%s) "
        "AND accion = 'ACTUALIZAR'",
        ([efecto_id, a.atribucion_id, b.atribucion_id],),
    ) == (3, 1, 1)
    # El snapshot anterior de la atribucion sobrevive a la correccion.
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT datos_antes->>'importe_atribuido' FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ACTUALIZAR'",
        (a.atribucion_id,),
    ) == ("22.2500",)


# ==================================================================
# R1..R6 — las formas reales de un reparto falso
# ==================================================================

def test_r1_importe_correcto_reparto_incorrecto(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    a = _atribucion(actor_a, MITAD)
    b = _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a, b], "COMPLETA"
    )
    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo="el reparto era 30/14,50",
            atribuciones_a_actualizar={
                a.atribucion_id: {"importe_atribuido": D("30.0000")},
                b.atribucion_id: {"importe_atribuido": D("14.5000")},
            },
        ),
    )
    assert _reparto(admin, contexto, efecto_id) == (2, TOTAL)


def test_r2_actor_falso_se_retira_y_se_redistribuye(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    """B nunca estuvo: se retira su fila y A asume el total."""
    a = _atribucion(actor_a, MITAD)
    b = _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a, b], "COMPLETA"
    )
    resultado = servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo="B no participo en esa cena",
            atribuciones_a_eliminar=(b.atribucion_id,),
            atribuciones_a_actualizar={
                a.atribucion_id: {"importe_atribuido": TOTAL}
            },
        ),
    )
    assert resultado.atribuciones_eliminadas == 1
    assert _reparto(admin, contexto, efecto_id) == (1, TOTAL)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT accion, datos_antes->>'actor_id' FROM gapto.auditoria "
        "WHERE registro_id = %s AND accion = 'ANULAR'",
        (b.atribucion_id,),
    ) == ("ANULAR", str(actor_b))


def test_r3_actor_omitido_se_crea(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    a = _atribucion(actor_a, TOTAL)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a], "COMPLETA"
    )
    resultado = servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo="faltaba la parte de B",
            atribuciones_a_actualizar={
                a.atribucion_id: {"importe_atribuido": MITAD}
            },
            atribuciones_a_crear=(
                DatosAtribucionNueva(
                    atribucion_id=uuid.uuid4(),
                    efecto_id=efecto_id,
                    actor_id=actor_b,
                    importe_atribuido=MITAD,
                    criterio_atribucion="MANUAL",
                ),
            ),
        ),
    )
    assert resultado.atribuciones_creadas == 1
    assert _reparto(admin, contexto, efecto_id) == (2, TOTAL)


def test_r4_completa_a_parcial(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    """Se declaro conocer todo el reparto y no era cierto."""
    a = _atribucion(actor_a, MITAD)
    b = _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a, b], "COMPLETA"
    )
    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo="la parte de B era desconocida",
            efectos_a_actualizar={efecto_id: {"estado_atribucion": "PARCIAL"}},
            atribuciones_a_eliminar=(b.atribucion_id,),
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado_atribucion FROM gapto.hecho_efectos WHERE id = %s",
        (efecto_id,),
    ) == ("PARCIAL",)
    assert _reparto(admin, contexto, efecto_id) == (1, MITAD)


def test_r5_completa_a_no_disponible(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    """Todo el reparto era falso y no puede reconstruirse."""
    a = _atribucion(actor_a, MITAD)
    b = _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a, b], "COMPLETA"
    )
    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo="ninguna de las dos partes era cierta",
            efectos_a_actualizar={
                efecto_id: {"estado_atribucion": "NO_DISPONIBLE"}
            },
            atribuciones_a_eliminar=(a.atribucion_id, b.atribucion_id),
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado_atribucion FROM gapto.hecho_efectos WHERE id = %s",
        (efecto_id,),
    ) == ("NO_DISPONIBLE",)
    assert _reparto(admin, contexto, efecto_id) == (0, 0)


def test_r6_parcial_a_completa(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    a = _atribucion(actor_a, MITAD)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a], "PARCIAL"
    )
    servicio_correcciones.corregir(
        contexto,
        DatosCorreccion(
            hecho_id=hecho_id,
            row_version_esperada=version,
            motivo="la parte que faltaba era de B",
            efectos_a_actualizar={efecto_id: {"estado_atribucion": "COMPLETA"}},
            atribuciones_a_crear=(
                DatosAtribucionNueva(
                    atribucion_id=uuid.uuid4(),
                    efecto_id=efecto_id,
                    actor_id=actor_b,
                    importe_atribuido=MITAD,
                    criterio_atribucion="MANUAL",
                ),
            ),
        ),
    )
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT estado_atribucion FROM gapto.hecho_efectos WHERE id = %s",
        (efecto_id,),
    ) == ("COMPLETA",)
    assert _reparto(admin, contexto, efecto_id) == (2, TOTAL)


# ==================================================================
# R7..R11 — lo que el estado final NO admite
# ==================================================================

def test_r7_no_disponible_con_filas_se_rechaza(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    a = _atribucion(actor_a, MITAD)
    b = _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a, b], "COMPLETA"
    )
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=version,
                motivo="intento invalido",
                efectos_a_actualizar={
                    efecto_id: {"estado_atribucion": "NO_DISPONIBLE"}
                },
                atribuciones_a_eliminar=(a.atribucion_id,),
            ),
        )
    assert excepcion.value.codigo is CodigoError.NO_DISPONIBLE_CON_FILAS
    assert _reparto(admin, contexto, efecto_id) == (2, TOTAL)


def test_r8_parcial_que_cubre_el_efecto_se_rechaza(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b
) -> None:
    """Si el reparto conocido cubre el efecto, el estado correcto es COMPLETA."""
    a = _atribucion(actor_a, MITAD)
    b = _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a, b], "COMPLETA"
    )
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=version,
                motivo="intento invalido",
                efectos_a_actualizar={efecto_id: {"estado_atribucion": "PARCIAL"}},
            ),
        )
    assert excepcion.value.codigo is CodigoError.SUMA_NO_CUADRA


def test_r9_completa_descuadrada_se_rechaza(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    a = _atribucion(actor_a, MITAD)
    b = _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a, b], "COMPLETA"
    )
    with pytest.raises(ErrorMotor):
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=version,
                motivo="solo se corrige una parte",
                atribuciones_a_actualizar={
                    a.atribucion_id: {"importe_atribuido": D("25.0000")}
                },
            ),
        )
    assert _reparto(admin, contexto, efecto_id) == (2, TOTAL)


def test_r10_cambiar_de_actor_por_update_no_esta_soportado(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b
) -> None:
    a = _atribucion(actor_a, TOTAL)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a], "COMPLETA"
    )
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=version,
                motivo="era B, no A",
                atribuciones_a_actualizar={a.atribucion_id: {"actor_id": actor_b}},
            ),
        )
    assert excepcion.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_r11_fallo_tardio_deshace_efecto_atribuciones_y_auditoria(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    """La correccion cuadra el reparto pero deja el hecho sin efectos: cae todo."""
    a = _atribucion(actor_a, MITAD)
    b = _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(
        servicio, servicio_efectos, contexto, [a, b], "COMPLETA"
    )
    with pytest.raises(ErrorMotor):
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_id,
                row_version_esperada=version,
                motivo="intento que deja el hecho vacio",
                atribuciones_a_eliminar=(a.atribucion_id, b.atribucion_id),
                efectos_a_eliminar=(efecto_id,),
            ),
        )
    assert _reparto(admin, contexto, efecto_id) == (2, TOTAL)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        "SELECT count(*), max(row_version) FROM gapto.hechos_financieros "
        "WHERE id = %s",
        (hecho_id,),
    ) == (1, version)
    assert leer_fila(
        admin,
        contexto.owner_user_id,
        # Solo mutaciones de ESTA correccion: el alta original si dejo su CREAR.
        "SELECT count(*) FROM gapto.auditoria WHERE registro_id = ANY(%s) "
        "AND accion IN ('ANULAR', 'ACTUALIZAR')",
        ([a.atribucion_id, b.atribucion_id, efecto_id],),
    ) == (0,)


def test_atribucion_de_otro_hecho_se_rechaza(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b
) -> None:
    a = _atribucion(actor_a, TOTAL)
    hecho_uno, _, _ = _cena(servicio, servicio_efectos, contexto, [a], "COMPLETA")
    otra = _atribucion(actor_b, TOTAL)
    hecho_dos, _, version_dos = _cena(
        servicio, servicio_efectos, contexto, [otra], "COMPLETA"
    )
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(
            contexto,
            DatosCorreccion(
                hecho_id=hecho_dos,
                row_version_esperada=version_dos,
                motivo="cruce de agregados",
                atribuciones_a_eliminar=(a.atribucion_id,),
            ),
        )
    assert excepcion.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO
