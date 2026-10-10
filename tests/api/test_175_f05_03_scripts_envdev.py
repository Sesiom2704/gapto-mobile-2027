# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_175_f05_03_scripts_envdev.py
# Ruta: tests/api/test_175_f05_03_scripts_envdev.py
# Descripcion: Scripts versionados de datos de ENV-DEV (F05-03/F05-04 J2
#   §1.0; F05-D032 C1/C4, D-032.5). Se ejercita su LOGICA (`aplicar`) contra
#   la base desechable de tests con un owner sintetico; la CLI solo acepta el
#   DSN de ENV-DEV (`exigir_envdev`), lo que tambien se prueba sin conectar.
#   - capacidades: 1 cuenta sin capacidades -> APLICADO (las de su tipo,
#     auditoria CREAR por fila); repetir -> SIN_CAMBIOS; 2 cuentas -> STOP
#     sin escritura; capacidades previas distintas -> STOP.
#   - conversion: 2 preferencias sin tipo -> APLICADO (comando unico);
#     repetir -> SIN_CAMBIOS; 3 -> STOP sin escritura.
#   - DSN: Neon, otro puerto u otra base -> rechazado antes de conectar.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.0)
# ============================================================

from __future__ import annotations

import pathlib
import sys

import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "envdev"))
import comun_envdev as ce  # noqa: E402
import envdev_capacidades_cuenta as cap  # noqa: E402
import envdev_convertir_preferencias_sin_tipo as conv  # noqa: E402


def _capacidades(owner, cuenta):
    return sorted(f[0] for f in h.leer(owner, "SELECT capacidad_codigo FROM gapto.cuenta_capacidades "
                                              "WHERE cuenta_id=%s", (cuenta,)))


def test_capacidades_aplica_una_vez_y_audita():
    owner, actor, _ = ph.tenant()
    cid = h.crear_cuenta(owner, [(actor, 100)], capacidades=())
    r = fh.en_transaccion(owner, cap.aplicar)
    assert r["resultado"] == "APLICADO"
    esperadas = ["PAGAR_GASTO", "RECIBIR_INGRESO", "TRANSFERIR_ENTRADA", "TRANSFERIR_SALIDA"]
    assert _capacidades(owner, cid) == esperadas
    assert r["previo"][0]["capacidades"] == [] and r["posterior"][0]["capacidades"] == esperadas
    aud = h.leer(owner, "SELECT accion FROM gapto.auditoria WHERE tabla='cuenta_capacidades' AND motivo=%s",
                 (cap.MOTIVO,))
    assert [a[0] for a in aud] == ["CREAR"] * 4
    r2 = fh.en_transaccion(owner, cap.aplicar)
    assert r2["resultado"] == "SIN_CAMBIOS" and _capacidades(owner, cid) == esperadas


def test_capacidades_stop_con_dos_cuentas_o_previas_distintas():
    owner, actor, _ = ph.tenant()
    a = h.crear_cuenta(owner, [(actor, 100)], capacidades=())
    h.crear_cuenta(owner, [(actor, 100)], capacidades=())
    r = fh.en_transaccion(owner, cap.aplicar)
    assert r["resultado"] == "STOP" and _capacidades(owner, a) == []
    otro, otro_actor = ph.tenant()[:2]
    c = h.crear_cuenta(otro, [(otro_actor, 100)], capacidades=("PAGAR_GASTO",))
    r = fh.en_transaccion(otro, cap.aplicar)
    assert r["resultado"] == "STOP" and _capacidades(otro, c) == ["PAGAR_GASTO"]


def test_conversion_aplica_una_vez():
    owner, actor, _ = ph.tenant()
    a = ph.cuenta(owner, actor)
    p1 = ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=a)
    p2 = ph.insertar_sql(owner, tipo_hecho_id=None, categoria_id=ph.categoria(owner, "Super"), presupuestable=True)
    r = fh.en_transaccion(owner, conv.aplicar)
    assert r["resultado"] == "APLICADO" and r["convertidas"] == sorted([str(p1), str(p2)])
    assert {p["tipo"] for p in r["posterior"]} == {"GASTO"}
    r2 = fh.en_transaccion(owner, conv.aplicar)
    assert r2["resultado"] == "SIN_CAMBIOS"


def test_conversion_stop_si_el_numero_no_es_el_esperado():
    owner, actor, _ = ph.tenant()
    a = ph.cuenta(owner, actor)
    ids = [ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=a) for _ in range(3)]
    r = fh.en_transaccion(owner, conv.aplicar)
    assert r["resultado"] == "STOP"
    assert all(ph.fila(owner, i)["tipo_hecho_id"] is None for i in ids)


@pytest.mark.parametrize("dsn", [
    "host=ep-algo.eu-central-1.aws.neon.tech port=5432 dbname=gapto2027_dev user=x",
    "host=127.0.0.1 port=5466 dbname=gapto2027_dev user=postgres",
    "host=127.0.0.1 port=5434 dbname=gapto2027_cleanroom user=app_dev",
    "postgresql://postgres@127.0.0.1:5466/j2_ref",
])
def test_solo_el_dsn_de_envdev(dsn):
    with pytest.raises(ce.NoEsEnvdev):
        ce.exigir_envdev(dsn)
    ce.exigir_envdev(ce.DSN_ENVDEV)
