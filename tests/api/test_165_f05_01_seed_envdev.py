# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_165_f05_01_seed_envdev.py
# Ruta: tests/api/test_165_f05_01_seed_envdev.py
# Descripcion: Seed de categorias de ENV-DEV (scripts/dev/bootstrap_dev_db.py
#   --seed-categorias), decision de ejecucion D33 del mandato S7-MAG backend:
#   el seed GARANTIZA EXISTENCIA, NO ESTADO.
#     - paso (2): una categoria que ya existe por su UUID determinista no
#       recibe ningun POST (aunque el usuario la haya renombrado, movido,
#       cambiado de icono u ordenado) y se registra «existente, no
#       modificada»; solo se dan de alta las que faltan;
#     - paso (4): solo se desactivan las categorias marcadas DESACTIVADA que
#       creo esa misma ejecucion; una existente no se toca;
#     - cualquier rechazo del alta aborta (SystemExit), sin corregir nada.
#   Test SIN base de datos: la API HTTP se sustituye por un doble que registra
#   las llamadas. No ejercita el SQL de los pasos (1) y (3) (SEED_DEV,
#   cubiertos por la ejecucion local de evidencia). test_044 (head autorizado)
#   no se toca: solo cambia en un cambio revisado.
# Version: 0.1.0 (F05-01 S7-MAG, D33)
# ============================================================

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev" / "bootstrap_dev_db.py"


@pytest.fixture()
def seed():
    especificacion = importlib.util.spec_from_file_location("bootstrap_dev_db_t165", _SCRIPT)
    modulo = importlib.util.module_from_spec(especificacion)
    sys.modules["bootstrap_dev_db_t165"] = modulo
    especificacion.loader.exec_module(modulo)
    yield modulo
    sys.modules.pop("bootstrap_dev_db_t165", None)


class _ApiDoble:
    """Arbol en memoria; registra cada llamada (metodo, ruta)."""

    def __init__(self, seed, existentes: dict[str, dict], rechazar: set[str] = frozenset()):
        self.seed, self.arbol, self.rechazar, self.llamadas = seed, dict(existentes), rechazar, []

    def __call__(self, api, token, metodo, ruta, cuerpo=None):
        self.llamadas.append((metodo, ruta))
        if metodo == "GET" and ruta == "/v1/categorias":
            return 200, {"categorias": list(self.arbol.values())}
        if metodo == "POST" and ruta == "/v1/categorias":
            if cuerpo["id"] in self.rechazar:
                return 409, {"codigo": "CATEGORIA_NOMBRE_DUPLICADO"}
            self.arbol[cuerpo["id"]] = {**cuerpo, "enabled": True, "row_version": 1}
            return 200, {"idempotente": False}
        if metodo == "POST" and ruta.endswith("/desactivar"):
            cid = ruta.split("/")[3]
            self.arbol[cid] = {**self.arbol[cid], "enabled": False, "row_version": self.arbol[cid]["row_version"] + 1}
            return 200, {"idempotente": False}
        raise AssertionError(f"llamada inesperada {metodo} {ruta}")

    def posts(self) -> list[str]:
        return [r for m, r in self.llamadas if m == "POST"]


def _nodo(seed, clave, **cambios) -> dict:
    return {"id": str(seed.id_categoria(clave)), "nombre": clave, "enabled": True, "row_version": 1, **cambios}


def test_existentes_no_reciben_ningun_post_aunque_hayan_cambiado(seed, monkeypatch):
    claves = [c[0] for c in seed.SEED_CATEGORIAS]
    existentes = {str(seed.id_categoria(k)): _nodo(seed, k) for k in claves}
    # Luz evoluciono en ENV-DEV (icono/nombre/orden): row_version > 1 y otro nombre.
    existentes[str(seed.id_categoria("luz"))] = _nodo(seed, "luz", nombre="Luz y potencia", row_version=4)
    doble = _ApiDoble(seed, existentes)
    monkeypatch.setattr(seed, "_api", doble)
    lineas, creadas = seed._seed_categorias_api("http://127.0.0.1:8027", "t")
    assert doble.posts() == [] and creadas == set()
    assert lineas == [f"CATEGORIA {k}: existente, no modificada" for k in claves]
    assert seed._seed_desactivar("http://127.0.0.1:8027", "t", creadas) == [
        f"DESACTIVADA {k}: existente, no modificada" for k in seed.SEED_DESACTIVADAS]
    assert doble.posts() == []
    assert doble.arbol[str(seed.id_categoria("luz"))]["nombre"] == "Luz y potencia"  # el seed no corrige


def test_solo_se_dan_de_alta_las_que_faltan(seed, monkeypatch):
    claves = [c[0] for c in seed.SEED_CATEGORIAS]
    presentes = {"alimentacion", "hogar", "luz", "viajes_2025"}
    doble = _ApiDoble(seed, {str(seed.id_categoria(k)): _nodo(seed, k) for k in presentes})
    monkeypatch.setattr(seed, "_api", doble)
    lineas, creadas = seed._seed_categorias_api("http://127.0.0.1:8027", "t")
    faltan = [k for k in claves if k not in presentes]
    assert doble.posts() == ["/v1/categorias"] * len(faltan) and creadas == set(faltan)
    assert sum(1 for x in lineas if x.endswith("existente, no modificada")) == len(presentes)
    # viajes_2025 ya existia: no se desactiva aunque este habilitada (existencia, no estado).
    assert seed._seed_desactivar("http://127.0.0.1:8027", "t", creadas) == ["DESACTIVADA viajes_2025: existente, no modificada"]
    assert doble.arbol[str(seed.id_categoria("viajes_2025"))]["enabled"] is True


def test_base_vacia_crea_las_23_y_desactiva_las_marcadas(seed, monkeypatch):
    doble = _ApiDoble(seed, {})
    monkeypatch.setattr(seed, "_api", doble)
    lineas, creadas = seed._seed_categorias_api("http://127.0.0.1:8027", "t")
    assert len(creadas) == len(seed.SEED_CATEGORIAS) == 23
    assert seed._seed_desactivar("http://127.0.0.1:8027", "t", creadas) == ["DESACTIVADA viajes_2025: desactivada"]
    assert doble.arbol[str(seed.id_categoria("viajes_2025"))]["enabled"] is False


def test_rechazo_del_alta_aborta_sin_corregir(seed, monkeypatch):
    doble = _ApiDoble(seed, {}, rechazar={str(seed.id_categoria("cafe"))})
    monkeypatch.setattr(seed, "_api", doble)
    with pytest.raises(SystemExit) as e:
        seed._seed_categorias_api("http://127.0.0.1:8027", "t")
    assert "ABORTADO en cafe" in str(e.value)
