# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_184_f05_05_periodos.py
# Ruta: tests/api/test_184_f05_05_periodos.py
# Descripcion: Helpers de periodo de la fecha funcional (F05-05 K2 §1.1;
#   F05 §49.4 A11, §49.5 R7; caso 19 de §49.9).
#   - limites_mes(fecha) -> [inicio, fin): dia 1, ultimo dia, diciembre,
#     febrero bisiesto.
#   - ventana(fecha, dias) -> (fecha - dias, fecha]: limites exclusivo e
#     inclusivo; dias < 1 rechazado.
#   - mes_actual_owner(sesion, reloj): 00:30 en Madrid (UTC aun en el mes
#     anterior), cambio de hora del 25-10-2026, UTC+3 y UTC-5, primer y
#     ultimo dia del mes.
#   - No regresion de gasto_mes tras retirar `rango_mes`: la formula retirada
#     se conserva aqui como oraculo y se compara mes a mes; gasto_mes sobre
#     hechos del dia 1 y del ultimo dia da el mismo resultado.
# Version: 0.1.0 (F05-05 K2 §1.1)
# ============================================================

from __future__ import annotations

import datetime as dt

import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h

UTC = dt.timezone.utc


def reloj(iso: str):
    instante = dt.datetime.fromisoformat(iso).replace(tzinfo=UTC)
    return lambda: instante


def _rango_mes_retirado(mes: str) -> tuple[dt.date, dt.date]:
    """Oraculo: formula de `lecturas_vs01.rango_mes` v0.4.0, retirada en v0.5.0."""
    anio, m = (int(p) for p in mes.split("-"))
    return dt.date(anio, m, 1), dt.date(anio + (m == 12), 1 if m == 12 else m + 1, 1)


@pytest.mark.parametrize("fecha,esperado", [
    ("2026-10-01", ("2026-10-01", "2026-11-01")),  # dia 1
    ("2026-10-31", ("2026-10-01", "2026-11-01")),  # ultimo dia
    ("2026-12-15", ("2026-12-01", "2027-01-01")),  # diciembre
    ("2028-02-29", ("2028-02-01", "2028-03-01")),  # febrero bisiesto
    ("2026-01-01", ("2026-01-01", "2026-02-01")),
])
def test_limites_mes(fecha, esperado):
    from app.comun.fecha_funcional import limites_mes

    assert limites_mes(dt.date.fromisoformat(fecha)) == tuple(dt.date.fromisoformat(x) for x in esperado)


def test_limites_mes_coincide_con_la_formula_retirada_en_todos_los_meses():
    from app.comun.fecha_funcional import limites_mes

    for anio in range(2020, 2031):
        for m in range(1, 13):
            mes = f"{anio:04d}-{m:02d}"
            assert limites_mes(dt.date(anio, m, 1)) == _rango_mes_retirado(mes), mes
            assert limites_mes(dt.date(anio, m, 28)) == _rango_mes_retirado(mes), mes


def test_ventana_semiabierta():
    from app.comun.fecha_funcional import ventana

    desde, hasta = ventana(dt.date(2026, 10, 10), 365)
    assert (desde, hasta) == (dt.date(2025, 10, 10), dt.date(2026, 10, 10))
    dentro = [d for d in (dt.date(2025, 10, 10), dt.date(2025, 10, 11), dt.date(2026, 10, 10), dt.date(2026, 10, 11))
              if desde < d <= hasta]
    assert dentro == [dt.date(2025, 10, 11), dt.date(2026, 10, 10)]  # excluye f-365 y el futuro
    assert ventana(dt.date(2026, 3, 1), 1) == (dt.date(2026, 2, 28), dt.date(2026, 3, 1))
    with pytest.raises(ValueError):
        ventana(dt.date(2026, 10, 10), 0)


@pytest.mark.parametrize("zona,instante,esperado", [
    ("Europe/Madrid", "2026-09-30T22:30:00", ("2026-10-01", "2026-11-01")),  # 00:30 del 1-10 en Madrid; UTC aun en septiembre
    ("Europe/Madrid", "2026-09-30T21:59:00", ("2026-09-01", "2026-10-01")),
    ("Europe/Madrid", "2026-10-24T22:30:00", ("2026-10-01", "2026-11-01")),  # 00:30 CEST del dia del cambio de hora
    ("Europe/Madrid", "2026-10-31T22:59:00", ("2026-10-01", "2026-11-01")),  # 23:59 CET del ultimo dia
    ("Europe/Madrid", "2026-10-31T23:00:00", ("2026-11-01", "2026-12-01")),  # 00:00 CET del 1-11
    ("Europe/Istanbul", "2026-10-31T21:30:00", ("2026-11-01", "2026-12-01")),  # UTC+3
    ("America/Bogota", "2026-11-01T04:30:00", ("2026-10-01", "2026-11-01")),  # UTC-5: aun 31-10
])
def test_mes_actual_owner(zona, instante, esperado):
    from app.comun.fecha_funcional import mes_actual_owner

    owner, _ = h.crear_tenant()
    h.como_owner(owner, "UPDATE gapto.usuarios SET timezone=%s WHERE id=%s", (zona, owner))
    obtenido = fh.en_transaccion(owner, lambda s: mes_actual_owner(s, reloj(instante)))
    assert obtenido == tuple(dt.date.fromisoformat(x) for x in esperado)


def test_gasto_mes_sin_regresion_en_los_limites_del_mes():
    """Hechos del ultimo dia del mes anterior, dia 1, ultimo dia y dia 1 del
    siguiente: solo cuentan los del mes, igual que con la formula retirada."""
    owner, actor = h.crear_tenant()
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    cli = h.cliente(owner, reloj=reloj("2026-12-15T12:00:00"))
    for fecha, importe in (("2026-09-30", "1.00"), ("2026-10-01", "10.00"), ("2026-10-31", "20.00"), ("2026-11-01", "100.00")):
        r = cli.post("/v1/intenciones/gasto-pagado", json=h.intencion(cuenta, fecha_hecho=fecha, importe=importe,
                     financiacion=h.propuesta_self_100(importe)), headers=h.AUTH)
        assert r.status_code == 200, r.text
    r = cli.get("/v1/vs01/gasto-mes", params={"mes": "2026-10"}, headers=h.AUTH)
    assert r.status_code == 200 and r.json()["gasto_atribuible"] == "30.00", r.text
    assert cli.get("/v1/vs01/gasto-mes", params={"mes": "2026-11"}, headers=h.AUTH).json()["gasto_atribuible"] == "100.00"
    assert cli.get("/v1/vs01/gasto-mes", params={"mes": "2026-09"}, headers=h.AUTH).json()["gasto_atribuible"] == "1.00"
