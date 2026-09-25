# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_143_f04_d050_idempotencia_exacta.py
# Ruta: tests/backend/test_143_f04_d050_idempotencia_exacta.py
# Descripcion: F04-D050. Bateria discriminante de la idempotencia EXACTA de
#   OP-22 (contrato A-E): el reconocimiento de una identidad ya materializada
#   exige igualdad exacta entre la intencion y el agregado persistido, no
#   inclusion.
#     - caso A15: con aportacion -> reintento sin ella -> conflicto (C), sin
#       mutaciones nuevas;
#     - direccion inversa: sin una dimension opcional -> reintento que la
#       anade -> conflicto (B), no extension silenciosa;
#     - reducciones por familia (etiqueta, pago, posicion, participante,
#       atribucion) -> conflicto;
#     - elemento anadido despues por una operacion legitima del agregado
#       (enriquecimiento de contexto) -> el reintento de la intencion original
#       ya no coincide exactamente -> conflicto (C);
#     - reintentos verdaderamente identicos siguen siendo idempotentes para
#       todas las familias que compone OP-22 (contexto completo, posicion con
#       y sin importe inicial, suplemento con relacion, prevision).
#   Cada test nombra en su docstring el caso del contrato que discrimina.
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
    DatosEtiquetaHecho,
    DatosHechoCompuesto,
    DatosPagoCompuesto,
    DatosPrevisionCompuesta,
)
from app.core.modelos_posicion import TIPO_DERECHO, DatosAltaPosicion
from app.core.modelos_prevision import DatosPrevisionManual
from app.core.modelos_suplemento import DatosSuplemento
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.compuesto_service import HechosCompuestosService
from app.services.contexto_service import ContextoService
from conftest import leer_fila
from f08_motor import aportacion, atribucion, conciliacion, efecto, movimiento

D = decimal.Decimal
F = dt.date.fromisoformat
FECHA = F("2027-06-01")
CONFLICTO = CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION

TABLAS_AGREGADO = (
    "hecho_efectos", "hecho_participantes", "hecho_movimientos_tesoreria",
    "hecho_aportaciones_pago", "hecho_entidades", "hecho_terceros",
    "hecho_magnitudes", "hecho_etiquetas", "prevision_hechos",
)


# ==================================================================
# Utilidades (locales: D-193, sin helpers compartidos por nombre ambiguo)
# ==================================================================

@pytest.fixture()
def op22(unidad: UnidadDeTrabajo) -> HechosCompuestosService:
    from app.services.previsiones_service import impacto_correccion_ancla

    return HechosCompuestosService(unidad, impacto_ancla=impacto_correccion_ancla)


def _como_owner(admin: psycopg.Connection, owner: uuid.UUID, sql: str, params: tuple) -> None:
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),))
            cursor.execute(sql, params)
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")


def _etiqueta(admin, owner) -> uuid.UUID:
    i = uuid.uuid4()
    _como_owner(admin, owner,
                "INSERT INTO gapto.etiquetas (id, owner_user_id, nombre, enabled) VALUES (%s,%s,%s,true)",
                (i, owner, f"etiqueta {i}"))
    return i


def _hecho(total="100.0000") -> DatosCreacionHecho:
    return DatosCreacionHecho(
        hecho_id=uuid.uuid4(), fecha_hecho=FECHA, moneda="EUR", presupuestable=True,
        estado_localizacion="DESCONOCIDA", tipo_hecho_codigo="GASTO",
        concepto="hecho compuesto D050", importe_total=D(total),
    )


def _pago(hecho_id, cuenta, importe) -> DatosPagoCompuesto:
    m = movimiento(cuenta, D(importe))
    return DatosPagoCompuesto(movimiento=m, conciliacion=conciliacion(hecho_id, m.movimiento_id, D(importe)))


def _alta(hecho_id, contraparte, importe="40.0000") -> DatosAltaPosicion:
    return DatosAltaPosicion(
        entidad_id=uuid.uuid4(), nombre="posicion D050", tipo=TIPO_DERECHO,
        contraparte_actor_id=contraparte, moneda="EUR", justificacion="DECISION_EXPLICITA",
        fecha_inicio_seguimiento=FECHA, saldo_apertura=D("0"), hecho_id=hecho_id,
        fecha_hecho=FECHA, concepto="posicion D050", efecto_id=uuid.uuid4(),
        vinculo_id=uuid.uuid4(), importe_inicial=None if importe is None else D(importe),
    )


def _huella(admin, owner, hecho_id) -> tuple:
    """Fotografia del agregado y de la auditoria del tenant: nada debe cambiar
    tras un rechazo."""
    filas = tuple(
        leer_fila(admin, owner, f"SELECT count(*) FROM gapto.{t} WHERE hecho_id = %s", (hecho_id,))[0]
        for t in TABLAS_AGREGADO
    )
    version = leer_fila(admin, owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id=%s", (hecho_id,))
    auditoria = leer_fila(admin, owner, "SELECT count(*) FROM gapto.auditoria", ())[0]
    movimientos = leer_fila(admin, owner, "SELECT count(*) FROM gapto.movimientos_tesoreria", ())[0]
    return filas, version, auditoria, movimientos


def _conflicto(op22, contexto, datos) -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        op22.registrar_hecho_compuesto(contexto, datos)
    assert excinfo.value.codigo is CONFLICTO, excinfo.value


def _completa(admin, contexto, cuenta, actor_a, contraparte) -> DatosHechoCompuesto:
    """Intencion con todas las familias opcionales que una reduccion puede
    quitar: atribucion, participante, pago, aportacion, posicion y etiqueta."""
    from app.services.participantes_service import DatosParticipante

    h = _hecho()
    p = _pago(h.hecho_id, cuenta, "-100.0000")
    return DatosHechoCompuesto(
        hecho=h,
        efectos=[efecto("GASTO", D("100.0000"), atribuciones=(atribucion(actor_a, D("100.0000")),))],
        participantes=[DatosParticipante(participante_id=uuid.uuid4(), actor_id=actor_a)],
        pagos=[p],
        aportaciones=[aportacion(D("100.0000"), actor_id=actor_a, conciliacion_id=p.conciliacion.conciliacion_id)],
        posiciones=[_alta(h.hecho_id, contraparte)],
        contexto=DatosContextoHecho(etiquetas=[
            DatosEtiquetaHecho(uuid.uuid4(), _etiqueta(admin, contexto.owner_user_id))]),
    )


# ==================================================================
# Caso A15 y direccion inversa
# ==================================================================

def test_a15_reintento_sin_la_aportacion_es_conflicto_sin_mutaciones(op22, contexto, admin, cuenta, actor_a) -> None:
    """F04-D050 caso A15 / contrato C. Primera ejecucion con aportacion; el
    mismo UUID con intencion identica salvo sin la aportacion NO es un
    reintento del mismo agregado."""
    owner = contexto.owner_user_id
    h = _hecho()
    p = _pago(h.hecho_id, cuenta, "-100.0000")
    con = DatosHechoCompuesto(
        hecho=h,
        efectos=[efecto("GASTO", D("100.0000"), atribuciones=(atribucion(actor_a, D("100.0000")),))],
        pagos=[p],
        aportaciones=[aportacion(D("100.0000"), actor_id=actor_a, conciliacion_id=p.conciliacion.conciliacion_id)],
    )
    op22.registrar_hecho_compuesto(contexto, con)
    antes = _huella(admin, owner, h.hecho_id)
    _conflicto(op22, contexto, dataclasses.replace(con, aportaciones=[]))
    assert _huella(admin, owner, h.hecho_id) == antes
    assert op22.registrar_hecho_compuesto(contexto, con).idempotente  # A: el identico sigue valiendo


def test_inversa_reintento_que_anade_una_aportacion_es_conflicto(op22, contexto, admin, cuenta, actor_a) -> None:
    """F04-D050 direccion inversa / contrato B. Sin aportacion en la primera
    ejecucion; reutilizar la identidad para anadirla es conflicto, no una
    extension silenciosa del agregado."""
    owner = contexto.owner_user_id
    h = _hecho()
    p = _pago(h.hecho_id, cuenta, "-100.0000")
    sin = DatosHechoCompuesto(hecho=h, efectos=[efecto("GASTO", D("100.0000"))], pagos=[p])
    op22.registrar_hecho_compuesto(contexto, sin)
    antes = _huella(admin, owner, h.hecho_id)
    con = dataclasses.replace(sin, aportaciones=[
        aportacion(D("100.0000"), actor_id=actor_a, conciliacion_id=p.conciliacion.conciliacion_id)])
    _conflicto(op22, contexto, con)
    assert _huella(admin, owner, h.hecho_id) == antes


# ==================================================================
# Reducciones por familia (contrato C)
# ==================================================================

REDUCCIONES = {
    "sin_etiqueta": lambda d: dataclasses.replace(d, contexto=DatosContextoHecho()),
    "sin_posicion": lambda d: dataclasses.replace(d, posiciones=[]),
    "sin_participante": lambda d: dataclasses.replace(d, participantes=[]),
    "sin_pago_ni_aportacion": lambda d: dataclasses.replace(d, pagos=[], aportaciones=[]),
    "sin_atribucion": lambda d: dataclasses.replace(
        d, efectos=[dataclasses.replace(d.efectos[0], atribuciones=())]),
}


@pytest.mark.parametrize("reduccion", REDUCCIONES, ids=list(REDUCCIONES))
def test_reduccion_de_cualquier_familia_es_conflicto(
    op22, contexto, admin, cuenta, actor_a, contraparte, reduccion
) -> None:
    """F04-D050 contrato C por familia: quitar de la intencion cualquier
    elemento ya materializado impide el reconocimiento idempotente."""
    owner = contexto.owner_user_id
    datos = _completa(admin, contexto, cuenta, actor_a, contraparte)
    op22.registrar_hecho_compuesto(contexto, datos)
    antes = _huella(admin, owner, datos.hecho_id)
    _conflicto(op22, contexto, REDUCCIONES[reduccion](datos))
    assert _huella(admin, owner, datos.hecho_id) == antes


def test_elemento_anadido_despues_impide_reconocer_la_intencion_original(op22, contexto, admin, cuenta, actor_a) -> None:
    """F04-D050 contrato C: un elemento del agregado no declarado por la
    intencion reutilizada -aunque lo haya anadido despues una operacion
    legitima (enriquecimiento de contexto)- hace que el agregado ya no
    coincida EXACTAMENTE con esa intencion: conflicto, no exito."""
    owner = contexto.owner_user_id
    h = _hecho()
    datos = DatosHechoCompuesto(hecho=h, efectos=[efecto("GASTO", D("100.0000"))],
                                pagos=[_pago(h.hecho_id, cuenta, "-100.0000")])
    r = op22.registrar_hecho_compuesto(contexto, datos)
    ContextoService(op22._unidad).enriquecer(
        contexto, hecho_id=h.hecho_id, row_version_esperada=r.hecho_row_version,
        datos=DatosContextoHecho(etiquetas=[DatosEtiquetaHecho(uuid.uuid4(), _etiqueta(admin, owner))]))
    _conflicto(op22, contexto, datos)


# ==================================================================
# Contrato A: los reintentos identicos siguen siendo idempotentes
# ==================================================================

def test_identico_completo_es_idempotente(op22, contexto, admin, cuenta, actor_a, contraparte) -> None:
    """F04-D050 contrato A con todas las familias que una reduccion ejercita."""
    owner = contexto.owner_user_id
    datos = _completa(admin, contexto, cuenta, actor_a, contraparte)
    primero = op22.registrar_hecho_compuesto(contexto, datos)
    antes = _huella(admin, owner, datos.hecho_id)
    segundo = op22.registrar_hecho_compuesto(contexto, datos)
    assert segundo.idempotente and segundo.hecho_row_version == primero.hecho_row_version
    assert _huella(admin, owner, datos.hecho_id) == antes


def test_identico_con_posicion_sin_importe_inicial_es_idempotente(op22, contexto, admin, contraparte) -> None:
    """F04-D050 contrato A. Una posicion declarada sin `importe_inicial` no
    crea efecto causal ni vinculo; la identidad esperada no los incluye y el
    reintento identico se reconoce."""
    h = _hecho()
    datos = DatosHechoCompuesto(hecho=h, efectos=[efecto("GASTO", D("100.0000"))],
                                posiciones=[_alta(h.hecho_id, contraparte, importe=None)])
    op22.registrar_hecho_compuesto(contexto, datos)
    assert op22.registrar_hecho_compuesto(contexto, datos).idempotente


def test_identico_suplemento_con_relacion_es_idempotente(op22, contexto, admin, cuenta) -> None:
    """F04-D050 contrato A para la raiz suplementaria (OP-18 adscrito) con
    relacion CORRIGE_A originada por la raiz."""
    original = _hecho()
    op22.registrar_hecho_compuesto(contexto, DatosHechoCompuesto(
        hecho=original, efectos=[efecto("GASTO", D("100.0000"))]))
    s = DatosSuplemento(
        hecho_id=uuid.uuid4(), efecto_id=uuid.uuid4(), tipo_efecto="GASTO", importe_delta=D("3.5000"),
        fecha_hecho=F("2027-06-12"), moneda="EUR", fecha_demostrada=True, concepto="recargo",
        presupuestable=True, relacion_id=uuid.uuid4(), hecho_ajustado_id=original.hecho_id,
    )
    assert s.con_relacion
    datos = DatosHechoCompuesto(suplemento=s, pagos=[_pago(s.hecho_id, cuenta, "-3.5000")])
    op22.registrar_hecho_compuesto(contexto, datos)
    assert op22.registrar_hecho_compuesto(contexto, datos).idempotente


def test_identico_con_prevision_es_idempotente(op22, servicio_previsiones, contexto, admin) -> None:
    """F04-D050 contrato A con vinculo a prevision y realizacion explicita."""
    prevision = DatosPrevisionManual(
        prevision_id=uuid.uuid4(), concepto="luz", tipo_hecho_codigo="GASTO",
        fecha_esperada_desde=F("2027-06-01"), fecha_esperada_hasta=F("2027-06-30"),
        flujo_tesoreria_esperado="SALIDA", moneda="EUR", presupuestable=True,
        importe_esperado=D("100.0000"),
    )
    version = servicio_previsiones.crear_manual(contexto, prevision).row_version
    h = _hecho()
    datos = DatosHechoCompuesto(
        hecho=h, efectos=[efecto("GASTO", D("100.0000"))],
        prevision=DatosPrevisionCompuesta(
            prevision_id=prevision.prevision_id, prevision_row_version_esperada=version,
            vinculo_id=uuid.uuid4(), importe_asignado=D("100.0000"), marcar_realizada=True),
    )
    op22.registrar_hecho_compuesto(contexto, datos)
    assert op22.registrar_hecho_compuesto(contexto, datos).idempotente
