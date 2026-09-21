# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_002_p1b_manifest_s1.py
# Ruta: tests/migration/test_rv3_002_p1b_manifest_s1.py
# Descripcion: RV3 / P1b. Tests del hash semantico RV3_S1_SEMHASH_V1 con corpus
#              SINTETICO: invariancia frente a orden fisico de filas y columnas,
#              representacion numerica y bytes del XLSX; sensibilidad frente a
#              cualquier cambio de valor, tipo, clave o estructura; fallo cerrado
#              ante clave ausente o duplicada.
#
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "rv3_p1b_manifest_s1", RAIZ / "scripts" / "migration_v3" / "rv3_p1b_manifest_s1.py")
p1b = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p1b)


def _libro(tablas, titulo_extra=None):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, (cab, filas) in tablas.items():
        ws = wb.create_sheet(nombre)
        ws.append(cab)
        for f in filas:
            ws.append(f)
    if titulo_extra:
        wb.properties.title = titulo_extra
    return wb


def _base():
    return {
        "public.a": (["id", "nombre", "importe", "activo", "fecha"],
                     [[1, "X", 10.5, True, "2025-01-01"], [2, "Y", 0, False, None]]),
        "public.patrimonio_compra": (["patrimonio_id", "total"], [["P-1", 100]]),
        "public.vacia": (["id", "z"], []),
    }


def _hash(tablas, tmp_path=None, **kw):
    wb = _libro(tablas, **kw)
    if tmp_path is not None:
        ruta = tmp_path / "s.xlsx"
        wb.save(ruta)
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    return p1b.hash_semantico(p1b.estado_semantico(wb))


def test_estable_entre_ejecuciones():
    assert _hash(_base()) == _hash(_base())


def test_invariante_al_orden_fisico_de_filas():
    t = _base()
    t["public.a"] = (t["public.a"][0], list(reversed(t["public.a"][1])))
    assert _hash(t) == _hash(_base())


def test_invariante_al_orden_de_columnas_y_hojas():
    cab, filas = _base()["public.a"]
    orden = [4, 2, 0, 3, 1]
    t = dict(reversed(list(_base().items())))
    t["public.a"] = ([cab[i] for i in orden], [[f[i] for i in orden] for f in filas])
    assert _hash(t) == _hash(_base())


def test_invariante_a_representacion_numerica_y_bytes_xlsx(tmp_path):
    t = _base()
    t["public.a"] = (t["public.a"][0], [[1.0, "X", 10.50, True, "2025-01-01"], [2.0, "Y", 0.0, False, None]])
    assert _hash(t, tmp_path, titulo_extra="export distinto") == _hash(_base())


def test_null_y_cadena_vacia_son_el_mismo_token():
    t = _base()
    t["public.a"][1][1][4] = ""
    assert _hash(t) == _hash(_base())


@pytest.mark.parametrize("hoja,fila,col,nuevo", [
    ("public.a", 0, 2, 10.51),          # valor numerico
    ("public.a", 0, 1, "x"),            # texto (mayusculas importan)
    ("public.a", 0, 3, False),          # booleano
    ("public.a", 1, 4, "2025-01-02"),   # null -> valor
    ("public.a", 0, 2, "10.5"),         # tipo: numero -> texto
    ("public.a", 1, 2, None),           # 0 -> null (UNKNOWN != 0)
    ("public.patrimonio_compra", 0, 1, 101),
])
def test_cualquier_cambio_de_contenido_cambia_el_hash(hoja, fila, col, nuevo):
    t = _base()
    t[hoja][1][fila][col] = nuevo
    assert _hash(t) != _hash(_base())


def test_cambio_de_clave_cambia_el_hash():
    t = _base()
    t["public.a"][1][1][0] = 3
    assert _hash(t) != _hash(_base())


def test_alta_de_fila_y_de_campo_cambian_el_hash():
    t = _base()
    t["public.vacia"] = (["id", "z"], [[1, "q"]])
    assert _hash(t) != _hash(_base())
    t2 = _base()
    t2["public.vacia"] = (["id", "z", "nuevo"], [])
    assert _hash(t2) != _hash(_base())


def test_clave_duplicada_falla_cerrado():
    t = _base()
    t["public.a"][1].append([1, "Z", 1, True, None])
    with pytest.raises(p1b.ErrorClave):
        _hash(t)


def test_columna_clave_ausente_falla_cerrado():
    t = _base()
    t["public.patrimonio_compra"] = (["otra", "total"], [["P-1", 100]])
    with pytest.raises(p1b.ErrorClave):
        _hash(t)


@pytest.mark.parametrize("v,tok", [
    (None, ["null"]), ("", ["null"]), (True, ["bool", "true"]), (1, ["num", "1"]),
    (1.0, ["num", "1"]), (10.50, ["num", "10.5"]), (0.0, ["num", "0"]), (1e-7, ["num", "0.0000001"]),
    (100, ["num", "100"]), ("141", ["str", "141"]), (141, ["num", "141"]),
    (dt.datetime(2025, 1, 2, 3, 4, 5), ["ts", "2025-01-02T03:04:05"]),
])
def test_tokens(v, tok):
    assert p1b.token(v) == tok
