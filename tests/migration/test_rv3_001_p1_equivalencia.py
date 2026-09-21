# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_001_p1_equivalencia.py
# Ruta: tests/migration/test_rv3_001_p1_equivalencia.py
# Descripcion: RV3 / P1. Tests del comparador Sheet V3 <-> snapshot RUN06 con
#              corpus SINTETICO construido en memoria (sin datos V3 reales).
#              Cubre la regla 141, la canonicalizacion de claves numericas,
#              equivalencias de representacion, secreto redactado, altas,
#              bajas, modificaciones, identidad de RUN06 y la prohibicion de
#              escribir evidencia dentro del repositorio.
#
#   Cada test que protege una garantia incluye su discriminante: el caso
#   defectuoso debe producir STOP_S3 / DISTINTO (WM §12C.2).
#
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "rv3_p1_equivalencia", RAIZ / "scripts" / "migration_v3" / "rv3_p1_equivalencia.py")
p1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p1)


# ---------------------------------------------------------------- corpus sintetico
def _snapshot_rows():
    # contenedor, clave, datos_origen (JSON tipado como en RUN06)
    return [
        ("public.cuentas", 1, {"id": 1, "nombre": "CTA-SINT-A", "saldo": 100.5, "fecha": "2025-01-02",
                               "activo": True, "baja": 141}),
        ("public.cuentas", 2, {"id": 2, "nombre": "CTA-SINT-B", "saldo": 0, "fecha": "2025-02-03",
                               "activo": False, "baja": 141}),
        ("public.cuotas", "C-1", {"id": "C-1", "num_cuota": 141, "importe": 10}),
        ("public.users", 1, {"id": 1, "email": "sintetico@example.invalid", "password": "[REDACTADO]"}),
    ]


def _sheet_tables():
    return {
        "public.cuentas": (["id", "nombre", "saldo", "fecha", "activo", "baja"], [
            [1.0, "CTA-SINT-A", 100.5, dt.datetime(2025, 1, 2), True, None],
            [2.0, "CTA-SINT-B", 0, dt.datetime(2025, 2, 3), False, None],
        ]),
        "public.cuotas": (["id", "num_cuota", "importe"], [["C-1", 141, 10]]),
        "public.users": (["id", "email", "password"], [[1, "sintetico@example.invalid", "otro-hash-sintetico"]]),
        "public.vacia": (["id", "x"], []),
    }


def _escribir_run06(ruta: Path, filas):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = p1.HOJA_SNAPSHOT
    ws.append(["id", "fuente_importacion_id", "contenedor_origen", "clave_origen", "numero_fila_origen",
               "datos_origen", "datos_origen_texto", "sha256_registro", "created_at"])
    for i, (cont, clave, datos) in enumerate(filas, 1):
        ws.append([f"r{i}", "f1", cont, clave, i, json.dumps(datos), None, None, None])
    wb.save(ruta)


def _escribir_sheet(ruta: Path, tablas):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, (cab, filas) in tablas.items():
        ws = wb.create_sheet(nombre)
        ws.append(cab)
        for f in filas:
            ws.append(f)
    wb.save(ruta)


def _ejecutar(tmp_path, snap_rows=None, tablas=None, monkeypatch=None):
    run06 = tmp_path / "run06.xlsx"
    sheet = tmp_path / "sheet.xlsx"
    _escribir_run06(run06, snap_rows if snap_rows is not None else _snapshot_rows())
    _escribir_sheet(sheet, tablas if tablas is not None else _sheet_tables())
    sha = hashlib.sha256(run06.read_bytes()).hexdigest()
    monkeypatch.setattr(p1, "ESPERADO", {"hojas": len(tablas or _sheet_tables()), "campos": sum(
        len(c) for c, _ in (tablas or _sheet_tables()).values()), "filas_snapshot": len(
        snap_rows if snap_rows is not None else _snapshot_rows()), "contenedores": len({r[0] for r in (
            snap_rows if snap_rows is not None else _snapshot_rows())})})
    monkeypatch.setattr(p1, "SHA256_RUN06", sha)
    salida = tmp_path / "evidencia"
    rc = p1.main(["--sheet", str(sheet), "--run06", str(run06), "--salida", str(salida), "--sha-run06", sha])
    informe = json.loads(next(salida.glob("rv3_p1_equivalencia_*.json")).read_text(encoding="utf-8")) \
        if salida.exists() and any(salida.glob("*.json")) else None
    return rc, informe


# ---------------------------------------------------------------- unidades
@pytest.mark.parametrize("entrada,esperado", [(9, "9"), (9.0, "9"), ("9", "9"), ("9.0", "9"),
                                               ("GASTO-X1", "GASTO-X1"), (9.5, "9.5"), ("007", "7")])
def test_canon_clave(entrada, esperado):
    assert p1.canon_clave(entrada) == esperado


@pytest.mark.parametrize("snap,sheet,cat", [
    (141, None, p1.EQUIV_141),
    ("141", "", p1.EQUIV_141),
    (141, 141, p1.IGUAL),                 # 141 real (p.ej. cuota numero 141) se conserva
    (141, "2026-01-01", p1.DISTINTO),     # un desconocido que pasa a valor es delta
    (None, 141, p1.DISTINTO),             # discriminante: la regla 141 NO es simetrica
    (0, None, p1.DISTINTO),               # UNKNOWN != 0 en ningun sentido
    (None, 0, p1.DISTINTO),
    (100.5, 100.5, p1.IGUAL),
    (1, 1.0, p1.EQUIV_REPR),
    ("2025-01-02", dt.datetime(2025, 1, 2), p1.EQUIV_REPR),
    ("2025-01-02", dt.datetime(2025, 1, 3), p1.DISTINTO),
    (True, True, p1.IGUAL),
    (True, False, p1.DISTINTO),
    (None, "", p1.EQUIV_NULO),
    ("None", "None", p1.IGUAL),
    ("None", None, p1.DISTINTO),          # literal None no se funde con blanco sin regla
])
def test_clasificar_celda(snap, sheet, cat):
    assert p1.clasificar_celda(snap, sheet) == cat


# ---------------------------------------------------------------- extremo a extremo
def test_corpus_equivalente(tmp_path, monkeypatch):
    rc, inf = _ejecutar(tmp_path, monkeypatch=monkeypatch)
    assert rc == 0, inf["deltas"]
    assert inf["veredicto"] == "EQUIVALENTE"
    assert inf["celdas"].get(p1.EQUIV_141) == 2
    assert inf["snapshot"]["literales_141"] == 3


def test_secreto_redactado_no_bloquea_ni_se_expone(tmp_path, monkeypatch):
    rc, inf = _ejecutar(tmp_path, monkeypatch=monkeypatch)
    assert rc == 0
    texto = json.dumps(inf)
    assert "otro-hash-sintetico" not in texto and "[REDACTADO]" not in texto
    assert any(d["tipo"] == "EQUIVALENTE_CON_SECRETO_REDACTADO" for d in inf["deltas"])


def test_informe_no_contiene_valores(tmp_path, monkeypatch):
    tablas = _sheet_tables()
    tablas["public.cuentas"][1][0][2] = 999.25
    rc, inf = _ejecutar(tmp_path, tablas=tablas, monkeypatch=monkeypatch)
    assert rc == 3
    texto = json.dumps(inf)
    assert "999.25" not in texto and "CTA-SINT-A" not in texto


def test_modificacion_es_stop_s3(tmp_path, monkeypatch):
    tablas = _sheet_tables()
    tablas["public.cuentas"][1][0][2] = 999.25
    rc, inf = _ejecutar(tmp_path, tablas=tablas, monkeypatch=monkeypatch)
    assert rc == 3 and inf["veredicto"] == "STOP_S3"
    assert inf["filas"][p1.FILA_MODIFICADA] == 1
    assert inf["columnas_modificadas_por_contenedor"] == {"public.cuentas": {"saldo": 1}}


def test_alta_posterior_es_stop_s3(tmp_path, monkeypatch):
    tablas = _sheet_tables()
    tablas["public.cuentas"][1].append([3, "CTA-SINT-C", 1, dt.datetime(2025, 3, 1), True, None])
    rc, inf = _ejecutar(tmp_path, tablas=tablas, monkeypatch=monkeypatch)
    assert rc == 3 and inf["filas"][p1.FILA_SOLO_SHEET] == 1


def test_baja_posterior_es_stop_s3(tmp_path, monkeypatch):
    tablas = _sheet_tables()
    tablas["public.cuentas"][1].pop()
    rc, inf = _ejecutar(tmp_path, tablas=tablas, monkeypatch=monkeypatch)
    assert rc == 3 and inf["filas"][p1.FILA_SOLO_SNAPSHOT] == 1


def test_filas_en_tabla_sin_snapshot_es_stop_s3(tmp_path, monkeypatch):
    tablas = _sheet_tables()
    tablas["public.vacia"][1].append([1, "x"])
    rc, inf = _ejecutar(tmp_path, tablas=tablas, monkeypatch=monkeypatch)
    assert rc == 3 and inf["inventario_sheet"]["hojas_con_filas_sin_snapshot"] == ["public.vacia"]


def test_desconocido_convertido_en_valor_es_stop_s3(tmp_path, monkeypatch):
    tablas = _sheet_tables()
    tablas["public.cuentas"][1][0][5] = dt.datetime(2026, 1, 1)
    rc, inf = _ejecutar(tmp_path, tablas=tablas, monkeypatch=monkeypatch)
    assert rc == 3


def test_run06_con_sha_no_canonico_es_stop(tmp_path, monkeypatch):
    run06 = tmp_path / "run06.xlsx"
    sheet = tmp_path / "sheet.xlsx"
    _escribir_run06(run06, _snapshot_rows())
    _escribir_sheet(sheet, _sheet_tables())
    rc = p1.main(["--sheet", str(sheet), "--run06", str(run06), "--salida", str(tmp_path / "e"),
                  "--sha-run06", "0" * 64])
    assert rc == 3


def test_salida_dentro_del_repo_se_rechaza(tmp_path):
    rc = p1.main(["--sheet", str(tmp_path / "a.xlsx"), "--run06", str(tmp_path / "b.xlsx"),
                  "--salida", str(RAIZ / "data" / "migration_v3" / "reports")])
    assert rc == 2
