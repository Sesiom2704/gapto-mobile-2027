# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_011_p5_dominio9.py
# Ruta: tests/migration/test_rv3_011_p5_dominio9.py
# Descripcion: RV3 / P5 v0.9.0. Corpus SINTETICO (sin PII) del dominio 9,
#              inversiones: POSICION sin padre, gestor = proveedor V3 (discrepancia
#              con dealer -> S20), objetivos en version con vigencia NULL (nunca
#              valoracion ni capital real), cierre sin fecha/motivo inventados,
#              tipo_producto PROPUESTA con fallo cerrado fuera de laboratorio, la
#              fila V3 que es cuenta no se duplica y coherencia del ROI objetivo.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import importlib.util
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", RAIZ / "scripts" / "migration_v3" / "rv3_p5_transformacion.py")
P5 = importlib.util.module_from_spec(_spec)
sys.modules["rv3_p5_transformacion"] = P5
_spec.loader.exec_module(P5)
_s8 = importlib.util.spec_from_file_location("t8", Path(__file__).resolve().parent / "test_rv3_008_p5_dominio8.py")
T8 = importlib.util.module_from_spec(_s8)
_s8.loader.exec_module(T8)
F = P5.fu
SHA = "0" * 64
IV = "public.inversion"
N = "141"


def _inv(k, **kw):
    d = {"id": k, "nombre": f"INV {k}", "estado": "ACTIVA", "moneda": "EUR", "fecha_inicio": "2019-03-11",
         "proveedor_id": "PA", "dealer_id": "PA", "aporte_estimado": "100.00", "retorno_esperado_total": "120.00",
         "roi_esperado_pct": "20.00", "irr_esperada_pct": N, "moic_esperado": N, "plazo_esperado_meses": N,
         "fecha_objetivo_salida": N, "fecha_cierre_real": N, "plazo_final_meses": N, "retorno_final_total": N,
         "descripcion": N}
    d.update(kw)
    return (IV, k, d)


def _filas(*extra):
    return T8._filas() + [_inv("IA"), _inv("IC", estado="CERRADA", plazo_final_meses=8, retorno_final_total="130.00",
                                          descripcion="Edificio"), _inv("ICTA")] + list(extra)


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(P5, "CONFIG_CUENTAS", {("public.cuentas_bancarias", "C1"): ("CORRIENTE", "ACTIVO", True, True, True, "EUR"),
                                               (IV, "ICTA"): ("AHORRO", "ACTIVO", True, True, False, "EUR")})
    monkeypatch.setattr(P5, "CUENTAS_DERIVADAS", {(IV, "ICTA"): ("CUENTA AHORRO", "proveedor_id")})
    monkeypatch.setattr(P5, "CONDICIONES_DECIDIDAS", {})
    monkeypatch.setattr(P5, "PARTICIPACION_FIN_SELF", {})
    monkeypatch.setattr(P5, "TIPO_PRODUCTO_PROPUESTO", {"IA": "FONDO", "IC": "OTRO"})


def _t(filas=None, lab=True):
    return P5.transformar(T8._b0(filas or _filas()), SHA, modo_lab=lab)


def _i(ds, k):
    return ds.filas["inversiones"][F.uuid_v3(IV, k, "entidades", "inversion")]


def _err(**kw):
    with pytest.raises(P5.ErrorP5) as e:
        _t(**kw)
    return e.value.codigo


def test_catalogo_real_de_tipos_cubre_las_siete_posiciones():
    real = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(real)
    assert len(real.TIPO_PRODUCTO_PROPUESTO) == 7 and real.TIPO_PRODUCTO_ESTADO == "PROPUESTA"
    assert set(real.TIPO_PRODUCTO_PROPUESTO.values()) <= {"PLAN", "CARTERA_GESTIONADA", "FONDO", "ACCION", "DEPOSITO", "OTRO"}


def test_posicion_sin_padre_con_gestor_v3_y_sin_capital_inventado():
    ds = _t()
    i = _i(ds, "IA")
    assert (i["rol_estructura"], i["inversion_padre_entidad_id"], i["tipo_producto"]) == ("POSICION", None, "FONDO")
    assert i["tercero_gestor_id"] == F.uuid_v3("public.proveedores", "PA", "terceros", "tercero")
    assert i["capital_invertido_apertura"] is None and i["fecha_capital_invertido_apertura"] is None


def test_cuenta_v3_no_se_duplica_como_inversion():
    ds = _t()
    assert F.uuid_v3(IV, "ICTA", "entidades", "inversion") not in ds.filas["inversiones"]
    assert len(ds.filas["inversiones"]) == 2


def test_objetivos_version_sin_vigencia_inventada():
    ds = _t()
    eid = F.uuid_v3(IV, "IA", "entidades", "inversion")
    o = [x for x in ds.filas["inversion_objetivos_versiones"].values() if x["inversion_entidad_id"] == eid]
    assert len(o) == 1 and o[0]["vigente_desde"] is None and o[0]["vigente_hasta"] is None
    assert (o[0]["aporte_objetivo_total"], o[0]["valor_objetivo_total"], o[0]["roi_objetivo_pct"]) == \
        (Decimal("100.00"), Decimal("120.00"), Decimal("20.00"))
    assert o[0]["irr_objetivo_pct"] is None and o[0]["plazo_objetivo_meses"] is None


def test_cerrada_sin_fecha_ni_motivo_inventados():
    i = _i(_t(), "IC")
    assert (i["estado"], i["fecha_fin_real"], i["motivo_cierre"], i["plazo_real_meses"]) == ("CERRADA", None, None, 8)


def test_tipo_producto_propuesto_falla_fuera_de_lab(monkeypatch):
    assert _err(lab=False) == "S20_TIPO_PRODUCTO"
    monkeypatch.setattr(P5, "TIPO_PRODUCTO_ESTADO", "CONFIRMADA")
    assert _t(lab=False).filas["inversiones"]


def test_gestor_discrepante_falla_s20():
    f = [x for x in _filas() if x[1] != "IA"] + [_inv("IA", dealer_id="PT")]
    assert _err(filas=f) == "S20_GESTOR_INVERSION"


def test_roi_objetivo_incoherente_falla():
    f = [x for x in _filas() if x[1] != "IA"] + [_inv("IA", roi_esperado_pct="25.00")]
    assert _err(filas=f) == "S9_ROI_OBJETIVO_INCOHERENTE"


def test_inversion_sin_tipo_declarado_falla():
    assert _err(filas=_filas(_inv("IX"))) == "S4_INVERSION_SIN_TIPO"


@pytest.mark.skipif(not os.environ.get("GAPTO_RV3_IMPORT_URL"), reason="sin laboratorio RV3_IMPORT")
def test_fisico_rv3_import_rollback():
    res = P5.validar_fisico(_t(), os.environ["GAPTO_RV3_IMPORT_URL"])
    assert res["inversiones"] == 2 and res["inversion_objetivos_versiones"] == 2
