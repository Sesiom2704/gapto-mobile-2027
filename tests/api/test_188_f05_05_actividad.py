# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_188_f05_05_actividad.py
# Ruta: tests/api/test_188_f05_05_actividad.py
# Descripcion: Lectura de la Actividad v0 (K2 §1.5; F05 §49.4 A7, §49.5
#   R8/R10-R12; AJ-F0505-05). Dominio ACTIVIDAD. Oraculos obligatorios:
#   (a) paginacion keyset (fecha_hecho DESC, id ASC) sin duplicados ni
#       omisiones con cinco hechos de la misma fecha e inserciones entre
#       paginas (caso 33);
#   (b) un hecho = una fila: dos efectos con categorias distintas -> «varias»;
#       GASTO + DEUDA -> una fila con su categoria;
#   (c) concepto historico (motor) y nota nueva en `nota`;
#   (d) sin hora: fecha_hecho es una fecha;
#   (e) cada importe declara si es total o «tu parte»: NO_DISPONIBLE sin
#       tu_parte (caso 17, R12), PARCIAL con la parte propia y `pendiente`.
#   Casos de §49.9: 12 (tres tipos, orden, transferencia neutra), 13
#   (busqueda por tercero, categoria y contexto sin nota), 14 (titulo: los
#   datos para el cliente nunca vacios), 15 (categoria deshabilitada visible y
#   marcada), 18 (aislamiento), 22 (todo el historial de un tercero), 24
#   (importe exacto y contexto). Ademas: filtros, total, periodo [desde,
#   hasta), cursor invalido, detalle con presupuestable y magnitudes.
# Version: 0.1.0 (F05-05 K2 §1.5)
# Version: 0.2.0 (F05-05 K2 §1.7; M5-08, A10): lecturas con `nota`; wire de escritura del gasto con `concepto`.
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_05_helpers as x
import vs01_api_helpers as h

URL = "/v1/actividad"


def pagina(cli, **params):
    r = cli.get(URL, params=params, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def ids(p):
    return [f["id"] for f in p["filas"]]


@pytest.fixture()
def e():
    owner, actor, cli, corriente, ahorro = x.entorno()
    return owner, actor, cli, corriente, ahorro


def test_caso12_tres_tipos_orden_y_transferencia_neutra(e):
    owner, actor, cli, cta, ahorro = e
    super_ = x.categoria(owner, "Supermercados")
    nomina = x.categoria(owner, "Nómina", "INGRESO")
    g = x.gasto(cli, cta, fecha="2026-10-10", importe="48.72", categoria_id=super_, concepto="Compra semanal")
    i = x.ingreso(cli, cta, fecha="2026-10-09", importe="2100.00", categoria_id=nomina)
    t = x.transferencia(cli, cta, ahorro, fecha="2026-10-10", importe="500.00")
    p = pagina(cli, desde="2026-10-01", hasta="2026-11-01")
    hoy = sorted([str(g), str(t)])
    assert ids(p) == hoy + [str(i)] and p["total"] == 3 and p["siguiente"] is None
    filas = {f["id"]: f for f in p["filas"]}
    fg, fi, ft = filas[str(g)], filas[str(i)], filas[str(t)]
    assert (fg["tipo"], fg["importe_total"], fg["estado_reparto"], fg["tu_parte"]) == ("GASTO", "48.72", "COMPLETA", "48.72")
    assert [c["rol"] for c in fg["cuentas"]] == ["PAGO"] and fg["nota"] == "Compra semanal"
    assert (fi["tipo"], fi["importe_total"], [c["rol"] for c in fi["cuentas"]]) == ("INGRESO", "2100.00", ["COBRO"])
    assert (ft["tipo"], ft["estado_reparto"], ft["tu_parte"], ft["categoria"]) == ("TRANSFERENCIA", None, None, None)
    assert sorted((c["rol"], c["cuenta_id"]) for c in ft["cuentas"]) == sorted([("ORIGEN", str(cta)), ("DESTINO", str(ahorro))])


def test_oraculo_a_caso33_paginacion_sin_duplicados_ni_omisiones(e):
    owner, actor, cli, cta, _ = e
    misma = [x.gasto(cli, cta, fecha="2026-10-05") for _ in range(5)]
    otros = [x.gasto(cli, cta, fecha=f) for f in ("2026-10-08", "2026-10-01")]
    esperados = [str(otros[0])] + sorted(str(i) for i in misma) + [str(otros[1])]
    vistos, cursor, insertados = [], None, False
    while True:
        params = {"limite": 2}
        if cursor:
            params["cursor"] = cursor
        p = pagina(cli, **params)
        vistos += ids(p)
        if not insertados:  # inserciones entre paginas: una mas reciente y otra de la misma fecha
            x.gasto(cli, cta, fecha="2026-10-09")
            x.gasto(cli, cta, fecha="2026-10-05")
            insertados = True
        cursor = p["siguiente"]
        if not cursor:
            break
    assert len(vistos) == len(set(vistos))  # sin duplicados
    assert [v for v in vistos if v in esperados] == esperados  # sin omisiones y en orden


def test_oraculo_b_un_hecho_una_fila(e):
    owner, actor, cli, _, _ = e
    a, b = x.categoria(owner, "Comida"), x.categoria(owner, "Bebida")
    dos_cat = x.hecho_motor(owner, [("GASTO", "10.00", "COMPLETA", a, [(actor, "10.00")]),
                                    ("GASTO", "5.00", "COMPLETA", b, [(actor, "5.00")])])
    con_deuda = x.hecho_motor(owner, [("GASTO", "30.30", "COMPLETA", a, [(actor, "30.30")]),
                                      ("DEUDA", "30.30", "COMPLETA", None, [(actor, "30.30")])], tipo="COMPRA_FINANCIADA",
                              total="30.30")
    p = pagina(cli)
    assert sorted(ids(p)) == sorted([str(dos_cat), str(con_deuda)]) and p["total"] == 2
    filas = {f["id"]: f for f in p["filas"]}
    assert filas[str(dos_cat)]["varias"] is True and filas[str(dos_cat)]["categoria"] is None
    assert filas[str(dos_cat)]["tu_parte"] == "15.00"
    assert filas[str(con_deuda)]["varias"] is False and filas[str(con_deuda)]["categoria"]["nombre"] == "Comida"


def test_oraculo_c_concepto_historico_y_nota_nueva_caso14(e):
    owner, actor, cli, cta, _ = e
    hist = x.hecho_motor(owner, [("GASTO", "61.04", "COMPLETA", None, [(actor, "61.04")])],
                         concepto="COMPRA ALDI SAN VICENTE")
    nueva = x.gasto(cli, cta, concepto="Compra semanal")
    sin_nota = x.gasto(cli, cta, concepto=None, tercero_id=x.tercero(cli, "ALDI"))
    filas = {f["id"]: f for f in pagina(cli)["filas"]}
    assert filas[str(hist)]["nota"] == "COMPRA ALDI SAN VICENTE"
    assert filas[str(nueva)]["nota"] == "Compra semanal"
    assert filas[str(sin_nota)]["nota"] is None and filas[str(sin_nota)]["tercero"]["nombre"] == "ALDI"


def test_oraculo_d_sin_hora(e):
    owner, actor, cli, cta, _ = e
    x.gasto(cli, cta, fecha="2026-10-05")
    f = pagina(cli)["filas"][0]
    assert f["fecha_hecho"] == "2026-10-05" and not any("hora" in k for k in f)


def test_oraculo_e_tu_parte_nunca_inventada_caso17(e):
    owner, actor, cli, cta, _ = e
    otro = h.crear_actor_tercero(owner)
    solo = x.gasto(cli, cta, importe="20.00", atribucion="SOLO_MIO")
    sin = x.gasto(cli, cta, importe="44.50", atribucion="SIN_INDICAR")
    parcial = x.hecho_motor(owner, [("GASTO", "90.00", "PARCIAL", None, [(actor, "30.00"), (otro, "20.00")])])
    cero = x.hecho_motor(owner, [("GASTO", "12.00", "COMPLETA", None, [(otro, "12.00")])])
    filas = {f["id"]: f for f in pagina(cli)["filas"]}
    assert (filas[str(solo)]["estado_reparto"], filas[str(solo)]["tu_parte"]) == ("COMPLETA", "20.00")
    assert (filas[str(sin)]["estado_reparto"], filas[str(sin)]["tu_parte"], filas[str(sin)]["importe_total"]) == (
        "NO_DISPONIBLE", None, "44.50")
    assert (filas[str(parcial)]["estado_reparto"], filas[str(parcial)]["tu_parte"], filas[str(parcial)]["pendiente"]) == (
        "PARCIAL", "30.00", "40.00")
    assert (filas[str(cero)]["estado_reparto"], filas[str(cero)]["tu_parte"]) == ("COMPLETA", "0.00")


def test_caso13_busqueda_sin_nota_por_tercero_categoria_y_contexto(e):
    owner, actor, cli, cta, _ = e
    luz = x.categoria(owner, "Luz y electricidad")
    iber = x.tercero(cli, "Iberdrola")
    ctx = x.contexto(cli, "Cumpleaños Tania")
    por_cat = x.gasto(cli, cta, categoria_id=luz, concepto=None, fecha="2026-09-15")
    por_nota = x.gasto(cli, cta, concepto="Factura luz agosto", fecha="2026-08-14")
    por_ter = x.gasto(cli, cta, tercero_id=iber, concepto=None, fecha="2026-07-01")
    por_ctx = x.gasto(cli, cta, contexto_id=ctx, concepto=None, fecha="2026-10-09")
    x.gasto(cli, cta, concepto="Otra cosa")
    p = pagina(cli, q="luz")
    assert ids(p) == [str(por_cat), str(por_nota)] and p["total"] == 2
    assert [f["coincide_en"] for f in p["filas"]] == [["CATEGORIA"], ["NOTA"]]
    p = pagina(cli, q="iberdrola")
    assert ids(p) == [str(por_ter)] and p["filas"][0]["coincide_en"] == ["TERCERO"]
    p = pagina(cli, q="cumple")
    assert ids(p) == [str(por_ctx)] and p["filas"][0]["coincide_en"] == ["CONTEXTO"]
    assert p["filas"][0]["contexto"]["nombre"] == "Cumpleaños Tania"
    assert pagina(cli, q="taller gómez")["filas"] == []


def test_caso24_importe_exacto_con_coma_o_punto_lo_resuelve_el_cliente(e):
    owner, actor, cli, cta, _ = e
    a = x.gasto(cli, cta, importe="48.72", fecha="2026-10-10")
    b = x.gasto(cli, cta, importe="48.72", fecha="2026-03-14")
    x.gasto(cli, cta, importe="48.70")
    p = pagina(cli, importe="48.72")
    assert ids(p) == [str(a), str(b)] and all(f["coincide_en"] == ["IMPORTE"] for f in p["filas"])
    assert ids(pagina(cli, importe="48.720")) == [str(a), str(b)]  # igualdad numerica


def test_caso15_categoria_deshabilitada_visible_y_marcada(e):
    owner, actor, cli, cta, _ = e
    fruta = x.categoria(owner, "Fruta y verdura")
    hid = x.gasto(cli, cta, categoria_id=fruta)
    x.desactivar_categoria(owner, fruta)
    f = pagina(cli)["filas"][0]
    assert f["id"] == str(hid) and f["maestros_desactivados"] == ["CATEGORIA"] and f["categoria"]["enabled"] is False


def test_tercero_desactivado_marcado(e):
    owner, actor, cli, cta, _ = e
    t = x.tercero(cli, "Viejo")
    x.gasto(cli, cta, tercero_id=t)
    x.desactivar_tercero(cli, t)
    assert pagina(cli)["filas"][0]["maestros_desactivados"] == ["TERCERO"]


def test_filtros_y_total(e):
    owner, actor, cli, cta, ahorro = e
    alim = x.categoria(owner, "Alimentación")
    super_ = x.categoria(owner, "Supermercados", parent_id=alim)
    aldi = x.tercero(cli, "ALDI")
    ctx = x.contexto(cli, "Viaje")
    g1 = x.gasto(cli, cta, categoria_id=super_, tercero_id=aldi)
    g2 = x.gasto(cli, cta, categoria_id=alim, contexto_id=ctx)
    g3 = x.gasto(cli, cta)
    i1 = x.ingreso(cli, cta)
    t1 = x.transferencia(cli, cta, ahorro)
    assert sorted(ids(pagina(cli, tipo=["GASTO"]))) == sorted(map(str, (g1, g2, g3)))
    assert sorted(ids(pagina(cli, tipo=["INGRESO", "TRANSFERENCIA"]))) == sorted(map(str, (i1, t1)))
    assert sorted(ids(pagina(cli, categoria_id=str(alim)))) == sorted(map(str, (g1, g2)))  # con subcategorias
    assert ids(pagina(cli, categoria_id=str(alim), incluir_subcategorias="false")) == [str(g2)]
    assert ids(pagina(cli, cuenta_id=str(ahorro))) == [str(t1)]
    assert ids(pagina(cli, tercero_id=str(aldi))) == [str(g1)]
    assert ids(pagina(cli, contexto_id=str(ctx))) == [str(g2)]
    p = pagina(cli, tipo=["GASTO"], cuenta_id=str(cta), limite=1)
    assert p["total"] == 3 and len(p["filas"]) == 1 and p["siguiente"]


def test_periodo_semiabierto(e):
    owner, actor, cli, cta, _ = e
    x.gasto(cli, cta, fecha="2026-09-30")
    d1 = x.gasto(cli, cta, fecha="2026-10-01")
    d10 = x.gasto(cli, cta, fecha="2026-10-10")
    x.gasto(cli, cta, fecha="2025-11-01")
    assert ids(pagina(cli, desde="2026-10-01", hasta="2026-11-01")) == [str(d10), str(d1)]
    assert pagina(cli, desde="2026-10-01", hasta="2026-10-01")["filas"] == []


def test_caso22_todo_el_historial_de_un_tercero(e):
    owner, actor, cli, cta, _ = e
    aldi = x.tercero(cli, "ALDI")
    hs = [x.gasto(cli, cta, tercero_id=aldi, fecha=f) for f in ("2026-10-10", "2026-03-01", "2025-06-01")]
    x.gasto(cli, cta)
    assert ids(pagina(cli, tercero_id=str(aldi))) == [str(i) for i in hs]


def test_caso18_aislamiento(e):
    owner, actor, cli, cta, _ = e
    mio = x.gasto(cli, cta)
    _, _, cli_b, cta_b, _ = x.entorno()
    ajeno = x.gasto(cli_b, cta_b)
    assert ids(pagina(cli)) == [str(mio)]
    assert pagina(cli, tercero_id=str(uuid.uuid4()))["filas"] == []
    r = cli.get(f"{URL}/{ajeno}", headers=h.AUTH)
    assert r.status_code == 404 and r.json()["codigo"] == "HECHO_NO_ENCONTRADO"


def test_entradas_invalidas(e):
    _, _, cli, _, _ = e
    assert cli.get(URL, params={"cursor": "no-es-un-cursor"}, headers=h.AUTH).status_code == 422
    assert cli.get(URL, params={"desde": "2026-10-10", "hasta": "2026-10-01"}, headers=h.AUTH).status_code == 422
    assert cli.get(URL, params={"limite": 0}, headers=h.AUTH).status_code == 422
    assert cli.get(URL, params={"tipo": "DEUDA"}, headers=h.AUTH).status_code == 422


def test_detalle_gasto_ingreso_y_transferencia(e):
    owner, actor, cli, cta, ahorro = e
    ctx = x.contexto(cli, "Cumpleaños Tania")
    rest = x.categoria(owner, "Restaurantes", parent_id=x.categoria(owner, "Ocio"))
    g = x.gasto(cli, cta, importe="44.50", categoria_id=rest, contexto_id=ctx, atribucion="SIN_INDICAR", concepto=None)
    t = x.transferencia(cli, cta, ahorro)
    r = cli.get(f"{URL}/{g}", headers=h.AUTH)
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["importe_total"], d["tu_parte"], d["estado_reparto"], d["presupuestable"]) == ("44.50", None, "NO_DISPONIBLE", True)
    assert d["categoria"]["ruta"] == "Ocio › Restaurantes" and d["contexto"]["nombre"] == "Cumpleaños Tania"
    assert d["magnitudes"] == [] and d["nota"] is None
    d = cli.get(f"{URL}/{t}", headers=h.AUTH).json()
    assert d["tipo"] == "TRANSFERENCIA" and d["tu_parte"] is None and {c["rol"] for c in d["cuentas"]} == {"ORIGEN", "DESTINO"}


def test_solo_lectura_y_sin_v_hechos_resumen():
    import pathlib

    fuente = (pathlib.Path(__file__).resolve().parents[2] / "backend" / "app" / "actividad" / "lecturas.py").read_text(
        encoding="utf-8")
    codigo = "\n".join(l for l in fuente.splitlines() if not l.lstrip().startswith("#"))
    assert "v_hechos_resumen" not in codigo
    for verbo in ("INSERT ", "UPDATE ", "DELETE ", "FOR UPDATE", "FOR SHARE", "FOR NO KEY"):
        assert verbo not in codigo.upper(), verbo


def test_m508_lecturas_exponen_nota_y_el_wire_del_gasto_conserva_concepto(e):
    """A10 / M5-08: la lectura nueva llama `nota` al dato; el wire de ESCRITURA
    del gasto sigue siendo `concepto` (deuda DEU-F05-WIRE-CONCEPTO -> F10)."""
    import pathlib

    owner, actor, cli, cta, _ = e
    cuerpo = h.intencion(cta, concepto="Cena con amigos", fecha_hecho="2026-10-05")
    assert cli.post(x.GASTO, json=cuerpo, headers=h.AUTH).status_code == 200
    con_nota = dict(h.intencion(cta, fecha_hecho="2026-10-05"), nota="Otra")
    con_nota.pop("concepto")
    assert cli.post(x.GASTO, json=con_nota, headers=h.AUTH).status_code == 422  # `nota` no existe en el wire del gasto
    fila = pagina(cli)["filas"][0]
    assert fila["nota"] == "Cena con amigos" and "concepto" not in fila
    detalle = cli.get(f"{URL}/{cuerpo['intencion_id']}", headers=h.AUTH).json()
    assert detalle["nota"] == "Cena con amigos" and "concepto" not in detalle
    dto = (pathlib.Path(__file__).resolve().parents[2] / "backend" / "app" / "api" / "dto_f05_05.py").read_text(encoding="utf-8")
    assert "concepto:" not in dto
