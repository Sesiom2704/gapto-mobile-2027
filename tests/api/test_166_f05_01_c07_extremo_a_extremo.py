# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_166_f05_01_c07_extremo_a_extremo.py
# Ruta: tests/api/test_166_f05_01_c07_extremo_a_extremo.py
# Descripcion: C07 de extremo a extremo por la API publica (F05 §22.2 C07,
#   §28.2-§28.6, §34; mandato P7 · N1). Una sola secuencia, en el orden del
#   uso real, sobre un tenant nuevo; SQL solo para lecturas de verificacion
#   (recuentos y filas) bajo gapto_runtime con RLS:
#     1) POST /v1/categorias: categoria GASTO «P7 E2E»;
#     2) POST /v1/categorias/{id}/magnitudes: origen NUEVA (precision 1,
#        obligatoria) y origen EXISTENTE (magnitud ya presente en el tenant,
#        como la del seed; opcional);
#     3) GET /v1/categorias: ambas asociaciones con asociacion_id, orden 0 y
#        1 y capturable = true;
#     4) registro VS-01 sin la obligatoria -> 409 MAGNITUD_OBLIGATORIA_AUSENTE,
#        recuentos de hechos_financieros, hecho_efectos, hecho_magnitudes y
#        auditoria iguales antes y despues;
#     5) registro con ambas -> hecho creado; hecho_magnitudes con unidad =
#        unidad_default de cada magnitud e id = uuid5(intencion_id,
#        "magnitud:<magnitud_id>");
#     6) obligatoria -> opcional: un registro nuevo sin ella se admite;
#     7) renombrar la magnitud: la fila de (5) no cambia (magnitud_id, valor,
#        unidad); NO se afirma snapshot del nombre (AJ-P7BAT-09);
#     8) retirar la asociacion: un registro nuevo que la envie -> 409
#        MAGNITUD_NO_ADMITIDA sin mutaciones; filas de (5) intactas;
#     9) retry identico de (5) tras 6-8 -> idempotente (mismo hecho, sin
#        filas nuevas).
#   WM 12C.2: test de COMPOSICION (comportamiento existente en c06d219): pasa
#   sobre c06d219 y muere con el mutante P01 (mutantes_f05_01.py:
#   `_asociaciones` devuelve lista vacia), cuya asercion discriminante es la
#   de la etapa 4.
#   Exige GAPTO_TEST_DATABASE_URL (base local desechable 0001..0340): confirma
#   filas.
# Version: 0.1.0 (F05-01 P7 · N1, AJ-P7BAT-04/09)
# ============================================================

from __future__ import annotations

import decimal
import uuid

import f05_01_helpers as fh
import vs01_api_helpers as h

URL_REGISTRO = "/v1/intenciones/gasto-pagado"
TABLAS = ("hechos_financieros", "hecho_efectos", "hecho_magnitudes", "auditoria")


def _post(cli, ruta: str, cuerpo: dict):
    return cli.post(ruta, json=cuerpo, headers=h.AUTH)


def _recuentos(owner) -> dict[str, int]:
    return {t: h.leer(owner, f"SELECT count(*) FROM gapto.{t}")[0][0] for t in TABLAS}


def _filas_magnitudes(owner, hecho) -> list[tuple]:
    return h.leer(owner, "SELECT id, magnitud_id, valor, unidad FROM gapto.hecho_magnitudes "
                         "WHERE hecho_id=%s ORDER BY magnitud_id", (hecho,))


def _registro(cuenta, cat, magnitudes) -> dict:
    return h.intencion(cuenta, concepto="P7 E2E", importe="12.40", categoria={
        "estado": "CATEGORIA", "categoria_id": str(cat),
        "magnitudes": [{"magnitud_id": str(m), "valor": v} for m, v in magnitudes]})


def _rechazo(r, codigo) -> None:
    assert r.status_code == 409, r.text
    assert r.json()["codigo"] == codigo and r.json()["reintentable"] is False


def test_c07_de_extremo_a_extremo_por_la_api_publica():
    owner, actor = h.crear_tenant()
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    cli = h.cliente(owner)

    # 1) alta de la categoria
    cat, r = fh.alta(cli, "P7 E2E")
    assert r.status_code == 200, r.text

    # 2) asociaciones: NUEVA obligatoria y EXISTENTE opcional
    nueva = uuid.uuid4()
    r = _post(cli, f"/v1/categorias/{cat}/magnitudes", {"origen": "NUEVA", "obligatoria": True, "magnitud": {
        "magnitud_id": str(nueva), "nombre": "Distancia P7", "unidad_default": "km", "precision_decimales": 1}})
    assert r.status_code == 200, r.text
    existente = h.crear_magnitud(owner, "Litros P7", unidad="l", precision=2)
    r = _post(cli, f"/v1/categorias/{cat}/magnitudes",
              {"origen": "EXISTENTE", "magnitud_id": str(existente), "obligatoria": False})
    assert r.status_code == 200, r.text

    # 3) lectura del arbol
    [nodo] = [c for c in cli.get("/v1/categorias", headers=h.AUTH).json()["categorias"] if c["id"] == str(cat)]
    assert nodo["capturable"] is True and nodo["motivo_no_capturable"] is None
    assert [(m["magnitud_id"], m["orden"], m["obligatoria"]) for m in nodo["magnitudes"]] == [
        (str(nueva), 0, True), (str(existente), 1, False)]
    assert all(uuid.UUID(m["asociacion_id"]) for m in nodo["magnitudes"])
    asociacion_nueva = nodo["magnitudes"][0]["asociacion_id"]

    # 4) sin la obligatoria: rechazo sin mutaciones (discriminante de P01)
    antes = _recuentos(owner)
    r = _post(cli, URL_REGISTRO, _registro(cuenta, cat, []))
    _rechazo(r, "MAGNITUD_OBLIGATORIA_AUSENTE")
    assert _recuentos(owner) == antes

    # 5) con ambas: hecho creado, unidad snapshot e identidad derivada
    cuerpo5 = _registro(cuenta, cat, [(nueva, "12.5"), (existente, "40.25")])
    r = _post(cli, URL_REGISTRO, cuerpo5)
    assert r.status_code == 200 and r.json()["idempotente"] is False, r.text
    hecho = uuid.UUID(r.json()["hecho_id"])
    intencion_id = uuid.UUID(cuerpo5["intencion_id"])
    esperadas = sorted([
        (uuid.uuid5(intencion_id, f"magnitud:{nueva}"), nueva, decimal.Decimal("12.5"), "km"),
        (uuid.uuid5(intencion_id, f"magnitud:{existente}"), existente, decimal.Decimal("40.25"), "l"),
    ], key=lambda f: f[1])
    filas5 = _filas_magnitudes(owner, hecho)
    assert filas5 == esperadas
    assert fh.categoria_del_efecto(owner, hecho) == [(cat,)]

    # 6) obligatoria -> opcional: un registro sin ella se admite
    r = _post(cli, f"/v1/categorias/{cat}/magnitudes/{asociacion_nueva}/obligatoria",
              {"magnitud_id": str(nueva), "obligatoria_actual": True, "obligatoria": False})
    assert r.status_code == 200, r.text
    r = _post(cli, URL_REGISTRO, _registro(cuenta, cat, []))
    assert r.status_code == 200 and r.json()["idempotente"] is False, r.text
    assert _filas_magnitudes(owner, uuid.UUID(r.json()["hecho_id"])) == []

    # 7) renombrar la magnitud: la fila de (5) no cambia (sin afirmar snapshot del nombre)
    rv = h.magnitud_persistida(owner, nueva)[4]
    r = _post(cli, f"/v1/magnitudes/{nueva}/renombrar", {"row_version": rv, "nombre": "Recorrido P7"})
    assert r.status_code == 200, r.text
    assert h.magnitud_persistida(owner, nueva)[0] == "Recorrido P7"
    assert [(m, v, u) for _, m, v, u in _filas_magnitudes(owner, hecho)] == [(m, v, u) for _, m, v, u in filas5]

    # 8) retirar la asociacion: enviarla es MAGNITUD_NO_ADMITIDA sin mutaciones
    r = _post(cli, f"/v1/categorias/{cat}/magnitudes/{asociacion_nueva}/retirar",
              {"magnitud_id": str(nueva), "obligatoria_actual": False})
    assert r.status_code == 200, r.text
    antes = _recuentos(owner)
    r = _post(cli, URL_REGISTRO, _registro(cuenta, cat, [(nueva, "3.0")]))
    _rechazo(r, "MAGNITUD_NO_ADMITIDA")
    assert _recuentos(owner) == antes
    assert _filas_magnitudes(owner, hecho) == filas5

    # 9) retry identico de (5) tras 6-8: idempotente, mismo hecho y sin filas nuevas
    antes = _recuentos(owner)
    r = _post(cli, URL_REGISTRO, cuerpo5)
    assert r.status_code == 200 and r.json()["idempotente"] is True, r.text
    assert uuid.UUID(r.json()["hecho_id"]) == hecho
    assert _recuentos(owner) == antes
    assert _filas_magnitudes(owner, hecho) == filas5
