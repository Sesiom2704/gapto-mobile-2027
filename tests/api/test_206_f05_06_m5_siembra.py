# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_206_f05_06_m5_siembra.py
# Ruta: tests/api/test_206_f05_06_m5_siembra.py
# Descripcion: Siembra de previsiones de F05-06 M5 (scripts/dev/siembra_previsiones_m5.py;
#   D-M5-14; dictamen Q12): destino fuera de la lista -> aborta ANTES de conectar;
#   uuid5 deterministas e idempotencia (segunda ejecucion: 0 altas); solo por
#   servicio (las previsiones nacen ABIERTAS sin regla; el seguro con 40 €
#   cubiertos por OP-22 + prevision, ABIERTA); manifiesto sin credenciales; los
#   fixtures cumplen M5-RULE-01 (ninguna prevision de consumo generico).
# Version: 0.1.0 (F05-06 M5 Fase 3)
# ============================================================

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import uuid

import pytest
from psycopg import conninfo

import f05_06_m5_helpers as m
import vs01_api_helpers as h

RUTA = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev" / "siembra_previsiones_m5.py"


@pytest.fixture()
def siembra(monkeypatch):
    spec = importlib.util.spec_from_file_location("siembra_previsiones_m5", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    partes = conninfo.conninfo_to_dict(h.dsn())
    # La base de tests (desechable, loopback) se anade SOLO en el test a la lista cerrada.
    monkeypatch.setitem(mod.PERMITIDOS, partes["dbname"], {int(partes.get("port") or 5432)})
    return mod


@pytest.mark.parametrize("dsn", [
    "host=db.neon.example port=5432 dbname=gapto2027_dev user=x password=y",
    "host=127.0.0.1 port=5432 dbname=postgres user=postgres",
    "host=127.0.0.1 port=5434 dbname=gapto2027_cleanroom user=postgres",
    "postgresql://u@10.0.0.5:5434/gapto2027_dev",
])
def test_destino_no_permitido_aborta_antes_de_conectar(dsn, monkeypatch):
    spec = importlib.util.spec_from_file_location("siembra_previsiones_m5", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod.psycopg, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("conecto")))
    with pytest.raises(SystemExit) as e:
        mod.sembrar(dsn, uuid.uuid4())
    assert "no permitido" in str(e.value) and "password" not in str(e.value) and "y" != str(e.value)


def test_envdev_y_e2e_permitidos(siembra):
    assert siembra.exigir_destino("host=127.0.0.1 port=5434 dbname=gapto2027_dev user=gapto_runtime password=z") == {
        "host": "127.0.0.1", "port": 5434, "dbname": "gapto2027_dev"}
    assert siembra.exigir_destino("postgresql://postgres@127.0.0.1:5463/gapto2027_dev")["port"] == 5463


def test_siembra_idempotente_y_manifiesto(siembra, tmp_path):
    owner, actor, cli, cta, ahorro = m.entorno()
    hoy = dt.date(2026, 10, 10)
    primera = siembra.sembrar(h.dsn(), owner, rol_runtime="gapto_runtime", hoy=hoy)
    altas = [r for r in primera if r["alta"]]
    assert len([r for r in altas if r["fixture"].startswith("prevision.")]) == 7
    assert len([r for r in altas if r["fixture"].startswith("tercero.")]) == 4
    segunda = siembra.sembrar(h.dsn(), owner, rol_runtime="gapto_runtime", hoy=hoy)
    assert [r for r in segunda if r["alta"]] == []
    assert [r["uuid"] for r in segunda] == [r["uuid"] for r in primera]  # uuid5 deterministas
    # Manifiesto sin credenciales.
    texto = json.dumps(segunda)
    assert "password" not in texto and "postgres@" not in texto and "user" not in texto
    # Estado: siete ABIERTAS sin regla; el seguro con 40 cubiertos y sigue ABIERTA; nada RODANTE.
    filas = m.leer(owner, "SELECT concepto, estado, regla_version_id, importe_esperado FROM gapto.previsiones ORDER BY concepto")
    assert len(filas) == 7 and all(e == "ABIERTA" and r is None for _, e, r, _ in filas)
    seguro = next(uuid.UUID(r["uuid"]) for r in primera if r["fixture"] == "prevision.seguro")
    assert m.detalle(cli, seguro)["cubierto"] == "40.00" and m.detalle(cli, seguro)["queda"] == "80.00"
    agua = next(uuid.UUID(r["uuid"]) for r in primera if r["fixture"] == "prevision.agua")
    assert m.detalle(cli, agua)["importe_esperado"] is None
    # M5-RULE-01: ocurrencias concretas; ninguna de consumo generico.
    conceptos = {c for c, *_ in filas}
    assert not conceptos & {"Supermercado", "Ropa", "Ocio"}
    # En Inicio: luz y nomina vencidas, seguro parcial -> 3 en Requiere atencion.
    ini = m.inicio(cli)
    assert ini["requiere_atencion"]["n"] == 3
