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
# Version: 0.2.0 (MANT-M5-ARNESES, AJ-M5-CIERRE-06): siembra entre dias. El mismo
#   dia da 0 altas; otro dia crea un juego nuevo de 7 previsiones (con su pago
#   parcial) sin tocar el anterior (estado y row_version iguales) y sin duplicar
#   terceros; identidades distintas por dia.
# Version: 0.3.0 (F05-07/GATE adenda 2, MANT-PRE-GATE test_206; F05-D050 §64.3,
#   DEU-T206-LOOPBACK, AJ-06): `skipif` contextual en los dos tests que siembran
#   sobre la base de la ejecucion: si el destino efectivo (host/hostaddr del DSN
#   de GAPTO_TEST_DATABASE_URL, o PGHOST si el DSN no trae host) no es loopback,
#   se omiten con razon visible ANTES de conectar (la siembra solo admite
#   loopback). SKIP != PASS. `test_destino_no_permitido_aborta_antes_de_conectar`
#   y `test_envdev_y_e2e_permitidos` se ejecutan siempre. `exigir_destino`,
#   LOOPBACK y PERMITIDOS del script no cambian. Nuevo test de la decision.
# ============================================================

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import pathlib
import uuid

import psycopg
import pytest
from psycopg import conninfo

import f05_06_m5_helpers as m
import vs01_api_helpers as h

RUTA = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev" / "siembra_previsiones_m5.py"


def _cargar_script():
    spec = importlib.util.spec_from_file_location("siembra_previsiones_m5", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def motivo_destino_no_loopback(dsn: str | None) -> str | None:
    """DEU-T206-LOOPBACK (AJ-06). Decide SIN conectar si el destino efectivo de la
    ejecucion queda fuera de LOOPBACK del script (el mismo criterio de host que
    `exigir_destino`, mas `hostaddr`, que libpq usa en lugar de resolver `host`).
    Devuelve la razon del SKIP o None. Sin DSN o con DSN ilegible no se omite: el
    test falla con su error de siempre (SKIP != PASS no puede ocultar un entorno
    roto)."""
    if not dsn:
        return None
    try:
        partes = conninfo.conninfo_to_dict(dsn)
    except psycopg.ProgrammingError:
        return None
    loopback = _cargar_script().LOOPBACK
    host = partes.get("host") or os.getenv("PGHOST", "")
    hostaddr = partes.get("hostaddr") or ""
    if host in loopback and (not hostaddr or hostaddr in loopback):
        return None
    return (f"destino de la ejecucion no loopback (host={host or '?'}"
            f"{', hostaddr=' + hostaddr if hostaddr else ''}): la siembra solo admite loopback "
            "(exigir_destino); se omite antes de conectar (DEU-T206-LOOPBACK). SKIP != PASS")


_MOTIVO = motivo_destino_no_loopback(os.getenv("GAPTO_TEST_DATABASE_URL"))
solo_loopback = pytest.mark.skipif(_MOTIVO is not None, reason=_MOTIVO or "destino loopback")


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
    mod = _cargar_script()
    monkeypatch.setattr(mod.psycopg, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("conecto")))
    with pytest.raises(SystemExit) as e:
        mod.sembrar(dsn, uuid.uuid4())
    assert "no permitido" in str(e.value) and "password" not in str(e.value) and "y" != str(e.value)


def test_envdev_y_e2e_permitidos(siembra):
    assert siembra.exigir_destino("host=127.0.0.1 port=5434 dbname=gapto2027_dev user=gapto_runtime password=z") == {
        "host": "127.0.0.1", "port": 5434, "dbname": "gapto2027_dev"}
    assert siembra.exigir_destino("postgresql://postgres@127.0.0.1:5463/gapto2027_dev")["port"] == 5463


@pytest.mark.parametrize(("dsn", "omite"), [
    ("postgresql://postgres@127.0.0.1:5463/ct_x", False),
    ("host=localhost port=5463 dbname=ct_x user=postgres", False),
    ("host=::1 port=5463 dbname=ct_x", False),
    ("postgresql://u@db.neon.example:5432/gapto2027_cleanroom", True),
    ("host=10.0.0.5 port=5463 dbname=ct_x", True),
    ("host=localhost hostaddr=10.0.0.5 port=5463 dbname=ct_x", True),
    ("host=127.0.0.1,db.neon.example port=5463 dbname=ct_x", True),
    (None, False),
])
def test_skip_contextual_decide_por_el_destino_sin_conectar(dsn, omite, monkeypatch):
    """La decision del skipif contextual: sin conectar (psycopg.connect prohibido),
    loopback -> se ejecuta; cualquier otro destino -> SKIP con razon visible y sin
    credenciales."""
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("conecto")))
    motivo = motivo_destino_no_loopback(dsn)
    assert (motivo is not None) == omite, motivo
    if motivo:
        assert "no loopback" in motivo and "SKIP != PASS" in motivo and "password" not in motivo


@solo_loopback
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


@solo_loopback
def test_siembra_entre_dias_juego_nuevo_sin_tocar_el_anterior(siembra):
    owner, actor, cli, cta, ahorro = m.entorno()
    d1, d2 = dt.date(2026, 10, 21), dt.date(2026, 10, 22)
    primera = siembra.sembrar(h.dsn(), owner, rol_runtime="gapto_runtime", hoy=d1)
    antes = m.leer(owner, "SELECT id, estado, row_version, fecha_esperada_hasta FROM gapto.previsiones ORDER BY id")
    assert len(antes) == 7
    otro = siembra.sembrar(h.dsn(), owner, rol_runtime="gapto_runtime", hoy=d2)
    altas = [r for r in otro if r["alta"]]
    # Siete previsiones nuevas y el pago parcial del seguro; ningun tercero nuevo.
    assert len([r for r in altas if r["fixture"].startswith("prevision.")]) == 7
    assert [r for r in altas if r["fixture"].startswith("tercero.")] == []
    assert [r["fixture"] for r in altas if r["fixture"].startswith("hecho.")] == ["hecho.seguro.cubierto"]
    ids1 = {r["uuid"] for r in primera if not r["fixture"].startswith("tercero.")}
    ids2 = {r["uuid"] for r in otro if not r["fixture"].startswith("tercero.")}
    assert ids1.isdisjoint(ids2)
    assert {r["uuid"] for r in primera if r["fixture"].startswith("tercero.")} == {r["uuid"] for r in otro if r["fixture"].startswith("tercero.")}
    # El juego anterior no cambia (estado, row_version y fechas).
    despues = m.leer(owner, "SELECT id, estado, row_version, fecha_esperada_hasta FROM gapto.previsiones ORDER BY id")
    assert len(despues) == 14
    assert [x for x in despues if x[0] in {uuid.UUID(i) for i in ids1}] == antes
    # Fechas relativas a cada dia: la luz del dia 2 vence un dia despues que la del dia 1.
    hasta = dict(m.leer(owner, "SELECT id, fecha_esperada_hasta FROM gapto.previsiones WHERE concepto = 'Electricidad' ORDER BY fecha_esperada_hasta"))
    assert sorted(hasta.values()) == [d1 - dt.timedelta(days=5), d2 - dt.timedelta(days=5)]
    # Repetir el dia 2: 0 altas.
    assert [r for r in siembra.sembrar(h.dsn(), owner, rol_runtime="gapto_runtime", hoy=d2) if r["alta"]] == []
