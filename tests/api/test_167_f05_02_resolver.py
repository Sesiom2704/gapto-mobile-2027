# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_167_f05_02_resolver.py
# Ruta: tests/api/test_167_f05_02_resolver.py
# Descripcion: Resolver de la propuesta de registro por campo (F05-02 B1;
#   F05-D026 §41.3/§41.4; E1/E2; criterio CC-02-2 y CC-02-3 (i)-(iv) a nivel
#   de resolver).
#   - Capas efectivas v1: preferencia > default general; plantilla sin
#     consumidor (AJ-D026-01); sin preferencia -> sin propuesta; nunca se
#     inventa un default de presupuestable.
#   - Especificidad 0/1/2 (AJ-D026-02), prioridad = mayor valor (AJ-D026-04),
#     especificidad antes que prioridad.
#   - Independencia por campo (E3, AJ-D026-07), empate no contradictorio
#     (AJ-D026-08), cabeza contradictoria -> sin propuesta (tampoco fallback).
#   - Cuenta (E2): elegible en `fecha` con la regla de cuentas_pago + EUR;
#     no elegible -> se ignora sin descender; fallback a la unica elegible.
#   - Categoria exacta sin herencia (AJ-D026-05); «Sin categoria»; tipo de
#     hecho; desactivadas y filas de otro owner ignoradas.
#   - Regresion de la extraccion de la regla de cuentas_pago.
#   Las filas de los escenarios se escriben por SQL directo como gapto_owner
#   (incluidas configuraciones que el writer rechazaria) y el resolver se
#   ejecuta como gapto_runtime con RLS.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid

import pytest

import f05_02_helpers as ph
import vs01_api_helpers as h

PREF = "PREFERENCIA"
DEF = "DEFAULT_GENERAL"


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    return owner, actor, cli


def _dos_cuentas(owner, actor):
    return ph.cuenta(owner, actor, nombre="A"), ph.cuenta(owner, actor, nombre="B")


# ------------------------------------------------------------------ capas
def test_sin_preferencias_y_varias_cuentas_no_hay_propuesta(t):
    owner, actor, _ = t
    _dos_cuentas(owner, actor)
    p = ph.resolver(owner, None)
    assert p == {"cuenta": None, "presupuestable": None}


def test_sin_preferencias_y_una_cuenta_default_general(t):
    owner, actor, _ = t
    c = ph.cuenta(owner, actor)
    p = ph.resolver(owner, None)
    assert ph.valor(p, "cuenta") == c and ph.origen(p, "cuenta") == (DEF, None)
    # Presupuestable no tiene default general (E1: sin preseleccion).
    assert p["presupuestable"] is None


def test_sin_cuentas_no_hay_propuesta_ni_error(t):
    owner, _, _ = t
    assert ph.resolver(owner, None) == {"cuenta": None, "presupuestable": None}


def test_preferencia_gana_al_default_general(t):
    owner, actor, _ = t
    a = ph.cuenta(owner, actor)
    pid = ph.insertar_sql(owner, cuenta=a, presupuestable=True)
    p = ph.resolver(owner, None)
    assert ph.origen(p, "cuenta") == (PREF, pid)
    assert ph.valor(p, "presupuestable") is True and ph.origen(p, "presupuestable") == (PREF, pid)


def test_plantilla_no_produce_propuesta(t):
    """AJ-D026-01: plantilla existe en el modelo pero no tiene consumidor."""
    owner, actor, _ = t
    a, b = _dos_cuentas(owner, actor)
    h.como_owner(owner, "INSERT INTO gapto.plantillas_registro (id, owner_user_id, nombre, tipo_hecho_id, "
                        "cuenta_default_id, presupuestable_default) VALUES (%s,%s,'Plantilla',%s,%s,true)",
                 (uuid.uuid4(), owner, ph.tipo_gasto(owner), a))
    assert ph.resolver(owner, None) == {"cuenta": None, "presupuestable": None}


# ------------------------------------------------------------------ especificidad y prioridad
def test_especificidad_0_1_2(t):
    owner, actor, _ = t
    c0, c1, c2 = ph.cuenta(owner, actor), ph.cuenta(owner, actor), ph.cuenta(owner, actor)
    cat = ph.categoria(owner, "Super")
    g = ph.tipo_gasto(owner)
    p0 = ph.insertar_sql(owner, cuenta=c0)
    p1 = ph.insertar_sql(owner, tipo_hecho_id=g, cuenta=c1)
    p2 = ph.insertar_sql(owner, tipo_hecho_id=g, categoria_id=cat, cuenta=c2)
    assert ph.origen(ph.resolver(owner, cat), "cuenta") == (PREF, p2)
    assert ph.origen(ph.resolver(owner, None), "cuenta") == (PREF, p1)
    # Otro tipo de hecho: solo coincide la global.
    assert ph.origen(ph.resolver(owner, None, tipo_hecho_id=ph.otro_tipo(owner)), "cuenta") == (PREF, p0)


def test_especificidad_categoria_sola_cuenta_como_1(t):
    owner, actor, _ = t
    c0, c1 = ph.cuenta(owner, actor), ph.cuenta(owner, actor)
    cat = ph.categoria(owner, "Super")
    ph.insertar_sql(owner, cuenta=c0)
    p1 = ph.insertar_sql(owner, categoria_id=cat, cuenta=c1)
    assert ph.origen(ph.resolver(owner, cat), "cuenta") == (PREF, p1)


def test_mayor_valor_de_prioridad_gana(t):
    owner, actor, _ = t
    c_alta, c_baja = ph.cuenta(owner, actor), ph.cuenta(owner, actor)
    ph.insertar_sql(owner, cuenta=c_baja, prioridad=50)
    p_alta = ph.insertar_sql(owner, cuenta=c_alta, prioridad=100)
    assert ph.origen(ph.resolver(owner, None), "cuenta") == (PREF, p_alta)


def test_especificidad_antes_que_prioridad(t):
    owner, actor, _ = t
    c_esp, c_prio = ph.cuenta(owner, actor), ph.cuenta(owner, actor)
    p_esp = ph.insertar_sql(owner, tipo_hecho_id=ph.tipo_gasto(owner), cuenta=c_esp, prioridad=10)
    ph.insertar_sql(owner, cuenta=c_prio, prioridad=100)
    assert ph.origen(ph.resolver(owner, None), "cuenta") == (PREF, p_esp)


# ------------------------------------------------------------------ por campo
def test_independencia_por_campo(t):
    """E3: la mas especifica solo propone presupuestable; la cuenta sale de
    una menos especifica."""
    owner, actor, _ = t
    a, _ = _dos_cuentas(owner, actor)
    cat = ph.categoria(owner, "Super")
    p_pres = ph.insertar_sql(owner, tipo_hecho_id=ph.tipo_gasto(owner), categoria_id=cat, presupuestable=False)
    p_cta = ph.insertar_sql(owner, cuenta=a)
    p = ph.resolver(owner, cat)
    assert ph.valor(p, "cuenta") == a and ph.origen(p, "cuenta") == (PREF, p_cta)
    assert ph.valor(p, "presupuestable") is False and ph.origen(p, "presupuestable") == (PREF, p_pres)


def test_presupuestable_de_la_mas_especifica_y_cuenta_de_otra(t):
    owner, actor, _ = t
    a, b = _dos_cuentas(owner, actor)
    cat = ph.categoria(owner, "Super")
    p_cat = ph.insertar_sql(owner, categoria_id=cat, cuenta=a, presupuestable=True)
    p_glob = ph.insertar_sql(owner, cuenta=b, presupuestable=False)
    p = ph.resolver(owner, cat)
    assert ph.origen(p, "cuenta") == (PREF, p_cat) and ph.origen(p, "presupuestable") == (PREF, p_cat)
    p = ph.resolver(owner, None)
    assert ph.origen(p, "cuenta") == (PREF, p_glob) and ph.valor(p, "presupuestable") is False


def test_empate_no_contradictorio_propone_el_valor_comun(t):
    owner, actor, _ = t
    a, _ = _dos_cuentas(owner, actor)
    cat = ph.categoria(owner, "Super")
    ids = sorted([ph.insertar_sql(owner, tipo_hecho_id=ph.tipo_gasto(owner), cuenta=a),
                  ph.insertar_sql(owner, categoria_id=cat, cuenta=a)])
    p = ph.resolver(owner, cat)
    assert ph.valor(p, "cuenta") == a and ph.origen(p, "cuenta") == (PREF, ids[0])


def test_cabeza_contradictoria_sin_propuesta_ni_fallback(t):
    """Configuracion invalida (solo por SQL): sin propuesta para el campo;
    tampoco el fallback a la unica cuenta EUR elegible."""
    owner, actor, _ = t
    eur = ph.cuenta(owner, actor)
    usd = ph.cuenta(owner, actor, moneda="USD")
    cat = ph.categoria(owner, "Super")
    ph.insertar_sql(owner, tipo_hecho_id=ph.tipo_gasto(owner), cuenta=eur, presupuestable=True)
    ph.insertar_sql(owner, categoria_id=cat, cuenta=usd, presupuestable=False)
    p = ph.resolver(owner, cat)
    assert p == {"cuenta": None, "presupuestable": None}
    # Fuera del contexto conflictivo, la del tipo propone con normalidad.
    p = ph.resolver(owner, None)
    assert ph.valor(p, "cuenta") == eur and ph.valor(p, "presupuestable") is True


def test_empate_en_un_campo_no_afecta_al_otro(t):
    owner, actor, _ = t
    a, b = _dos_cuentas(owner, actor)
    p1 = ph.insertar_sql(owner, cuenta=a, presupuestable=True)
    p2 = ph.insertar_sql(owner, cuenta=b, presupuestable=True)
    p = ph.resolver(owner, None)
    assert p["cuenta"] is None
    assert ph.valor(p, "presupuestable") is True and ph.origen(p, "presupuestable") == (PREF, min(p1, p2))


# ------------------------------------------------------------------ CC-02-3 cuenta
def test_cc02_3_i_varias_elegibles_y_preferencia_elegible(t):
    owner, actor, _ = t
    a, b = _dos_cuentas(owner, actor)
    pid = ph.insertar_sql(owner, cuenta=b)
    p = ph.resolver(owner, None)
    assert ph.valor(p, "cuenta") == b and ph.origen(p, "cuenta") == (PREF, pid)


def test_cc02_3_ii_preferencia_no_elegible_y_unica_elegible(t):
    owner, actor, _ = t
    unica = ph.cuenta(owner, actor)
    deshabilitada = ph.cuenta(owner, actor, enabled=False)
    ph.insertar_sql(owner, cuenta=deshabilitada, presupuestable=True)
    p = ph.resolver(owner, None)
    assert ph.valor(p, "cuenta") == unica and ph.origen(p, "cuenta") == (DEF, None)
    assert ph.valor(p, "presupuestable") is True


def test_cc02_3_iii_varias_elegibles_sin_preferencia_aplicable(t):
    owner, actor, _ = t
    a, _ = _dos_cuentas(owner, actor)
    otra = ph.categoria(owner, "Otra")
    ph.insertar_sql(owner, categoria_id=otra, cuenta=a)
    assert ph.resolver(owner, None)["cuenta"] is None


def test_cc02_3_iv_varias_elegibles_y_preferencia_no_elegible(t):
    owner, actor, _ = t
    _dos_cuentas(owner, actor)
    cerrada = ph.cuenta(owner, actor, fecha_cierre=dt.date(2026, 9, 1))
    ph.insertar_sql(owner, cuenta=cerrada)
    assert ph.resolver(owner, None)["cuenta"] is None


def test_no_elegible_no_desciende_a_la_siguiente_preferencia(t):
    owner, actor, _ = t
    a, b = _dos_cuentas(owner, actor)
    baja = ph.cuenta(owner, actor, enabled=False)
    ph.insertar_sql(owner, tipo_hecho_id=ph.tipo_gasto(owner), cuenta=baja)
    ph.insertar_sql(owner, cuenta=a)
    assert ph.resolver(owner, None)["cuenta"] is None


@pytest.mark.parametrize("motivo", ["otra_moneda", "pasivo", "deshabilitada", "cerrada_en_fecha"])
def test_cuenta_no_elegible_se_ignora_sin_error(t, motivo):
    owner, actor, _ = t
    _dos_cuentas(owner, actor)
    kw = {"otra_moneda": {"moneda": "USD"}, "pasivo": {"naturaleza": "PASIVO"},
          "deshabilitada": {"enabled": False}, "cerrada_en_fecha": {"fecha_cierre": ph.FECHA}}[motivo]
    mala = ph.cuenta(owner, actor, **kw)
    ph.insertar_sql(owner, cuenta=mala, presupuestable=False)
    p = ph.resolver(owner, None)
    assert p["cuenta"] is None and ph.valor(p, "presupuestable") is False


def test_cuenta_con_cierre_posterior_tampoco_es_elegible(t):
    """La regla de cuentas_pago depende de `fecha` solo via fecha_cierre, y
    ck_cuentas__cierre_deshabilita exige enabled=false con cierre: una cuenta
    con cierre no es elegible en ninguna fecha (ni antes del cierre)."""
    owner, actor, _ = t
    _dos_cuentas(owner, actor)
    cierra = ph.cuenta(owner, actor, fecha_cierre=dt.date(2026, 9, 30))
    ph.insertar_sql(owner, cuenta=cierra)
    for f in (dt.date(2026, 9, 29), dt.date(2026, 9, 30)):
        assert ph.resolver(owner, None, fecha=f)["cuenta"] is None


def test_fallback_solo_cuenta_cuentas_eur(t):
    """D1: el fallback de cuenta unica cuenta solo las elegibles en EUR."""
    owner, actor, _ = t
    eur = ph.cuenta(owner, actor)
    ph.cuenta(owner, actor, moneda="USD")
    p = ph.resolver(owner, None)
    assert ph.valor(p, "cuenta") == eur and ph.origen(p, "cuenta") == (DEF, None)


def test_preferencia_hacia_cuenta_compartida_se_propone(t):
    """§41.7: la preferencia propone la cuenta; la financiacion queda para
    REG-01 (no determinada si no es self 100 %)."""
    owner, actor, _ = t
    otro = h.crear_actor_tercero(owner)
    _dos_cuentas(owner, actor)
    compartida = h.crear_cuenta(owner, [(actor, 50), (otro, 50)])
    pid = ph.insertar_sql(owner, cuenta=compartida)
    assert ph.origen(ph.resolver(owner, None), "cuenta") == (PREF, pid)


# ------------------------------------------------------------------ coincidencia
def test_categoria_exacta_sin_herencia_de_ancestros(t):
    owner, actor, _ = t
    a, b = _dos_cuentas(owner, actor)
    padre = ph.categoria(owner, "Hogar")
    hija = ph.categoria(owner, "Luz", parent_id=padre)
    ph.insertar_sql(owner, categoria_id=padre, cuenta=a, presupuestable=True)
    p = ph.resolver(owner, hija)
    assert p == {"cuenta": None, "presupuestable": None}
    assert ph.valor(ph.resolver(owner, padre), "cuenta") == a


def test_hija_sin_preferencia_propia_cae_en_la_global_no_en_el_padre(t):
    owner, actor, _ = t
    a, b = _dos_cuentas(owner, actor)
    padre = ph.categoria(owner, "Hogar")
    hija = ph.categoria(owner, "Luz", parent_id=padre)
    ph.insertar_sql(owner, categoria_id=padre, cuenta=a)
    p_glob = ph.insertar_sql(owner, cuenta=b)
    assert ph.origen(ph.resolver(owner, hija), "cuenta") == (PREF, p_glob)


def test_sin_categoria_solo_coinciden_preferencias_de_categoria_nula(t):
    owner, actor, _ = t
    a, b = _dos_cuentas(owner, actor)
    cat = ph.categoria(owner, "Super")
    ph.insertar_sql(owner, categoria_id=cat, cuenta=a)
    assert ph.resolver(owner, None)["cuenta"] is None
    p_glob = ph.insertar_sql(owner, cuenta=b)
    assert ph.origen(ph.resolver(owner, None), "cuenta") == (PREF, p_glob)


def test_preferencia_global_coincide_con_cualquier_contexto(t):
    owner, actor, _ = t
    a, _ = _dos_cuentas(owner, actor)
    pid = ph.insertar_sql(owner, cuenta=a)
    for ctx in (None, ph.categoria(owner, "X")):
        assert ph.origen(ph.resolver(owner, ctx), "cuenta") == (PREF, pid)
    assert ph.origen(ph.resolver(owner, None, tipo_hecho_id=ph.otro_tipo(owner)), "cuenta") == (PREF, pid)


def test_desactivada_se_ignora(t):
    owner, actor, _ = t
    a, _ = _dos_cuentas(owner, actor)
    ph.insertar_sql(owner, cuenta=a, presupuestable=True, enabled=False)
    assert ph.resolver(owner, None) == {"cuenta": None, "presupuestable": None}


def test_preferencias_de_otro_owner_no_cuentan(t):
    owner, actor, _ = t
    _dos_cuentas(owner, actor)
    otro, otro_actor = h.crear_tenant()
    ajena = ph.cuenta(otro, otro_actor)
    ph.insertar_sql(otro, cuenta=ajena, presupuestable=True)
    assert ph.resolver(owner, None) == {"cuenta": None, "presupuestable": None}


# ------------------------------------------------------------------ HTTP
def test_endpoint_propuesta(t):
    owner, actor, cli = t
    a, _ = _dos_cuentas(owner, actor)
    cat = ph.categoria(owner, "Super")
    pid = ph.insertar_sql(owner, categoria_id=cat, cuenta=a, presupuestable=False)
    r = ph.propuesta_http(cli, cat)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "cuenta": {"valor": str(a), "origen": {"capa": "PREFERENCIA", "preferencia_id": str(pid)}},
        "presupuestable": {"valor": False, "origen": {"capa": "PREFERENCIA", "preferencia_id": str(pid)}},
    }
    r = ph.propuesta_http(cli, None)
    assert r.status_code == 200 and r.json() == {"cuenta": None, "presupuestable": None}


def test_endpoint_propuesta_exige_fecha(t):
    _, _, cli = t
    r = cli.get(f"{ph.BASE}/propuesta", headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA"


# ------------------------------------------------------------------ regresion cuentas_pago
def test_regresion_cuentas_pago_tras_la_extraccion(t):
    """La regla extraida conserva el comportamiento de cuentas_pago: mismas
    cuentas (incluida otra moneda), mismo orden, misma propuesta."""
    owner, actor, cli = t
    otro = h.crear_actor_tercero(owner)
    a = ph.cuenta(owner, actor, nombre="Zeta")
    b = ph.cuenta(owner, actor, nombre="Alfa")
    usd = ph.cuenta(owner, actor, moneda="USD", nombre="Dolar")
    comp = h.crear_cuenta(owner, [(actor, 50), (otro, 50)])
    ph.cuenta(owner, actor, enabled=False)
    ph.cuenta(owner, actor, fecha_cierre=ph.FECHA)
    ph.cuenta(owner, actor, naturaleza="PASIVO")
    tardia = ph.cuenta(owner, actor, fecha_cierre=ph.FECHA + dt.timedelta(days=1))
    # La consulta literal previa a la extraccion (lecturas_vs01 v0.2.0).
    esperado = h.leer(owner, "SELECT id FROM gapto.cuentas WHERE enabled AND (fecha_cierre IS NULL OR "
                             "fecha_cierre > %s) AND naturaleza = 'ACTIVO' ORDER BY orden, nombre, id", (ph.FECHA,))
    r = cli.get(f"/v1/vs01/cuentas-pago?fecha={ph.FECHA.isoformat()}", headers=h.AUTH)
    assert r.status_code == 200, r.text
    filas = r.json()["cuentas"]
    assert [f["cuenta_id"] for f in filas] == [str(e[0]) for e in esperado]
    assert {str(a), str(b), str(usd), str(comp)} <= {f["cuenta_id"] for f in filas}
    assert str(tardia) not in {f["cuenta_id"] for f in filas}  # deshabilitada (cierre exige enabled=false)
    prop = {f["cuenta_id"]: f["propuesta_financiacion"] for f in filas}
    assert prop[str(a)] == "SELF_100" and prop[str(comp)] == "NO_DETERMINADA"
