# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_298_f06_01h_f05_actividad_hd.py
# Ruta: tests/api/test_298_f06_01h_f05_actividad_hd.py
# Descripcion: Reapertura nominal y acotada de F05 Q3-Hd (literal LITERAL_REAPERTURA_F05_Q3_HD_v1.1, parte (b);
#   mandato T3-F06 bloque 2 F06-01H v1.1 §11.5). Oraculos de servidor por HTTP como gapto_runtime con RLS:
#   - O-HD-1: GET /v1/actividad (lista) y GET /v1/actividad/{id} (detalle) del Hd de una compra con hipoteca: la
#     cuenta de desembolso sale con rol PRESTAMO_RECIBIDO; ninguna fila de Hd con rol COBRO; con filtro de tipo
#     INGRESO, Hd no aparece.
#   - O-HD-2 (no ampliacion): un INGRESO ordinario, un REEMBOLSO de cobro y un GENERACION_DERECHO_OBLIGACION con
#     movimiento + SIN vinculo de nivel efecto a FINANCIACION siguen con rol COBRO, byte a byte como en la
#     composicion de c5e4ff8 (emulada anulando el predicado HD-S1: es la unica diferencia de las superficies).
#   Mutantes que matan: MHD-S1 (el rol del Hd vuelve a COBRO) y MHD-S2 (el rol se aplica a todo GDO con entrada).
#   Discriminacion: en el HEAD de inicio (superficies identicas en c5e4ff8 y 7eed34c) falla con COBRO.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H; literal F05 Q3-Hd v1.1, paso 9)
# ============================================================

from __future__ import annotations

import json
import pathlib
import sys
import uuid
from decimal import Decimal as D

import pytest

import f05_05_helpers as x5
import f05_06_m3_helpers as m3
import f05_06_m5_helpers as m
import vs01_api_helpers as h
from test_289_f06_01h_alta_en_compra import LabHip

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
import f04_r_hip_formas as fz  # noqa: E402

ROL = "PRESTAMO_RECIBIDO"


class Lab298(LabHip):
    """Compra con hipoteca (Hd real del alta) y, en el mismo owner, los tres negativos de O-HD-2."""

    def __init__(self):
        super().__init__()
        cuerpo = self.peticion_hip(hip=self.bloque(numero_cuotas=12))
        r = self.compra(cuerpo)
        assert r.status_code == 200, r.text
        self.hd = uuid.uuid5(uuid.UUID(cuerpo["intencion_id"]), "gapto.f06.compra.desembolso")
        # negativo 1: INGRESO ordinario
        self.ingreso = x5.ingreso(self.cli, self.cd, fecha="2026-10-05", importe="1200.00")
        # negativo 2: REEMBOLSO de cobro (Tania me debe su parte de la cena y me la paga)
        tania, carlos = m3.persona(self.cli, "Tania"), m3.persona(self.cli, "Carlos")
        c, r = m3.cena(self.cli, self.c1, tania, carlos)
        assert r.status_code == 200, r.text
        entidad = m3.entidad_de_posicion(self.owner, uuid.UUID(c["intencion_id"]))
        _, r = m3.cobro(self.cli, entidad, self.c1, "15.00")
        assert r.status_code == 200, r.text
        self.reembolso = (m.uno(self.owner, "SELECT h.id FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho "
                                                     "th ON th.id = h.tipo_hecho_id WHERE th.codigo = 'REEMBOLSO'")[0])
        # negativo 3: GDO con DEUDA + y movimiento +, sin vinculo de nivel efecto a FINANCIACION
        from app.core.modelos_efectos import DatosEfecto
        from app.services.efectos_service import EfectosService
        import f05_01_helpers as fh

        ctx = m.ctx(self.owner)
        importe = D("5000.00")
        self.gdo, v = fz._hecho(fh.unidad(), ctx, "GENERACION_DERECHO_OBLIGACION", importe, False)
        r = EfectosService(fh.unidad()).registrar_efectos(ctx, hecho_id=self.gdo, row_version_esperada=v, efectos=[
            DatosEfecto(efecto_id=uuid.uuid4(), tipo_efecto="DEUDA", importe_delta=importe,
                        estado_atribucion="NO_DISPONIBLE")])
        fz._tesoreria(fh.unidad(), ctx, self.gdo, self.cd, importe, r.row_version)


@pytest.fixture()
def lab():
    return Lab298()


def _get(cli, ruta: str, **params) -> dict:
    r = cli.get(ruta, params=params, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _lista(cli, **params) -> dict[str, dict]:
    return {f["id"]: f for f in _get(cli, "/v1/actividad", limite=100, **params)["filas"]}


def _sin_predicado(monkeypatch, fn):
    """Composicion de c5e4ff8: HD-S1 anulado (ningun hecho es un desembolso Hd)."""
    import app.actividad.lecturas as lect

    with monkeypatch.context() as mp:
        mp.setattr(lect, "_desembolsos_hd", lambda cur, ids: set(), raising=False)
        return fn()


# ================================================================== O-HD-1
def test_o_hd_1_lista_y_detalle_del_hd(lab, monkeypatch):
    filas = _lista(lab.cli)
    hd = filas[str(lab.hd)]
    assert hd["tipo"] == "GENERACION_DERECHO_OBLIGACION"
    assert [(c["cuenta_id"], c["rol"]) for c in hd["cuentas"]] == [(str(lab.cd), ROL)]
    detalle = _get(lab.cli, f"/v1/actividad/{lab.hd}")
    assert [(c["cuenta_id"], c["rol"]) for c in detalle["cuentas"]] == [(str(lab.cd), ROL)]
    # ninguna fila de Hd con COBRO; reparto y «tu parte» sin cambio (Hd no es GASTO/INGRESO)
    assert all(c["rol"] != "COBRO" for c in hd["cuentas"] + detalle["cuentas"])
    assert (hd["estado_reparto"], hd["tu_parte"]) == (None, None)
    # con filtro de tipo INGRESO, Hd no aparece (el ingreso ordinario si)
    ingresos = _lista(lab.cli, tipo="INGRESO")
    assert str(lab.hd) not in ingresos and str(lab.ingreso) in ingresos
    # la unica diferencia con la composicion de c5e4ff8 es el rol del movimiento + del Hd
    inicio = _sin_predicado(monkeypatch, lambda: (_lista(lab.cli), _get(lab.cli, f"/v1/actividad/{lab.hd}")))
    assert [c["rol"] for c in inicio[0][str(lab.hd)]["cuentas"]] == ["COBRO"]
    for antes, ahora in ((inicio[0][str(lab.hd)], hd), (inicio[1], detalle)):
        assert json.dumps(ahora).replace(f'"{ROL}"', '"COBRO"') == json.dumps(antes)


# ================================================================== O-HD-2
def test_o_hd_2_negativos_siguen_con_cobro_byte_a_byte(lab, monkeypatch):
    filas = _lista(lab.cli)
    inicio = _sin_predicado(monkeypatch, lambda: _lista(lab.cli))
    for hid, tipo in ((lab.ingreso, "INGRESO"), (lab.reembolso, "REEMBOLSO"),
                      (lab.gdo, "GENERACION_DERECHO_OBLIGACION")):
        f = filas[str(hid)]
        assert f["tipo"] == tipo and [c["rol"] for c in f["cuentas"]] == ["COBRO"], f
        assert json.dumps(f) == json.dumps(inicio[str(hid)])
        detalle = _get(lab.cli, f"/v1/actividad/{hid}")
        antes = _sin_predicado(monkeypatch, lambda: _get(lab.cli, f"/v1/actividad/{hid}"))
        assert [c["rol"] for c in detalle["cuentas"]] == ["COBRO"] and json.dumps(detalle) == json.dumps(antes)
    # el resto de la lista, identico salvo el Hd
    otras = {k: v for k, v in filas.items() if k != str(lab.hd)}
    assert json.dumps(otras) == json.dumps({k: v for k, v in inicio.items() if k != str(lab.hd)})
    assert all(c["rol"] != ROL for f in otras.values() for c in f["cuentas"])
