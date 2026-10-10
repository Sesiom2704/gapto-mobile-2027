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
#
#   v0.2.0 (F05-03/F05-04 J2 §1.5; F05 §46.4 R6, §46.5 E2/E3; F05-D032 C4;
#   decision OPCION A2 del STOP 2, tabla «tests adaptados» del handoff
#   J2+J3): se retira la preferencia global sin tipo y tercero_id pasa a ser
#   dimension operativa. Las filas sin `tipo_hecho_id` explicito se escriben
#   con tipo GASTO (helper, sustitucion «Todos los gastos»). Adaptados con
#   oraculo nuevo, conservando cada caso: especificidad (la fila sin tipo se
#   ignora; 1 = tipo, 2 = tipo + categoria o tipo + tercero), categoria sin
#   tipo ignorada, especificidad antes que prioridad, empate no
#   contradictorio y cabeza contradictoria (tipo + categoria frente a tipo +
#   tercero), no elegible sin descender (mas especifica por categoria) y
#   «Todos los gastos» frente a otro tipo. Nuevos: tipo + tercero consumido
#   solo con ese tercero y fila sin tipo ignorada.
#
#   v0.3.0 (F05-03/F05-04 J2 §1.1; F05-D031 E1/A10, F05 §46.4 R1, F05-D032
#   C1; decision OPCION A del STOP 1, tabla «tests adaptados»): la
#   elegibilidad es por capacidad. Caso «pasivo» conservado con el motivo
#   nuevo (PASIVO sin PAGAR_GASTO -> no elegible); nuevos «sin capacidad» y
#   «ledger posterior»; positivo «CREDITO con PAGAR_GASTO es elegible». La
#   regresion de cuentas_pago tiene como oraculo la regla R1 literal (capacidad,
#   EUR, ledger, cierre, habilitada) en lugar del SQL con naturaleza ACTIVO.
# Version: 0.3.0
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
    """E3/R6: la fila sin tipo (antigua especificidad 0) se ignora; 1 = tipo,
    2 = tipo + categoria o tipo + tercero."""
    owner, actor, _ = t
    c0, c1, c2, c3 = (ph.cuenta(owner, actor) for _ in range(4))
    cat = ph.categoria(owner, "Super")
    ter = ph.tercero(owner)
    g = ph.tipo_gasto(owner)
    ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=c0)
    p1 = ph.insertar_sql(owner, tipo_hecho_id=g, cuenta=c1)
    p2 = ph.insertar_sql(owner, tipo_hecho_id=g, categoria_id=cat, cuenta=c2)
    p3 = ph.insertar_sql(owner, tipo_hecho_id=g, tercero_id=ter, cuenta=c3)
    assert ph.origen(ph.resolver(owner, cat), "cuenta") == (PREF, p2)
    assert ph.origen(ph.resolver(owner, None), "cuenta") == (PREF, p1)
    assert ph.origen(ph.resolver(owner, None, tercero_id=ter), "cuenta") == (PREF, p3)
    # Otro tipo de hecho: la fila sin tipo ya no coincide (E3) -> sin propuesta.
    assert ph.resolver(owner, None, tipo_hecho_id=ph.otro_tipo(owner))["cuenta"] is None


def test_especificidad_categoria_sola_cuenta_como_1(t):
    """E3: una preferencia de categoria SIN tipo ya no cuenta (se ignora); la
    de «Todos los gastos» decide."""
    owner, actor, _ = t
    c0, c1 = ph.cuenta(owner, actor), ph.cuenta(owner, actor)
    cat = ph.categoria(owner, "Super")
    p0 = ph.insertar_sql(owner, cuenta=c0)
    ph.insertar_sql(owner, tipo_hecho_id=None, categoria_id=cat, cuenta=c1)
    assert ph.origen(ph.resolver(owner, cat), "cuenta") == (PREF, p0)


def test_mayor_valor_de_prioridad_gana(t):
    owner, actor, _ = t
    c_alta, c_baja = ph.cuenta(owner, actor), ph.cuenta(owner, actor)
    ph.insertar_sql(owner, cuenta=c_baja, prioridad=50)
    p_alta = ph.insertar_sql(owner, cuenta=c_alta, prioridad=100)
    assert ph.origen(ph.resolver(owner, None), "cuenta") == (PREF, p_alta)


def test_especificidad_antes_que_prioridad(t):
    owner, actor, _ = t
    c_esp, c_prio = ph.cuenta(owner, actor), ph.cuenta(owner, actor)
    cat = ph.categoria(owner, "Super")
    p_esp = ph.insertar_sql(owner, categoria_id=cat, cuenta=c_esp, prioridad=10)
    ph.insertar_sql(owner, cuenta=c_prio, prioridad=100)
    assert ph.origen(ph.resolver(owner, cat), "cuenta") == (PREF, p_esp)


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
    ter = ph.tercero(owner)
    # Misma especificidad (2): tipo + categoria frente a tipo + tercero (E2).
    ids = sorted([ph.insertar_sql(owner, categoria_id=cat, cuenta=a),
                  ph.insertar_sql(owner, tercero_id=ter, cuenta=a)])
    p = ph.resolver(owner, cat, tercero_id=ter)
    assert ph.valor(p, "cuenta") == a and ph.origen(p, "cuenta") == (PREF, ids[0])


def test_cabeza_contradictoria_sin_propuesta_ni_fallback(t):
    """Configuracion invalida (solo por SQL): sin propuesta para el campo;
    tampoco el fallback a la unica cuenta EUR elegible."""
    owner, actor, _ = t
    eur = ph.cuenta(owner, actor)
    usd = ph.cuenta(owner, actor, moneda="USD")
    cat = ph.categoria(owner, "Super")
    ter = ph.tercero(owner)
    # Misma especificidad (2) y pueden coincidir: tipo + categoria / tipo + tercero (E2).
    ph.insertar_sql(owner, categoria_id=cat, cuenta=eur, presupuestable=True)
    ph.insertar_sql(owner, tercero_id=ter, cuenta=usd, presupuestable=False)
    p = ph.resolver(owner, cat, tercero_id=ter)
    assert p == {"cuenta": None, "presupuestable": None}
    # Fuera del contexto conflictivo, la de categoria propone con normalidad.
    p = ph.resolver(owner, cat)
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
    cat = ph.categoria(owner, "Super")
    ph.insertar_sql(owner, categoria_id=cat, cuenta=baja)
    ph.insertar_sql(owner, cuenta=a)
    assert ph.resolver(owner, cat)["cuenta"] is None


@pytest.mark.parametrize("motivo", ["otra_moneda", "pasivo", "deshabilitada", "cerrada_en_fecha", "sin_capacidad",
                                    "ledger_posterior"])
def test_cuenta_no_elegible_se_ignora_sin_error(t, motivo):
    owner, actor, _ = t
    _dos_cuentas(owner, actor)
    # R1/C1: «pasivo» = PASIVO SIN PAGAR_GASTO (con la capacidad es elegible, ver el positivo).
    kw = {"otra_moneda": {"moneda": "USD"}, "pasivo": {"naturaleza": "PASIVO", "capacidades": ("TRANSFERIR_ENTRADA",)},
          "deshabilitada": {"enabled": False}, "cerrada_en_fecha": {"fecha_cierre": ph.FECHA},
          "sin_capacidad": {"capacidades": ()}, "ledger_posterior": {}}[motivo]
    mala = ph.cuenta(owner, actor, **kw)
    if motivo == "ledger_posterior":
        h.como_owner(owner, "UPDATE gapto.cuentas SET saldo_apertura=0, fecha_inicio_ledger=%s WHERE id=%s",
                     (ph.FECHA + dt.timedelta(days=1), mala))
    ph.insertar_sql(owner, cuenta=mala, presupuestable=False)
    p = ph.resolver(owner, None)
    assert p["cuenta"] is None and ph.valor(p, "presupuestable") is False


def test_credito_con_pagar_gasto_es_elegible(t):
    """R2/E1: una cuenta de credito (PASIVO) con PAGAR_GASTO es elegible para
    «Pagado con»: la preferencia hacia ella se propone."""
    owner, actor, _ = t
    _dos_cuentas(owner, actor)
    credito = ph.cuenta(owner, actor, naturaleza="PASIVO")
    pid = ph.insertar_sql(owner, cuenta=credito)
    p = ph.resolver(owner, None)
    assert ph.valor(p, "cuenta") == credito and ph.origen(p, "cuenta") == (PREF, pid)


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
    """E3: «Todos los gastos» coincide con cualquier categoria y tercero del
    gasto, pero no con otro tipo; una fila sin tipo no coincide con nada."""
    owner, actor, _ = t
    a, b = _dos_cuentas(owner, actor)
    pid = ph.insertar_sql(owner, cuenta=a)
    ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=b)
    ter = ph.tercero(owner)
    for ctx in (None, ph.categoria(owner, "X")):
        assert ph.origen(ph.resolver(owner, ctx), "cuenta") == (PREF, pid)
        assert ph.origen(ph.resolver(owner, ctx, tercero_id=ter), "cuenta") == (PREF, pid)
    assert ph.resolver(owner, None, tipo_hecho_id=ph.otro_tipo(owner))["cuenta"] is None


def test_tipo_mas_tercero_solo_coincide_con_ese_tercero(t):
    """E2: la preferencia tipo + tercero se consume solo en el contexto de ese
    tercero; sin tercero o con otro tercero, decide la del tipo."""
    owner, actor, _ = t
    a, b = _dos_cuentas(owner, actor)
    ter, otro = ph.tercero(owner), ph.tercero(owner)
    p_ter = ph.insertar_sql(owner, tercero_id=ter, cuenta=a, presupuestable=True)
    p_tipo = ph.insertar_sql(owner, cuenta=b)
    p = ph.resolver(owner, None, tercero_id=ter)
    assert ph.origen(p, "cuenta") == (PREF, p_ter) and ph.origen(p, "presupuestable") == (PREF, p_ter)
    for contexto in (None, otro):
        p = ph.resolver(owner, None, tercero_id=contexto)
        assert ph.origen(p, "cuenta") == (PREF, p_tipo) and p["presupuestable"] is None


def test_fila_sin_tipo_se_ignora(t):
    """E3 (C4): una fila sin tipo (previa a la conversion o por SQL directo)
    nunca produce propuesta, aunque sea la unica."""
    owner, actor, _ = t
    a, _ = _dos_cuentas(owner, actor)
    ph.insertar_sql(owner, tipo_hecho_id=None, cuenta=a, presupuestable=True)
    assert ph.resolver(owner, None) == {"cuenta": None, "presupuestable": None}


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
    """cuentas_pago aplica la regla UNICA R1 para GASTO (J2 §1.1; E1, C1):
    mismas cuentas y mismo orden que la regla literal, misma propuesta. Antes
    el oraculo era el SQL con naturaleza = 'ACTIVO' y sin moneda."""
    owner, actor, cli = t
    otro = h.crear_actor_tercero(owner)
    a = ph.cuenta(owner, actor, nombre="Zeta")
    b = ph.cuenta(owner, actor, nombre="Alfa")
    usd = ph.cuenta(owner, actor, moneda="USD", nombre="Dolar")
    comp = h.crear_cuenta(owner, [(actor, 50), (otro, 50)])
    ph.cuenta(owner, actor, enabled=False)
    ph.cuenta(owner, actor, fecha_cierre=ph.FECHA)
    pasivo_sin = ph.cuenta(owner, actor, naturaleza="PASIVO", capacidades=("TRANSFERIR_ENTRADA",))
    credito = ph.cuenta(owner, actor, naturaleza="PASIVO", nombre="Tarjeta credito")
    sin_capacidad = ph.cuenta(owner, actor, capacidades=())
    con_ledger = ph.cuenta(owner, actor, nombre="Con ledger")
    ledger_posterior = ph.cuenta(owner, actor, nombre="Ledger posterior")
    h.como_owner(owner, "UPDATE gapto.cuentas SET saldo_apertura=0, fecha_inicio_ledger=%s WHERE id=%s",
                 (ph.FECHA, con_ledger))
    h.como_owner(owner, "UPDATE gapto.cuentas SET saldo_apertura=0, fecha_inicio_ledger=%s WHERE id=%s",
                 (ph.FECHA + dt.timedelta(days=1), ledger_posterior))
    tardia = ph.cuenta(owner, actor, fecha_cierre=ph.FECHA + dt.timedelta(days=1))
    # Regla R1 literal para GASTO.
    esperado = h.leer(owner, "SELECT c.id FROM gapto.cuentas c WHERE c.enabled AND (c.fecha_cierre IS NULL OR "
                             "c.fecha_cierre > %s) AND (c.fecha_inicio_ledger IS NULL OR c.fecha_inicio_ledger <= %s) "
                             "AND c.moneda = 'EUR' AND EXISTS (SELECT 1 FROM gapto.cuenta_capacidades k "
                             "WHERE k.cuenta_id = c.id AND k.capacidad_codigo = 'PAGAR_GASTO') "
                             "ORDER BY c.orden, c.nombre, c.id", (ph.FECHA, ph.FECHA))
    r = cli.get(f"/v1/vs01/cuentas-pago?fecha={ph.FECHA.isoformat()}", headers=h.AUTH)
    assert r.status_code == 200, r.text
    filas = r.json()["cuentas"]
    assert [f["cuenta_id"] for f in filas] == [str(e[0]) for e in esperado]
    ids = {f["cuenta_id"] for f in filas}
    assert {str(a), str(b), str(comp), str(credito), str(con_ledger)} <= ids
    for fuera in (usd, pasivo_sin, sin_capacidad, ledger_posterior, tardia):
        assert str(fuera) not in ids  # tardia: deshabilitada (cierre exige enabled=false)
    prop = {f["cuenta_id"]: f["propuesta_financiacion"] for f in filas}
    assert prop[str(a)] == "SELF_100" and prop[str(comp)] == "NO_DETERMINADA"
