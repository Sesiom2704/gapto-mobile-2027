# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_196_f05_06_m2_devolucion.py
# Ruta: tests/api/test_196_f05_06_m2_devolucion.py
# Descripcion: Devolucion contextual D-194 (F05-06 M2-A §A5; F05 §51.2,
#   §51.4 criterio especifico de M2; lamina DEV v0.1). Con el rol real
#   gapto_runtime (adaptador HTTP) y RLS:
#     - oraculo Ropa 120/40 en el Resultado con el origen COMPLETA y con el
#       origen NO_DISPONIBLE (estado fisico completo);
#     - categoria «De la compra», conservada aunque este deshabilitada;
#     - abono «Todavía no» sin liquidez y «Registrar abono» posterior con
#       movimiento y conciliacion; «Ya cobrado» en la misma transaccion; sin
#       abono doble (YA_CONCILIADO);
#     - parciales acumuladas 40 + 60 y exceso +30 (EXCEDE_CAPACIDAD_REVERSIBLE
#       con «lo que queda»);
#     - repeticion idempotente y misma identidad con otra intencion;
#     - nunca INGRESO (wire, origen INGRESO y devolucion de una devolucion);
#     - relacion visible en los dos sentidos (Actividad y detalle);
#     - origen anulado despues (G-R1-A de F04-R1);
#     - P-DEV-01 (SOLO_MIO solo con COMPLETA de un unico actor propio),
#       P-DEV-05 (V3 con un unico efecto GASTO), R15 (una categoria);
#     - cuenta sin capacidad, fecha futura e IDs de otro owner sin efectos.
#   Reloj fijo 2026-10-10 (Madrid).
# Version: 0.1.0 (F05-06 M2-A §A5)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest

import f05_05_helpers as x
import f05_06_m2_helpers as m
import vs01_api_helpers as h
from app.api import errores_http as eh
from app.core.errores import CodigoError, ErrorMotor

D = decimal.Decimal
RESULTADO = "/v1/inicio/resultado-mes"


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = x.entorno()
    ropa = x.categoria(owner, "Ropa")
    return owner, actor, cli, cta, ahorro, ropa


def _cod(r):
    return r.json().get("codigo")


def _resultado(cli, fecha):
    r = cli.get(RESULTADO, params={"fecha": fecha}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _detalle(cli, hecho):
    r = cli.get(f"/v1/actividad/{hecho}", headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _contexto(cli, origen):
    r = cli.get(m.url_devoluciones(origen), headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _fisico(owner, dev):
    """(tipo_hecho, importe_total, efectos [(tipo, delta, estado, categoria)], atribuciones [(es_self, importe)],
    relaciones [(destino, tipo, importe)], movimientos [(cuenta, fecha, importe)])."""
    tipo = h.leer(owner, "SELECT t.codigo, h.importe_total FROM gapto.hechos_financieros h "
                         "JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id WHERE h.id=%s", (dev,))[0]
    efectos = h.leer(owner, "SELECT tipo_efecto, importe_delta, estado_atribucion, categoria_id FROM gapto.hecho_efectos "
                            "WHERE hecho_id=%s", (dev,))
    atrib = h.leer(owner, "SELECT af.tercero_id IS NULL, a.importe_atribuido FROM gapto.efecto_atribuciones a "
                          "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id "
                          "JOIN gapto.actores_financieros af ON af.id = a.actor_id WHERE e.hecho_id=%s", (dev,))
    rel = h.leer(owner, "SELECT hecho_destino_id, tipo_relacion, importe_relacionado FROM gapto.hecho_relaciones "
                        "WHERE hecho_origen_id=%s", (dev,))
    mov = h.leer(owner, "SELECT m.cuenta_id, m.fecha_movimiento, m.importe FROM gapto.hecho_movimientos_tesoreria hm "
                        "JOIN gapto.movimientos_tesoreria m ON m.id = hm.movimiento_tesoreria_id WHERE hm.hecho_id=%s",
                 (dev,))
    return tipo, efectos, atrib, rel, mov


# ------------------------------------------------------------------ oraculo Ropa 120/40
def test_oraculo_ropa_origen_completa(t):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa)
    version_origen = m.contar(owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id=%s", (origen,))
    ctx = _contexto(cli, origen)
    assert (ctx["disponible"], ctx["atribucion_propuesta"], ctx["tuya_disponible"]) == (True, "SOLO_MIO", True)
    assert (ctx["importe_total"], ctx["devuelto"], ctx["queda"], ctx["categoria"]) == ("120.00", "0.00", "120.00", "Ropa")
    assert ctx["cuenta_compra"]["cuenta_id"] == str(cta)

    c, r = m.devolver(cli, origen)
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["estado_atribucion"], j["abono"], j["devuelto"], j["queda"], j["idempotente"]) == (
        "COMPLETA", "PENDIENTE", "40.00", "80.00", False)
    dev = uuid.UUID(c["intencion_id"])
    tipo, efectos, atrib, rel, mov = _fisico(owner, dev)
    assert tipo == ("GASTO", D("40.0000"))
    assert efectos == [("GASTO", D("-40.0000"), "COMPLETA", ropa)]
    assert atrib == [(True, D("-40.0000"))]
    assert rel == [(origen, "DEVOLUCION_DE", D("40.0000"))]
    assert mov == []  # «Todavía no»: sin movimiento
    # La compra no cambia (D-DEV-05).
    assert m.contar(owner, "SELECT importe_total FROM gapto.hechos_financieros WHERE id=%s", (origen,)) == D("120.0000")
    assert m.contar(owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id=%s", (origen,)) == version_origen

    agosto, septiembre = _resultado(cli, "2026-08-31"), _resultado(cli, "2026-09-30")
    assert (agosto["gastos_propios"], agosto["resultado"]) == ("120.00", "-120.00")
    assert (septiembre["gastos_propios"], septiembre["resultado"]) == ("-40.00", "40.00")
    assert septiembre["sin_indicar"]["gastos"] == {"n": 0, "importe": "0.00"}


def test_oraculo_ropa_origen_no_disponible(t):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa, atribucion="SIN_INDICAR")
    ctx = _contexto(cli, origen)
    assert (ctx["atribucion_propuesta"], ctx["tuya_disponible"]) == ("SIN_INDICAR", False)

    antes = m.huella(owner)
    _, r = m.devolver(cli, origen, atribucion="SOLO_MIO")
    assert (r.status_code, _cod(r)) == (409, "DEVOLUCION_ATRIBUCION_NO_DEMOSTRABLE")
    assert m.huella(owner) == antes

    c, r = m.devolver(cli, origen, atribucion="SIN_INDICAR")
    assert r.status_code == 200, r.text
    assert r.json()["estado_atribucion"] == "NO_DISPONIBLE"
    _, efectos, atrib, _, _ = _fisico(owner, uuid.UUID(c["intencion_id"]))
    assert efectos == [("GASTO", D("-40.0000"), "NO_DISPONIBLE", ropa)] and atrib == []

    agosto, septiembre = _resultado(cli, "2026-08-31"), _resultado(cli, "2026-09-30")
    assert agosto["gastos_propios"] == "0.00" and agosto["sin_indicar"]["gastos"] == {"n": 1, "importe": "120.00"}
    assert septiembre["gastos_propios"] == "0.00"
    assert septiembre["sin_indicar"]["gastos"] == {"n": 1, "importe": "-40.00"}


def test_categoria_de_la_compra_aunque_este_deshabilitada(t):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa)
    x.desactivar_categoria(owner, ropa)
    c, r = m.devolver(cli, origen)
    assert r.status_code == 200, r.text
    assert _fisico(owner, uuid.UUID(c["intencion_id"]))[1][0][3] == ropa


# ------------------------------------------------------------------ abono
def test_pendiente_sin_liquidez_y_abono_posterior(t):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa)
    movs = m.contar(owner, "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE cuenta_id=%s", (cta,))
    c, r = m.devolver(cli, origen)
    dev = uuid.UUID(c["intencion_id"])
    assert m.contar(owner, "SELECT count(*) FROM gapto.movimientos_tesoreria WHERE cuenta_id=%s", (cta,)) == movs
    assert _detalle(cli, dev)["abono"] == "PENDIENTE"
    version = m.contar(owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id=%s", (dev,))

    ab, r = m.abonar(cli, dev, cta, fecha="2026-09-12")
    assert r.status_code == 200, r.text
    assert (r.json()["importe"], r.json()["abono"], r.json()["idempotente"]) == ("40.00", "COBRADO", False)
    tipo, efectos, atrib, rel, mov = _fisico(owner, dev)
    assert mov == [(cta, dt.date(2026, 9, 12), D("40.0000"))]
    assert efectos == [("GASTO", D("-40.0000"), "COMPLETA", ropa)] and rel[0][2] == D("40.0000")  # no cambia
    conc = h.leer(owner, "SELECT importe_asignado FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id=%s", (dev,))
    assert conc == [(D("40.0000"),)]
    assert m.contar(owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id=%s", (dev,)) == version + 1
    assert _detalle(cli, dev)["abono"] == "COBRADO"

    # Repeticion de la misma intencion: idempotente; otra intencion: no hay abono doble.
    r = cli.post(m.url_abono(dev), json=ab, headers=h.AUTH)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    antes = m.huella(owner)
    _, r = m.abonar(cli, dev, cta)
    assert (r.status_code, _cod(r)) == (409, "YA_CONCILIADO")
    assert m.huella(owner) == antes
    otro = dict(ab, fecha="2026-09-13")
    r = cli.post(m.url_abono(dev), json=otro, headers=h.AUTH)
    assert (r.status_code, _cod(r)) == (409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")


def test_ya_cobrado_en_la_misma_transaccion(t):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa)
    c, r = m.devolver(cli, origen, abono=m.cobrado(cta))
    assert r.status_code == 200 and r.json()["abono"] == "COBRADO", r.text
    dev = uuid.UUID(c["intencion_id"])
    assert _fisico(owner, dev)[4] == [(cta, dt.date(2026, 9, 10), D("40.0000"))]
    _, r = m.abonar(cli, dev, cta)
    assert (r.status_code, _cod(r)) == (409, "YA_CONCILIADO")


def test_abono_sobre_algo_que_no_es_devolucion(t):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa)
    antes = m.huella(owner)
    _, r = m.abonar(cli, origen, cta)
    assert (r.status_code, _cod(r)) == (409, "HECHO_NO_ES_DEVOLUCION")
    assert m.huella(owner) == antes


# ------------------------------------------------------------------ limite acumulado
def test_parciales_40_mas_60_y_exceso_30(t):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa)
    assert m.devolver(cli, origen, importe="40.00")[1].json()["queda"] == "80.00"
    assert m.devolver(cli, origen, importe="60.00")[1].json()["queda"] == "20.00"
    antes = m.huella(owner)
    _, r = m.devolver(cli, origen, importe="30.00")
    assert (r.status_code, _cod(r)) == (409, "EXCEDE_CAPACIDAD_REVERSIBLE")
    assert r.json()["detalle"] == {"queda": "20.00"} and "20,00 €" in r.json()["mensaje"]
    assert m.huella(owner) == antes
    ctx = _contexto(cli, origen)
    assert (ctx["devuelto"], ctx["queda"], ctx["neto"], len(ctx["devoluciones"])) == ("100.00", "20.00", "20.00", 2)
    assert m.devolver(cli, origen, importe="20.00")[1].json()["queda"] == "0.00"
    ctx = _contexto(cli, origen)
    assert (ctx["disponible"], ctx["motivo"]) == (False, "EXCEDE_CAPACIDAD_REVERSIBLE")


# ------------------------------------------------------------------ idempotencia
def test_repeticion_idempotente_y_otra_intencion(t):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa)
    for abono in ({"estado": "PENDIENTE"}, m.cobrado(cta)):
        c, r1 = m.devolver(cli, origen, importe="10.00", abono=abono)
        assert r1.status_code == 200, r1.text
        antes = m.huella(owner)
        r2 = cli.post(m.url_devoluciones(origen), json=c, headers=h.AUTH)
        assert r2.status_code == 200 and r2.json()["idempotente"] is True
        assert r2.json()["hecho_id"] == r1.json()["hecho_id"] and m.huella(owner) == antes
        for cambio in ({"importe": "11.00"}, {"fecha_hecho": "2026-09-11"}, {"nota": "otra"},
                       {"atribucion": "SIN_INDICAR"},
                       {"abono": m.cobrado(cta) if abono["estado"] == "PENDIENTE" else {"estado": "PENDIENTE"}}):
            r = cli.post(m.url_devoluciones(origen), json={**c, **cambio}, headers=h.AUTH)
            assert (r.status_code, _cod(r)) == (409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"), cambio
            assert m.huella(owner) == antes
    # La misma identidad con otro origen tampoco es la misma intencion.
    otro = m.compra(cli, cta, categoria_id=ropa)
    r = cli.post(m.url_devoluciones(otro), json=c, headers=h.AUTH)
    assert (r.status_code, _cod(r)) == (409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")


# ------------------------------------------------------------------ nunca INGRESO
def test_nunca_ingreso(t):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa)
    antes = m.huella(owner)
    for extra in ({"tipo": "INGRESO"}, {"naturaleza": "INGRESO"}, {"tipo_efecto_devolucion": "INGRESO"}):
        r = cli.post(m.url_devoluciones(origen), json={**m.cuerpo(), **extra}, headers=h.AUTH)
        assert r.status_code == 422, extra
    assert m.huella(owner) == antes
    ingreso = x.ingreso(cli, cta, fecha="2026-09-01")
    antes = m.huella(owner)  # el alta del ingreso es legitima; la devolucion rechazada no escribe nada
    _, r = m.devolver(cli, ingreso)
    assert (r.status_code, _cod(r)) == (409, "DEVOLUCION_ORIGEN_NO_GASTO")
    assert m.huella(owner) == antes
    c, r = m.devolver(cli, origen)
    dev = uuid.UUID(c["intencion_id"])
    # Devolver una devolucion tampoco: su GASTO es negativo.
    _, r = m.devolver(cli, dev)
    assert (r.status_code, _cod(r)) == (409, "DEVOLUCION_ORIGEN_NO_GASTO")
    assert m.contar(owner, "SELECT count(*) FROM gapto.hecho_efectos e JOIN gapto.hecho_relaciones r "
                           "ON r.hecho_origen_id = e.hecho_id WHERE e.tipo_efecto = 'INGRESO'") == 0
    assert _fisico(owner, dev)[0][0] == "GASTO"
    assert "ingreso" not in str(_contexto(cli, origen)).lower()


# ------------------------------------------------------------------ relacion en los dos sentidos
def test_relacion_visible_en_los_dos_sentidos(t):
    owner, _, cli, cta, _, ropa = t
    tercero = x.tercero(cli, "Zara")
    cuerpo_compra = h.intencion(cta, fecha_hecho=m.FECHA_COMPRA, importe="120.00", concepto="Abrigo",
                                categoria={"estado": "CATEGORIA", "categoria_id": str(ropa)}, tercero_id=str(tercero))
    assert cli.post("/v1/intenciones/gasto-pagado", json=cuerpo_compra, headers=h.AUTH).status_code == 200
    origen = uuid.UUID(cuerpo_compra["intencion_id"])
    c, _ = m.devolver(cli, origen)
    dev = uuid.UUID(c["intencion_id"])

    d_origen = _detalle(cli, origen)
    assert d_origen["devolucion_de"] is None and d_origen["abono"] is None
    assert d_origen["devoluciones"] == {"items": [{"hecho_id": str(dev), "fecha_hecho": m.FECHA_DEVOLUCION,
                                                   "importe": "40.00", "abono": "PENDIENTE"}],
                                        "devuelto": "40.00", "queda": "80.00", "neto": "80.00"}
    d_dev = _detalle(cli, dev)
    assert d_dev["devolucion_de"] == {"hecho_id": str(origen), "nota": "Abrigo", "fecha_hecho": m.FECHA_COMPRA,
                                      "tercero": "Zara"}
    assert d_dev["abono"] == "PENDIENTE" and d_dev["devoluciones"] is None
    filas = {f["id"]: f for f in cli.get("/v1/actividad", headers=h.AUTH).json()["filas"]}
    assert filas[str(dev)]["devolucion_de"]["hecho_id"] == str(origen) and filas[str(dev)]["abono"] == "PENDIENTE"
    assert filas[str(origen)]["devolucion_de"] is None
    assert filas[str(dev)]["tipo"] == "GASTO" and filas[str(dev)]["importe_total"] == "40.00"


# ------------------------------------------------------------------ origen anulado despues (G-R1-A)
def test_origen_anulado_despues_g_r1_a(t):
    owner, actor, cli, cta, _, ropa = t
    origen = x.hecho_motor(owner, [("GASTO", "120", "COMPLETA", ropa, [(actor, "120")])], fecha=m.FECHA_COMPRA)
    c, r = m.devolver(cli, origen)
    assert r.status_code == 200, r.text
    dev = uuid.UUID(c["intencion_id"])
    exc = m.anular_op03(owner, origen)
    assert isinstance(exc, ErrorMotor) and exc.codigo is CodigoError.HECHO_CON_REALIDAD_ASOCIADA
    assert exc.contexto_extra["motivo"] == "DEPENDENCIAS_ACTIVAS"
    assert exc.contexto_extra["dependientes"] == [{"hecho_id": str(dev), "tipo_relacion": "DEVOLUCION_DE"}]
    assert eh.traducir_error_motor(exc.codigo)[0] == 409
    assert not isinstance(m.anular_op03(owner, dev), ErrorMotor)
    antes = m.huella(owner)
    _, r = m.abonar(cli, dev, cta)
    assert (r.status_code, _cod(r)) == (409, "DEVOLUCION_NO_ACTIVA")
    assert m.huella(owner) == antes
    assert not isinstance(m.anular_op03(owner, origen), ErrorMotor)
    ctx = _contexto(cli, origen)
    assert (ctx["disponible"], ctx["motivo"]) == (False, "DEVOLUCION_ORIGEN_NO_ACTIVO")
    antes = m.huella(owner)
    _, r = m.devolver(cli, origen)
    assert (r.status_code, _cod(r)) == (409, "DEVOLUCION_ORIGEN_NO_ACTIVO")
    assert m.huella(owner) == antes


# ------------------------------------------------------------------ P-DEV-01 / P-DEV-05 / R15
@pytest.mark.parametrize("caso", ["dos_actores", "otro_actor", "parcial", "no_disponible"])
def test_solo_mio_exige_completa_de_un_unico_actor_propio(t, caso):
    owner, actor, cli, cta, _, ropa = t
    otro = h.crear_actor_tercero(owner)
    efecto = {"dos_actores": ("COMPLETA", [(actor, "60"), (otro, "60")]),
              "otro_actor": ("COMPLETA", [(otro, "120")]),
              "parcial": ("PARCIAL", [(actor, "60")]),
              "no_disponible": ("NO_DISPONIBLE", [])}[caso]
    origen = x.hecho_motor(owner, [("GASTO", "120", efecto[0], ropa, efecto[1])], fecha=m.FECHA_COMPRA)
    assert _contexto(cli, origen)["tuya_disponible"] is False
    antes = m.huella(owner)
    _, r = m.devolver(cli, origen, atribucion="SOLO_MIO")
    assert (r.status_code, _cod(r)) == (409, "DEVOLUCION_ATRIBUCION_NO_DEMOSTRABLE")
    assert m.huella(owner) == antes
    assert m.devolver(cli, origen, atribucion="SIN_INDICAR")[1].status_code == 200


def test_v3_solo_con_un_unico_efecto_gasto(t):
    owner, actor, cli, cta, _, ropa = t
    dos = [("GASTO", "70", "COMPLETA", ropa, [(actor, "70")]), ("GASTO", "50", "COMPLETA", ropa, [(actor, "50")])]
    nativo, v3 = (x.hecho_motor(owner, dos, fecha=m.FECHA_COMPRA) for _ in range(2))
    m.marcar_v3(owner, v3)
    antes = m.huella(owner)
    _, r = m.devolver(cli, v3)
    assert (r.status_code, _cod(r)) == (409, "DEVOLUCION_ORIGEN_V3_VARIOS_EFECTOS")
    assert m.huella(owner) == antes
    assert _contexto(cli, v3)["motivo"] == "DEVOLUCION_ORIGEN_V3_VARIOS_EFECTOS"
    assert m.devolver(cli, nativo)[1].status_code == 200  # la guarda es solo de V3
    uno = x.hecho_motor(owner, [("GASTO", "120", "COMPLETA", ropa, [(actor, "120")])], fecha=m.FECHA_COMPRA)
    m.marcar_v3(owner, uno)
    assert m.devolver(cli, uno)[1].status_code == 200


def test_varias_categorias_fuera(t):
    owner, actor, cli, cta, _, ropa = t
    deporte = x.categoria(owner, "Deporte")
    origen = x.hecho_motor(owner, [("GASTO", "70", "NO_DISPONIBLE", ropa, []),
                                   ("GASTO", "50", "NO_DISPONIBLE", deporte, [])], fecha=m.FECHA_COMPRA)
    _, r = m.devolver(cli, origen, atribucion="SIN_INDICAR")
    assert (r.status_code, _cod(r)) == (409, "DEVOLUCION_ORIGEN_MULTICATEGORIA")


# ------------------------------------------------------------------ cuenta, fecha y owner
def test_cuenta_sin_capacidad_sin_escritura(t):
    owner, actor, cli, cta, _, ropa = t
    sin = h.crear_cuenta(owner, [(actor, 100)], capacidades=("RECIBIR_INGRESO",))
    origen = m.compra(cli, cta, categoria_id=ropa)
    antes = m.huella(owner)
    _, r = m.devolver(cli, origen, abono=m.cobrado(sin))
    assert (r.status_code, _cod(r)) == (409, "CUENTA_SIN_CAPACIDAD")
    assert r.json()["detalle"]["operacion"] == "ABONO_DEVOLUCION" and "ingreso" not in r.json()["mensaje"].lower()
    assert m.huella(owner) == antes
    c, _ = m.devolver(cli, origen)
    antes = m.huella(owner)
    _, r = m.abonar(cli, uuid.UUID(c["intencion_id"]), sin)
    assert (r.status_code, _cod(r)) == (409, "CUENTA_SIN_CAPACIDAD")
    assert m.huella(owner) == antes


def test_fecha_futura(t):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa)
    antes = m.huella(owner)
    for kw in ({"fecha": "2026-10-11"}, {"abono": m.cobrado(cta, "2026-10-11")}):
        _, r = m.devolver(cli, origen, **kw)
        assert (r.status_code, _cod(r)) == (422, "FECHA_FUTURA"), kw
    assert m.huella(owner) == antes


def test_ids_de_otro_owner_sin_efectos(t):
    owner, _, cli, cta, _, ropa = t
    origen = m.compra(cli, cta, categoria_id=ropa)
    c, _ = m.devolver(cli, origen)
    dev = uuid.UUID(c["intencion_id"])
    otro_owner, otro_actor, otro_cli, otra_cta, _ = x.entorno()
    antes, antes_otro = m.huella(owner), m.huella(otro_owner)
    assert otro_cli.get(m.url_devoluciones(origen), headers=h.AUTH).status_code == 404
    _, r = m.devolver(otro_cli, origen)
    assert (r.status_code, _cod(r)) == (404, "AGREGADO_NO_ENCONTRADO")
    _, r = m.abonar(otro_cli, dev, otra_cta)
    assert (r.status_code, _cod(r)) == (404, "AGREGADO_NO_ENCONTRADO")
    # La cuenta ajena tampoco sirve para el abono propio.
    _, r = m.abonar(cli, dev, otra_cta)
    assert (r.status_code, _cod(r)) == (422, "CUENTA_DESCONOCIDA")
    assert (m.huella(owner), m.huella(otro_owner)) == (antes, antes_otro)
