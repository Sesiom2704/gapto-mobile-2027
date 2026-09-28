# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_152_f05_01_elegibilidad_categoria.py
# Ruta: tests/api/test_152_f05_01_elegibilidad_categoria.py
# Descripcion: Pruebas discriminantes de la guarda de elegibilidad categorial
#   de F05-01 (F05-D009 §23.2-§23.3 C-a; F05-D008 C01/C02/C04; mandato F05-01
#   backend v0.2, AJ-01/AJ-02):
#     - matriz C02 literal (AMBOS = GASTO + INGRESO, nunca otra naturaleza);
#     - owner, enabled y ambito releidos dentro de la transaccion;
#     - tres estados categoriales (CATEGORIA / SIN_CATEGORIA /
#       NO_CAPTURADA_LEGACY derivado solo de la ausencia);
#     - bloqueo transitorio CATEGORIA_REQUIERE_MAGNITUDES sin mutacion parcial;
#     - identidad antes que guarda (reintento idempotente con la categoria ya
#       deshabilitada);
#     - concurrencia en AMBOS ordenes con barrera explicita (WM 12C.1): registro
#       con FOR SHARE frente a desactivacion y frente a cambio de ambito.
#   Base local desechable 0001..0340 (estos tests confirman filas).
#
#   v0.1.1: los PID de las sesiones de barrera se leen con pg_backend_pid()
#   (fh.pid_servidor); `info.backend_pid` no es el PID real tras el proxy de
#   Neon. No cambia ninguna asercion ni el mecanismo observado.
# Version: 0.1.1
# ============================================================

from __future__ import annotations

import threading
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h

URL = "/v1/intenciones/gasto-pagado"


@pytest.fixture()
def tenant():
    owner, actor = h.crear_tenant()
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    return owner, actor, cuenta


def _con_categoria(cuenta, categoria_id, **extra) -> dict:
    return h.intencion(cuenta, categoria={"estado": "CATEGORIA", "categoria_id": str(categoria_id)}, **extra)


def _hid(cuerpo) -> uuid.UUID:
    return uuid.UUID(cuerpo["intencion_id"])


def _cero(owner, hid) -> None:
    assert fh.huella_agregado(owner, hid) == {
        "hechos": 0, "efectos": 0, "conciliaciones": 0, "aportaciones": 0, "auditoria": 0,
    }


# ------------------------------------------------------------ C02 y C04
@pytest.mark.parametrize("ambito", ["GASTO", "AMBOS"])
def test_categoria_elegible_se_sella_en_el_efecto(tenant, ambito):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, f"Cafe {ambito}", ambito)
    cuerpo = _con_categoria(cuenta, cat)
    r = h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["estado_categorial"] == "CATEGORIA"
    assert fh.categoria_del_efecto(owner, _hid(cuerpo)) == [(cat,)]


def test_ambito_ingreso_no_es_elegible_para_gasto(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Nomina", "INGRESO")
    cuerpo = _con_categoria(cuenta, cat)
    r = h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "CATEGORIA_NO_ELEGIBLE"
    assert r.json()["reintentable"] is False
    _cero(owner, _hid(cuerpo))


def test_categoria_deshabilitada_no_es_elegible(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Antigua", "GASTO", enabled=False)
    cuerpo = _con_categoria(cuenta, cat)
    r = h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "CATEGORIA_NO_ELEGIBLE"
    _cero(owner, _hid(cuerpo))


def test_nodo_intermedio_habilitado_es_elegible(tenant):
    owner, _, cuenta = tenant
    padre = fh.crear_categoria(owner, "Alimentacion", "GASTO")
    fh.crear_categoria(owner, "Supermercado", "GASTO", parent_id=padre)
    cuerpo = _con_categoria(cuenta, padre)
    r = h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("origen", ["OTRO_TENANT", "INEXISTENTE"])
def test_categoria_ajena_o_inexistente_mismo_codigo_sin_revelar(tenant, origen):
    owner, _, cuenta = tenant
    if origen == "OTRO_TENANT":
        otro, _ = h.crear_tenant()
        cat = fh.crear_categoria(otro, "Ajena", "GASTO")
    else:
        cat = uuid.uuid4()
    cuerpo = _con_categoria(cuenta, cat)
    r = h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "CATEGORIA_NO_ELEGIBLE"
    _cero(owner, _hid(cuerpo))


@pytest.mark.parametrize("naturaleza", ["DEUDA", "DERECHO_COBRO", "INVERSION", "VALOR_ACTIVO"])
@pytest.mark.parametrize("ambito", ["GASTO", "INGRESO", "AMBOS"])
def test_matriz_c02_otras_naturalezas_solo_null(tenant, naturaleza, ambito):
    """AMBOS no significa 'cualquier naturaleza' (F05-D009 §23.2). Se invoca la
    guarda directamente porque VS-01 solo produce GASTO."""
    from app.api.elegibilidad_categoria import validar_seleccion_categoria

    owner, _, _ = tenant
    cat = fh.crear_categoria(owner, f"C {naturaleza} {ambito}", ambito)
    res = fh.en_transaccion(owner, lambda s: validar_seleccion_categoria(s, cat, naturaleza))
    assert res == "CATEGORIA_NO_ELEGIBLE"


@pytest.mark.parametrize(
    "naturaleza,ambito,esperado",
    [
        ("GASTO", "GASTO", None), ("GASTO", "AMBOS", None), ("GASTO", "INGRESO", "CATEGORIA_NO_ELEGIBLE"),
        ("INGRESO", "INGRESO", None), ("INGRESO", "AMBOS", None), ("INGRESO", "GASTO", "CATEGORIA_NO_ELEGIBLE"),
    ],
)
def test_matriz_c02_gasto_ingreso(tenant, naturaleza, ambito, esperado):
    from app.api.elegibilidad_categoria import validar_seleccion_categoria

    owner, _, _ = tenant
    cat = fh.crear_categoria(owner, f"M {naturaleza} {ambito}", ambito)
    assert fh.en_transaccion(owner, lambda s: validar_seleccion_categoria(s, cat, naturaleza)) == esperado


# ------------------------------------------------------------ C01 / AJ-01
def test_sin_categoria_explicita_persiste_null(tenant):
    owner, _, cuenta = tenant
    cuerpo = h.intencion(cuenta, categoria={"estado": "SIN_CATEGORIA"})
    r = h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["estado_categorial"] == "SIN_CATEGORIA"
    assert fh.categoria_del_efecto(owner, _hid(cuerpo)) == [(None,)]


def test_ausencia_es_no_capturada_legacy_y_no_sin_categoria(tenant):
    owner, _, cuenta = tenant
    cuerpo = h.intencion(cuenta)
    assert "categoria" not in cuerpo
    r = h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["estado_categorial"] == "NO_CAPTURADA_LEGACY"
    assert fh.categoria_del_efecto(owner, _hid(cuerpo)) == [(None,)]


@pytest.mark.parametrize(
    "valor",
    [None, {"estado": "NO_CAPTURADA_LEGACY"}, {"estado": "CATEGORIA"}, {"estado": "SIN_CATEGORIA", "categoria_id": str(uuid.uuid4())}],
)
def test_legacy_no_es_un_valor_enviable(tenant, valor):
    owner, _, cuenta = tenant
    cuerpo = h.intencion(cuenta, categoria=valor)
    r = h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 422
    _cero(owner, _hid(cuerpo))


# ------------------------------------------------------------ AJ-02 (C07)
def test_magnitud_obligatoria_bloquea_sin_mutacion_parcial(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Combustible", "GASTO")
    fh.crear_magnitud_categoria(owner, cat, obligatoria=True)
    cuerpo = _con_categoria(cuenta, cat)
    r = h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "CATEGORIA_REQUIERE_MAGNITUDES"
    _cero(owner, _hid(cuerpo))


def test_magnitud_no_obligatoria_no_bloquea(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Limpieza", "GASTO")
    fh.crear_magnitud_categoria(owner, cat, obligatoria=False)
    r = h.cliente(owner).post(URL, json=_con_categoria(cuenta, cat), headers=h.AUTH)
    assert r.status_code == 200, r.text


# ------------------------------------------------------------ identidad antes que guarda
def test_reintento_tras_commit_es_idempotente_aunque_la_categoria_se_desactive(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Ropa", "GASTO")
    cli = h.cliente(owner)
    cuerpo = _con_categoria(cuenta, cat)
    assert cli.post(URL, json=cuerpo, headers=h.AUTH).status_code == 200
    h.como_owner(owner, "UPDATE gapto.categorias_financieras SET enabled=false WHERE id=%s", (cat,))
    r = cli.post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["idempotente"] is True
    assert fh.categoria_del_efecto(owner, _hid(cuerpo)) == [(cat,)]


def test_misma_identidad_con_otra_categoria_no_es_idempotente(tenant):
    owner, _, cuenta = tenant
    a = fh.crear_categoria(owner, "A", "GASTO")
    b = fh.crear_categoria(owner, "B", "GASTO")
    cli = h.cliente(owner)
    cuerpo = _con_categoria(cuenta, a)
    assert cli.post(URL, json=cuerpo, headers=h.AUTH).status_code == 200
    otro = dict(cuerpo, categoria={"estado": "CATEGORIA", "categoria_id": str(b)})
    r = cli.post(URL, json=otro, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert fh.categoria_del_efecto(owner, _hid(cuerpo)) == [(a,)]


# ------------------------------------------------------------ concurrencia (WM 12C.1)
_MUTACIONES = {
    "DESACTIVAR": "UPDATE gapto.categorias_financieras SET enabled=false WHERE id=%s",
    "AMBITO_INGRESO": "UPDATE gapto.categorias_financieras SET ambito='INGRESO' WHERE id=%s",
}


@pytest.mark.parametrize("mutacion", sorted(_MUTACIONES))
@pytest.mark.parametrize("desenlace_b", ["COMMIT", "ROLLBACK"])
def test_orden_1_catalogo_primero_registro_espera_y_relee(tenant, mutacion, desenlace_b):
    """B (gestion del catalogo) modifica la categoria y retiene el lock de fila.
    El registro A debe QUEDAR ESPERANDO en su FOR SHARE; al terminar B relee:
      COMMIT   -> ya no es elegible -> CATEGORIA_NO_ELEGIBLE sin escritura;
      ROLLBACK -> sigue elegible    -> se registra con la categoria.
    Sin FOR SHARE, A no espera y decide sobre la fila anterior: el test falla."""
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, f"Concurrente {mutacion}", "GASTO")
    cli = h.cliente(owner)
    cuerpo = _con_categoria(cuenta, cat)
    salida: dict = {}
    b = fh.sesion_owner(owner)
    try:
        b.execute(_MUTACIONES[mutacion], (cat,))
        pid_b = fh.pid_servidor(b)
        hilo = threading.Thread(target=lambda: salida.update(r=cli.post(URL, json=cuerpo, headers=h.AUTH)))
        hilo.start()
        assert fh.esperar_bloqueo((pid_b,)), "el registro no espero el lock de la categoria"
        assert hilo.is_alive() and "r" not in salida
        b.execute(desenlace_b)
    finally:
        b.close()
    hilo.join(timeout=15)
    assert not hilo.is_alive()
    r = salida["r"]
    if desenlace_b == "COMMIT":
        assert r.status_code == 409 and r.json()["codigo"] == "CATEGORIA_NO_ELEGIBLE", r.text
        _cero(owner, _hid(cuerpo))
    else:
        assert r.status_code == 200, r.text
        assert fh.categoria_del_efecto(owner, _hid(cuerpo)) == [(cat,)]


@pytest.mark.parametrize("mutacion", sorted(_MUTACIONES))
def test_orden_2_registro_primero_catalogo_espera(tenant, mutacion):
    """El registro A toma FOR SHARE y queda retenido DESPUES de la guarda: una
    sesion C bloquea la fila del usuario (FOR UPDATE), que el INSERT del hecho
    necesita en FOR KEY SHARE. Con A retenido, B intenta modificar la
    categoria y debe QUEDAR ESPERANDO el FOR SHARE de A. Al liberar C, A
    confirma con la categoria (era elegible al validarla) y solo despues B
    aplica su cambio; la historia conserva la categoria (D-198)."""
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, f"Retenida {mutacion}", "GASTO")
    cli = h.cliente(owner)
    cuerpo = _con_categoria(cuenta, cat)
    salida: dict = {}
    c = fh.sesion_owner(owner)
    b = None
    hilo_b = None
    try:
        c.execute("SELECT id FROM gapto.usuarios WHERE id=%s FOR UPDATE", (owner,))
        pid_c = fh.pid_servidor(c)
        hilo_a = threading.Thread(target=lambda: salida.update(r=cli.post(URL, json=cuerpo, headers=h.AUTH)))
        hilo_a.start()
        assert fh.esperar_bloqueo((pid_c,)), "el registro no llego a retenerse tras la guarda"

        b = fh.sesion_owner(owner)
        pid_b = fh.pid_servidor(b)

        def _mutar():
            try:
                b.execute(_MUTACIONES[mutacion], (cat,))
                salida["b"] = "aplicada"
            except psycopg.Error as exc:  # pragma: no cover - diagnostico
                salida["b"] = type(exc).__name__

        hilo_b = threading.Thread(target=_mutar)
        hilo_b.start()
        assert fh.esperar_bloqueo((pid_c,), minimo=2), "la gestion del catalogo no espero el FOR SHARE"
        assert pid_b in fh.pids_esperando((pid_b,))
        assert "b" not in salida
        c.execute("COMMIT")
    finally:
        c.close()
    hilo_a.join(timeout=15)
    assert not hilo_a.is_alive()
    assert salida["r"].status_code == 200, salida["r"].text
    hilo_b.join(timeout=15)
    assert salida.get("b") == "aplicada"
    b.execute("COMMIT")
    b.close()
    assert fh.categoria_del_efecto(owner, _hid(cuerpo)) == [(cat,)]
