# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_146_f04_d053_raiz_bloqueo.py
# Ruta: tests/backend/test_146_f04_d053_raiz_bloqueo.py
# Descripcion: F04-D053 B1 · B8 / CC-D053-3. Raiz de bloqueo de la posicion
#   generica: carrera e interbloqueo con operaciones REALES concurrentes.
#
#   Metodo: la operacion T1 se PAUSA justo despues de adquirir su raiz
#   (envoltura de `integridad_posicion.adquirir_raiz` solo en el hilo T1) y
#   T2 arranca. Que T2 espere o no se observa en pg_stat_activity
#   (wait_event_type = 'Lock', advisory incluido), sin sleep fijo. Al
#   liberar T1, las dos terminan y se comprueba el resultado. Unidades con
#   max_intentos=1: un 40P01 aflora como CONFLICTO_CONCURRENCIA y no se oculta
#   tras un reintento.
#
#   1. Misma posicion: T2 (OP-21, OP-02, OP-03, cierre, creacion) ESPERA a T1.
#   2. Posiciones distintas, mismo owner, vias sin advisory: T2 NO espera.
#   3. Owners distintos, dos creaciones: T2 NO espera.
#   4. Mismo owner, dos creaciones sobre posiciones distintas: T2 espera en el
#      advisory D-080 (serializacion por owner, D-158; ver DISENO_BLOQUEO.md).
#   5. Interbloqueo D-158: OP-21 con contexto (advisory -> hecho -> posicion)
#      frente a OP-21 de importe y frente a creacion sobre la misma posicion:
#      sin 40P01.
# Version: 0.1.0
#   0.1.0 (F04-D053 B1 · P0-1): carrera e interbloqueo de la raiz B8.
# ============================================================
from __future__ import annotations

import decimal
import threading
import time
import uuid
from contextlib import contextmanager

import psycopg
import pytest

import app.services.integridad_posicion as integridad_posicion
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import CamposCorreccion
from app.core.modelos_compuesto import DatosContextoHecho, DatosEntidadHecho
from app.core.modelos_posicion import (
    TIPO_OBLIGACION,
    DatosCierre,
    DatosCondonacionObligacion,
)
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.services.contexto_service import ContextoService
from app.services.correcciones_service import CorreccionesService, DatosCorreccion
from app.services.hechos_service import HechosService
from app.services.posiciones_service import PosicionesService
from app.services.previsiones_service import impacto_correccion_ancla
from conftest import ROL_RUNTIME, _crear_actor, _crear_cuenta, _crear_usuario
from test_109_op12_posiciones import CONDONACION, PAGO, alta, delta, tesoreria_nueva
from test_140_f04_r3_op22 import nueva_entidad

D = decimal.Decimal
TIMEOUT = 30
REPETICIONES = 5


# ==================================================================
# Infraestructura de concurrencia
# ==================================================================

class Servicios:
    """Servicios sobre una unidad propia, con application_name identificable."""

    def __init__(self, dsn: str, nombre: str) -> None:
        @contextmanager
        def _abrir():
            with psycopg.connect(dsn, application_name=nombre) as conexion:
                yield conexion

        unidad = UnidadDeTrabajo(
            _abrir, rol_runtime=ROL_RUNTIME, max_intentos=1, espera_inicial_s=0.001
        )
        self.nombre = nombre
        self.unidad = unidad
        self.pos = PosicionesService(unidad)
        self.cor = CorreccionesService(unidad)
        self.hec = HechosService(unidad, impacto_ancla=impacto_correccion_ancla)


class Pausa:
    """Retiene a T1 justo despues de adquirir su raiz B8."""

    def __init__(self, monkeypatch, hilo: str = "T1") -> None:
        self.adquirida = threading.Event()
        self.liberar = threading.Event()
        original = integridad_posicion.adquirir_raiz

        def envuelta(*args, **kwargs):
            resultado = original(*args, **kwargs)
            if threading.current_thread().name == hilo:
                self.adquirida.set()
                if not self.liberar.wait(TIMEOUT):
                    raise RuntimeError("pausa de T1 sin liberar")
            return resultado

        monkeypatch.setattr(integridad_posicion, "adquirir_raiz", envuelta)


class Hilo(threading.Thread):
    def __init__(self, nombre: str, funcion) -> None:
        super().__init__(name=nombre, daemon=True)
        self.funcion = funcion
        self.resultado = None
        self.error: BaseException | None = None
        self.fin: float | None = None

    def run(self) -> None:
        try:
            self.resultado = self.funcion()
        except BaseException as exc:  # noqa: BLE001 - se clasifica en el oraculo
            self.error = exc
        finally:
            self.fin = time.monotonic()


def _espera_lock(admin: psycopg.Connection, nombre: str, limite: float) -> bool:
    """True si la sesion `nombre` llega a esperar un lock (fila o advisory)."""
    tope = time.monotonic() + limite
    while time.monotonic() < tope:
        fila = admin.execute(
            "SELECT wait_event_type FROM pg_stat_activity "
            "WHERE application_name = %s AND state = 'active'",
            (nombre,),
        ).fetchone()
        if fila is not None and fila[0] == "Lock":
            return True
        threading.Event().wait(0.02)
    return False


def _sin_error(*hilos: Hilo) -> None:
    for h in hilos:
        assert not h.is_alive(), f"{h.name} sigue colgado"
        if isinstance(h.error, ErrorMotor):
            assert h.error.codigo is not CodigoError.CONFLICTO_CONCURRENCIA, (
                f"{h.name}: 40P01/40001 ({h.error.mensaje})"
            )
        assert h.error is None, f"{h.name}: {h.error!r}"


def _carrera(admin, monkeypatch, t1, t2, nombre_t2: str):
    """T1 pausado con su raiz; arranca T2; devuelve (t2_espero, T1, T2)."""
    pausa = Pausa(monkeypatch)
    h1, h2 = Hilo("T1", t1), Hilo("T2", t2)
    h1.start()
    assert pausa.adquirida.wait(TIMEOUT), f"T1 no adquirio su raiz: {h1.error!r}"
    h2.start()
    espero = _espera_lock(admin, nombre_t2, 3.0)
    if not espero:
        h2.join(TIMEOUT)  # sin espera: T2 debe terminar con T1 aun pausado
        assert not h2.is_alive()
    pausa.liberar.set()
    h1.join(TIMEOUT)
    h2.join(TIMEOUT)
    return espero, h1, h2


# ==================================================================
# Escenario: obligacion 100 con un pago 30 (REEMBOLSO) y una condonacion 10
# ==================================================================

@pytest.fixture()
def escenario(dsn, admin, owner, contraparte, cuenta):
    return _montar(dsn, owner, contraparte, cuenta)


def _montar(dsn, owner, contraparte, cuenta) -> dict:
    s = Servicios(dsn, f"montaje-{uuid.uuid4()}")
    ctx = ContextoOperacion.de_usuario(owner)

    def posicion() -> dict:
        a = alta(contraparte, tipo=TIPO_OBLIGACION, nombre="D053 B8")
        r = s.pos.crear_posicion(ctx, a)
        pago = delta("30.0000", causa=PAGO)
        r = s.pos.reducir_obligacion(
            ctx, entidad_id=a.entidad_id, entidad_row_version_esperada=r.entidad_row_version,
            delta=pago, movimiento=tesoreria_nueva(cuenta),
        )
        cond = delta("10.0000", causa=CONDONACION)
        r = s.pos.condonar_obligacion(
            ctx, entidad_id=a.entidad_id, entidad_row_version_esperada=r.entidad_row_version,
            datos=DatosCondonacionObligacion(delta=cond),
        )
        return {"entidad": a.entidad_id, "alta": a, "pago": pago, "cond": cond}

    return {"ctx": ctx, "owner": owner, "cuenta": cuenta, "p1": posicion(), "p2": posicion()}


def _version_hecho(admin, owner, hecho_id) -> int:
    from conftest import leer_fila

    return leer_fila(admin, owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s",
                     (hecho_id,))[0]


def _version_entidad(admin, owner, entidad_id) -> int:
    from conftest import leer_fila

    return leer_fila(admin, owner, "SELECT row_version FROM gapto.entidades WHERE id = %s",
                     (entidad_id,))[0]


# Operaciones parametrizables -------------------------------------------------

def _op_crear(s, e, admin, p, importe="5.0000"):
    return lambda: s.pos.reducir_obligacion(
        e["ctx"], entidad_id=p["entidad"],
        entidad_row_version_esperada=_version_entidad(admin, e["owner"], p["entidad"]),
        delta=delta(importe, causa=PAGO), movimiento=tesoreria_nueva(e["cuenta"]),
    )


def _op21_importe(s, e, admin, p):
    return lambda: s.cor.corregir(e["ctx"], DatosCorreccion(
        hecho_id=p["alta"].hecho_id,
        row_version_esperada=_version_hecho(admin, e["owner"], p["alta"].hecho_id),
        motivo="D053 B8 importe",
        efectos_a_actualizar={p["alta"].efecto_id: {"importe_delta": D("110.0000")}},
    ))


def _op21_descripcion(s, e, admin, p):
    return lambda: s.cor.corregir(e["ctx"], DatosCorreccion(
        hecho_id=p["pago"].hecho_id,
        row_version_esperada=_version_hecho(admin, e["owner"], p["pago"].hecho_id),
        motivo="D053 B8 descripcion",
        efectos_a_actualizar={p["pago"].efecto_id: {"descripcion": "captura"}},
    ))


def _op21_contexto(s, e, admin, p):
    """OP-21 con superficie de contexto (advisory -> hecho -> posicion).

    OP-21 solo da de alta como REEMPLAZO: antes se enriquece el hecho con una
    entidad (fuera de la carrera) y OP-21 la sustituye por otra.
    """
    hecho_id = p["pago"].hecho_id
    previa = DatosEntidadHecho(uuid.uuid4(), nueva_entidad(admin, e["owner"]), "AFECTA_A",
                               principal=False)
    ContextoService(s.unidad).enriquecer(
        e["ctx"], hecho_id=hecho_id,
        row_version_esperada=_version_hecho(admin, e["owner"], hecho_id),
        datos=DatosContextoHecho(entidades=[previa]),
    )
    reemplazo = DatosEntidadHecho(uuid.uuid4(), nueva_entidad(admin, e["owner"]), "AFECTA_A",
                                  principal=False)
    return lambda: s.cor.corregir(e["ctx"], DatosCorreccion(
        hecho_id=hecho_id,
        row_version_esperada=_version_hecho(admin, e["owner"], hecho_id),
        motivo="D053 B8 contexto",
        entidades_a_eliminar=(previa.registro_id,), entidades_a_crear=(reemplazo,),
    ))


def _op02(s, e, admin, p):
    return lambda: s.hec.corregir_hecho(
        e["ctx"], hecho_id=p["cond"].hecho_id,
        row_version_esperada=_version_hecho(admin, e["owner"], p["cond"].hecho_id),
        campos=CamposCorreccion(concepto="D053 B8"), motivo="D053 B8 OP-02",
    )


def _op03(s, e, admin, p):
    return lambda: s.hec.anular_hecho(
        e["ctx"], hecho_id=p["cond"].hecho_id,
        row_version_esperada=_version_hecho(admin, e["owner"], p["cond"].hecho_id),
        motivo_anulacion="D053 B8 OP-03",
    )


def _cerrar(s, e, admin, p):
    import datetime as dt

    return lambda: s.pos.cerrar_posicion(
        e["ctx"], entidad_id=p["entidad"],
        entidad_row_version_esperada=_version_entidad(admin, e["owner"], p["entidad"]),
        cierre=DatosCierre(motivo_cierre="OTRO", fecha_cierre=dt.date(2026, 7, 1)),
    )


OPERACIONES = {
    "op21_importe": _op21_importe,
    "op21_descripcion": _op21_descripcion,
    "op21_contexto": _op21_contexto,
    "op02": _op02,
    "op03": _op03,
    "cerrar": _cerrar,
    "crear": _op_crear,
}


# ==================================================================
# 1 · Misma posicion: T2 espera a T1 y termina despues
# ==================================================================

@pytest.mark.parametrize("t1", ["crear", "op21_importe", "op02", "op03", "cerrar"])
@pytest.mark.parametrize("t2", sorted(OPERACIONES))
def test_1_misma_posicion_serializa(dsn, admin, monkeypatch, escenario, t1, t2) -> None:
    if t1 == t2 and t1 in ("op02", "op03", "cerrar", "op21_importe"):
        pytest.skip("misma operacion sobre el mismo hecho/version: lo cubre el control optimista")
    s1, s2 = Servicios(dsn, f"T1-{uuid.uuid4()}"), Servicios(dsn, f"T2-{uuid.uuid4()}")
    p = escenario["p1"]
    f1 = OPERACIONES[t1](s1, escenario, admin, p)
    f2 = OPERACIONES[t2](s2, escenario, admin, p)
    espero, h1, h2 = _carrera(admin, monkeypatch, f1, f2, s2.nombre)
    assert espero, f"{t2} no espero a {t1} sobre la misma posicion"
    assert h1.error is None, repr(h1.error)
    assert h2.fin >= h1.fin
    # T2 leyo su version ANTES de que T1 confirmase y valida DESPUES: puede
    # perder por lo que T1 dejo confirmado (version, hecho anulado, posicion
    # cerrada); nunca por 40P01.
    if h2.error is not None:
        assert isinstance(h2.error, ErrorMotor), repr(h2.error)
        assert h2.error.codigo in PERDEDOR_LEGITIMO, h2.error.codigo


PERDEDOR_LEGITIMO = frozenset({
    CodigoError.VERSION_DESFASADA,
    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
    CodigoError.POSICION_CERRADA,
})


# ==================================================================
# 2 · Posiciones distintas, mismo owner, vias sin advisory: sin espera
# ==================================================================

@pytest.mark.parametrize("t1", ["op02", "op03", "cerrar", "op21_descripcion"])
@pytest.mark.parametrize("t2", ["op02", "op03", "cerrar", "op21_descripcion", "crear"])
def test_2_posiciones_distintas_no_esperan(dsn, admin, monkeypatch, escenario, t1, t2) -> None:
    s1, s2 = Servicios(dsn, f"T1-{uuid.uuid4()}"), Servicios(dsn, f"T2-{uuid.uuid4()}")
    f1 = OPERACIONES[t1](s1, escenario, admin, escenario["p1"])
    f2 = OPERACIONES[t2](s2, escenario, admin, escenario["p2"])
    espero, h1, h2 = _carrera(admin, monkeypatch, f1, f2, s2.nombre)
    assert not espero, f"{t2} sobre P2 espero a {t1} sobre P1: bloqueo innecesario"
    _sin_error(h1, h2)
    assert h2.fin < h1.fin  # T2 termino con T1 todavia pausado


# ==================================================================
# 3 · Owners distintos: dos creaciones no se esperan
# ==================================================================

def test_3_owners_distintos_no_esperan(dsn, admin, monkeypatch, escenario) -> None:
    otro = uuid.uuid4()
    _crear_usuario(admin, otro)
    _crear_actor(admin, otro, con_tercero=False)
    contraparte = _crear_actor(admin, otro, con_tercero=True)
    ajeno = _montar(dsn, otro, contraparte, _crear_cuenta(admin, otro, "EUR"))
    s1, s2 = Servicios(dsn, f"T1-{uuid.uuid4()}"), Servicios(dsn, f"T2-{uuid.uuid4()}")
    f1 = _op_crear(s1, escenario, admin, escenario["p1"])
    f2 = _op_crear(s2, ajeno, admin, ajeno["p1"])
    espero, h1, h2 = _carrera(admin, monkeypatch, f1, f2, s2.nombre)
    assert not espero, "una creacion de otro owner espero: bloqueo global"
    _sin_error(h1, h2)
    assert h2.fin < h1.fin


# ==================================================================
# 4 · Mismo owner, creaciones sobre posiciones distintas: advisory D-080
# ==================================================================

def test_4_mismo_owner_creaciones_serializan_en_advisory(dsn, admin, monkeypatch, escenario) -> None:
    s1, s2 = Servicios(dsn, f"T1-{uuid.uuid4()}"), Servicios(dsn, f"T2-{uuid.uuid4()}")
    f1 = _op_crear(s1, escenario, admin, escenario["p1"])
    f2 = _op_crear(s2, escenario, admin, escenario["p2"])
    espero, h1, h2 = _carrera(admin, monkeypatch, f1, f2, s2.nombre)
    assert espero, "la creacion debe tomar el advisory D-080 antes de cualquier fila"
    _sin_error(h1, h2)


# ==================================================================
# 5 · Interbloqueo D-158: sin 40P01
# ==================================================================

@pytest.mark.parametrize("pareja", [
    ("op21_importe", "op21_contexto"),
    ("op21_contexto", "op21_importe"),
    ("crear", "op21_contexto"),
    ("op21_contexto", "crear"),
    ("op02", "op21_contexto"),
    ("op21_contexto", "op03"),
])
def test_5_interbloqueo_d158_pausado(dsn, admin, monkeypatch, escenario, pareja) -> None:
    t1, t2 = pareja
    s1, s2 = Servicios(dsn, f"T1-{uuid.uuid4()}"), Servicios(dsn, f"T2-{uuid.uuid4()}")
    p = escenario["p1"]
    f1 = OPERACIONES[t1](s1, escenario, admin, p)
    f2 = OPERACIONES[t2](s2, escenario, admin, p)
    espero, h1, h2 = _carrera(admin, monkeypatch, f1, f2, s2.nombre)
    assert espero
    for h in (h1, h2):
        assert not h.is_alive()
        if isinstance(h.error, ErrorMotor):
            assert h.error.codigo in PERDEDOR_LEGITIMO, (h.name, h.error.codigo)
        else:
            assert h.error is None, repr(h.error)


@pytest.mark.parametrize("pareja", [
    ("op21_importe", "op21_contexto"),
    ("crear", "op21_contexto"),
    ("crear", "op21_importe"),
])
def test_5_interbloqueo_d158_libre(dsn, admin, owner, contraparte, cuenta, pareja) -> None:
    """Sin pausa, arranque simultaneo con barrera, REPETICIONES veces."""
    for _ in range(REPETICIONES):
        e = _montar(dsn, owner, contraparte, cuenta)
        s1, s2 = Servicios(dsn, f"T1-{uuid.uuid4()}"), Servicios(dsn, f"T2-{uuid.uuid4()}")
        f1 = OPERACIONES[pareja[0]](s1, e, admin, e["p1"])
        f2 = OPERACIONES[pareja[1]](s2, e, admin, e["p1"])
        barrera = threading.Barrier(2)
        h1 = Hilo("L1", lambda: (barrera.wait(TIMEOUT), f1())[1])
        h2 = Hilo("L2", lambda: (barrera.wait(TIMEOUT), f2())[1])
        h1.start(), h2.start()
        h1.join(TIMEOUT), h2.join(TIMEOUT)
        for h in (h1, h2):
            assert not h.is_alive()
            if isinstance(h.error, ErrorMotor):
                assert h.error.codigo in PERDEDOR_LEGITIMO, (h.name, h.error.codigo)
            else:
                assert h.error is None, repr(h.error)
