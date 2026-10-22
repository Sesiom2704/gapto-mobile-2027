# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_210_f05_06_m1_categoria_v3.py
# Ruta: tests/api/test_210_f05_06_m1_categoria_v3.py
# Descripcion: F05-06 M1 v1.1 · «Corregir categoria» de un registro de V3 por
#   HTTP (Q9 opcion (a); STOP_M5BM1_Q9; F05-D047 §61.3 limitado a la
#   categoria). Con el rol real gapto_runtime y RLS:
#     - GET /v1/hechos/{id}/edicion: `acciones.corregir_categoria` y
#       `categoria` solo en V3 (None fuera); corregir y anular siguen
#       deshabilitados con ORIGEN_IMPORTADO; anulado y varios efectos;
#     - POST /v1/hechos/{id}/corregir-categoria: OK con su oraculo (solo cambia
#       la categoria del efecto; SIN efecto retroactivo: movimientos,
#       importes, fechas, concepto y notas intactos; auditoria con el motivo;
#       la raiz sube su version); cada campo fuera de la lista blanca 422 sin
#       escritura; registro no V3, anulado, categoria no elegible (ambito,
#       deshabilitada, otro owner) y C07 (obligatoria que el hecho no tiene)
#       rechazados en el servidor sin escritura; motivo ausente 422;
#       VERSION_DESFASADA 409 con la edicion releida; reintento de la misma
#       intencion idempotente y con otra categoria IDENTIDAD_REUTILIZADA; otro
#       owner 404;
#     - orden de bloqueos: categoria (C-a + C07) -> raiz del hecho.
#   Reloj fijo 2026-10-10 12:00Z (Madrid).
# Version: 0.1.0 (F05-06 M1 v1.1)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_01_helpers as c01
import f05_05_helpers as x
import f05_06_m2_helpers as m2
import vs01_api_helpers as h


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = x.entorno()
    return owner, cli, cta


def _uno(owner, sql, params=()):
    return h.leer(owner, sql, params)[0]


def _ed(cli, hid):
    r = cli.get(f"/v1/hechos/{hid}/edicion", headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _v3(owner, cli, cta, *, importe="65.00", categoria_id=None):
    hid = x.gasto(cli, cta, importe=importe, categoria_id=categoria_id, concepto="FONTANERO BAÑO")
    m2.marcar_v3(owner, hid)
    return hid


def _huella(owner):
    """Todo lo que no puede cambiar al corregir la categoria (sin efecto retroactivo)."""
    return (_uno(owner, "SELECT count(*), COALESCE(sum(importe), 0), string_agg(fecha_movimiento::text, ',' "
                        "ORDER BY id), COALESCE(sum(row_version), 0) FROM gapto.movimientos_tesoreria"),
            _uno(owner, "SELECT count(*), COALESCE(sum(importe_total), 0), string_agg(fecha_hecho::text || "
                        "COALESCE(concepto, '') || COALESCE(notas, '') || estado, ',' ORDER BY id) "
                        "FROM gapto.hechos_financieros"),
            _uno(owner, "SELECT count(*), COALESCE(sum(importe_delta), 0), string_agg(tipo_efecto || "
                        "COALESCE(descripcion, '') || estado_atribucion, ',' ORDER BY id) FROM gapto.hecho_efectos"),
            _uno(owner, "SELECT count(*), COALESCE(sum(importe_asignado), 0) FROM gapto.hecho_movimientos_tesoreria"),
            _uno(owner, "SELECT count(*), COALESCE(sum(importe_atribuido), 0) FROM gapto.efecto_atribuciones"))


def _nada_escrito(owner):
    """Huella completa, categorias y auditoria incluidas (oraculo de rechazo)."""
    return (_huella(owner), _uno(owner, "SELECT string_agg(COALESCE(categoria_id::text, '-'), ',' ORDER BY id) "
                                        "FROM gapto.hecho_efectos"),
            _uno(owner, "SELECT count(*), COALESCE(sum(row_version), 0) FROM gapto.hechos_financieros"),
            _uno(owner, "SELECT count(*) FROM gapto.auditoria"))


def _corregir(cli, hid, e, cat, **kw):
    c = {"intencion_id": str(uuid.uuid4()), "row_version": e["row_version"], "motivo": "Categoría mal asignada en V3",
         "categoria_id": None if cat is None else str(cat)}
    c.update(kw)
    c = {k: v for k, v in c.items() if v is not ...}
    return c, cli.post(f"/v1/hechos/{hid}/corregir-categoria", json=c, headers=h.AUTH)


def _categoria_efecto(owner, hid):
    return _uno(owner, "SELECT categoria_id FROM gapto.hecho_efectos WHERE hecho_id = %s", (hid,))[0]


# ==================================================================
# Lectura de elegibilidad
# ==================================================================
def test_edicion_v3_ofrece_solo_corregir_categoria(t):
    owner, cli, cta = t
    hogar = x.categoria(owner, "Hogar")
    hid = _v3(owner, cli, cta, categoria_id=hogar)
    e = _ed(cli, hid)
    assert e["origen_v3"] is True
    assert e["acciones"]["corregir_categoria"] == {"disponible": True, "codigo": None, "motivo": None}
    for k in ("corregir", "anular_duplicado"):
        assert e["acciones"][k]["codigo"] == "ORIGEN_IMPORTADO" and "Corregir categoría" in e["acciones"][k]["motivo"]
    efecto = _uno(owner, "SELECT id FROM gapto.hecho_efectos WHERE hecho_id = %s", (hid,))[0]
    assert e["categoria"] == {"efecto_id": str(efecto), "naturaleza": "GASTO", "categoria_id": str(hogar), "nombre": "Hogar"}


def test_edicion_no_v3_sin_corregir_categoria(t):
    owner, cli, cta = t
    hid = x.gasto(cli, cta, importe="10.00")
    e = _ed(cli, hid)
    assert e["acciones"]["corregir_categoria"] is None and e["categoria"] is None
    assert e["acciones"]["corregir"]["disponible"] is True


def test_edicion_v3_sin_categoria_tambien_se_ofrece(t):
    owner, cli, cta = t
    e = _ed(cli, _v3(owner, cli, cta))
    assert e["acciones"]["corregir_categoria"]["disponible"] is True
    assert (e["categoria"]["categoria_id"], e["categoria"]["nombre"]) == (None, None)


def test_edicion_v3_anulado_atenuado(t):
    owner, cli, cta = t
    hid = _v3(owner, cli, cta)
    x.anular(owner, hid)
    e = _ed(cli, hid)
    assert e["acciones"]["corregir_categoria"]["codigo"] == "HECHO_ANULADO" and e["categoria"] is None
    assert e["acciones"]["corregir_categoria"]["motivo"] == "Este registro está anulado."


def test_edicion_v3_varios_efectos_atenuado(t):
    owner, cli, cta = t
    hid = x.hecho_motor(owner, [("GASTO", "30.00", "NO_DISPONIBLE", None, []), ("GASTO", "20.00", "NO_DISPONIBLE", None, [])])
    m2.marcar_v3(owner, hid)
    a = _ed(cli, hid)["acciones"]["corregir_categoria"]
    assert a["codigo"] == "VARIOS_EFECTOS" and a["motivo"]


# ==================================================================
# Corregir categoria
# ==================================================================
def test_corregir_categoria_v3_solo_cambia_la_categoria(t):
    owner, cli, cta = t
    hogar, obras = x.categoria(owner, "Hogar"), x.categoria(owner, "Obras")
    hid = _v3(owner, cli, cta, categoria_id=hogar)
    e = _ed(cli, hid)
    base = _huella(owner)
    auditoria = _uno(owner, "SELECT count(*) FROM gapto.auditoria")[0]
    c, r = _corregir(cli, hid, e, obras)
    assert r.status_code == 200, r.text
    assert r.json() == {"intencion_id": c["intencion_id"], "hecho_id": str(hid), "row_version": e["row_version"] + 1,
                        "estado": "ACTIVO", "idempotente": False}
    assert _categoria_efecto(owner, hid) == obras
    assert _huella(owner) == base  # sin efecto retroactivo: movimientos, importes, fechas, concepto y notas
    nuevas = h.leer(owner, "SELECT tabla, accion, motivo FROM gapto.auditoria WHERE request_id = %s ORDER BY tabla",
                    (uuid.UUID(c["intencion_id"]),))
    assert ("hecho_efectos", "ACTUALIZAR", "Categoría mal asignada en V3") in nuevas
    assert {n[2] for n in nuevas} == {"Categoría mal asignada en V3"}
    assert _uno(owner, "SELECT count(*) FROM gapto.auditoria")[0] == auditoria + len(nuevas)
    e2 = _ed(cli, hid)
    assert (e2["categoria"]["categoria_id"], e2["categoria"]["nombre"]) == (str(obras), "Obras")


def test_corregir_categoria_v3_desde_sin_categoria(t):
    owner, cli, cta = t
    obras = x.categoria(owner, "Obras")
    hid = _v3(owner, cli, cta)
    _, r = _corregir(cli, hid, _ed(cli, hid), obras)
    assert r.status_code == 200, r.text
    assert _categoria_efecto(owner, hid) == obras


def test_corregir_categoria_v3_ingreso(t):
    owner, cli, cta = t
    nomina = x.categoria(owner, "Nómina", "INGRESO")
    hid = x.ingreso(cli, cta, importe="100.00")
    m2.marcar_v3(owner, hid)
    _, r = _corregir(cli, hid, _ed(cli, hid), nomina)
    assert r.status_code == 200, r.text
    assert _categoria_efecto(owner, hid) == nomina


@pytest.mark.parametrize("campo", [
    {"importe": "60.00"}, {"fecha": "2026-10-04"}, {"cuenta_id": str(uuid.uuid4())},
    {"pagador": {"tipo": "CUENTA"}}, {"descripcion": "Otra"}, {"concepto": "Otro"}, {"notas": "Nota"},
    {"tipo": "INGRESO"}, {"tipo_efecto": "INGRESO"}, {"atribucion": "COMPARTIDO"}, {"importe_delta": "-1.00"},
    {"estado_atribucion": "COMPLETA"}, {"efecto_id": str(uuid.uuid4())}, {"tercero_id": str(uuid.uuid4())},
    {"magnitudes": []}, {"presupuestable": False}, {"categoria": {"estado": "SIN_CATEGORIA"}},
    {"efectos_a_actualizar": {}}, {"error_de_registro": True},
])
def test_corregir_categoria_campo_fuera_de_la_lista_blanca(t, campo):
    owner, cli, cta = t
    obras = x.categoria(owner, "Obras")
    hid = _v3(owner, cli, cta)
    base = _nada_escrito(owner)
    _, r = _corregir(cli, hid, _ed(cli, hid), obras, **campo)
    assert r.status_code == 422, r.text
    assert _nada_escrito(owner) == base


def test_corregir_categoria_sin_categoria_rechazada(t):
    owner, cli, cta = t
    hid = _v3(owner, cli, cta)
    base = _nada_escrito(owner)
    _, r = _corregir(cli, hid, _ed(cli, hid), None)
    assert r.status_code == 422 and _nada_escrito(owner) == base


def test_corregir_categoria_no_v3_rechazada_en_servidor(t):
    owner, cli, cta = t
    obras = x.categoria(owner, "Obras")
    hid = x.gasto(cli, cta, importe="10.00")
    base = _nada_escrito(owner)
    _, r = _corregir(cli, hid, _ed(cli, hid), obras)
    assert r.status_code == 409, r.text
    assert (r.json()["codigo"], r.json()["detalle"]["motivo"]) == ("CATEGORIA_V3_NO_CORREGIBLE", "NO_IMPORTADO")
    assert r.json()["mensaje"].startswith("Solo los registros migrados") and "No se ha cambiado nada" in r.json()["mensaje"]
    assert _nada_escrito(owner) == base


def test_corregir_categoria_v3_anulado_rechazado(t):
    owner, cli, cta = t
    obras = x.categoria(owner, "Obras")
    hid = _v3(owner, cli, cta)
    e = _ed(cli, hid)
    x.anular(owner, hid)
    base = _nada_escrito(owner)
    _, r = _corregir(cli, hid, e, obras)
    assert r.status_code == 409 and r.json()["detalle"]["motivo"] == "HECHO_ANULADO", r.text
    assert _nada_escrito(owner) == base


@pytest.mark.parametrize("caso", ["ambito", "deshabilitada", "otro_owner", "inexistente"])
def test_corregir_categoria_no_elegible(t, caso):
    owner, cli, cta = t
    hid = _v3(owner, cli, cta)
    if caso == "ambito":
        cat = x.categoria(owner, "Nómina", "INGRESO")
    elif caso == "deshabilitada":
        cat = x.categoria(owner, "Antigua", enabled=False)
    elif caso == "otro_owner":
        otro, _, _, _, _ = x.entorno()
        cat = x.categoria(otro, "Ajena")
    else:
        cat = uuid.uuid4()
    base = _nada_escrito(owner)
    _, r = _corregir(cli, hid, _ed(cli, hid), cat)
    assert r.status_code == 409 and r.json()["codigo"] == "CATEGORIA_NO_ELEGIBLE", r.text
    assert _nada_escrito(owner) == base


def test_corregir_categoria_c07_obligatoria_que_el_hecho_no_tiene(t):
    owner, cli, cta = t
    gasolina = x.categoria(owner, "Gasolina")
    c01.crear_magnitud_categoria(owner, gasolina, obligatoria=True)
    hid = _v3(owner, cli, cta)
    base = _nada_escrito(owner)
    _, r = _corregir(cli, hid, _ed(cli, hid), gasolina)
    assert r.status_code == 409 and r.json()["codigo"] == "MAGNITUD_OBLIGATORIA_AUSENTE", r.text
    assert _nada_escrito(owner) == base


def test_corregir_categoria_c07_opcional_se_admite(t):
    owner, cli, cta = t
    gasolina = x.categoria(owner, "Gasolina")
    c01.crear_magnitud_categoria(owner, gasolina, obligatoria=False)
    hid = _v3(owner, cli, cta)
    _, r = _corregir(cli, hid, _ed(cli, hid), gasolina)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("motivo", [None, "   "])
def test_corregir_categoria_sin_motivo(t, motivo):
    owner, cli, cta = t
    obras = x.categoria(owner, "Obras")
    hid = _v3(owner, cli, cta)
    base = _nada_escrito(owner)
    _, r = _corregir(cli, hid, _ed(cli, hid), obras, motivo=motivo)
    assert r.status_code == 422 and r.json()["codigo"] == "MOTIVO_AUSENTE", r.text
    assert _nada_escrito(owner) == base


def test_corregir_categoria_version_desfasada(t):
    owner, cli, cta = t
    obras, hogar = x.categoria(owner, "Obras"), x.categoria(owner, "Hogar")
    hid = _v3(owner, cli, cta)
    vieja = _ed(cli, hid)
    _, r = _corregir(cli, hid, vieja, obras)
    assert r.status_code == 200
    base = _nada_escrito(owner)
    _, r = _corregir(cli, hid, vieja, hogar)  # otro dispositivo, con la version anterior
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DESFASADA", r.text
    assert r.json()["detalle"]["edicion"]["categoria"]["categoria_id"] == str(obras)
    assert r.json()["detalle"]["edicion"]["row_version"] == vieja["row_version"] + 1
    assert _nada_escrito(owner) == base


def test_corregir_categoria_reintento_idempotente_y_reutilizada(t):
    owner, cli, cta = t
    obras, hogar = x.categoria(owner, "Obras"), x.categoria(owner, "Hogar")
    hid = _v3(owner, cli, cta)
    e = _ed(cli, hid)
    c, r = _corregir(cli, hid, e, obras)
    assert r.status_code == 200
    base = _nada_escrito(owner)
    r2 = cli.post(f"/v1/hechos/{hid}/corregir-categoria", json=c, headers=h.AUTH)
    assert r2.status_code == 200, r2.text
    assert r2.json() == {**r.json(), "idempotente": True}
    assert _nada_escrito(owner) == base
    r3 = cli.post(f"/v1/hechos/{hid}/corregir-categoria", json={**c, "categoria_id": str(hogar)}, headers=h.AUTH)
    assert r3.status_code == 409 and r3.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION", r3.text
    assert _nada_escrito(owner) == base


def test_corregir_categoria_otro_owner_404(t):
    owner, cli, cta = t
    hid = _v3(owner, cli, cta)
    otro, _, cli_otro, _, _ = x.entorno()
    cat = x.categoria(otro, "Obras")
    base = _nada_escrito(owner)
    r = cli_otro.post(f"/v1/hechos/{hid}/corregir-categoria", headers=h.AUTH,
                      json={"intencion_id": str(uuid.uuid4()), "row_version": 1, "motivo": "x", "categoria_id": str(cat)})
    assert r.status_code == 404, r.text
    assert _nada_escrito(owner) == base


def test_corregir_pago_de_v3_sigue_rechazado(t):
    """La via nueva no abre las demas: corregir importe de V3 sigue en ORIGEN_IMPORTADO."""
    owner, cli, cta = t
    hid = _v3(owner, cli, cta)
    e = _ed(cli, hid)
    r = cli.post(f"/v1/hechos/{hid}/corregir-pago", headers=h.AUTH, json={
        "intencion_id": str(uuid.uuid4()), "row_version": e["row_version"],
        "movimiento_row_version": e["movimientos"][0]["row_version"], "motivo": "x", "error_de_registro": True,
        "importe": "60.00"})
    assert r.status_code == 422 and r.json()["detalle"]["motivo"] == "ORIGEN_IMPORTADO", r.text


# ==================================================================
# Orden de bloqueos: categoria (C-a + C07) -> raiz del hecho
# ==================================================================
def test_orden_locks_categoria_antes_que_la_raiz(t, monkeypatch):
    from app.api import ejecucion_categoria_v3
    from app.services import integridad_posicion

    owner, cli, cta = t
    obras = x.categoria(owner, "Obras")
    hid = _v3(owner, cli, cta)
    e = _ed(cli, hid)
    orden: list[str] = []
    guarda, raiz = ejecucion_categoria_v3.validar_categoria_y_magnitudes, integridad_posicion.adquirir_raiz

    def g(*a, **k):
        orden.append("categoria")
        return guarda(*a, **k)

    def r_(*a, **k):
        orden.append("raiz")
        return raiz(*a, **k)

    monkeypatch.setattr(ejecucion_categoria_v3, "validar_categoria_y_magnitudes", g)
    monkeypatch.setattr(integridad_posicion, "adquirir_raiz", r_)
    _, r = _corregir(cli, hid, e, obras)
    assert r.status_code == 200, r.text
    assert orden[:2] == ["categoria", "raiz"], orden
