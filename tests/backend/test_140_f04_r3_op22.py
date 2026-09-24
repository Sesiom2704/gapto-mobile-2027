# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_140_f04_r3_op22.py
# Ruta: tests/backend/test_140_f04_r3_op22.py
# Descripcion: F04-D048 R3 (A17). Bateria discriminante de OP-22 «Registrar
#   hecho compuesto»: intenciones I1..I7, no inferencia de posiciones ni
#   aportaciones, realizacion explicita de prevision, idempotencia de agregado
#   (identidad ANTES de validacion mutable), atomicidad con fallos tardios por
#   familia de componente, row_version, frontera F07/D-080 y Q03.
#
#   Cada test nombra en su docstring el punto del mandato R3 (§) o la
#   intencion (I1..I7) que discrimina.
# Version: 0.1.0
# ============================================================
from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import uuid

import psycopg
import pytest

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_compuesto import (
    DatosContextoHecho,
    DatosEntidadHecho,
    DatosEtiquetaHecho,
    DatosHechoCompuesto,
    DatosMagnitudHecho,
    DatosPagoCompuesto,
    DatosPrevisionCompuesta,
    DatosTerceroHecho,
)
from app.core.modelos_posicion import (
    TIPO_DERECHO,
    TIPO_HECHO_POSICION,
    TIPO_OBLIGACION,
    DatosAltaPosicion,
)
from app.core.modelos_prevision import DatosPrevisionManual
from app.core.modelos_suplemento import DatosSuplemento
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.compuesto_service import HechosCompuestosService
from conftest import leer_fila
from f08_motor import aportacion, atribucion, conciliacion, efecto, movimiento

D = decimal.Decimal
F = dt.date.fromisoformat
FECHA = F("2027-06-01")


# ==================================================================
# Utilidades
# ==================================================================

@pytest.fixture()
def op22(unidad: UnidadDeTrabajo) -> HechosCompuestosService:
    from app.services.previsiones_service import impacto_correccion_ancla

    return HechosCompuestosService(unidad, impacto_ancla=impacto_correccion_ancla)


def como_owner(admin: psycopg.Connection, owner: uuid.UUID, sql: str, params: tuple) -> None:
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),))
            cursor.execute(sql, params)
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")


SUBTIPOS = {
    "PROPIEDAD": "INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad) VALUES (%s, 'VIVIENDA')",
    "CONTEXTO": "INSERT INTO gapto.contextos (entidad_id, tipo_contexto) VALUES (%s, 'VIAJE')",
    "INVERSION": "INSERT INTO gapto.inversiones (entidad_id, rol_estructura, tipo_producto, moneda) "
                 "VALUES (%s, 'POSICION', 'FONDO', 'EUR')",
    "FINANCIACION": "INSERT INTO gapto.financiaciones (entidad_id, tipo_financiacion, moneda) "
                    "VALUES (%s, 'PRESTAMO', 'EUR')",
}


def nueva_entidad(admin, owner, tipo="PROPIEDAD", enabled=True) -> uuid.UUID:
    """Entidad + su subtipo en UNA transaccion (el subtipo unico es diferido)."""
    i = uuid.uuid4()
    with admin.transaction():
        with admin.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE gapto_owner")
            cursor.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
            cursor.execute(
                "INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre, enabled) "
                "VALUES (%s, %s, %s, %s, %s)", (i, owner, tipo, f"entidad {tipo}", enabled))
            cursor.execute(SUBTIPOS[tipo], (i,))
    return i


def nueva_etiqueta(admin, owner, enabled=True) -> uuid.UUID:
    i = uuid.uuid4()
    como_owner(admin, owner,
               "INSERT INTO gapto.etiquetas (id, owner_user_id, nombre, enabled) VALUES (%s,%s,%s,%s)",
               (i, owner, f"etiqueta {i}", enabled))
    return i


def nuevo_tercero(admin, owner, enabled=True) -> uuid.UUID:
    i = uuid.uuid4()
    como_owner(admin, owner,
               "INSERT INTO gapto.terceros (id, owner_user_id, nombre, enabled) VALUES (%s,%s,%s,%s)",
               (i, owner, f"tercero {i}", enabled))
    return i


def nueva_magnitud(admin, owner, unidad="km") -> uuid.UUID:
    i = uuid.uuid4()
    como_owner(admin, owner,
               "INSERT INTO gapto.magnitudes (id, owner_user_id, nombre, unidad_default, precision_decimales) "
               "VALUES (%s,%s,%s,%s,2)", (i, owner, f"magnitud {i}", unidad))
    return i


def cuenta_filas(admin, owner, tabla: str, columna: str, valor) -> int:
    return leer_fila(admin, owner, f"SELECT count(*) FROM gapto.{tabla} WHERE {columna} = %s", (valor,))[0]


def hecho(presupuestable=True, tipo="GASTO", total="100.0000", localizacion="DESCONOCIDA") -> DatosCreacionHecho:
    return DatosCreacionHecho(
        hecho_id=uuid.uuid4(), fecha_hecho=FECHA, moneda="EUR",
        presupuestable=presupuestable, estado_localizacion=localizacion,
        tipo_hecho_codigo=tipo, concepto="hecho compuesto",
        importe_total=D(total) if total is not None else None,
    )


def pago(hecho_id, cuenta, importe) -> DatosPagoCompuesto:
    m = movimiento(cuenta, D(importe))
    return DatosPagoCompuesto(movimiento=m, conciliacion=conciliacion(hecho_id, m.movimiento_id, D(importe)))


def alta(hecho_id, contraparte, tipo=TIPO_DERECHO, importe="100.0000") -> DatosAltaPosicion:
    return DatosAltaPosicion(
        entidad_id=uuid.uuid4(), nombre="posicion explicita", tipo=tipo,
        contraparte_actor_id=contraparte, moneda="EUR", justificacion="DECISION_EXPLICITA",
        fecha_inicio_seguimiento=FECHA, saldo_apertura=D("0"), hecho_id=hecho_id,
        fecha_hecho=FECHA, concepto="posicion explicita", efecto_id=uuid.uuid4(),
        vinculo_id=uuid.uuid4(), importe_inicial=D(importe),
    )


def posiciones_del_hecho(admin, owner, hecho_id) -> int:
    return leer_fila(
        admin, owner,
        "SELECT count(*) FROM gapto.hecho_entidades v JOIN gapto.derechos_obligaciones_financieras p "
        "ON p.entidad_id = v.entidad_id WHERE v.hecho_id = %s", (hecho_id,),
    )[0]


def efectos_de(admin, owner, hecho_id) -> dict:
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),))
        try:
            cursor.execute(
                "SELECT tipo_efecto, sum(importe_delta) FROM gapto.hecho_efectos "
                "WHERE hecho_id = %s GROUP BY tipo_efecto", (hecho_id,))
            return {r[0]: r[1] for r in cursor.fetchall()}
        finally:
            cursor.execute("RESET ALL")


def rechazo(fn, codigo):
    with pytest.raises(ErrorMotor) as excinfo:
        fn()
    assert excinfo.value.codigo is codigo, excinfo.value
    return excinfo.value


# ==================================================================
# I1..I5 · Intenciones
# ==================================================================

def test_i1_gasto_mas_pago(op22, contexto, admin, cuenta, actor_a, actor_b) -> None:
    """I1. GASTO +X, tesoreria -X, conciliacion, aportacion real declarada y
    atribucion INDEPENDIENTE (otro actor). Sin posicion alguna."""
    h = hecho()
    p = pago(h.hecho_id, cuenta, "-100.0000")
    datos = DatosHechoCompuesto(
        hecho=h,
        efectos=[efecto("GASTO", D("100.0000"), atribuciones=(atribucion(actor_b, D("100.0000")),))],
        pagos=[p],
        aportaciones=[aportacion(D("100.0000"), actor_id=actor_a, conciliacion_id=p.conciliacion.conciliacion_id)],
    )
    r = op22.registrar_hecho_compuesto(contexto, datos)
    assert not r.idempotente and r.efectos_creados == 1 and r.conciliaciones_creadas == 1
    assert efectos_de(admin, contexto.owner_user_id, h.hecho_id) == {"GASTO": D("100.0000")}
    assert posiciones_del_hecho(admin, contexto.owner_user_id, h.hecho_id) == 0
    assert leer_fila(admin, contexto.owner_user_id,
                     "SELECT row_version FROM gapto.hechos_financieros WHERE id=%s", (h.hecho_id,))[0] == r.hecho_row_version


def test_i2_ingreso_mas_cobro(op22, contexto, admin, cuenta) -> None:
    """I2. INGRESO +X, tesoreria +X, conciliacion; sin aportacion inventada."""
    h = hecho(tipo="INGRESO")
    datos = DatosHechoCompuesto(hecho=h, efectos=[efecto("INGRESO", D("100.0000"))],
                                pagos=[pago(h.hecho_id, cuenta, "100.0000")])
    op22.registrar_hecho_compuesto(contexto, datos)
    assert efectos_de(admin, contexto.owner_user_id, h.hecho_id) == {"INGRESO": D("100.0000")}
    assert cuenta_filas(admin, contexto.owner_user_id, "hecho_aportaciones_pago", "hecho_id", h.hecho_id) == 0


def test_i2_aportacion_en_cobro_se_rechaza_y_no_deja_nada(op22, contexto, admin, cuenta, actor_a) -> None:
    """I2 adversarial. Una aportacion sobre un cobro es incompatible: rechazo
    discriminante del contrato de OP-06 y rollback de TODA la intencion."""
    h = hecho(tipo="INGRESO")
    p = pago(h.hecho_id, cuenta, "100.0000")
    datos = DatosHechoCompuesto(
        hecho=h, efectos=[efecto("INGRESO", D("100.0000"))], pagos=[p],
        aportaciones=[aportacion(D("100.0000"), actor_id=actor_a, conciliacion_id=p.conciliacion.conciliacion_id)],
    )
    rechazo(lambda: op22.registrar_hecho_compuesto(contexto, datos), CodigoError.USO_EN_COBRO_NO_PERMITIDO)
    assert cuenta_filas(admin, contexto.owner_user_id, "hechos_financieros", "id", h.hecho_id) == 0
    assert cuenta_filas(admin, contexto.owner_user_id, "movimientos_tesoreria", "id", p.movimiento.movimiento_id) == 0


@pytest.mark.parametrize("tipo, naturaleza", [(TIPO_DERECHO, "DERECHO_COBRO"), (TIPO_OBLIGACION, "DEUDA")])
def test_i3_i4_gasto_con_posicion_explicita(op22, contexto, admin, cuenta, contraparte, tipo, naturaleza) -> None:
    """I3/I4. La posicion solo nace porque se DECLARA, con contraparte e
    importe propios, por el servicio certificado OP-12 enganchado a la raiz."""
    h = hecho()
    a = alta(h.hecho_id, contraparte, tipo=tipo, importe="40.0000")
    pagos = [pago(h.hecho_id, cuenta, "-100.0000")] if tipo == TIPO_DERECHO else []
    r = op22.registrar_hecho_compuesto(
        contexto, DatosHechoCompuesto(hecho=h, efectos=[efecto("GASTO", D("100.0000"))], posiciones=[a], pagos=pagos)
    )
    assert posiciones_del_hecho(admin, contexto.owner_user_id, h.hecho_id) == 1
    assert efectos_de(admin, contexto.owner_user_id, h.hecho_id)[naturaleza] == D("40.0000")
    assert a.entidad_id in r.posiciones
    if tipo == TIPO_OBLIGACION:  # I4: pago un tercero; el usuario no mueve caja
        assert cuenta_filas(admin, contexto.owner_user_id, "hecho_movimientos_tesoreria", "hecho_id", h.hecho_id) == 0


def test_posicion_no_se_infiere_por_diferencia(op22, contexto, admin, cuenta, actor_a, actor_b) -> None:
    """§5 / INV-04. Atribucion 100 a B y aportacion 100 de A: la diferencia NO
    crea ninguna posicion si no se declara."""
    h = hecho()
    p = pago(h.hecho_id, cuenta, "-100.0000")
    op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(
        hecho=h,
        efectos=[efecto("GASTO", D("100.0000"), atribuciones=(atribucion(actor_b, D("100.0000")),))],
        pagos=[p],
        aportaciones=[aportacion(D("100.0000"), actor_id=actor_a, conciliacion_id=p.conciliacion.conciliacion_id)],
    ))
    assert posiciones_del_hecho(admin, contexto.owner_user_id, h.hecho_id) == 0
    assert "DERECHO_COBRO" not in efectos_de(admin, contexto.owner_user_id, h.hecho_id)


@pytest.mark.parametrize("con_aportacion", [False, True])
def test_i5_adelanto_puro(op22, contexto, admin, cuenta, contraparte, actor_a, con_aportacion) -> None:
    """I5 / Q01. Hecho de generacion de posicion + DERECHO_COBRO explicito +
    movimiento -X + conciliacion. Sin GASTO. La aportacion es opcional: solo
    existe si se declara; nunca se infiere del movimiento, la cuenta ni la
    posicion."""
    h = hecho(presupuestable=False, tipo=TIPO_HECHO_POSICION, total="50.0000")
    p = pago(h.hecho_id, cuenta, "-50.0000")
    aportaciones = (
        [aportacion(D("50.0000"), actor_id=actor_a, conciliacion_id=p.conciliacion.conciliacion_id)]
        if con_aportacion else []
    )
    op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(
        hecho=h, posiciones=[alta(h.hecho_id, contraparte, importe="50.0000")], pagos=[p], aportaciones=aportaciones,
    ))
    assert efectos_de(admin, contexto.owner_user_id, h.hecho_id) == {"DERECHO_COBRO": D("50.0000")}
    assert cuenta_filas(admin, contexto.owner_user_id, "hecho_aportaciones_pago", "hecho_id", h.hecho_id) == (
        1 if con_aportacion else 0
    )


# ==================================================================
# I6 · Prevision -> realidad
# ==================================================================

def _prevision(admin, contexto, servicio_previsiones) -> tuple[uuid.UUID, int]:
    datos = DatosPrevisionManual(
        prevision_id=uuid.uuid4(), concepto="luz", tipo_hecho_codigo="GASTO",
        fecha_esperada_desde=F("2027-06-01"), fecha_esperada_hasta=F("2027-06-30"),
        flujo_tesoreria_esperado="SALIDA", moneda="EUR", presupuestable=True,
        importe_esperado=D("100.0000"),
    )
    r = servicio_previsiones.crear_manual(contexto, datos)
    return datos.prevision_id, r.row_version


@pytest.mark.parametrize("realizar, esperado", [(True, "REALIZADA"), (False, "ABIERTA")])
def test_i6_prevision_realidad_solo_por_decision_explicita(
    op22, servicio_previsiones, contexto, admin, realizar, esperado
) -> None:
    """I6. OP-22 compone OP-17: el vinculo se crea siempre; REALIZADA solo si
    `marcar_realizada=True`. Nunca por defecto."""
    prevision_id, version = _prevision(admin, contexto, servicio_previsiones)
    h = hecho()
    r = op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(
        hecho=h, efectos=[efecto("GASTO", D("100.0000"))],
        prevision=DatosPrevisionCompuesta(
            prevision_id=prevision_id, prevision_row_version_esperada=version,
            vinculo_id=uuid.uuid4(), importe_asignado=D("100.0000"), marcar_realizada=realizar),
    ))
    assert r.prevision_row_version is not None
    assert leer_fila(admin, contexto.owner_user_id, "SELECT estado FROM gapto.previsiones WHERE id=%s",
                     (prevision_id,)) == (esperado,)
    assert cuenta_filas(admin, contexto.owner_user_id, "prevision_hechos", "hecho_id", h.hecho_id) == 1


def test_i6_marcar_realizada_es_obligatorio() -> None:
    """I6. Sin decision no hay DTO: `marcar_realizada` no tiene default."""
    with pytest.raises(TypeError):
        DatosPrevisionCompuesta(prevision_id=uuid.uuid4(), prevision_row_version_esperada=1,
                                vinculo_id=uuid.uuid4(), importe_asignado=D("1"))


def test_prevision_version_desfasada_revierte_todo(op22, servicio_previsiones, contexto, admin) -> None:
    """§16. row_version stale de la prevision: VERSION_DESFASADA y nada
    confirmado del agregado (el hecho ya creado en la misma transaccion cae)."""
    prevision_id, version = _prevision(admin, contexto, servicio_previsiones)
    h = hecho()
    rechazo(lambda: op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(
        hecho=h, efectos=[efecto("GASTO", D("100.0000"))],
        prevision=DatosPrevisionCompuesta(prevision_id=prevision_id, prevision_row_version_esperada=version + 7,
                                          vinculo_id=uuid.uuid4(), importe_asignado=D("100.0000"),
                                          marcar_realizada=True)),
    ), CodigoError.VERSION_DESFASADA)
    assert cuenta_filas(admin, contexto.owner_user_id, "hechos_financieros", "id", h.hecho_id) == 0


# ==================================================================
# I7 · Suplemento (+ pago)
# ==================================================================

def _suplemento(**extra) -> DatosSuplemento:
    base = dict(hecho_id=uuid.uuid4(), efecto_id=uuid.uuid4(), tipo_efecto="GASTO",
                importe_delta=D("3.5000"), fecha_hecho=F("2027-06-12"), moneda="EUR",
                fecha_demostrada=True, concepto="recargo", presupuestable=True)
    base.update(extra)
    return DatosSuplemento(**base)


def test_i7_suplemento_sin_pago_sigue_siendo_op18(servicio_suplementos, contexto, admin) -> None:
    """I7 / Q02. OP-18 autonomo no cambia: sin tesoreria."""
    s = _suplemento()
    servicio_suplementos.registrar(contexto, s)
    assert efectos_de(admin, contexto.owner_user_id, s.hecho_id) == {"GASTO": D("3.5000")}
    assert cuenta_filas(admin, contexto.owner_user_id, "hecho_movimientos_tesoreria", "hecho_id", s.hecho_id) == 0


def test_i7_suplemento_con_pago_simultaneo_por_op22(op22, contexto, admin, cuenta, actor_a) -> None:
    """I7 / Q02. OP-22 invoca OP-18 adscrito y compone movimiento,
    conciliacion y aportacion en la MISMA transaccion."""
    s = _suplemento()
    p = pago(s.hecho_id, cuenta, "-3.5000")
    r = op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(
        suplemento=s, pagos=[p],
        aportaciones=[aportacion(D("3.5000"), actor_id=actor_a, conciliacion_id=p.conciliacion.conciliacion_id)],
    ))
    assert efectos_de(admin, contexto.owner_user_id, s.hecho_id) == {"GASTO": D("3.5000")}
    assert cuenta_filas(admin, contexto.owner_user_id, "hecho_movimientos_tesoreria", "hecho_id", s.hecho_id) == 1
    assert cuenta_filas(admin, contexto.owner_user_id, "hecho_aportaciones_pago", "hecho_id", s.hecho_id) == 1
    assert r.conciliaciones_creadas == 1


def test_i7_op22_conserva_el_contrato_de_op18(op22, contexto, admin, cuenta) -> None:
    """I7 / Q02. OP-22 invoca OP-18 ADSCRITO, no una copia ampliada: sus
    guardas siguen vigentes (fecha economica no demostrada -> rechazo) y no
    queda nada del pago compuesto."""
    s = _suplemento(fecha_demostrada=False)
    p = pago(s.hecho_id, cuenta, "-3.5000")
    rechazo(lambda: op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(suplemento=s, pagos=[p])),
            CodigoError.FECHA_ECONOMICA_NO_DEMOSTRADA)
    assert cuenta_filas(admin, contexto.owner_user_id, "movimientos_tesoreria", "id", p.movimiento.movimiento_id) == 0


def test_raiz_exactamente_una(op22, contexto) -> None:
    """§3. OP-22 exige exactamente una raiz."""
    rechazo(lambda: op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto()), CodigoError.ENTRADA_INVALIDA)
    rechazo(lambda: op22.registrar_hecho_compuesto(
        contexto, DatosHechoCompuesto(hecho=hecho(), suplemento=_suplemento())), CodigoError.ENTRADA_INVALIDA)


# ==================================================================
# Contexto en el alta
# ==================================================================

def _contexto_completo(admin, owner) -> DatosContextoHecho:
    return DatosContextoHecho(
        terceros=[DatosTerceroHecho(uuid.uuid4(), nuevo_tercero(admin, owner), "VENDEDOR", principal=True)],
        entidades=[DatosEntidadHecho(uuid.uuid4(), nueva_entidad(admin, owner), "AFECTA_A", principal=False)],
        magnitudes=[DatosMagnitudHecho(uuid.uuid4(), nueva_magnitud(admin, owner), D("123.5"))],
        etiquetas=[DatosEtiquetaHecho(uuid.uuid4(), nueva_etiqueta(admin, owner))],
    )


def test_alta_con_las_cuatro_dimensiones(op22, contexto, admin) -> None:
    """A18 en el alta. Tercero, entidad, magnitud (unidad snapshot del default
    de captura) y etiqueta nacen con el hecho."""
    owner = contexto.owner_user_id
    h = hecho()
    c = _contexto_completo(admin, owner)
    r = op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(
        hecho=h, efectos=[efecto("GASTO", D("100.0000"))], contexto=c))
    assert r.contexto_creado == 4
    for tabla in ("hecho_terceros", "hecho_entidades", "hecho_magnitudes", "hecho_etiquetas"):
        assert cuenta_filas(admin, owner, tabla, "hecho_id", h.hecho_id) == 1
    assert leer_fila(admin, owner, "SELECT valor, unidad FROM gapto.hecho_magnitudes WHERE hecho_id=%s",
                     (h.hecho_id,)) == (D("123.500000"), "km")


def test_q03_magnitud_obligatoria_ausente_no_rechaza(op22, contexto, admin) -> None:
    """Q03. `categoria_magnitudes.obligatoria` NO es invariante F04: un hecho
    de esa categoria sin la magnitud se registra."""
    owner = contexto.owner_user_id
    categoria = uuid.uuid4()
    como_owner(admin, owner, "INSERT INTO gapto.categorias_financieras (id, owner_user_id, nombre, ambito, "
               "presupuestable_default) VALUES (%s,%s,'Coche','GASTO',true)", (categoria, owner))
    magnitud = nueva_magnitud(admin, owner)
    como_owner(admin, owner, "INSERT INTO gapto.categoria_magnitudes (id, categoria_id, magnitud_id, obligatoria) "
               "VALUES (%s,%s,%s,true)", (uuid.uuid4(), categoria, magnitud))
    h = hecho()
    e = dataclasses.replace(efecto("GASTO", D("100.0000")), categoria_id=categoria)
    op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(hecho=h, efectos=[e]))
    assert cuenta_filas(admin, owner, "hecho_magnitudes", "hecho_id", h.hecho_id) == 0


def test_magnitud_desconocida_es_ausencia_nunca_cero(op22, contexto, admin) -> None:
    """§9. valor=None se rechaza y no queda ninguna fila (ni a cero)."""
    owner = contexto.owner_user_id
    h = hecho()
    c = DatosContextoHecho(magnitudes=[DatosMagnitudHecho(uuid.uuid4(), nueva_magnitud(admin, owner), None)])
    rechazo(lambda: op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(
        hecho=h, efectos=[efecto("GASTO", D("100.0000"))], contexto=c)), CodigoError.ENTRADA_INVALIDA)
    assert cuenta_filas(admin, owner, "hechos_financieros", "id", h.hecho_id) == 0


@pytest.mark.parametrize("nivel_efecto, principal", [(True, False), (False, True)])
def test_d080_inversion_fuera_de_matriz_es_ownership_f07(op22, contexto, admin, nivel_efecto, principal) -> None:
    """§8/§21 + R3-01. Inversion a nivel de efecto o principal -> OWNERSHIP_F07
    y nada confirmado."""
    owner = contexto.owner_user_id
    h = hecho()
    e = efecto("GASTO", D("100.0000"))
    c = DatosContextoHecho(entidades=[DatosEntidadHecho(
        uuid.uuid4(), nueva_entidad(admin, owner, "INVERSION"), "RELACIONADO_CON", principal=principal,
        efecto_id=e.efecto_id if nivel_efecto else None)])
    rechazo(lambda: op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(hecho=h, efectos=[e], contexto=c)),
            CodigoError.OWNERSHIP_F07)
    assert cuenta_filas(admin, owner, "hechos_financieros", "id", h.hecho_id) == 0


def test_d080_inversion_a_nivel_de_hecho_se_admite(op22, contexto, admin) -> None:
    """R3-01. Inversion como contexto a nivel de hecho, principal=false."""
    owner = contexto.owner_user_id
    h = hecho()
    c = DatosContextoHecho(entidades=[DatosEntidadHecho(
        uuid.uuid4(), nueva_entidad(admin, owner, "INVERSION"), "RELACIONADO_CON", principal=False)])
    op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(hecho=h, efectos=[efecto("GASTO", D("100.0000"))], contexto=c))
    assert cuenta_filas(admin, owner, "hecho_entidades", "hecho_id", h.hecho_id) == 1


# ==================================================================
# §13/§14 · Identidad e idempotencia del agregado
# ==================================================================

def _intencion_completa(admin, contexto, cuenta, actor_a) -> DatosHechoCompuesto:
    h = hecho()
    p = pago(h.hecho_id, cuenta, "-100.0000")
    return DatosHechoCompuesto(
        hecho=h,
        efectos=[efecto("GASTO", D("100.0000"), atribuciones=(atribucion(actor_a, D("100.0000")),))],
        pagos=[p],
        aportaciones=[aportacion(D("100.0000"), actor_id=actor_a, conciliacion_id=p.conciliacion.conciliacion_id)],
        contexto=_contexto_completo(admin, contexto.owner_user_id),
    )


def test_replay_identico_es_idempotente(op22, contexto, admin, cuenta, actor_a) -> None:
    """§13. Mismo agregado completo -> idempotente, sin filas ni version nuevas."""
    datos = _intencion_completa(admin, contexto, cuenta, actor_a)
    primero = op22.registrar_hecho_compuesto(contexto, datos)
    auditorias = leer_fila(admin, contexto.owner_user_id, "SELECT count(*) FROM gapto.auditoria", ())[0]
    segundo = op22.registrar_hecho_compuesto(contexto, datos)
    assert segundo.idempotente and segundo.hecho_row_version == primero.hecho_row_version
    assert segundo.movimientos == primero.movimientos
    assert leer_fila(admin, contexto.owner_user_id, "SELECT count(*) FROM gapto.auditoria", ())[0] == auditorias


def test_replay_con_intencion_distinta_es_conflicto(op22, contexto, admin, cuenta, actor_a) -> None:
    """§13. Mismos UUID, otro importe de aportacion -> conflicto, sin cambios."""
    datos = _intencion_completa(admin, contexto, cuenta, actor_a)
    op22.registrar_hecho_compuesto(contexto, datos)
    otra = dataclasses.replace(datos, aportaciones=[dataclasses.replace(datos.aportaciones[0], importe=D("99.0000"))])
    rechazo(lambda: op22.registrar_hecho_compuesto(contexto, otra), CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION)


def test_agregado_parcial_preexistente_no_se_completa(op22, servicio, contexto, admin, cuenta, actor_a) -> None:
    """§13. La raiz existe (OP-01 suelto) pero no el resto: conflicto; no se
    completan en silencio los componentes ausentes."""
    datos = _intencion_completa(admin, contexto, cuenta, actor_a)
    servicio.crear_hecho(contexto, datos.hecho)
    rechazo(lambda: op22.registrar_hecho_compuesto(contexto, datos), CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION)
    assert cuenta_filas(admin, contexto.owner_user_id, "hecho_efectos", "hecho_id", datos.hecho.hecho_id) == 0


def test_identidad_antes_de_validacion_mutable(op22, contexto, admin, cuenta, actor_a) -> None:
    """§14. Tras un exito confirmado se deshabilitan la entidad, la etiqueta y
    el tercero usados. El reintento sigue siendo idempotente (la identidad se
    resuelve antes de validar estado mutable); una intencion NUEVA con esos
    objetos si se rechaza."""
    owner = contexto.owner_user_id
    datos = _intencion_completa(admin, contexto, cuenta, actor_a)
    op22.registrar_hecho_compuesto(contexto, datos)
    c = datos.contexto
    como_owner(admin, owner, "UPDATE gapto.entidades SET enabled=false WHERE id=%s", (c.entidades[0].entidad_id,))
    como_owner(admin, owner, "UPDATE gapto.etiquetas SET enabled=false WHERE id=%s", (c.etiquetas[0].etiqueta_id,))
    como_owner(admin, owner, "UPDATE gapto.terceros SET enabled=false WHERE id=%s", (c.terceros[0].tercero_id,))
    assert op22.registrar_hecho_compuesto(contexto, datos).idempotente
    nueva = DatosHechoCompuesto(
        hecho=hecho(), efectos=[efecto("GASTO", D("100.0000"))],
        contexto=DatosContextoHecho(entidades=[dataclasses.replace(c.entidades[0], registro_id=uuid.uuid4())]))
    rechazo(lambda: op22.registrar_hecho_compuesto(contexto, nueva), CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO)


# ==================================================================
# §15 · Atomicidad: fallo tardio tras cada familia de componente
# ==================================================================

PUNTOS = [
    ("app.services.hechos_service.HechosService", "crear_hecho"),
    ("app.services.efectos_service.EfectosService", "registrar_efectos"),
    ("app.services.posiciones_service.PosicionesService", "crear_posicion"),
    ("app.services.tesoreria_service.TesoreriaService", "registrar_movimiento"),
    ("app.services.tesoreria_service.TesoreriaService", "conciliar"),
    ("app.services.tesoreria_service.TesoreriaService", "registrar_aportaciones"),
    ("app.repositories.contexto_repository", "insertar_tercero"),
    ("app.repositories.contexto_repository", "insertar_entidad"),
    ("app.repositories.contexto_repository", "insertar_magnitud"),
    ("app.repositories.contexto_repository", "insertar_etiqueta"),
    ("app.services.previsiones_service.PrevisionesService", "vincular_realidad"),
]


class FalloTardio(Exception):
    pass


@pytest.mark.parametrize("ruta, metodo", PUNTOS, ids=[p[1] for p in PUNTOS])
def test_fallo_tardio_no_deja_nada(
    op22, servicio_previsiones, contexto, admin, cuenta, actor_a, contraparte, monkeypatch, ruta, metodo
) -> None:
    """§15. El componente se ejecuta y DESPUES falla: cero persistencia de la
    intencion completa (hecho, efectos, atribucion, movimiento, conciliacion,
    aportacion, posicion, contexto, vinculo con prevision)."""
    import importlib

    owner = contexto.owner_user_id
    prevision_id, version = _prevision(admin, contexto, servicio_previsiones)
    datos = _intencion_completa(admin, contexto, cuenta, actor_a)
    a = alta(datos.hecho.hecho_id, contraparte, importe="10.0000")
    vinculo = uuid.uuid4()
    datos = dataclasses.replace(datos, posiciones=[a], prevision=DatosPrevisionCompuesta(
        prevision_id=prevision_id, prevision_row_version_esperada=version, vinculo_id=vinculo,
        importe_asignado=D("100.0000"), marcar_realizada=True))

    modulo, _, clase = ruta.rpartition(".")
    if ruta.startswith("app.repositories"):
        objetivo = importlib.import_module(ruta)
    else:
        objetivo = getattr(importlib.import_module(modulo), clase)
    original = getattr(objetivo, metodo)

    def envoltura(*args, **kwargs):
        original(*args, **kwargs)
        raise FalloTardio(metodo)

    monkeypatch.setattr(objetivo, metodo, envoltura)
    with pytest.raises(ErrorMotor) as excinfo:
        op22.registrar_hecho_compuesto(contexto, datos)
    # La unidad de trabajo clasifica el fallo inesperado como INTERNO y
    # conserva la causa: se comprueba que es EL fallo inyectado.
    assert excinfo.value.codigo is CodigoError.INTERNO
    assert isinstance(excinfo.value.causa, FalloTardio)
    monkeypatch.undo()

    hecho_id = datos.hecho.hecho_id
    for tabla, columna, valor in (
        ("hechos_financieros", "id", hecho_id),
        ("hecho_efectos", "hecho_id", hecho_id),
        ("efecto_atribuciones", "id", datos.efectos[0].atribuciones[0].atribucion_id),
        ("movimientos_tesoreria", "id", datos.pagos[0].movimiento.movimiento_id),
        ("hecho_movimientos_tesoreria", "hecho_id", hecho_id),
        ("hecho_aportaciones_pago", "hecho_id", hecho_id),
        ("entidades", "id", a.entidad_id),
        ("hecho_terceros", "hecho_id", hecho_id),
        ("hecho_entidades", "hecho_id", hecho_id),
        ("hecho_magnitudes", "hecho_id", hecho_id),
        ("hecho_etiquetas", "hecho_id", hecho_id),
        ("prevision_hechos", "id", vinculo),
    ):
        assert cuenta_filas(admin, owner, tabla, columna, valor) == 0, tabla
    assert leer_fila(admin, owner, "SELECT estado FROM gapto.previsiones WHERE id=%s", (prevision_id,)) == ("ABIERTA",)
