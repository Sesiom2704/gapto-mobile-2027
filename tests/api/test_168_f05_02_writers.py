# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_168_f05_02_writers.py
# Ruta: tests/api/test_168_f05_02_writers.py
# Descripcion: Writers de preferencias de registro (F05-02 B1; F05-D026
#   §41.3/§41.4; criterio CC-02-5). Por HTTP salvo la defensa del CHECK:
#   - alta, idempotencia del alta e identidad reutilizada;
#   - todos los codigos: SIN_VALOR (y el CHECK fisico traducido por
#     identidad), DIMENSION_DIFERIDA, PRIORIDAD_NO_ADMITIDA,
#     CUENTA_NO_ELEGIBLE, CATEGORIA_NO_ELEGIBLE, EMPATE_CONTRADICTORIO (con
#     el id en conflicto), NO_ENCONTRADO, VERSION_DESFASADA, ENTRADA_INVALIDA;
#   - regla de empate de AJ-D026-03 (comodines, campos distintos, mismo
#     valor, otra especificidad, sin posibilidad de coincidir) en alta,
#     edicion y reactivacion;
#   - row_version, desactivar/reactivar e idempotencias sin escritura;
#   - auditoria CREAR/ACTUALIZAR con motivo por operacion;
#   - aislamiento por owner (RLS); lista con cuenta_disponible_hoy.
#   Todo rechazo se comprueba SIN escritura (fila y auditoria intactas).
#
#   v0.2.0 (F05-02 B1-C, AJ-B1-04): el alta con un UUID de OTRO owner (E09)
#   afirma de forma explicita el codigo, la fila ajena intacta (contenido y
#   row_version), ninguna fila nueva y ninguna auditoria escrita.
#
#   v0.3.0 (F05-03/F05-04 J2 §1.5; F05 §46.4 R6, §46.5 E2/E3; F05-D032 C4;
#   decision OPCION A2 del STOP 2, tabla «tests adaptados» del handoff
#   J2+J3): las altas sin tipo explicito llevan tipo GASTO (helper). Con
#   oraculo nuevo, conservando cada caso negativo: tercero en el alta ->
#   categoria + tercero rechazado con PREFERENCIA_AMBITO_NO_ADMITIDO; empate
#   por comodines entre tipo + categoria y tipo + tercero; «mismo valor» a
#   igual especificidad (tipo + categoria / tipo + tercero); editar valida
#   tambien SIN_TIPO, AMBITO_NO_ADMITIDO y TERCERO_NO_ELEGIBLE; reactivar
#   una fila con entidad (DIMENSION_DIFERIDA) o sin tipo (SIN_TIPO). Nuevos:
#   alta tipo + tercero admitida, alta sin tipo -> PREFERENCIA_SIN_TIPO,
#   tercero ajeno/inexistente/desactivado -> PREFERENCIA_TERCERO_NO_ELEGIBLE;
#   la lista informa los ids de GASTO e INGRESO (`tipos`).
#
#   v0.4.0 (F05-03/F05-04 J2 §1.1; F05-D031 E1/A10, F05 §46.4 R1, F05-D032
#   C1; decision OPCION A del STOP 1, tabla «tests adaptados»): caso «pasivo»
#   de test_cuenta_no_elegible conservado con el motivo nuevo (PASIVO sin
#   PAGAR_GASTO); nuevo «sin_capacidad»; positivo: preferencia hacia una
#   cuenta de credito con PAGAR_GASTO admitida; una preferencia de INGRESO
#   exige RECIBIR_INGRESO.
# Version: 0.4.0
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

EMPATE = "PREFERENCIA_EMPATE_CONTRADICTORIO"


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    a = ph.cuenta(owner, actor, nombre="A")
    b = ph.cuenta(owner, actor, nombre="B")
    return owner, actor, cli, a, b


def _codigo(r):
    return r.json().get("codigo")


def _sin_escritura(owner, pid):
    assert ph.fila(owner, pid) is None
    assert ph.auditorias(owner, pid) == []


# ------------------------------------------------------------------ alta
def test_alta_persiste_y_audita(t):
    owner, _, cli, a, _ = t
    cat = ph.categoria(owner, "Super")
    g = ph.tipo_gasto(owner)
    pid, r = ph.alta(cli, tipo_hecho_id=g, categoria_id=cat, cuenta_default_id=a, presupuestable_default=True)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["idempotente"] is False and cuerpo["modificadas"] == [str(pid)]
    assert cuerpo["preferencia"]["row_version"] == 1 and cuerpo["preferencia"]["prioridad"] == 100
    assert ph.fila(owner, pid) == {"tipo_hecho_id": g, "categoria_id": cat, "cuenta_default_id": a,
                                   "presupuestable_default": True, "prioridad": 100, "enabled": True,
                                   "row_version": 1}
    assert ph.auditorias(owner, pid) == [("CREAR", "F05-02 ALTA")]


def test_alta_solo_presupuestable_y_global(t):
    owner, _, cli, _, _ = t
    pid, r = ph.alta(cli, presupuestable_default=False)
    assert r.status_code == 200, r.text
    assert ph.fila(owner, pid)["presupuestable_default"] is False


def test_alta_idempotente_y_reutilizada(t):
    owner, _, cli, a, b = t
    pid, r = ph.alta(cli, cuenta_default_id=a)
    assert r.status_code == 200
    _, r = ph.alta(cli, pid, cuenta_default_id=a)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    _, r = ph.alta(cli, pid, cuenta_default_id=b)
    assert r.status_code == 409 and _codigo(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert ph.auditorias(owner, pid) == [("CREAR", "F05-02 ALTA")]
    # Tras evolucionar (row_version 2) el mismo alta ya no es idempotente.
    assert ph.desactivar(cli, pid, 1).status_code == 200
    _, r = ph.alta(cli, pid, cuenta_default_id=a)
    assert r.status_code == 409 and _codigo(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"


def _auditorias_preferencias(owner) -> int:
    return h.leer(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla='preferencias_registro'")[0][0]


def test_alta_con_id_de_otro_owner_es_identidad_reutilizada(t):
    """E09 / AJ-B1-04: el UUID ya existe en OTRO owner (oculto por RLS). Se
    rechaza con IDENTIDAD_REUTILIZADA sin tocar nada: la fila ajena conserva
    contenido y row_version, no nace ninguna fila y no se audita nada."""
    owner, _, cli, a, _ = t
    otro, otro_actor = h.crear_tenant()
    ajena = ph.insertar_sql(otro, cuenta=ph.cuenta(otro, otro_actor), presupuestable=True)
    fila_ajena = ph.fila(otro, ajena)
    antes = {"owner": ph.n_preferencias(owner), "otro": ph.n_preferencias(otro),
             "aud_owner": _auditorias_preferencias(owner), "aud_otro": _auditorias_preferencias(otro)}
    _, r = ph.alta(cli, ajena, cuenta_default_id=a)
    assert r.status_code == 409 and _codigo(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert ph.fila(otro, ajena) == fila_ajena and fila_ajena["row_version"] == 1
    assert ph.fila(owner, ajena) is None
    assert {"owner": ph.n_preferencias(owner), "otro": ph.n_preferencias(otro),
            "aud_owner": _auditorias_preferencias(owner), "aud_otro": _auditorias_preferencias(otro)} == antes
    assert ph.auditorias(owner, ajena) == [] and ph.auditorias(otro, ajena) == []


# ------------------------------------------------------------------ codigos de entrada
def test_sin_valor(t):
    owner, _, cli, _, _ = t
    pid, r = ph.alta(cli, categoria_id=ph.categoria(owner, "Super"))
    assert r.status_code == 422 and _codigo(r) == "PREFERENCIA_SIN_VALOR"
    _sin_escritura(owner, pid)


def test_check_fisico_propone_valor_mapeado_por_identidad(t):
    """Defensa residual: si el CHECK llega (sin la validacion previa), se
    traduce por la identidad de la constraint a PREFERENCIA_SIN_VALOR."""
    owner, _, _, a, _ = t
    from app.preferencias import repositorio as repo
    from app.preferencias import servicio

    pid = ph.insertar_sql(owner, cuenta=a)

    def op(s):
        return servicio._escribir(s, lambda: repo.actualizar_preferencia(
            s, pid, {"cuenta_default_id": None, "presupuestable_default": None}))

    assert fh.en_transaccion(owner, op) == servicio.Rechazo("PREFERENCIA_SIN_VALOR")
    assert ph.fila(owner, pid)["cuenta_default_id"] == a


@pytest.mark.parametrize("campo", ["tercero_id", "entidad_id"])
def test_dimension_diferida_en_alta(t, campo):
    """entidad_id sigue diferida. tercero_id es operativo (E2): su caso
    negativo es el ambito no admitido categoria + tercero (R6)."""
    owner, _, cli, a, _ = t
    if campo == "tercero_id":
        pid, r = ph.alta(cli, cuenta_default_id=a, categoria_id=ph.categoria(owner, "Super"),
                         tercero_id=ph.tercero(owner))
        assert r.status_code == 422 and _codigo(r) == "PREFERENCIA_AMBITO_NO_ADMITIDO"
    else:
        pid, r = ph.alta(cli, cuenta_default_id=a, entidad_id=uuid.uuid4())
        assert r.status_code == 422 and _codigo(r) == "PREFERENCIA_DIMENSION_DIFERIDA"
    _sin_escritura(owner, pid)


def test_alta_tipo_mas_tercero_admitida(t):
    """E2/R6: el ambito tipo + tercero se admite y persiste el tercero."""
    owner, _, cli, a, _ = t
    ter = ph.tercero(owner)
    pid, r = ph.alta(cli, tercero_id=ter, cuenta_default_id=a)
    assert r.status_code == 200, r.text
    assert r.json()["preferencia"]["tercero_id"] == str(ter)
    assert h.leer(owner, "SELECT tercero_id FROM gapto.preferencias_registro WHERE id=%s", (pid,)) == [(ter,)]
    assert ph.auditorias(owner, pid) == [("CREAR", "F05-02 ALTA")]


def test_alta_sin_tipo_rechazada(t):
    """E3/R6: no hay preferencia sin tipo (antes «global»)."""
    owner, _, cli, a, _ = t
    for campos in ({"cuenta_default_id": a}, {"categoria_id": ph.categoria(owner, "Super"), "cuenta_default_id": a}):
        pid, r = ph.alta(cli, tipo_hecho_id=None, **campos)
        assert r.status_code == 422 and _codigo(r) == "PREFERENCIA_SIN_TIPO"
        _sin_escritura(owner, pid)


@pytest.mark.parametrize("motivo", ["desactivado", "ajeno", "inexistente"])
def test_tercero_no_elegible(t, motivo):
    owner, _, cli, a, _ = t
    if motivo == "ajeno":
        otro, _ = h.crear_tenant()
        ter = ph.tercero(otro)
    elif motivo == "inexistente":
        ter = uuid.uuid4()
    else:
        ter = ph.tercero(owner)
        h.como_owner(owner, "UPDATE gapto.terceros SET enabled=false WHERE id=%s", (ter,))
    pid, r = ph.alta(cli, tercero_id=ter, cuenta_default_id=a)
    assert r.status_code == 409 and _codigo(r) == "PREFERENCIA_TERCERO_NO_ELEGIBLE"
    _sin_escritura(owner, pid)


@pytest.mark.parametrize("prioridad", [0, 50, 99, 101, 1000])
def test_prioridad_distinta_de_100(t, prioridad):
    owner, _, cli, a, _ = t
    pid, r = ph.alta(cli, cuenta_default_id=a, prioridad=prioridad)
    assert r.status_code == 422 and _codigo(r) == "PREFERENCIA_PRIORIDAD_NO_ADMITIDA"
    _sin_escritura(owner, pid)


def test_prioridad_100_explicita_admitida(t):
    _, _, cli, a, _ = t
    assert ph.alta(cli, cuenta_default_id=a, prioridad=100)[1].status_code == 200


@pytest.mark.parametrize("motivo", ["deshabilitada", "cerrada", "pasivo", "otra_moneda", "ajena", "inexistente",
                                    "sin_capacidad"])
def test_cuenta_no_elegible(t, motivo):
    owner, actor, cli, _, _ = t
    if motivo == "ajena":
        otro, otro_actor = h.crear_tenant()
        c = ph.cuenta(otro, otro_actor)
    elif motivo == "inexistente":
        c = uuid.uuid4()
    else:
        # R1/C1: «pasivo» = PASIVO SIN PAGAR_GASTO.
        kw = {"deshabilitada": {"enabled": False}, "cerrada": {"fecha_cierre": ph.FECHA},
              "pasivo": {"naturaleza": "PASIVO", "capacidades": ("TRANSFERIR_ENTRADA",)}, "otra_moneda": {"moneda": "USD"},
              "sin_capacidad": {"capacidades": ()}}[motivo]
        c = ph.cuenta(owner, actor, **kw)
    pid, r = ph.alta(cli, cuenta_default_id=c)
    assert r.status_code == 409 and _codigo(r) == "PREFERENCIA_CUENTA_NO_ELEGIBLE"
    _sin_escritura(owner, pid)


def test_preferencia_hacia_credito_con_pagar_gasto_admitida(t):
    """R2/E1: una cuenta de credito (PASIVO) con PAGAR_GASTO es elegible."""
    owner, actor, cli, _, _ = t
    credito = ph.cuenta(owner, actor, naturaleza="PASIVO")
    pid, r = ph.alta(cli, cuenta_default_id=credito)
    assert r.status_code == 200, r.text
    assert ph.fila(owner, pid)["cuenta_default_id"] == credito


def test_preferencia_de_ingreso_exige_recibir_ingreso(t):
    """R1: la cuenta de una preferencia de INGRESO necesita RECIBIR_INGRESO;
    una de credito (solo PAGAR_GASTO y TRANSFERIR_ENTRADA) no vale."""
    owner, actor, cli, a, _ = t
    ingreso = h.leer(owner, "SELECT id FROM gapto.tipos_hecho WHERE codigo='INGRESO'")[0][0]
    credito = ph.cuenta(owner, actor, naturaleza="PASIVO")
    pid, r = ph.alta(cli, tipo_hecho_id=ingreso, cuenta_default_id=credito)
    assert r.status_code == 409 and _codigo(r) == "PREFERENCIA_CUENTA_NO_ELEGIBLE"
    _sin_escritura(owner, pid)
    assert ph.alta(cli, tipo_hecho_id=ingreso, cuenta_default_id=a)[1].status_code == 200


@pytest.mark.parametrize("motivo", ["deshabilitada", "ajena", "inexistente"])
def test_categoria_no_elegible(t, motivo):
    owner, _, cli, a, _ = t
    if motivo == "deshabilitada":
        cat = ph.categoria(owner, "Vieja", enabled=False)
    elif motivo == "ajena":
        otro, _ = h.crear_tenant()
        cat = ph.categoria(otro, "Ajena")
    else:
        cat = uuid.uuid4()
    pid, r = ph.alta(cli, categoria_id=cat, cuenta_default_id=a)
    assert r.status_code == 409 and _codigo(r) == "PREFERENCIA_CATEGORIA_NO_ELEGIBLE"
    _sin_escritura(owner, pid)


def test_tipo_de_hecho_inexistente_es_entrada_invalida(t):
    owner, _, cli, a, _ = t
    pid, r = ph.alta(cli, tipo_hecho_id=uuid.uuid4(), cuenta_default_id=a)
    assert r.status_code == 422 and _codigo(r) == "ENTRADA_INVALIDA"
    _sin_escritura(owner, pid)


def test_forma_invalida_es_entrada_invalida(t):
    _, _, cli, _, _ = t
    r = cli.post(ph.BASE, json={"id": str(uuid.uuid4()), "presupuestable_default": True, "extra": 1}, headers=h.AUTH)
    assert r.status_code == 422 and _codigo(r) == "ENTRADA_INVALIDA"


# ------------------------------------------------------------------ empate
def test_empate_misma_clave_valores_distintos(t):
    owner, _, cli, a, b = t
    cat = ph.categoria(owner, "Super")
    p1, r = ph.alta(cli, categoria_id=cat, cuenta_default_id=a)
    assert r.status_code == 200
    p2, r = ph.alta(cli, categoria_id=cat, cuenta_default_id=b)
    assert r.status_code == 409 and _codigo(r) == EMPATE
    assert r.json()["detalle"] == {"preferencia_conflicto_id": str(p1)}
    _sin_escritura(owner, p2)


def test_empate_por_comodines(t):
    """tipo + categoria frente a tipo + tercero (E2): misma especificidad (2)
    y pueden coincidir (cada dimension: igual o alguna NULL)."""
    owner, _, cli, a, b = t
    cat = ph.categoria(owner, "Super")
    p1, r = ph.alta(cli, categoria_id=cat, cuenta_default_id=a)
    assert r.status_code == 200
    _, r = ph.alta(cli, tercero_id=ph.tercero(owner), cuenta_default_id=b)
    assert r.status_code == 409 and _codigo(r) == EMPATE
    assert r.json()["detalle"]["preferencia_conflicto_id"] == str(p1)


def test_empate_en_presupuestable(t):
    owner, _, cli, _, _ = t
    assert ph.alta(cli, presupuestable_default=True)[1].status_code == 200
    _, r = ph.alta(cli, presupuestable_default=False)
    assert r.status_code == 409 and _codigo(r) == EMPATE


@pytest.mark.parametrize("caso", ["campos_distintos", "mismo_valor", "otra_especificidad", "categorias_distintas",
                                  "tipos_distintos"])
def test_no_empate(t, caso):
    owner, _, cli, a, b = t
    g = ph.tipo_gasto(owner)
    c1, c2 = ph.categoria(owner, "Uno"), ph.categoria(owner, "Dos")
    primero, segundo = {
        "campos_distintos": ({"categoria_id": c1, "cuenta_default_id": a},
                             {"categoria_id": c1, "presupuestable_default": True}),
        "mismo_valor": ({"categoria_id": c1, "cuenta_default_id": a},
                        {"tercero_id": ph.tercero(owner), "cuenta_default_id": a}),
        "otra_especificidad": ({"cuenta_default_id": a}, {"categoria_id": c1, "cuenta_default_id": b}),
        "categorias_distintas": ({"categoria_id": c1, "cuenta_default_id": a},
                                 {"categoria_id": c2, "cuenta_default_id": b}),
        "tipos_distintos": ({"tipo_hecho_id": g, "cuenta_default_id": a},
                            {"tipo_hecho_id": ph.otro_tipo(owner), "cuenta_default_id": b}),
    }[caso]
    assert ph.alta(cli, **primero)[1].status_code == 200
    _, r = ph.alta(cli, **segundo)
    assert r.status_code == 200, r.text


def test_desactivada_no_genera_empate(t):
    owner, _, cli, a, b = t
    p1, _ = ph.alta(cli, cuenta_default_id=a)
    assert ph.desactivar(cli, p1, 1).status_code == 200
    assert ph.alta(cli, cuenta_default_id=b)[1].status_code == 200


def test_fila_con_dimension_diferida_no_genera_empate(t):
    owner, _, cli, a, b = t
    ph.insertar_sql(owner, tercero_id=ph.tercero(owner), cuenta=a)
    assert ph.alta(cli, cuenta_default_id=b)[1].status_code == 200


# ------------------------------------------------------------------ editar
def test_editar_row_version_y_auditoria(t):
    owner, _, cli, a, b = t
    pid, _ = ph.alta(cli, cuenta_default_id=a)
    r = ph.editar(cli, pid, 1, cuenta_default_id=b, presupuestable_default=True)
    assert r.status_code == 200, r.text
    assert r.json()["preferencia"]["row_version"] == 2
    f = ph.fila(owner, pid)
    assert f["cuenta_default_id"] == b and f["presupuestable_default"] is True
    assert ph.auditorias(owner, pid) == [("CREAR", "F05-02 ALTA"), ("ACTUALIZAR", "F05-02 EDITAR")]
    r = ph.editar(cli, pid, 1, cuenta_default_id=a)
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA"
    assert ph.fila(owner, pid)["row_version"] == 2


def test_editar_sin_cambios_es_idempotente_sin_escritura(t):
    owner, _, cli, a, _ = t
    pid, _ = ph.alta(cli, cuenta_default_id=a)
    r = ph.editar(cli, pid, 1, cuenta_default_id=a)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    assert ph.fila(owner, pid)["row_version"] == 1 and len(ph.auditorias(owner, pid)) == 1


def test_editar_valida_como_el_alta(t):
    owner, actor, cli, a, _ = t
    pid, _ = ph.alta(cli, cuenta_default_id=a)
    casos = [
        ({}, "PREFERENCIA_SIN_VALOR"),
        ({"cuenta_default_id": a, "tipo_hecho_id": None}, "PREFERENCIA_SIN_TIPO"),
        ({"cuenta_default_id": a, "tercero_id": ph.tercero(owner), "categoria_id": ph.categoria(owner, "Cat")},
         "PREFERENCIA_AMBITO_NO_ADMITIDO"),
        ({"cuenta_default_id": a, "tercero_id": uuid.uuid4()}, "PREFERENCIA_TERCERO_NO_ELEGIBLE"),
        ({"cuenta_default_id": a, "entidad_id": uuid.uuid4()}, "PREFERENCIA_DIMENSION_DIFERIDA"),
        ({"cuenta_default_id": a, "prioridad": 90}, "PREFERENCIA_PRIORIDAD_NO_ADMITIDA"),
        ({"cuenta_default_id": ph.cuenta(owner, actor, moneda="USD")}, "PREFERENCIA_CUENTA_NO_ELEGIBLE"),
        ({"cuenta_default_id": a, "categoria_id": ph.categoria(owner, "Off", enabled=False)},
         "PREFERENCIA_CATEGORIA_NO_ELEGIBLE"),
    ]
    for campos, codigo in casos:
        r = ph.editar(cli, pid, 1, **campos)
        assert _codigo(r) == codigo, (campos, r.text)
    assert ph.fila(owner, pid)["row_version"] == 1 and len(ph.auditorias(owner, pid)) == 1


def test_editar_que_crea_empate_se_rechaza(t):
    owner, _, cli, a, b = t
    cat = ph.categoria(owner, "Super")
    p1, _ = ph.alta(cli, categoria_id=cat, cuenta_default_id=a)
    p2, _ = ph.alta(cli, categoria_id=ph.categoria(owner, "Otra"), cuenta_default_id=b)
    r = ph.editar(cli, p2, 1, categoria_id=cat, cuenta_default_id=b)
    assert r.status_code == 409 and _codigo(r) == EMPATE
    assert r.json()["detalle"]["preferencia_conflicto_id"] == str(p1)
    assert ph.fila(owner, p2)["row_version"] == 1


def test_editar_la_propia_no_choca_consigo_misma(t):
    _, _, cli, a, b = t
    pid, _ = ph.alta(cli, cuenta_default_id=a)
    assert ph.editar(cli, pid, 1, cuenta_default_id=b).status_code == 200


def test_editar_desactivada_no_evalua_empate_hasta_reactivar(t):
    owner, _, cli, a, b = t
    p1, _ = ph.alta(cli, cuenta_default_id=a)
    p2, _ = ph.alta(cli, presupuestable_default=True)
    assert ph.desactivar(cli, p2, 1).status_code == 200
    assert ph.editar(cli, p2, 2, cuenta_default_id=b).status_code == 200
    r = ph.reactivar(cli, p2, 3)
    assert r.status_code == 409 and _codigo(r) == EMPATE
    assert r.json()["detalle"]["preferencia_conflicto_id"] == str(p1)
    assert ph.fila(owner, p2)["enabled"] is False


def test_editar_inexistente(t):
    _, _, cli, a, _ = t
    r = ph.editar(cli, uuid.uuid4(), 1, cuenta_default_id=a)
    assert r.status_code == 404 and _codigo(r) == "AGREGADO_NO_ENCONTRADO"


# ------------------------------------------------------------------ desactivar / reactivar
def test_desactivar_y_reactivar(t):
    owner, _, cli, a, _ = t
    pid, _ = ph.alta(cli, cuenta_default_id=a)
    r = ph.desactivar(cli, pid, 1)
    assert r.status_code == 200 and r.json()["preferencia"]["enabled"] is False
    r = ph.desactivar(cli, pid, 2)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    r = ph.reactivar(cli, pid, 1)
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA"
    r = ph.reactivar(cli, pid, 2)
    assert r.status_code == 200 and r.json()["preferencia"]["enabled"] is True
    r = ph.reactivar(cli, pid, 3)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    assert ph.auditorias(owner, pid) == [("CREAR", "F05-02 ALTA"), ("ACTUALIZAR", "F05-02 DESACTIVAR"),
                                         ("ACTUALIZAR", "F05-02 REACTIVAR")]
    assert ph.fila(owner, pid)["row_version"] == 3


def test_desactivar_version_desfasada(t):
    owner, _, cli, a, _ = t
    pid, _ = ph.alta(cli, cuenta_default_id=a)
    r = ph.desactivar(cli, pid, 7)
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA"
    assert ph.fila(owner, pid)["enabled"] is True


def test_reactivacion_que_crea_empate_se_rechaza(t):
    owner, _, cli, a, b = t
    p1, _ = ph.alta(cli, cuenta_default_id=a)
    assert ph.desactivar(cli, p1, 1).status_code == 200
    p2, _ = ph.alta(cli, cuenta_default_id=b)
    r = ph.reactivar(cli, p1, 2)
    assert r.status_code == 409 and _codigo(r) == EMPATE
    assert r.json()["detalle"]["preferencia_conflicto_id"] == str(p2)
    assert ph.fila(owner, p1)["enabled"] is False and len(ph.auditorias(owner, p1)) == 2


def test_reactivar_no_revalida_la_cuenta(t):
    """La cuenta que deja de ser elegible no impide reactivar: el resolver la
    ignora y la lista lo avisa (R-F05-02-03)."""
    owner, _, cli, a, _ = t
    pid, _ = ph.alta(cli, cuenta_default_id=a)
    assert ph.desactivar(cli, pid, 1).status_code == 200
    ph.deshabilitar_cuenta(owner, a)
    assert ph.reactivar(cli, pid, 2).status_code == 200


def test_reactivar_fila_con_dimension_diferida_se_rechaza(t):
    """entidad_id sigue diferida (DIMENSION_DIFERIDA); una fila sin tipo
    tampoco se pone en uso (E3, SIN_TIPO). Una fila tipo + tercero ya es
    valida (E2) y no entra aqui."""
    owner, _, cli, a, _ = t
    for kw, codigo in (({"entidad_id": ph.entidad(owner)}, "PREFERENCIA_DIMENSION_DIFERIDA"),
                       ({"tipo_hecho_id": None}, "PREFERENCIA_SIN_TIPO")):
        pid = ph.insertar_sql(owner, cuenta=a, enabled=False, **kw)
        r = ph.reactivar(cli, pid, 1)
        assert r.status_code == 422 and _codigo(r) == codigo
        assert ph.fila(owner, pid)["enabled"] is False


@pytest.mark.parametrize("comando", ["desactivar", "reactivar"])
def test_inexistente_404(t, comando):
    _, _, cli, _, _ = t
    r = getattr(ph, comando)(cli, uuid.uuid4(), 1)
    assert r.status_code == 404 and _codigo(r) == "AGREGADO_NO_ENCONTRADO"


# ------------------------------------------------------------------ RLS y lista
def test_aislamiento_por_owner(t):
    owner, _, cli, a, _ = t
    otro, otro_actor = h.crear_tenant()
    ajena = ph.insertar_sql(otro, cuenta=ph.cuenta(otro, otro_actor))
    for r in (ph.editar(cli, ajena, 1, presupuestable_default=True), ph.desactivar(cli, ajena, 1),
              ph.reactivar(cli, ajena, 1)):
        assert r.status_code == 404 and _codigo(r) == "AGREGADO_NO_ENCONTRADO"
    assert ph.fila(otro, ajena)["row_version"] == 1
    # La del otro owner no cuenta para el empate.
    assert ph.alta(cli, cuenta_default_id=a)[1].status_code == 200
    ids = {p["id"] for p in cli.get(ph.BASE, headers=h.AUTH).json()["preferencias"]}
    assert str(ajena) not in ids


def test_lista_con_desactivadas_y_cuenta_disponible_hoy(t):
    owner, _, cli, a, b = t
    cat = ph.categoria(owner, "Super")
    p1, _ = ph.alta(cli, cuenta_default_id=a)
    p2, _ = ph.alta(cli, categoria_id=cat, cuenta_default_id=b)
    p3, _ = ph.alta(cli, categoria_id=cat, presupuestable_default=True)
    assert ph.desactivar(cli, p1, 1).status_code == 200
    ph.deshabilitar_cuenta(owner, b)
    r = cli.get(ph.BASE, headers=h.AUTH)
    assert r.status_code == 200, r.text
    lista = {p["id"]: p for p in r.json()["preferencias"]}
    assert [p["id"] for p in r.json()["preferencias"]] == [str(p1), str(p2), str(p3)]
    assert lista[str(p1)]["enabled"] is False and lista[str(p1)]["cuenta_disponible_hoy"] is True
    assert lista[str(p2)]["cuenta_disponible_hoy"] is False
    assert lista[str(p3)]["cuenta_disponible_hoy"] is None


def test_lista_incluye_los_tipos_de_registro(t):
    """E3 (J2 §1.5): GET /v1/preferencias informa los ids de GASTO e INGRESO
    para que el cliente envie siempre el tipo."""
    owner, _, cli, _, _ = t
    r = cli.get(ph.BASE, headers=h.AUTH)
    assert r.status_code == 200
    ingreso = h.leer(owner, "SELECT id FROM gapto.tipos_hecho WHERE codigo='INGRESO'")[0][0]
    assert r.json()["tipos"] == {"GASTO": str(ph.tipo_gasto(owner)), "INGRESO": str(ingreso)}
