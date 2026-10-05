# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_162_f05_01_magnitudes_comandos.py
# Ruta: tests/api/test_162_f05_01_magnitudes_comandos.py
# Descripcion: Comandos y lecturas de S7-MAG (F05-D020, expediente F05 §34;
#   mandato S7-MAG backend v0.1 §5): a) asociar existente, b) alta rapida,
#   c) obligatoriedad, d) retirar con compactacion, e) reordenar, f)
#   renombrar, g) deshabilitar con confirmacion de impacto, h) rehabilitar;
#   i) GET /v1/magnitudes; j) asociacion_id en GET /v1/categorias.
#   Idempotencias, codigos y orden de evaluacion, 422 del DTO, P1, D-S7-03,
#   R-08, R-09, invariante de orden D-S7-04, auditoria D-MAG-09 y tenant
#   (AJ-S7MAG-04). Se ejecutan bajo gapto_runtime con RLS (adaptador HTTP);
#   los fixtures se crean como gapto_owner. Base local desechable 0001..0340.
# Version: 0.1.0 (F05-01 S7-MAG)
# Version: 0.2.0 (F05-01 S7-MAG correctivo AJ-S7MAGIMPL-02): identidad derivada
#   de la asociacion del alta rapida, uuid5(magnitud_id, "asociacion:<cat>"):
#   (a) alta -> retirar -> asociar EXISTENTE con la misma obligatoriedad ->
#   reintento del alta = IDENTIDAD_REUTILIZADA sin mutaciones; (b) reintento
#   inmediato idempotente con el mismo id; (c) tras cambiar la obligatoriedad
#   -> 409; (d) tras reordenar -> idempotente (D39: el orden no cuenta); (e)
#   EXISTENTE genera ids aleatorios; (f) el id del alta es el derivado.
# Version: 0.3.0 (F05-01 P7 · N7, S7-MAG-BE-01; AJ-P7BAT-04, Q2): confirmacion
#   de un impacto que ya no existe. Magnitud obligatoria en una categoria
#   (impacto [cat]) -> se lee el impacto -> se retira la asociacion (impacto
#   vigente []) -> deshabilitar con confirmacion_impacto=[cat] -> 409
#   MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION con categorias_no_capturables
#   = [], magnitud sin cambios (enabled, row_version) y sin auditoria nueva.
#   Discriminante del mutante P02 (mutantes_f05_01.py).
# ============================================================

from __future__ import annotations

import json
import uuid

import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h

URL_REGISTRO = "/v1/intenciones/gasto-pagado"


@pytest.fixture()
def ctx():
    owner, actor = h.crear_tenant()
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    return owner, cuenta, h.cliente(owner)


def _post(cli, ruta: str, cuerpo: dict):
    return cli.post(ruta, json=cuerpo, headers=h.AUTH)


def _asociar(cli, cat, mid, obligatoria):
    return _post(cli, f"/v1/categorias/{cat}/magnitudes",
                 {"origen": "EXISTENTE", "magnitud_id": str(mid), "obligatoria": obligatoria})


def _nueva(cli, cat, mid, nombre, obligatoria=True, unidad="h", precision=0):
    return _post(cli, f"/v1/categorias/{cat}/magnitudes", {"origen": "NUEVA", "obligatoria": obligatoria, "magnitud": {
        "magnitud_id": str(mid), "nombre": nombre, "unidad_default": unidad, "precision_decimales": precision}})


def _obligatoria(cli, cat, aid, mid, actual, nueva):
    return _post(cli, f"/v1/categorias/{cat}/magnitudes/{aid}/obligatoria",
                 {"magnitud_id": str(mid), "obligatoria_actual": actual, "obligatoria": nueva})


def _retirar(cli, cat, aid, mid, actual):
    return _post(cli, f"/v1/categorias/{cat}/magnitudes/{aid}/retirar",
                 {"magnitud_id": str(mid), "obligatoria_actual": actual})


def _reordenar(cli, cat, filas):
    return _post(cli, f"/v1/categorias/{cat}/magnitudes/reordenar", {"asociaciones": [
        {"asociacion_id": str(a), "magnitud_id": str(m), "orden": o, "obligatoria": ob} for a, m, ob, o in filas]})


def _nodo(cli, cat) -> dict:
    [n] = [c for c in cli.get("/v1/categorias", headers=h.AUTH).json()["categorias"] if c["id"] == str(cat)]
    return n


def _catalogo(cli) -> dict:
    r = cli.get("/v1/magnitudes", headers=h.AUTH)
    assert r.status_code == 200, r.text
    return {m["id"]: m for m in r.json()["magnitudes"]}


def _cat_rv(owner, cat) -> int:
    return fh.rv(owner, cat)


# ------------------------------------------------------------------ a) asociar existente
def test_asociar_existente_en_posicion_n_con_auditoria(ctx):
    owner, _, cli = ctx
    cat = fh.crear_categoria(owner, "Luz")
    m1, m2 = h.crear_magnitud(owner, "Consumo"), h.crear_magnitud(owner, "Potencia")
    rv_cat = _cat_rv(owner, cat)
    r1 = _asociar(cli, cat, m1, True)
    assert r1.status_code == 200, r1.text
    r2 = _asociar(cli, cat, m2, False)
    js = r2.json()
    assert js["idempotente"] is False and js["asociacion"]["orden"] == 1 and js["asociacion"]["obligatoria"] is False
    assert js["magnitud"]["id"] == str(m2) and js["categoria_id"] == str(cat)
    assert [(m, o, n) for _, m, o, n in h.asociaciones_persistidas(owner, cat)] == [(m1, True, 0), (m2, False, 1)]
    aud = [(t, a, mo) for t, _, a, mo, *_ in h.auditorias_mag(owner)]
    assert aud == [("categoria_magnitudes", "CREAR", "F05-01 MAG_ASOCIAR")] * 2
    assert _cat_rv(owner, cat) == rv_cat  # D-MAG-04: la categoria no cambia de version


def test_asociar_existente_idempotente_y_ya_existe(ctx):
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Agua"), h.crear_magnitud(owner)
    assert _asociar(cli, cat, mid, False).status_code == 200
    r = _asociar(cli, cat, mid, False)
    assert r.status_code == 200 and r.json()["idempotente"] is True and r.json()["modificadas"] == []
    r = _asociar(cli, cat, mid, True)
    assert r.status_code == 409 and r.json()["codigo"] == "ASOCIACION_YA_EXISTE"
    assert len(h.asociaciones_persistidas(owner, cat)) == 1 and len(h.auditorias_mag(owner)) == 1


def test_asociar_en_categoria_deshabilitada_p1(ctx):
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Apagada", enabled=False), h.crear_magnitud(owner)
    r = _asociar(cli, cat, mid, True)
    assert r.status_code == 200, r.text


def test_asociar_magnitud_deshabilitada_d_s7_03(ctx):
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Gas"), h.crear_magnitud(owner, enabled=False)
    assert _nodo(cli, cat)["capturable"] is True
    r = _asociar(cli, cat, mid, True)
    assert r.status_code == 200, r.text
    assert r.json()["magnitud"]["enabled"] is False  # asociar no reactiva nada
    nodo = _nodo(cli, cat)
    assert nodo["capturable"] is False and nodo["motivo_no_capturable"] == "MAGNITUD_OBLIGATORIA_NO_DISPONIBLE"


def test_asociar_normaliza_orden_previo_no_contiguo(ctx):
    owner, _, cli = ctx
    cat = fh.crear_categoria(owner, "Coche")
    a = h.crear_asociacion(owner, cat, h.crear_magnitud(owner, "A"), obligatoria=False, orden=3)
    b = h.crear_asociacion(owner, cat, h.crear_magnitud(owner, "B"), obligatoria=False, orden=7)
    c = h.crear_magnitud(owner, "C")
    r = _asociar(cli, cat, c, True)
    assert r.status_code == 200 and r.json()["asociacion"]["orden"] == 2
    assert [(i, o) for i, _, _, o in h.asociaciones_persistidas(owner, cat)][:2] == [(a, 0), (b, 1)]
    motivos = [mo for _, _, _, mo, *_ in h.auditorias_mag(owner)]
    assert motivos == ["F05-01 MAG_ORDEN", "F05-01 MAG_ORDEN", "F05-01 MAG_ASOCIAR"]


def test_asociar_capacidad_de_orden_agotada_es_entrada_invalida(ctx):
    owner, _, cli = ctx
    cat = fh.crear_categoria(owner, "Llena")
    # Dos sentencias: la RLS WITH CHECK de categoria_magnitudes no ve filas de la misma sentencia.
    h.como_owner(owner, "INSERT INTO gapto.magnitudes (id, owner_user_id, nombre, unidad_default, precision_decimales) "
                        "SELECT gen_random_uuid(), %s, 'm' || g, 'u', 0 FROM generate_series(0, 32767) g", (owner,))
    h.como_owner(owner, "INSERT INTO gapto.categoria_magnitudes (categoria_id, magnitud_id, orden) "
                        "SELECT %s, id, substr(nombre, 2)::int FROM gapto.magnitudes WHERE owner_user_id = %s",
                 (cat, owner))
    r = _asociar(cli, cat, h.crear_magnitud(owner, "Una mas"), False)
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA", r.text
    assert h.auditorias_mag(owner) == []


# ------------------------------------------------------------------ b) alta rapida
def test_alta_rapida_crea_magnitud_y_asociacion_en_un_comando(ctx):
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Trabajo"), uuid.uuid4()
    r = _nueva(cli, cat, mid, "  Horas   extra ", unidad=" h ", precision=0)
    assert r.status_code == 200, r.text
    js = r.json()
    assert js["magnitud"] == {"id": str(mid), "nombre": "Horas extra", "unidad_default": "h",
                              "precision_decimales": 0, "enabled": True, "row_version": 1}
    assert js["asociacion"]["magnitud_id"] == str(mid) and js["asociacion"]["orden"] == 0
    assert set(js["modificadas"]) == {str(mid), js["asociacion"]["asociacion_id"]}
    aud = h.auditorias_mag(owner)
    assert [(t, a, mo) for t, _, a, mo, *_ in aud] == [
        ("categoria_magnitudes", "CREAR", "F05-01 MAG_ASOCIAR"), ("magnitudes", "CREAR", "F05-01 MAG_ALTA")]
    assert len({fila[4] for fila in aud}) == 1  # mismo request_id


def test_alta_rapida_idempotente_y_reutilizada(ctx):
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Ocio"), uuid.uuid4()
    assert _nueva(cli, cat, mid, "Horas").status_code == 200
    r = _nueva(cli, cat, mid, "Horas")
    assert r.status_code == 200 and r.json()["idempotente"] is True
    for cambio in ({"nombre": "Otra"}, {"unidad": "min"}, {"precision": 1}, {"obligatoria": False}):
        kw = {"nombre": "Horas", **cambio}
        r = _nueva(cli, cat, mid, kw.pop("nombre"), **kw)
        assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION", cambio
    # Tras evolucionar (row_version 2), la repeticion exacta ya no es idempotente (AJ-S4-05).
    assert _post(cli, f"/v1/magnitudes/{mid}/renombrar", {"nombre": "Horas!", "row_version": 1}).status_code == 200
    r = _nueva(cli, cat, mid, "Horas!")
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert len(h.asociaciones_persistidas(owner, cat)) == 1


def test_alta_rapida_identidad_de_otro_owner_no_se_revela(ctx):
    owner, _, cli = ctx
    otro, _ = h.crear_tenant()
    ajena = h.crear_magnitud(otro, "Ajena")
    cat = fh.crear_categoria(owner, "Propia")
    r = _nueva(cli, cat, ajena, "Ajena")
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert "detalle" not in r.json() and h.asociaciones_persistidas(owner, cat) == []
    assert h.auditorias_mag(owner) == []


def _derivado(mid, cat) -> str:
    return str(uuid.uuid5(mid, f"asociacion:{cat}"))


def test_alta_rapida_asociacion_id_derivado_y_reintento_inmediato(ctx):
    """2.5 (b) y (f)."""
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Trabajo"), uuid.uuid4()
    r = _nueva(cli, cat, mid, "Horas")
    assert r.status_code == 200 and r.json()["asociacion"]["asociacion_id"] == _derivado(mid, cat), r.text
    assert [str(i) for i, *_ in h.asociaciones_persistidas(owner, cat)] == [_derivado(mid, cat)]
    r2 = _nueva(cli, cat, mid, "Horas")
    assert r2.status_code == 200 and r2.json()["idempotente"] is True
    assert r2.json()["asociacion"]["asociacion_id"] == _derivado(mid, cat)


def test_alta_rapida_reintento_tras_retirar_y_reasociar_es_reutilizada(ctx):
    """2.5 (a): contraejemplo AJ-S7MAGIMPL-02 (A2 != A por construccion)."""
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Trabajo"), uuid.uuid4()
    assert _nueva(cli, cat, mid, "Horas", obligatoria=True).status_code == 200
    assert _retirar(cli, cat, _derivado(mid, cat), mid, True).status_code == 200
    r = _asociar(cli, cat, mid, True)
    assert r.status_code == 200 and r.json()["asociacion"]["asociacion_id"] != _derivado(mid, cat)
    antes = (h.asociaciones_persistidas(owner, cat), h.magnitud_persistida(owner, mid), len(h.auditorias_mag(owner)))
    r = _nueva(cli, cat, mid, "Horas", obligatoria=True)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION", r.text
    assert (h.asociaciones_persistidas(owner, cat), h.magnitud_persistida(owner, mid),
            len(h.auditorias_mag(owner))) == antes


def test_alta_rapida_reintento_tras_cambiar_obligatoriedad_es_reutilizada(ctx):
    """2.5 (c)."""
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Luz"), uuid.uuid4()
    assert _nueva(cli, cat, mid, "Horas", obligatoria=False).status_code == 200
    assert _obligatoria(cli, cat, _derivado(mid, cat), mid, False, True).status_code == 200
    r = _nueva(cli, cat, mid, "Horas", obligatoria=False)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"


def test_alta_rapida_reintento_tras_reordenar_sigue_idempotente(ctx):
    """2.5 (d): el orden no forma parte del criterio (D39)."""
    owner, _, cli = ctx
    cat = fh.crear_categoria(owner, "Coche")
    otra = h.crear_magnitud(owner, "Litros")
    a_otra = h.crear_asociacion(owner, cat, otra, obligatoria=False, orden=0)
    mid = uuid.uuid4()
    assert _nueva(cli, cat, mid, "Horas", obligatoria=True).status_code == 200
    derivado = uuid.UUID(_derivado(mid, cat))
    r = _reordenar(cli, cat, [(derivado, mid, True, 1), (a_otra, otra, False, 0)])
    assert r.status_code == 200 and not r.json()["idempotente"], r.text
    r = _nueva(cli, cat, mid, "Horas", obligatoria=True)
    assert r.status_code == 200 and r.json()["idempotente"] is True, r.text
    assert r.json()["asociacion"]["orden"] == 0


def test_asociar_existente_genera_identidades_aleatorias(ctx):
    """2.5 (e)."""
    owner, _, cli = ctx
    c1, c2 = fh.crear_categoria(owner, "Uno"), fh.crear_categoria(owner, "Dos")
    mid = h.crear_magnitud(owner, "Compartida")
    ids = [_asociar(cli, c, mid, False).json()["asociacion"]["asociacion_id"] for c in (c1, c2)]
    assert ids[0] != ids[1]
    assert ids[0] != _derivado(mid, c1) and ids[1] != _derivado(mid, c2)


@pytest.mark.parametrize("existente_enabled", [True, False])
def test_alta_rapida_nombre_duplicado_normalizado(ctx, existente_enabled):
    owner, _, cli = ctx
    cat = fh.crear_categoria(owner, "Hogar")
    previa = h.crear_magnitud(owner, "Consumo eléctrico", enabled=existente_enabled)
    r = _nueva(cli, cat, uuid.uuid4(), "  CONSUMO   electrico ")
    assert r.status_code == 409 and r.json()["codigo"] == "MAGNITUD_NOMBRE_DUPLICADO"
    assert r.json()["detalle"] == {"magnitud_id": str(previa), "enabled": existente_enabled}
    assert h.asociaciones_persistidas(owner, cat) == [] and h.auditorias_mag(owner) == []


def test_alta_rapida_nombre_de_otro_owner_no_colisiona(ctx):
    owner, _, cli = ctx
    otro, _ = h.crear_tenant()
    h.crear_magnitud(otro, "Horas")
    r = _nueva(cli, fh.crear_categoria(owner, "X"), uuid.uuid4(), "Horas")
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ c) obligatoriedad
def test_cambiar_obligatoria_idempotencia_e_identidad(ctx):
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Luz"), h.crear_magnitud(owner)
    aid = h.crear_asociacion(owner, cat, mid, obligatoria=False)
    r = _obligatoria(cli, cat, aid, mid, False, True)
    assert r.status_code == 200 and r.json()["asociacion"]["obligatoria"] is True, r.text
    assert [(a, mo) for _, _, a, mo, *_ in h.auditorias_mag(owner)] == [("ACTUALIZAR", "F05-01 MAG_OBLIGATORIA")]
    r = _obligatoria(cli, cat, aid, mid, True, True)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    otra = h.crear_magnitud(owner)
    for args in ((uuid.uuid4(), mid, True), (aid, otra, True), (aid, mid, False)):
        r = _obligatoria(cli, cat, args[0], args[1], args[2], False)
        assert r.status_code == 409 and r.json()["codigo"] == "ASOCIACION_NO_EXISTE", args
    assert len(h.auditorias_mag(owner)) == 1


def test_opcional_a_obligatoria_con_hechos_previos_no_revalida_r08(ctx):
    owner, cuenta, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Combustible"), h.crear_magnitud(owner)
    aid = h.crear_asociacion(owner, cat, mid, obligatoria=False)
    cuerpo = h.intencion(cuenta, categoria={"estado": "CATEGORIA", "categoria_id": str(cat)})
    assert cli.post(URL_REGISTRO, json=cuerpo, headers=h.AUTH).status_code == 200
    hid = uuid.UUID(cuerpo["intencion_id"])
    antes = h.leer(owner, "SELECT estado, importe_total FROM gapto.hechos_financieros WHERE id=%s", (hid,))
    r = _obligatoria(cli, cat, aid, mid, False, True)
    assert r.status_code == 200, r.text
    assert h.leer(owner, "SELECT estado, importe_total FROM gapto.hechos_financieros WHERE id=%s", (hid,)) == antes
    assert h.leer(owner, "SELECT count(*) FROM gapto.hecho_magnitudes WHERE hecho_id=%s", (hid,)) == [(0,)]


# ------------------------------------------------------------------ d) retirar
def test_retirar_elimina_audita_y_compacta(ctx):
    owner, _, cli = ctx
    cat = fh.crear_categoria(owner, "Luz")
    ms = [h.crear_magnitud(owner, n) for n in ("A", "B", "C")]
    ids = [h.crear_asociacion(owner, cat, m, obligatoria=(i == 1), orden=i) for i, m in enumerate(ms)]
    r = _retirar(cli, cat, ids[0], ms[0], False)
    assert r.status_code == 200, r.text
    assert [(a["asociacion_id"], a["orden"]) for a in r.json()["asociaciones"]] == [(str(ids[1]), 0), (str(ids[2]), 1)]
    assert [(i, o) for i, _, _, o in h.asociaciones_persistidas(owner, cat)] == [(ids[1], 0), (ids[2], 1)]
    aud = h.auditorias_mag(owner)
    assert [(a, mo) for _, _, a, mo, *_ in aud] == [
        ("ACTUALIZAR", "F05-01 MAG_ORDEN"), ("ACTUALIZAR", "F05-01 MAG_ORDEN"), ("ELIMINAR", "F05-01 MAG_RETIRAR")]
    assert len({fila[4] for fila in aud}) == 1  # mismo request_id
    eliminada = aud[2]
    assert eliminada[1] == ids[0] and eliminada[6] is None
    antes = eliminada[5] if isinstance(eliminada[5], dict) else json.loads(eliminada[5])
    assert antes["id"] == str(ids[0]) and antes["magnitud_id"] == str(ms[0]) and antes["orden"] == 0
    assert h.magnitud_persistida(owner, ms[0]) is not None  # la magnitud no se borra
    r = _retirar(cli, cat, ids[0], ms[0], False)
    assert r.status_code == 409 and r.json()["codigo"] == "ASOCIACION_NO_EXISTE"


def test_retirar_conserva_la_historia_r09(ctx):
    owner, cuenta, cli = ctx
    cat, mid = fh.crear_categoria(owner, "Agua"), h.crear_magnitud(owner, precision=3)
    aid = h.crear_asociacion(owner, cat, mid, obligatoria=True)
    cuerpo = h.intencion(cuenta, categoria={"estado": "CATEGORIA", "categoria_id": str(cat),
                                            "magnitudes": [{"magnitud_id": str(mid), "valor": "12.5"}]})
    assert cli.post(URL_REGISTRO, json=cuerpo, headers=h.AUTH).status_code == 200
    hid = uuid.UUID(cuerpo["intencion_id"])
    assert _retirar(cli, cat, aid, mid, True).status_code == 200
    assert h.leer(owner, "SELECT magnitud_id, unidad FROM gapto.hecho_magnitudes WHERE hecho_id=%s", (hid,)) == [
        (mid, "l")]
    assert _catalogo(cli)[str(mid)]["n_hechos"] == 1


def test_retirar_con_obligatoria_actual_distinta_no_borra(ctx):
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "X"), h.crear_magnitud(owner)
    aid = h.crear_asociacion(owner, cat, mid, obligatoria=True)
    r = _retirar(cli, cat, aid, mid, False)
    assert r.status_code == 409 and r.json()["codigo"] == "ASOCIACION_NO_EXISTE"
    assert len(h.asociaciones_persistidas(owner, cat)) == 1


# ------------------------------------------------------------------ e) reordenar
def _tres(owner):
    cat = fh.crear_categoria(owner, "Coche")
    ms = [h.crear_magnitud(owner, n) for n in ("A", "B", "C")]
    ids = [h.crear_asociacion(owner, cat, m, obligatoria=False, orden=i) for i, m in enumerate(ms)]
    return cat, list(zip(ids, ms))


def test_reordenar_escribe_solo_las_filas_que_cambian(ctx):
    owner, _, cli = ctx
    cat, filas = _tres(owner)
    (a, ma), (b, mb), (c, mc) = filas
    r = _reordenar(cli, cat, [(a, ma, False, 0), (c, mc, False, 2), (b, mb, False, 1)])
    assert r.status_code == 200, r.text
    assert set(r.json()["modificadas"]) == {str(b), str(c)}
    assert [i for i, *_ in h.asociaciones_persistidas(owner, cat)] == [a, c, b]
    assert [mo for _, _, _, mo, *_ in h.auditorias_mag(owner)] == ["F05-01 MAG_ORDEN"] * 2
    r = _reordenar(cli, cat, [(a, ma, False, 0), (c, mc, False, 1), (b, mb, False, 2)])
    assert r.status_code == 200 and r.json()["idempotente"] is True and len(h.auditorias_mag(owner)) == 2


@pytest.mark.parametrize("defecto", ["FALTA", "SOBRA", "OTRA_MISMO_TAMANO", "ORDEN", "OBLIGATORIA", "MAGNITUD"])
def test_reordenar_conjunto_desfasado(ctx, defecto):
    owner, _, cli = ctx
    cat, filas = _tres(owner)
    pedido = [(i, m, False, o) for o, (i, m) in enumerate(filas)]
    if defecto == "FALTA":
        pedido = pedido[:2]
    elif defecto == "SOBRA":
        pedido.append((uuid.uuid4(), h.crear_magnitud(owner), False, 3))
    elif defecto == "OTRA_MISMO_TAMANO":
        pedido[2] = (uuid.uuid4(), pedido[2][1], False, 2)
    elif defecto == "ORDEN":
        pedido[0] = (pedido[0][0], pedido[0][1], False, 5)
    elif defecto == "OBLIGATORIA":
        pedido[1] = (pedido[1][0], pedido[1][1], True, 1)
    else:
        pedido[1] = (pedido[1][0], h.crear_magnitud(owner), False, 1)
    pedido.reverse()
    r = _reordenar(cli, cat, pedido)
    assert r.status_code == 409 and r.json()["codigo"] == "CONJUNTO_MAGNITUDES_DESFASADO", r.text
    assert [o for *_, o in h.asociaciones_persistidas(owner, cat)] == [0, 1, 2] and h.auditorias_mag(owner) == []


def test_reordenar_desde_estado_no_contiguo(ctx):
    owner, _, cli = ctx
    cat = fh.crear_categoria(owner, "Seed")
    ma, mb = h.crear_magnitud(owner, "A"), h.crear_magnitud(owner, "B")
    a = h.crear_asociacion(owner, cat, ma, obligatoria=True, orden=0)
    b = h.crear_asociacion(owner, cat, mb, obligatoria=False, orden=0)
    r = _reordenar(cli, cat, [(b, mb, False, 0), (a, ma, True, 0)])
    assert r.status_code == 200, r.text
    assert dict((i, o) for i, _, _, o in h.asociaciones_persistidas(owner, cat)) == {b: 0, a: 1}


# ------------------------------------------------------------------ f) g) h) magnitud
def test_renombrar_version_idempotencia_y_colision(ctx):
    owner, _, cli = ctx
    mid = h.crear_magnitud(owner, "Litros")
    h.crear_magnitud(owner, "Kilómetros", enabled=False)
    url = f"/v1/magnitudes/{mid}/renombrar"
    r = _post(cli, url, {"nombre": " Litros  de combustible ", "row_version": 1})
    assert r.status_code == 200 and r.json()["magnitud"]["nombre"] == "Litros de combustible", r.text
    assert r.json()["magnitud"]["row_version"] == 2
    r = _post(cli, url, {"nombre": "Litros de combustible", "row_version": 2})
    assert r.status_code == 200 and r.json()["idempotente"] is True
    r = _post(cli, url, {"nombre": "Otro", "row_version": 1})
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DESFASADA"
    r = _post(cli, url, {"nombre": "KILOMETROS", "row_version": 2})
    assert r.status_code == 409 and r.json()["codigo"] == "MAGNITUD_NOMBRE_DUPLICADO"
    assert r.json()["detalle"]["enabled"] is False
    assert [(a, mo) for _, _, a, mo, *_ in h.auditorias_mag(owner)] == [("ACTUALIZAR", "F05-01 MAG_RENOMBRAR")]


def test_renombrar_no_toca_unidad_ni_precision_r17(ctx):
    owner, _, cli = ctx
    mid = h.crear_magnitud(owner, "Kwh", unidad="kWh", precision=2)
    r = _post(cli, f"/v1/magnitudes/{mid}/renombrar", {"nombre": "kWh", "row_version": 1, "unidad_default": "Wh"})
    assert r.status_code == 422
    assert h.magnitud_persistida(owner, mid)[1:3] == ("kWh", 2)


def test_deshabilitar_exige_confirmacion_exacta_del_impacto(ctx):
    owner, _, cli = ctx
    mid = h.crear_magnitud(owner, "Consumo")
    c1 = fh.crear_categoria(owner, "Luz")
    c2 = fh.crear_categoria(owner, "Placas")
    c3 = fh.crear_categoria(owner, "Vieja", enabled=False)
    for c, ob in ((c1, True), (c2, False), (c3, True)):
        h.crear_asociacion(owner, c, mid, obligatoria=ob)
    url = f"/v1/magnitudes/{mid}/deshabilitar"
    r = _post(cli, url, {"row_version": 1, "confirmacion_impacto": None})
    assert r.status_code == 409 and r.json()["codigo"] == "MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION"
    assert r.json()["detalle"] == {"categorias_no_capturables": [
        {"categoria_id": str(c1), "nombre": "Luz", "obligatoria": True}]}
    r = _post(cli, url, {"row_version": 1, "confirmacion_impacto": [str(c1), str(c2)]})
    assert r.status_code == 409 and r.json()["codigo"] == "MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION"
    assert h.auditorias_mag(owner) == [] and h.magnitud_persistida(owner, mid)[3] is True
    r = _post(cli, url, {"row_version": 1, "confirmacion_impacto": [str(c1)]})
    assert r.status_code == 200 and r.json()["magnitud"]["enabled"] is False, r.text
    assert _nodo(cli, c1)["capturable"] is False and _nodo(cli, c2)["capturable"] is True
    assert len(h.asociaciones_persistidas(owner, c1)) == 1  # deshabilitar no elimina asociaciones
    r = _post(cli, url, {"row_version": 2, "confirmacion_impacto": None})
    assert r.status_code == 200 and r.json()["idempotente"] is True
    assert [(a, mo) for _, _, a, mo, *_ in h.auditorias_mag(owner)] == [("ACTUALIZAR", "F05-01 MAG_DESHABILITAR")]


def test_deshabilitar_con_confirmacion_de_un_impacto_que_ya_no_existe_be01(ctx):
    """S7-MAG-BE-01 (N7): confirmar [cat] cuando el impacto vigente es [] no
    deshabilita; se pide otra confirmacion con el impacto vigente (vacio)."""
    owner, _, cli = ctx
    cat = fh.crear_categoria(owner, "Taller")
    mid = uuid.uuid4()
    r = _nueva(cli, cat, mid, "Horas de taller", obligatoria=True)
    assert r.status_code == 200, r.text
    url = f"/v1/magnitudes/{mid}/deshabilitar"
    r = _post(cli, url, {"row_version": 1, "confirmacion_impacto": None})
    assert r.status_code == 409 and r.json()["codigo"] == "MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION"
    impacto = [c["categoria_id"] for c in r.json()["detalle"]["categorias_no_capturables"]]
    assert impacto == [str(cat)]
    [(aid, _, _, _)] = h.asociaciones_persistidas(owner, cat)
    r = _retirar(cli, cat, aid, mid, True)
    assert r.status_code == 200, r.text
    antes, auditorias_antes = h.magnitud_persistida(owner, mid), h.auditorias_mag(owner)
    r = _post(cli, url, {"row_version": 1, "confirmacion_impacto": impacto})
    assert r.status_code == 409, r.text
    assert r.json()["codigo"] == "MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION"
    assert r.json()["detalle"] == {"categorias_no_capturables": []}
    despues = h.magnitud_persistida(owner, mid)
    assert despues == antes and despues[3] is True and despues[4] == 1  # enabled y row_version intactos
    assert h.auditorias_mag(owner) == auditorias_antes


def test_deshabilitar_sin_impacto_y_rehabilitar(ctx):
    owner, _, cli = ctx
    mid = h.crear_magnitud(owner)
    r = _post(cli, f"/v1/magnitudes/{mid}/deshabilitar", {"row_version": 1, "confirmacion_impacto": None})
    assert r.status_code == 200, r.text
    r = _post(cli, f"/v1/magnitudes/{mid}/rehabilitar", {"row_version": 1})
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DESFASADA"
    r = _post(cli, f"/v1/magnitudes/{mid}/rehabilitar", {"row_version": 2})
    assert r.status_code == 200 and r.json()["magnitud"]["enabled"] is True and r.json()["magnitud"]["row_version"] == 3
    r = _post(cli, f"/v1/magnitudes/{mid}/rehabilitar", {"row_version": 3})
    assert r.status_code == 200 and r.json()["idempotente"] is True
    assert [mo for _, _, _, mo, *_ in h.auditorias_mag(owner)] == ["F05-01 MAG_DESHABILITAR", "F05-01 MAG_REHABILITAR"]


@pytest.mark.parametrize("accion,cuerpo", [
    ("renombrar", {"nombre": "X", "row_version": 1}),
    ("deshabilitar", {"row_version": 1, "confirmacion_impacto": None}),
    ("rehabilitar", {"row_version": 1}),
])
def test_magnitud_de_la_ruta_ajena_o_inexistente_es_404(ctx, accion, cuerpo):
    owner, _, cli = ctx
    otro, _ = h.crear_tenant()
    for mid in (h.crear_magnitud(otro, enabled=False), uuid.uuid4()):
        r = _post(cli, f"/v1/magnitudes/{mid}/{accion}", cuerpo)
        assert r.status_code == 404 and r.json()["codigo"] == "AGREGADO_NO_ENCONTRADO", r.text


# ------------------------------------------------------------------ tenant (AJ-S7MAG-04)
def test_magnitud_ajena_o_inexistente_al_asociar_sin_revelar(ctx):
    owner, _, cli = ctx
    otro, _ = h.crear_tenant()
    cat = fh.crear_categoria(owner, "Propia")
    respuestas = [_asociar(cli, cat, mid, True) for mid in (h.crear_magnitud(otro), uuid.uuid4())]
    assert [(r.status_code, r.json()) for r in respuestas] == [(409, respuestas[1].json())] * 2
    assert respuestas[0].json()["codigo"] == "MAGNITUD_NO_ADMITIDA"
    assert h.asociaciones_persistidas(owner, cat) == []


def test_categoria_ajena_o_inexistente_es_404(ctx):
    owner, _, cli = ctx
    otro, _ = h.crear_tenant()
    mid = h.crear_magnitud(owner)
    for cat in (fh.crear_categoria(otro, "Ajena"), uuid.uuid4()):
        r = _asociar(cli, cat, mid, True)
        assert r.status_code == 404 and r.json()["codigo"] == "AGREGADO_NO_ENCONTRADO"
        r = _reordenar(cli, cat, [(uuid.uuid4(), mid, False, 0)])
        assert r.status_code == 404


def test_asociacion_de_otra_categoria_o_tenant_no_existe(ctx):
    owner, _, cli = ctx
    otro, _ = h.crear_tenant()
    mia, otra_mia = fh.crear_categoria(owner, "Mia"), fh.crear_categoria(owner, "Otra")
    mid = h.crear_magnitud(owner)
    de_otra = h.crear_asociacion(owner, otra_mia, mid, obligatoria=False)
    cat_ajena, mag_ajena = fh.crear_categoria(otro, "Ajena"), h.crear_magnitud(otro)
    ajena = h.crear_asociacion(otro, cat_ajena, mag_ajena, obligatoria=False)
    for aid, m in ((de_otra, mid), (ajena, mag_ajena)):
        r = _obligatoria(cli, mia, aid, m, False, True)
        assert r.status_code == 409 and r.json()["codigo"] == "ASOCIACION_NO_EXISTE"
        r = _retirar(cli, mia, aid, m, False)
        assert r.status_code == 409 and r.json()["codigo"] == "ASOCIACION_NO_EXISTE"
    r = _retirar(cli, cat_ajena, ajena, mag_ajena, False)
    assert r.status_code == 404
    assert len(h.asociaciones_persistidas(otro, cat_ajena)) == 1


# ------------------------------------------------------------------ 422 del DTO
@pytest.mark.parametrize("magnitud,campo", [
    ({"nombre": "   ", "unidad_default": "h", "precision_decimales": 0}, "nombre"),
    ({"nombre": "ﬁ" * 41, "unidad_default": "h", "precision_decimales": 0}, "nombre"),  # 82 visibles tras NFKC
    ({"nombre": "a" * 81, "unidad_default": "h", "precision_decimales": 0}, "nombre"),
    ({"nombre": "Horas", "unidad_default": "u" * 21, "precision_decimales": 0}, "unidad_default"),
    ({"nombre": "Horas", "unidad_default": " ", "precision_decimales": 0}, "unidad_default"),
    ({"nombre": "Horas", "unidad_default": "h", "precision_decimales": 7}, "precision_decimales"),
    ({"nombre": "Horas", "unidad_default": "h", "precision_decimales": -1}, "precision_decimales"),
    ({"nombre": "Horas", "unidad_default": "h", "precision_decimales": True}, "precision_decimales"),
    ({"nombre": "Horas", "unidad_default": "h"}, "precision_decimales"),
], ids=["nombre_blanco", "81_tras_nfkc", "81", "unidad_21", "unidad_blanca", "precision_7", "precision_neg",
        "precision_bool", "sin_precision"])
def test_alta_rapida_422_estructural(ctx, magnitud, campo):
    owner, _, cli = ctx
    cat = fh.crear_categoria(owner, "X")
    r = _post(cli, f"/v1/categorias/{cat}/magnitudes",
              {"origen": "NUEVA", "obligatoria": True, "magnitud": {"magnitud_id": str(uuid.uuid4()), **magnitud}})
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA", r.text
    # 422 ESTRUCTURAL del DTO, que nombra el campo; no la defensa fisica varchar(80) (DataError sin campo).
    assert f"magnitud.{campo}" in r.json()["mensaje"], r.text
    assert h.leer(owner, "SELECT count(*) FROM gapto.magnitudes") == [(0,)]


def test_renombrar_81_visibles_es_422_estructural(ctx):
    owner, _, cli = ctx
    mid = h.crear_magnitud(owner, "Litros")
    r = _post(cli, f"/v1/magnitudes/{mid}/renombrar", {"nombre": "ﬁ" * 41, "row_version": 1})
    assert r.status_code == 422 and "nombre" in r.json()["mensaje"], r.text
    assert h.magnitud_persistida(owner, mid)[0] == "Litros"


def test_nombre_de_80_visibles_tras_nfkc_se_admite(ctx):
    owner, _, cli = ctx
    r = _nueva(cli, fh.crear_categoria(owner, "X"), uuid.uuid4(), "ﬁ" * 40)
    assert r.status_code == 200 and len(r.json()["magnitud"]["nombre"]) == 80, r.text


@pytest.mark.parametrize("cuerpo", [
    {"origen": "OTRO", "magnitud_id": str(uuid.uuid4()), "obligatoria": True},
    {"origen": "EXISTENTE", "magnitud_id": str(uuid.uuid4())},
    {"origen": "EXISTENTE", "magnitud_id": str(uuid.uuid4()), "obligatoria": "si"},
    {"origen": "EXISTENTE", "magnitud_id": str(uuid.uuid4()), "obligatoria": True, "orden": 0},
], ids=["origen", "sin_obligatoria", "obligatoria_texto", "campo_extra"])
def test_asociar_422_estructural(ctx, cuerpo):
    owner, _, cli = ctx
    r = _post(cli, f"/v1/categorias/{fh.crear_categoria(owner, 'X')}/magnitudes", cuerpo)
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA", r.text


@pytest.mark.parametrize("defecto", ["orden_negativo", "orden_32768", "ids_repetidos", "vacio"])
def test_reordenar_422_estructural(ctx, defecto):
    owner, _, cli = ctx
    cat, filas = _tres(owner)
    pedido = [{"asociacion_id": str(i), "magnitud_id": str(m), "orden": o, "obligatoria": False}
              for o, (i, m) in enumerate(filas)]
    if defecto == "orden_negativo":
        pedido[0]["orden"] = -1
    elif defecto == "orden_32768":
        pedido[0]["orden"] = 32768
    elif defecto == "ids_repetidos":
        pedido[1]["asociacion_id"] = pedido[0]["asociacion_id"]
    else:
        pedido = []
    r = _post(cli, f"/v1/categorias/{cat}/magnitudes/reordenar", {"asociaciones": pedido})
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA", r.text


def test_deshabilitar_422_estructural(ctx):
    owner, _, cli = ctx
    mid, cat = h.crear_magnitud(owner), uuid.uuid4()
    url = f"/v1/magnitudes/{mid}/deshabilitar"
    for cuerpo in ({"row_version": 1}, {"row_version": 1, "confirmacion_impacto": [str(cat), str(cat)]},
                   {"row_version": 0, "confirmacion_impacto": None}):
        r = _post(cli, url, cuerpo)
        assert r.status_code == 422, cuerpo


# ------------------------------------------------------------------ i) GET /v1/magnitudes, j) arbol
def test_catalogo_del_owner_con_categorias_y_n_hechos(ctx):
    owner, cuenta, cli = ctx
    otro, _ = h.crear_tenant()
    h.crear_magnitud(otro, "Ajena")
    usada = h.crear_magnitud(owner, "Consumo", unidad="kWh")
    sola = h.crear_magnitud(owner, "Apagada", enabled=False)
    luz, placas = fh.crear_categoria(owner, "Luz"), fh.crear_categoria(owner, "Placas", enabled=False)
    h.crear_asociacion(owner, luz, usada, obligatoria=True)
    h.crear_asociacion(owner, placas, usada, obligatoria=False)
    for valor in ("1", "2", "3"):  # 3 hechos frente a 2 categorias: contadores distinguibles
        cuerpo = h.intencion(cuenta, categoria={"estado": "CATEGORIA", "categoria_id": str(luz),
                                                "magnitudes": [{"magnitud_id": str(usada), "valor": valor}]})
        assert cli.post(URL_REGISTRO, json=cuerpo, headers=h.AUTH).status_code == 200
    r = cli.get("/v1/magnitudes", headers=h.AUTH)
    assert r.status_code == 200
    lista = r.json()["magnitudes"]
    assert [m["nombre"] for m in lista] == ["Apagada", "Consumo"]  # solo el owner, por nombre
    cat = {m["id"]: m for m in lista}
    assert cat[str(usada)]["n_hechos"] == 3 and cat[str(sola)]["n_hechos"] == 0
    assert cat[str(sola)]["categorias"] == [] and cat[str(sola)]["enabled"] is False
    assert cat[str(usada)]["categorias"] == [
        {"categoria_id": str(luz), "nombre": "Luz", "obligatoria": True, "categoria_enabled": True},
        {"categoria_id": str(placas), "nombre": "Placas", "obligatoria": False, "categoria_enabled": False}]
    assert set(cat[str(usada)]) == {"id", "nombre", "unidad_default", "precision_decimales", "enabled",
                                    "row_version", "categorias", "n_hechos"}


def test_catalogo_vacio_y_token(ctx):
    owner, _, cli = ctx
    assert cli.get("/v1/magnitudes", headers=h.AUTH).json() == {"magnitudes": []}
    assert cli.get("/v1/magnitudes").status_code == 401


def test_arbol_expone_asociacion_id_de_los_comandos(ctx):
    owner, _, cli = ctx
    cat = fh.crear_categoria(owner, "Luz")
    aid = _nueva(cli, cat, uuid.uuid4(), "Horas").json()["asociacion"]["asociacion_id"]
    assert [m["asociacion_id"] for m in _nodo(cli, cat)["magnitudes"]] == [aid]


def test_comandos_exigen_token(ctx):
    owner, _, cli = ctx
    cat, mid = fh.crear_categoria(owner, "X"), h.crear_magnitud(owner)
    r = cli.post(f"/v1/categorias/{cat}/magnitudes", json={"origen": "EXISTENTE", "magnitud_id": str(mid),
                                                           "obligatoria": True})
    assert r.status_code == 401 and h.asociaciones_persistidas(owner, cat) == []
