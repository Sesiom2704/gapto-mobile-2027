# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_253_f06_01_b2_reserva_h0hk_pb005.py
# Ruta: tests/api/test_253_f06_01_b2_reserva_h0hk_pb005.py
# Descripcion: F06 T1-F06 · B2 N1 · reserva funcional de H0/Hk por operaciones (R1 v0.9.5 §II.7, AJ-TR1-08;
#   oraculos O10.23 v0.7 y O10.27; FA-02 del mandato) y condiciones de PB0-05 (v0.8/v0.9 §II.5), por HTTP como
#   gapto_runtime, sobre una compra REAL (H0 y Hk con pago conciliado):
#   (a) reparto y corregir-categoria: rechazados sin escrituras sobre H0/Hk; si llegan a OP-21, nunca con
#       importe_delta, efectos_a_eliminar ni entidades_a_eliminar (espia sobre CorreccionesService.corregir).
#       Anomalia A-1 del mandato: la correccion de reparto sobre ADQUISICION_PATRIMONIAL se RECHAZA (regla de la
#       v0.8), por HTTP y por llamada directa al adaptador;
#   (b) corregir-pago, corregir-transferencia, anular-duplicado, devoluciones y abono sobre H0/Hk: rechazo sin
#       escrituras;
#   (c) la lectura de edicion de H0/Hk no ofrece corregir ni anular;
#   (d) inventario: ningun modulo de B2 (patrimonio) usa OP-21, OP-02 ni OP-03.
#   PB0-05: los hechos de la compra salen en Actividad sin filtro con tipo ADQUISICION_PATRIMONIAL (fuente de
#   «no es gasto del mes», HF-14), el filtro HTTP `tipo` no se amplia, [desde, hasta) (O10.19 parte servidor),
#   y el Resultado del mes, el gasto del mes de VS-01 y las senales no cambian con la compra.
#   Cada caso deja su JSON si GAPTO_B2_EVIDENCIA apunta a una carpeta (inventario O10.23 por superficie).
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# Version: 0.2.0 (F06 T1-F06 B3 N1; adaptacion declarada y minima por la regla v2 de T1-F06, decision de Moises del
#   2026-11-12 `5b54258a…`): O10.23 (d) admite, en lista cerrada, la UNICA importacion de lectura que C-MEJ-03 hace
#   de un modulo de tesoreria: `from app.repositories.correccion_tesoreria_repository import periodo_cerrado` (guarda
#   de periodo cerrado de la v0.9 §III.3.3, paso 6; no expone OP-21P). Los demas tokens prohibidos y la lista de
#   rutas de B2 no cambian; las rutas de B3 las inventaria test_258.
# ============================================================

from __future__ import annotations

import json
import os
import pathlib
import re
import uuid

import pytest

import f06_01_b2_helpers as c2
import vs01_api_helpers as h
from app.services.correcciones_service import CorreccionesService

RAIZ = pathlib.Path(__file__).resolve().parents[2]


def evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_B2_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def compra():
    lab = c2.Lab()
    cuerpo = lab.peticion()
    r = lab.compra(cuerpo)
    assert r.status_code == 200, r.text
    h0 = uuid.UUID(cuerpo["intencion_id"])
    hk = uuid.uuid5(h0, f"gapto.f06.compra.gasto:{cuerpo['gastos'][0]['linea_id']}")
    return lab, h0, hk


def _version(lab, hecho) -> int:
    return lab.sql("SELECT row_version FROM gapto.hechos_financieros WHERE id = %s", (hecho,))[0][0]


def _movs(lab, hecho) -> list[tuple]:
    return lab.sql("SELECT m.id::text, m.row_version FROM gapto.movimientos_tesoreria m JOIN "
                   "gapto.hecho_movimientos_tesoreria c ON c.movimiento_tesoreria_id = m.id WHERE c.hecho_id = %s",
                   (hecho,))


def _atribuciones(lab, hecho) -> list[tuple]:
    return lab.sql("SELECT t.id::text, t.importe_atribuido FROM gapto.efecto_atribuciones t JOIN gapto.hecho_efectos e "
                   "ON e.id = t.efecto_id WHERE e.hecho_id = %s ORDER BY t.id", (hecho,))


def _peticiones(lab, hecho) -> dict[str, tuple[str, dict]]:
    movs = _movs(lab, hecho)
    v = _version(lab, hecho)
    atr = _atribuciones(lab, hecho)
    return {
        "reparto": (f"/v1/hechos/{hecho}/reparto", {"row_version": v, "motivo": "O10.23", "partes": [
            {"atribucion_id": a, "importe": str((imp * 0 + 1).quantize(imp)) if i == 0 else str(imp)}
            for i, (a, imp) in enumerate(atr)]}),
        "corregir_categoria": (f"/v1/hechos/{hecho}/corregir-categoria",
                               {"intencion_id": str(uuid.uuid4()), "row_version": v, "categoria_id": str(uuid.uuid4())}),
        "corregir_pago": (f"/v1/hechos/{hecho}/corregir-pago", {
            "intencion_id": str(uuid.uuid4()), "row_version": v, "movimiento_row_version": movs[0][1],
            "error_de_registro": True, "motivo": "O10.23", "importe": "1.00"}),
        "corregir_transferencia": (f"/v1/transferencias/{hecho}/corregir", {
            "intencion_id": str(uuid.uuid4()), "row_version": v, "movimientos_row_version": {m: rv for m, rv in movs},
            "error_de_registro": True, "motivo": "O10.23", "importe": "1.00"}),
        "anular_duplicado": (f"/v1/hechos/{hecho}/anular-duplicado", {
            "intencion_id": str(uuid.uuid4()), "row_version": v, "movimientos_row_version": {m: rv for m, rv in movs},
            "duplicado_declarado": True, "motivo": "O10.23"}),
        "devolucion": (f"/v1/hechos/{hecho}/devoluciones", {
            "intencion_id": str(uuid.uuid4()), "importe": "10.00", "moneda": "EUR", "fecha_hecho": c2.HOY,
            "atribucion": "SOLO_MIO", "abono": {"estado": "PENDIENTE"}}),
        "abono": (f"/v1/hechos/{hecho}/abono", {"intencion_id": str(uuid.uuid4()), "cuenta_id": str(lab.c1),
                                                "fecha": c2.HOY}),
    }


@pytest.mark.parametrize("raiz", ["H0", "Hk"])
def test_o10_23_superficies_existentes_rechazan_p1_a_p4(compra, monkeypatch, raiz):
    lab, h0, hk = compra
    hecho = h0 if raiz == "H0" else hk
    espia = []
    original = CorreccionesService.corregir
    monkeypatch.setattr(CorreccionesService, "corregir",
                        lambda self, ctx, datos: espia.append(datos) or original(self, ctx, datos))
    inventario = {}
    for nombre, (ruta, cuerpo) in _peticiones(lab, hecho).items():
        antes = c2.huella()
        r = lab.cli.post(ruta, json=cuerpo, headers=h.AUTH)
        inventario[nombre] = {"ruta": ruta.replace(str(hecho), "{id}"), "status": r.status_code,
                              "codigo": r.json().get("codigo"), "sin_escrituras": c2.huella() == antes}
        assert r.status_code >= 400, (nombre, r.text)
        assert c2.huella() == antes, nombre
    for datos in espia:                                                    # (a) si llego a OP-21, sin P1/P2
        assert not getattr(datos, "efectos_a_actualizar", None) or all(
            "importe_delta" not in v for v in datos.efectos_a_actualizar.values())
        assert not getattr(datos, "efectos_a_eliminar", None) and not getattr(datos, "entidades_a_eliminar", None)
    inventario["llamadas_op21"] = len(espia)
    ed = lab.cli.get(f"/v1/hechos/{hecho}/edicion", headers=h.AUTH)          # (c)
    assert ed.status_code == 200, ed.text
    acciones = ed.json()["acciones"]
    inventario["edicion"] = acciones
    assert acciones["corregir"]["disponible"] is False and acciones["anular_duplicado"]["disponible"] is False
    assert acciones["corregir_categoria"] is None or acciones["corregir_categoria"]["disponible"] is False
    evidencia(f"O10_23_superficies_{raiz}", inventario)


def test_a1_correccion_de_reparto_rechazada_por_llamada_directa(compra):
    from app.api import ejecucion_reparto as rep
    from app.api.dto_reparto import IntencionCorregirReparto
    lab, h0, _ = compra
    _, cuerpo = _peticiones(lab, h0)["reparto"]
    antes = c2.huella()
    try:
        salida = rep.corregir_reparto(c2.unidad(), c2.ctx(lab.owner), h0, IntencionCorregirReparto(**cuerpo))
        codigo = getattr(salida, "codigo", None)
    except Exception as exc:  # ErrorMotor de la capa
        codigo = getattr(getattr(exc, "codigo", None), "value", repr(exc))
    evidencia("A1_reparto_llamada_directa", {"codigo": codigo})
    assert codigo is not None
    assert c2.huella() == antes


#: regla v2 (F06 B3): unica importacion de lectura admitida (guarda de periodo cerrado de C-MEJ-03).
ADMITIDA_B3 = "from app.repositories.correccion_tesoreria_repository import periodo_cerrado"


def test_o10_23_d_inventario_b2_no_expone_op21_op02_op03():
    texto = "\n".join(f.read_text(encoding="utf-8") for f in (RAIZ / "backend" / "app" / "patrimonio").rglob("*.py"))
    codigo = "\n".join(l.split("#", 1)[0] for l in texto.splitlines() if l.strip() != ADMITIDA_B3)
    for prohibido in ("CorreccionesService", "correcciones_service", "anular_hecho", "corregir_hecho",
                      "AnulacionTesoreriaService", "correccion_tesoreria", "devoluciones_service", "ejecucion_reparto",
                      "ejecucion_correccion", "ejecucion_anulacion"):
        assert prohibido not in codigo, prohibido
    rutas = re.findall(r'@app\.(?:post|get)\("([^"]+)"', (RAIZ / "backend" / "app" / "patrimonio" / "rutas.py").read_text(encoding="utf-8"))
    assert sorted(rutas) == sorted(["/v1/propiedades/{propiedad_id}/compra", "/v1/propiedades/{propiedad_id}/compra/gastos",
                                    "/v1/propiedades/{propiedad_id}/completitud", "/v1/propiedades/{propiedad_id}/coste",
                                    "/v1/propiedades/{propiedad_id}/titularidad-en-fecha"])


# ================================================================== PB0-05
def test_actividad_sin_filtro_nuevo_y_tipo_patrimonial(compra):
    lab, h0, hk = compra
    r = lab.cli.get("/v1/actividad", params={"desde": "2026-02-01", "hasta": "2026-04-01"}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    filas = {f["id"]: f for f in r.json()["filas"]}
    assert str(h0) in filas and str(hk) in filas
    assert {filas[str(h0)]["tipo"], filas[str(hk)]["tipo"]} == {"ADQUISICION_PATRIMONIAL"}
    assert lab.cli.get("/v1/actividad", params={"tipo": "ADQUISICION_PATRIMONIAL"}, headers=h.AUTH).status_code == 422
    con_gasto = lab.cli.get("/v1/actividad", params={"tipo": "GASTO"}, headers=h.AUTH).json()["filas"]
    assert str(h0) not in {f["id"] for f in con_gasto}


def test_o10_19_periodo_semiabierto(compra):
    lab, h0, _ = compra
    agencia = "2026-02-28"
    def ids(desde, hasta):
        r = lab.cli.get("/v1/actividad", params={"desde": desde, "hasta": hasta}, headers=h.AUTH)
        assert r.status_code == 200, r.text
        return {f["fecha_hecho"] for f in r.json()["filas"]}
    assert agencia in ids(agencia, "2026-03-20")              # fecha = desde: aparece
    assert c2.ESCRITURA in ids("2026-03-01", "2026-03-21")    # fecha = hasta - 1: aparece
    assert c2.ESCRITURA not in ids("2026-03-01", c2.ESCRITURA)  # fecha = hasta: no aparece


def test_inicio_gasto_del_mes_y_senales_no_cambian_con_la_compra():
    lab = c2.Lab()
    def foto():
        out = {}
        for fecha in ("2026-02-15", c2.ESCRITURA, "2026-03-30"):
            out[f"resultado_{fecha}"] = lab.cli.get("/v1/inicio/resultado-mes", params={"fecha": fecha}, headers=h.AUTH).json()
            out[f"senales_{fecha}"] = lab.cli.get("/v1/senales/categorias", params={"tipo": "GASTO", "fecha": fecha},
                                                  headers=h.AUTH).json()
            out[f"inicio_prev_{fecha}"] = lab.cli.get("/v1/inicio/previsiones", params={"fecha": fecha}, headers=h.AUTH).status_code
        out["gasto_mes_vs01"] = lab.cli.get("/v1/vs01/gasto-mes", headers=h.AUTH).json()
        return out
    antes = foto()
    r = lab.compra(lab.peticion())
    assert r.status_code == 200, r.text
    despues = foto()
    evidencia("PB0_05_inicio_senales", {"antes": antes, "despues": despues})
    assert despues == antes
