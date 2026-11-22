# ============================================================
# GAPTO MOBILE 2027
# Fichero: aj05_helpers.py
# Ruta: tests/api/aj05_helpers.py
# Descripcion: Utilidades de los tests de AJ-05 (F06 T4; plazos de servidor, desenlaces de persistencia y registro de
#   peticiones). Solo tests; no cambian el codigo bajo prueba:
#   - `Proveedor`: proveedor de conexiones con ganchos por apertura (antes de conectar, antes del COMMIT y despues del
#     COMMIT) para provocar cortes, esperas y errores en puntos exactos de una unidad de trabajo. La conexion real es
#     de psycopg contra GAPTO_TEST_DATABASE_URL; el gancho recibe el numero de apertura y la conexion.
#   - `cliente`: TestClient con el reloj fijo de los laboratorios, el proveedor y el registro de peticiones inyectados.
#   - `registro`/`eventos`: registro JSONL real en un directorio temporal y lectura de sus eventos.
#   - `bloquear_raiz`: otra sesion retiene el advisory por raiz de OP-22 de una intencion (espera por lock real).
#   - `plazo`: fija los plazos de clase para un test (monkeypatch).
# Version: 0.1.0 (F06 T4 · AJ-05 ampliado + R-C7-07, mandato b4ff6b70… y adenda 01 24113472…)
# ============================================================
from __future__ import annotations

import contextlib
import json
import pathlib
import time
import uuid
from typing import Any, Callable

import psycopg

import f05_05_helpers as x
import vs01_api_helpers as h
from app.api import registro_peticiones as regp
from app.core import peticion as pet

GASTO = "/v1/intenciones/gasto-pagado"
RELOJ = "2026-10-10T12:00:00"


class _Tx:
    """Envuelve `conexion.transaction()`: ganchos justo antes de pedir el COMMIT y justo despues de confirmarlo."""

    def __init__(self, interna, prov: "Proveedor", n: int, real) -> None:
        self._i, self._p, self._n, self._real = interna, prov, n, real

    def __enter__(self):
        return self._i.__enter__()

    def __exit__(self, et, ev, tb):
        if et is None and self._p.antes_commit is not None:
            self._p.antes_commit(self._n, self._real)
        r = self._i.__exit__(et, ev, tb)
        if et is None:
            self._p.confirmadas.append(self._n)
            if self._p.despues_commit is not None:
                self._p.despues_commit(self._n, self._real)
        return r


class ConexionEspia:
    """Delega todo en la conexion real salvo `transaction()`."""

    def __init__(self, real, prov: "Proveedor", n: int) -> None:
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_prov", prov)
        object.__setattr__(self, "_n", n)

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)

    def __setattr__(self, nombre, valor):
        setattr(self._real, nombre, valor)

    def transaction(self, *a, **k):
        return _Tx(self._real.transaction(*a, **k), self._prov, self._n, self._real)


class Proveedor:
    """Una conexion nueva por apertura (como el proveedor por defecto) con ganchos opcionales."""

    def __init__(self) -> None:
        self.aperturas = 0
        self.confirmadas: list[int] = []
        self.al_abrir: Callable[[int], None] | None = None
        self.antes_commit: Callable[[int, Any], None] | None = None
        self.despues_commit: Callable[[int, Any], None] | None = None

    def limpiar(self) -> None:
        self.al_abrir = self.antes_commit = self.despues_commit = None

    @contextlib.contextmanager
    def __call__(self):
        self.aperturas += 1
        n = self.aperturas
        if self.al_abrir is not None:
            self.al_abrir(n)
        estado = pet.actual()
        with psycopg.connect(h.dsn(), connect_timeout=estado.connect_timeout_s() if estado else 5) as c:
            yield ConexionEspia(c, self, n)


def cliente(owner: uuid.UUID, *, proveedor: Proveedor | None = None, registro=None, reloj: str = RELOJ):
    kw: dict[str, Any] = {"reloj": x.reloj(reloj)}
    if proveedor is not None:
        kw["proveedor_conexion"] = proveedor
    if registro is not None:
        kw["registro"] = registro
    return h.cliente(owner, **kw)


def registro(directorio: pathlib.Path, **kw) -> regp.RegistroPeticiones:
    return regp.RegistroPeticiones.abrir(directorio, **kw)


def eventos(reg: regp.RegistroPeticiones) -> list[dict]:
    f = reg.fichero_actual()
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def terminadas(reg: regp.RegistroPeticiones, ruta: str | None = None) -> list[dict]:
    return [e for e in eventos(reg) if e["evento"] == "TERMINADA" and (ruta is None or e["ruta"] == ruta)]


def ultima(reg: regp.RegistroPeticiones, ruta: str | None = None) -> dict:
    t = terminadas(reg, ruta)
    assert t, f"sin TERMINADA para {ruta}"
    return t[-1]


@contextlib.contextmanager
def bloquear_raiz(intencion_id: str):
    """Otra sesion (superusuario de la base desechable) retiene el advisory por raiz de OP-22 de la intencion
    (compuesto_repository.tomar_advisory_raiz) hasta salir del bloque."""
    with psycopg.connect(h.dsn()) as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('gapto:OP22'), hashtext(%s::uuid::text))", (intencion_id,))
        yield
        c.rollback()


def plazo(monkeypatch, *, a: float | None = None, b: float | None = None) -> None:
    if a is not None:
        monkeypatch.setitem(pet.PLAZO_CLASE_S, "A", a)
    if b is not None:
        monkeypatch.setitem(pet.PLAZO_CLASE_S, "B", b)


def dormir_hasta_restante(limite_s: float) -> None:
    """Desde dentro de una unidad: consume el plazo de la peticion hasta que queden `limite_s` segundos."""
    e = pet.actual()
    assert e is not None, "fuera de una peticion HTTP"
    time.sleep(max(0.0, e.restante() - limite_s))


def hechos(owner: uuid.UUID, hecho_id) -> int:
    return h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (str(hecho_id),))[0][0]


def auditoria(owner: uuid.UUID) -> int:
    return h.leer(owner, "SELECT count(*) FROM gapto.auditoria")[0][0]


def corte(*_a) -> None:
    raise psycopg.OperationalError("conexion perdida (simulada por el test)")
