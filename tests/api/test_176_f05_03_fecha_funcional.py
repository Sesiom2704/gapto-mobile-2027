# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_176_f05_03_fecha_funcional.py
# Ruta: tests/api/test_176_f05_03_fecha_funcional.py
# Descripcion: Fecha funcional del owner (F05-03/F05-04 J2 §1.2; F05-D032 C6,
#   politica A+B). Reloj inyectado (create_app(reloj=...)); la base sigue en
#   UTC y la UdT de F04 no se toca.
#   - hoy_owner: 00:30 en Madrid (UTC aun en el dia anterior), cambio de hora
#     de octubre de 2026 (25-10 y 26-10), UTC+3 y UTC-5, zona no reconocida
#     -> Europe/Madrid.
#   - Registro: FECHA_FUTURA con el «hoy» del owner (no el de UTC ni el del
#     servidor); cambio de zona entre la carga y la confirmacion (manda la
#     zona al confirmar); un reintento de una intencion ya materializada no
#     se rechaza despues.
#   - Preferencias: `cuenta_disponible_hoy` y la validacion del writer usan
#     hoy_owner (regla de ledger en el limite del dia).
#   - Sin current_date en la capa F05 de preferencias.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.2)
# ============================================================

from __future__ import annotations

import datetime as dt
import pathlib
import uuid

import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

UTC = dt.timezone.utc
URL = "/v1/intenciones/gasto-pagado"


def reloj(iso: str):
    instante = dt.datetime.fromisoformat(iso).replace(tzinfo=UTC)
    return lambda: instante


def _zona(owner, nombre: str) -> None:
    h.como_owner(owner, "UPDATE gapto.usuarios SET timezone=%s WHERE id=%s", (nombre, owner))


def _hoy(owner, iso: str) -> dt.date:
    from app.comun.fecha_funcional import hoy_owner

    return fh.en_transaccion(owner, lambda s: hoy_owner(s, reloj(iso)))


@pytest.mark.parametrize("zona,instante,esperado", [
    ("Europe/Madrid", "2026-10-09T22:30:00", "2026-10-10"),  # 00:30 en Madrid; UTC sigue el 9
    ("Europe/Madrid", "2026-10-09T21:59:00", "2026-10-09"),
    ("Europe/Madrid", "2026-10-24T22:30:00", "2026-10-25"),  # 00:30 CEST del dia del cambio de hora
    ("Europe/Madrid", "2026-10-25T22:30:00", "2026-10-25"),  # 23:30 CET, ya sin horario de verano
    ("Europe/Madrid", "2026-10-25T23:30:00", "2026-10-26"),  # 00:30 CET del 26-10
    ("Europe/Istanbul", "2026-10-09T21:30:00", "2026-10-10"),  # UTC+3
    ("America/Bogota", "2026-10-10T04:30:00", "2026-10-09"),  # UTC-5
    ("Marte/Base_Alfa", "2026-10-09T22:30:00", "2026-10-10"),  # zona no reconocida -> Madrid
])
def test_hoy_owner(zona, instante, esperado):
    owner, _ = h.crear_tenant()
    _zona(owner, zona)
    assert _hoy(owner, instante) == dt.date.fromisoformat(esperado)


def test_el_reloj_debe_tener_zona():
    from app.comun.fecha_funcional import hoy_en, zona

    with pytest.raises(ValueError):
        hoy_en(zona(None), lambda: dt.datetime(2026, 10, 9, 22, 30))


@pytest.fixture()
def t():
    owner, actor = h.crear_tenant()
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    return owner, actor, cuenta


def test_fecha_del_owner_admitida_aunque_utc_siga_en_el_dia_anterior(t):
    owner, _, cuenta = t
    cli = h.cliente(owner, reloj=reloj("2026-10-09T22:30:00"))  # 00:30 del 10 en Madrid
    r = cli.post(URL, json=h.intencion(cuenta, fecha_hecho="2026-10-10"), headers=h.AUTH)
    assert r.status_code == 200, r.text
    r = cli.post(URL, json=h.intencion(cuenta, fecha_hecho="2026-10-11"), headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "FECHA_FUTURA" and "fecha_hecho" in r.json()["mensaje"]


def test_fecha_futura_segun_la_zona_del_owner(t):
    owner, _, cuenta = t
    _zona(owner, "America/Bogota")  # mismo instante: en Bogota aun es el 9
    cli = h.cliente(owner, reloj=reloj("2026-10-09T22:30:00"))
    cuerpo = h.intencion(cuenta, fecha_hecho="2026-10-10")
    r = cli.post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "FECHA_FUTURA"
    assert h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s",
                  (uuid.UUID(cuerpo["intencion_id"]),))[0][0] == 0


def test_cambio_de_zona_entre_la_carga_y_la_confirmacion(t):
    """Manda la zona vigente al CONFIRMAR; un reintento de una intencion ya
    materializada no se rechaza despues del cambio."""
    owner, _, cuenta = t
    cli = h.cliente(owner, reloj=reloj("2026-10-09T22:30:00"))
    registrada = h.intencion(cuenta, fecha_hecho="2026-10-10")
    assert cli.post(URL, json=registrada, headers=h.AUTH).status_code == 200  # en Madrid es el 10
    cargada = h.intencion(cuenta, fecha_hecho="2026-10-10")  # cargada con la zona de Madrid
    _zona(owner, "America/Bogota")  # cambia antes de confirmar
    r = cli.post(URL, json=cargada, headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "FECHA_FUTURA"
    r = cli.post(URL, json=registrada, headers=h.AUTH)  # reintento de la ya materializada
    assert r.status_code == 200 and r.json()["idempotente"] is True


def test_preferencias_evaluan_la_cuenta_con_hoy_owner():
    """Regla de ledger en el limite del dia: una cuenta cuyo ledger empieza
    «hoy» en Madrid esta disponible aunque en UTC aun sea ayer; con la zona
    UTC no lo esta."""
    owner, actor, _ = ph.tenant()
    cuenta = ph.cuenta(owner, actor)
    h.como_owner(owner, "UPDATE gapto.cuentas SET saldo_apertura=0, fecha_inicio_ledger=%s WHERE id=%s",
                 (dt.date(2026, 10, 10), cuenta))
    cli = h.cliente(owner, reloj=reloj("2026-10-09T22:30:00"))
    pid, r = ph.alta(cli, cuenta_default_id=cuenta)
    assert r.status_code == 200, r.text
    assert cli.get(ph.BASE, headers=h.AUTH).json()["preferencias"][0]["cuenta_disponible_hoy"] is True
    _zona(owner, "UTC")
    assert cli.get(ph.BASE, headers=h.AUTH).json()["preferencias"][0]["cuenta_disponible_hoy"] is False
    _, r = ph.alta(cli, presupuestable_default=True, cuenta_default_id=cuenta,
                   categoria_id=ph.categoria(owner, "Super"))
    assert r.status_code == 409 and r.json()["codigo"] == "PREFERENCIA_CUENTA_NO_ELEGIBLE"


def test_sin_current_date_en_la_capa_f05_de_preferencias():
    raiz = pathlib.Path(__file__).resolve().parents[2] / "backend" / "app" / "preferencias"
    for p in sorted(raiz.rglob("*.py")):
        codigo = "\n".join(linea for linea in p.read_text(encoding="utf-8").splitlines()
                           if not linea.lstrip().startswith("#"))
        assert "current_date" not in codigo, p.name
