# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_152_f05_01_elegibilidad_categoria.py
# Ruta: tests/api/test_152_f05_01_elegibilidad_categoria.py
# Descripcion: Pruebas discriminantes de la guarda de elegibilidad categorial
#   de F05-01 (F05-D009 §23.2-§23.3 C-a; F05-D008 C01/C02/C04; mandato F05-01
#   backend v0.2, AJ-01/AJ-02):
#     - matriz C02 literal (AMBOS = GASTO + INGRESO, nunca otra naturaleza);
#     - owner, enabled y ambito releidos dentro de la transaccion;
#     - estados categoriales (CATEGORIA / SIN_CATEGORIA; desde v0.3.0 la
#       ausencia y `null` son 422);
#     - magnitud obligatoria sin informar bloquea sin mutacion parcial (C07;
#       desde v0.2.0 con el codigo definitivo MAGNITUD_OBLIGATORIA_AUSENTE);
#     - identidad antes que guarda (reintento idempotente con la categoria ya
#       deshabilitada);
#     - concurrencia en AMBOS ordenes con barrera explicita (WM 12C.1): registro
#       con FOR SHARE frente a desactivacion y frente a cambio de ambito.
#   Base local desechable 0001..0340 (estos tests confirman filas).
#
#   v0.1.1: los PID de las sesiones de barrera se leen con pg_backend_pid()
#   (fh.pid_servidor); `info.backend_pid` no es el PID real tras el proxy de
#   Neon. No cambia ninguna asercion ni el mecanismo observado.
#
#   v0.2.0 (F05-01, S6-C07; F05-D014 §28.2): se retira el bloqueo transitorio
#   CATEGORIA_REQUIERE_MAGNITUDES. La propiedad que protegia el test se
#   conserva (obligatoria sin informar -> 409 sin escritura) con el codigo
#   definitivo de C07. La bateria completa de C07 esta en test_158.
#
#   v0.3.0 (F05-01 S6-WIRE+UI (este mandato); F05 §26.2 AJ-03): la ausencia de
#   `categoria` deja de derivar un estado de compatibilidad: 422 sin hecho,
#   igual que `null`. El literal del estado retirado sigue sin ser enviable.
#
#   v0.4.0 (F05-01 P7 · HP7-01, decision de Moises; F05 §22.2 C04, §22.5
#   viñeta 4): el registro NO toma el advisory (CATEGORIAS, owner). Una sesion
#   del mismo owner lo retiene con la MISMA primitiva de los comandos del
#   catalogo (`tomar_advisory`) en una transaccion abierta; un registro con
#   categoria y otro «Sin categoría» completan sin esperar (ninguna sesion
#   bloqueada por el retenedor segun pg_blocking_pids y respuesta dentro de
#   un timeout acotado), con el advisory aun retenido. Discriminante del
#   mutante P04 (mutantes_f05_01.py). WM 12C.2: la propiedad ya se cumple en
#   c06d219 (test de composicion); P04 lo discrimina.
# Version: 0.4.0
# ============================================================

from __future__ import annotations

import threading
import time
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


def test_ausencia_de_categoria_es_422_y_no_sin_categoria(tenant):
    owner, _, cuenta = tenant
    cuerpo = h.intencion(cuenta)
    del cuerpo["categoria"]
    r = h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA", r.text
    _cero(owner, _hid(cuerpo))


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


# ------------------------------------------------------------ C07 (S6-C07)
def test_magnitud_obligatoria_bloquea_sin_mutacion_parcial(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Combustible", "GASTO")
    fh.crear_magnitud_categoria(owner, cat, obligatoria=True)
    cuerpo = _con_categoria(cuenta, cat)
    r = h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "MAGNITUD_OBLIGATORIA_AUSENTE"
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


# ------------------------------------------------------------------ HP7-01: el registro no toma el advisory
class _SesionDeCatalogo:
    """Adaptador minimo (`uno`) para invocar la primitiva real `tomar_advisory`
    de los comandos del catalogo sobre una conexion con transaccion abierta."""

    def __init__(self, conexion: psycopg.Connection) -> None:
        self.conexion = conexion

    def uno(self, sql: str, params: tuple | None = None):
        return self.conexion.execute(sql, params).fetchone()


def _bloqueados_por(retenedor: int) -> list[int]:
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        filas = mon.execute(
            "SELECT pid FROM pg_stat_activity WHERE datname = current_database() "
            "AND %s = ANY(pg_blocking_pids(pid))", (retenedor,)).fetchall()
    return [f[0] for f in filas]


@pytest.mark.parametrize("seleccion", ["CATEGORIA", "SIN_CATEGORIA"])
def test_el_registro_no_toma_el_advisory_del_catalogo(tenant, seleccion):
    """HP7-01 (§22.5 viñeta 4; C04): con el advisory (CATEGORIAS, owner)
    retenido por otra sesion del mismo owner, el registro completa sin esperar."""
    from app.categorias.repositorio import tomar_advisory

    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, f"Sin advisory {seleccion}", "GASTO")
    cuerpo = _con_categoria(cuenta, cat) if seleccion == "CATEGORIA" else h.intencion(cuenta)
    retenedor = fh.sesion_owner(owner)
    salida: dict = {}
    hilo = None
    try:
        tomar_advisory(_SesionDeCatalogo(retenedor))
        pid_r = fh.pid_servidor(retenedor)
        concedido = retenedor.execute(
            "SELECT count(*) FROM pg_locks WHERE pid = pg_backend_pid() AND locktype = 'advisory' AND granted"
        ).fetchone()[0]
        assert concedido == 1, "el retenedor no tiene el advisory del catalogo"
        cli = h.cliente(owner)
        hilo = threading.Thread(target=lambda: salida.update(r=cli.post(URL, json=cuerpo, headers=h.AUTH)))
        hilo.start()
        fin = time.monotonic() + 10.0
        esperando: list[int] = []
        while hilo.is_alive() and time.monotonic() < fin and not esperando:
            esperando = _bloqueados_por(pid_r)
            time.sleep(0.05)
        assert esperando == [], f"el registro espera al advisory del catalogo (pids {esperando})"
        hilo.join(timeout=max(0.0, fin - time.monotonic()))
        assert not hilo.is_alive(), "el registro no respondio con el advisory retenido"
        assert retenedor.execute("SELECT count(*) FROM pg_locks WHERE pid = pg_backend_pid() "
                                 "AND locktype = 'advisory' AND granted").fetchone()[0] == 1
    finally:
        retenedor.execute("ROLLBACK")
        retenedor.close()
        if hilo is not None:
            hilo.join(timeout=15)
    assert salida["r"].status_code == 200, salida["r"].text
    esperado = [(cat,)] if seleccion == "CATEGORIA" else [(None,)]
    assert fh.categoria_del_efecto(owner, _hid(cuerpo)) == esperado
