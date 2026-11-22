# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_297_f06_01h_f05_q3_listas.py
# Ruta: tests/api/test_297_f06_01h_f05_q3_listas.py
# Descripcion: Reapertura nominal y acotada de F05 Q3-Hd (literal LITERAL_REAPERTURA_F05_Q3_HD_v1.1, parte (a);
#   mandato T3-F06 bloque 2 F06-01H v1.1 §11.5). Oraculos de servidor por HTTP como gapto_runtime con RLS:
#   - O-Q3-1: GET /v1/inicio/previsiones y GET /v1/previsiones/pendientes con previsiones de cuota ABIERTAS
#     (vencidas y proxima) y ordinarias del mismo importe: la fila de la cuota lleva codigo = PREVISION_DE_CUOTA;
#     la ordinaria NO lleva la clave (claves y orden de claves de FilaPrevision en c5e4ff8, y JSON byte a byte
#     igual al de la composicion de c5e4ff8, emulada anulando la marca: Q3-S2 es la unica diferencia).
#   - O-Q3-2: resueltas_mes con la prevision REALIZADA de una cuota pagada: marca presente; n, por_pagar,
#     por_cobrar, secciones y orden identicos a los de la composicion de c5e4ff8 para el mismo fixture.
#   Mutantes que matan: MQ3-S1 (sin marca) y MQ3-S2 (marca en todas las filas o codigo: null en las ordinarias).
#   Discriminacion: en el HEAD de inicio (superficies identicas en c5e4ff8 y 7eed34c) falla por falta de marca.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H; literal F05 Q3-Hd v1.1, paso 9)
# Version: 0.2.0 (F06 T4 · D-C7-10, mandato 7041970a…; STOP STOP_F06-T4_DC710_TEST297_CLAVES_v1.0, opcion A de
#   Moises): solo la FORMA de O-Q3-1: la fila de cuota de Inicio y Pendientes lleva `codigo` y despues el bloque
#   `cuota`; `_quitar_marca` quita tambien `cuota`. Filas ordinarias, recuentos, orden, resueltas y el caso
#   «sin cuotas» (byte a byte) sin cambios.
# ============================================================

from __future__ import annotations

import json

import pytest

import f05_06_m5_helpers as m
import vs01_api_helpers as h
from test_293_f06_01h_pago_cuota import LabPago

#: Claves (y su orden) de la fila de lista en c5e4ff8 (dto_prevision.FilaPrevision).
CLAVES_C5E4FF8 = ["id", "row_version", "estado", "tipo", "naturaleza", "concepto", "tercero", "categoria",
                  "fecha_desde", "fecha_hasta", "moneda", "importe_esperado", "cubierto", "queda", "desviacion",
                  "con_realidad", "pagos", "vencida", "cuenta_salida", "cuenta_entrada", "origen", "presupuestable"]
CLAVES_RESUELTA_C5E4FF8 = CLAVES_C5E4FF8 + ["estado_derivado", "resuelta_el", "resuelta_por"]
MARCA = "PREVISION_DE_CUOTA"


class Lab297(LabPago):
    """Hipoteca de 12 cuotas (primera 2026-04-20; reloj 2026-10-10: 6 vencidas, la 7.ª proxima) y dos
    previsiones ordinarias GASTO del mismo importe que la cuota: una vencida y una proxima (fechas propias)."""

    def bloque(self, **cambios) -> dict:
        cambios.setdefault("numero_cuotas", 12)
        return super().bloque(**cambios)

    def __init__(self):
        super().__init__()
        self.cuotas = {n: p for n, p in self.sql(
            "SELECT numero_cuota, prevision_id FROM gapto.financiacion_cuotas WHERE financiacion_entidad_id = %s "
            "ORDER BY numero_cuota", (self.f,))}
        importe = self.sql("SELECT importe_esperado::numeric(18,2)::text FROM gapto.previsiones WHERE id = %s",
                           (self.cuotas[1],))[0][0]
        self.importe = importe
        self.ord_vencida = m.prevision(self.owner, "Seguro hogar", desde="2026-05-05", importe=importe)
        self.ord_proxima = m.prevision(self.owner, "Comunidad", desde="2026-10-25", importe=importe)


@pytest.fixture()
def lab():
    return Lab297()


def _get(cli, ruta: str) -> dict:
    r = cli.get(ruta, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _sin_marca(monkeypatch, fn):
    """Composicion de c5e4ff8: Q3-S2 anulada (la marca es la unica diferencia de las superficies)."""
    import app.previsiones.lecturas as lect

    with monkeypatch.context() as mp:
        mp.setattr(lect, "_marcar_cuotas", lambda sesion, filas: filas, raising=False)
        return fn()


def _filas(cuerpo) -> list[dict]:
    """Todas las filas de las listas de una respuesta (inicio o pendientes), en orden."""
    if "requiere_atencion" in cuerpo:
        return cuerpo["requiere_atencion"]["primeras"] + cuerpo["proximos"]
    s = cuerpo["secciones"]
    return s["vencidas"] + s["con_pago_parcial"] + s["sin_fecha"] + cuerpo["resueltas_mes"]["filas"]


def _quitar_marca(cuerpo):
    """Copia profunda sin la clave codigo ni el bloque cuota (D-C7-10; solo en las filas de cuota)."""
    if isinstance(cuerpo, dict):
        return {k: _quitar_marca(v) for k, v in cuerpo.items() if k not in ("codigo", "cuota")}
    if isinstance(cuerpo, list):
        return [_quitar_marca(v) for v in cuerpo]
    return cuerpo


def _claves(f: dict) -> list[str]:
    return CLAVES_RESUELTA_C5E4FF8 if "resuelta_el" in f else CLAVES_C5E4FF8


def _marcas(lab, final: dict):
    cuotas = {str(p) for p in lab.cuotas.values()}
    filas = _filas(final)
    assert filas, final
    for f in filas:
        if f["id"] in cuotas:
            # la marca solo en la fila de una cuota, con su valor exacto; despues, en Inicio y Pendientes (no en las
            # resueltas), el bloque `cuota` de D-C7-10 como ultima clave (decision de Moises, opcion A del STOP)
            extra = ["codigo"] if "resuelta_el" in f else ["codigo", "cuota"]
            assert f.get("codigo") == MARCA and list(f) == _claves(f) + extra, f
        else:
            # la ordinaria: sin la clave (ni codigo: null) y con las claves de c5e4ff8 en su orden
            assert "codigo" not in f and list(f) == _claves(f), f


def _igual(final: dict, inicio: dict):
    # byte a byte: sin la marca, la respuesta es la de c5e4ff8 (orden, recuentos, filas y claves)
    assert json.dumps(_quitar_marca(final), sort_keys=False) == json.dumps(inicio, sort_keys=False)
    # y la composicion de c5e4ff8 no lleva ninguna marca
    assert "codigo" not in json.dumps(inicio)


# ================================================================== O-Q3-1
def test_o_q3_1_inicio_marca_solo_la_cuota(lab, monkeypatch):
    final = _get(lab.cli, "/v1/inicio/previsiones")
    _marcas(lab, final)
    inicio = _sin_marca(monkeypatch, lambda: _get(lab.cli, "/v1/inicio/previsiones"))
    _igual(final, inicio)
    ids = [f["id"] for f in _filas(final)]
    # vencidas de cuota y la ordinaria vencida en requiere_atencion; la proxima de cuota (7.ª, 2026-10-20) en proximos
    assert str(lab.cuotas[1]) in ids and str(lab.ord_vencida) in ids
    proximos = {f["id"]: f for f in final["proximos"]}
    assert proximos[str(lab.cuotas[7])]["codigo"] == MARCA and "codigo" not in proximos[str(lab.ord_proxima)]
    # mismo importe: la marca no sale del importe ni del tipo
    assert proximos[str(lab.cuotas[7])]["importe_esperado"] == proximos[str(lab.ord_proxima)]["importe_esperado"]


def test_o_q3_1_pendientes_marca_solo_la_cuota(lab, monkeypatch):
    final = _get(lab.cli, "/v1/previsiones/pendientes")
    _marcas(lab, final)
    inicio = _sin_marca(monkeypatch, lambda: _get(lab.cli, "/v1/previsiones/pendientes"))
    _igual(final, inicio)
    vencidas = {f["id"]: f for f in final["secciones"]["vencidas"]}
    assert {str(lab.cuotas[n]) for n in range(1, 7)} <= set(vencidas) and str(lab.ord_vencida) in vencidas
    assert all(vencidas[str(lab.cuotas[n])]["codigo"] == MARCA for n in range(1, 7))
    assert "codigo" not in vencidas[str(lab.ord_vencida)]
    # recuentos de c5e4ff8 (6 cuotas + 1 ordinaria vencidas, todo GASTO)
    assert final["n"] == inicio["n"] == 7
    assert final["por_pagar"] == inicio["por_pagar"] and final["por_cobrar"] == inicio["por_cobrar"]


# ================================================================== O-Q3-2
def test_o_q3_2_resueltas_mes_con_la_cuota_pagada(lab, monkeypatch):
    r = lab.pagar(1, lab.cuerpo())
    assert r.status_code == 200, r.text
    assert lab.sql("SELECT estado FROM gapto.previsiones WHERE id = %s", (lab.cuotas[1],))[0][0] == "REALIZADA"
    # «Resueltas este mes» se mide con la fecha de la auditoria (hora real del servidor): reloj = hoy real.
    hoy = m.uno(lab.owner, "SELECT (now() AT TIME ZONE 'Europe/Madrid')::date")[0]
    cli = h.cliente(lab.owner, reloj=m.x.reloj(f"{hoy.isoformat()}T12:00:00"))
    final = _get(cli, "/v1/previsiones/pendientes")
    _marcas(lab, final)
    inicio = _sin_marca(monkeypatch, lambda: _get(cli, "/v1/previsiones/pendientes"))
    _igual(final, inicio)
    resueltas = final["resueltas_mes"]["filas"]
    fila = next(f for f in resueltas if f["id"] == str(lab.cuotas[1]))
    assert fila["codigo"] == MARCA and fila["estado"] == "REALIZADA"
    assert list(fila) == CLAVES_RESUELTA_C5E4FF8 + ["codigo"]
    # recuentos y orden identicos a c5e4ff8
    assert (final["n"], final["por_pagar"], final["por_cobrar"]) == (inicio["n"], inicio["por_pagar"],
                                                                     inicio["por_cobrar"])
    assert final["resueltas_mes"]["n"] == inicio["resueltas_mes"]["n"]
    assert [f["id"] for f in resueltas] == [f["id"] for f in inicio["resueltas_mes"]["filas"]]
    assert all("codigo" not in f for f in inicio["resueltas_mes"]["filas"])


def test_o_q3_listas_sin_cuotas_no_cambian(monkeypatch):
    """Sin cuotas: ni una fila lleva la clave y la respuesta es la de c5e4ff8 byte a byte."""
    owner, _, cli, cta, _ = m.entorno()
    m.prevision(owner, "Luz", desde="2026-09-01", importe="74.00", cuenta_salida=cta)
    m.prevision(owner, "Agua", desde="2026-10-20", importe="30.00")
    for ruta in ("/v1/inicio/previsiones", "/v1/previsiones/pendientes"):
        final = _get(cli, ruta)
        inicio = _sin_marca(monkeypatch, lambda: _get(cli, ruta))
        assert json.dumps(final) == json.dumps(inicio) and "codigo" not in json.dumps(final)
        assert _filas(final) and all(list(f) == _claves(f) for f in _filas(final))
