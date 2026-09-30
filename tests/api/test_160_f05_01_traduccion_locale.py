# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_160_f05_01_traduccion_locale.py
# Ruta: tests/api/test_160_f05_01_traduccion_locale.py
# Descripcion: R-LOCALE (F05 §30.6). La traduccion de los rechazos por
#   trigger (servicio._FUNCIONES_TRIGGER, AJ-S4-07) no depende del idioma
#   del servidor (lc_messages).
#   - Capa pura (sin base de datos; corre tambien en Neon): contextos
#     diag.context REALES capturados de PostgreSQL 17.5 (cluster local
#     desechable 0001..0340, rechazo por trigger real bajo gapto_runtime con
#     RLS), en ingles (lc_messages=C) y en espanol (lc_messages=es_ES), mas
#     negativos derivados del mismo formato (firma que solo es prefijo de
#     otra, otra funcion gapto, contexto vacio).
#   - Capa con PostgreSQL en cada idioma (C y es_ES, fijado por conexion con
#     options=-c lc_messages): los tres rechazos por trigger con su codigo,
#     sin escritura. Ciclo: el servicio rechaza antes el descendiente
#     (mover(), comprobacion de subarbol), asi que la aciclicidad se ejercita
#     con servicio._escribir sobre repo.actualizar (como test_159, AJ-S6ICONO-03).
#     D-122 y D-121 no tienen comprobacion previa: se ejercitan por la API.
#     Sonda obligatoria del idioma: si el rol no puede fijar lc_messages
#     (parametro de superusuario; Neon) se omite con MOTIVO_SKIP; si puede
#     pero el mensaje no sale en el idioma pedido, FALLA.
#   Base local desechable 0001..0340 (estos tests confirman filas). Datos
#   sinteticos, creados como gapto_owner con la GUC del tenant (WM 12C.7).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import urllib.parse
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h
from app.categorias import repositorio as repo
from app.categorias import servicio

B = fh.BASE
PADRE_NO_VALIDO = "CATEGORIA_PADRE_NO_VALIDO"
BLOQUEADO = "CATEGORIA_MOVIMIENTO_BLOQUEADO_POR_PRESUPUESTO"
MOTIVO_SKIP = "R-LOCALE: el rol de conexion no puede fijar lc_messages (parametro de superusuario)"

#: diag.context literal capturado (PostgreSQL 17.5, cluster local desechable
#: 0001..0340, 2026-09-30; evidencia rlocale/contextos_capturados.txt).
CONTEXTOS = {
    ("C", "fn_check_jerarquia_aciclica"):
        "PL/pgSQL function gapto.fn_check_jerarquia_aciclica() line 63 at RAISE",
    ("C", "fn_check_categoria_deriva"):
        "PL/pgSQL function gapto.fn_check_categoria_deriva() line 57 at RAISE",
    ("C", "fn_check_bolsa_prioridad"):
        "PL/pgSQL function gapto.fn_check_bolsa_prioridad() line 79 at RAISE",
    ("es_ES", "fn_check_jerarquia_aciclica"):
        "función PL/pgSQL gapto.fn_check_jerarquia_aciclica() en la línea 63 en RAISE",
    ("es_ES", "fn_check_categoria_deriva"):
        "función PL/pgSQL gapto.fn_check_categoria_deriva() en la línea 57 en RAISE",
    ("es_ES", "fn_check_bolsa_prioridad"):
        "función PL/pgSQL gapto.fn_check_bolsa_prioridad() en la línea 79 en RAISE",
}
ESPERADO = {
    "fn_check_jerarquia_aciclica": PADRE_NO_VALIDO,
    "fn_check_categoria_deriva": BLOQUEADO,
    "fn_check_bolsa_prioridad": BLOQUEADO,
}
SONDA = {"C": "division by zero", "es_ES": "división por cero"}


# ------------------------------------------------------------------ capa pura (sin BD)
@pytest.mark.parametrize("lc,funcion", sorted(CONTEXTOS))
def test_contexto_capturado_se_traduce_en_cualquier_idioma(lc, funcion):
    assert servicio._funcion_trigger(CONTEXTOS[(lc, funcion)]) == ESPERADO[funcion]


@pytest.mark.parametrize("contexto", [
    # Firma que solo es prefijo de otra (fn_check_bolsa_prioridad_alcance existe en el catalogo).
    "PL/pgSQL function gapto.fn_check_bolsa_prioridad_alcance() line 12 at RAISE",
    "función PL/pgSQL gapto.fn_check_bolsa_prioridad_alcance() en la línea 12 en RAISE",
    # Otra funcion gapto.
    "PL/pgSQL function gapto.fn_check_participacion_suma() line 20 at RAISE",
    # Contexto vacio o ausente.
    "",
    None,
])
def test_contexto_sin_firma_conocida_no_se_traduce(contexto):
    assert servicio._funcion_trigger(contexto) is None


# ------------------------------------------------------------------ capa con PostgreSQL en cada idioma
def _dsn_con_lc(base: str, lc: str) -> str:
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}options={urllib.parse.quote(f'-c lc_messages={lc}')}"


@pytest.fixture(params=["C", "es_ES"])
def idioma(request, monkeypatch):
    """Todas las conexiones del test (adaptador, UdT y helpers) con
    lc_messages fijado; sonda obligatoria del idioma."""
    lc = request.param
    # Privilegio por catalogo (no por el texto del error de conexion, que se
    # traduce y ademas no trae sqlstate).
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        puede = c.execute(
            "SELECT r.rolsuper OR has_parameter_privilege(current_user, 'lc_messages', 'SET') "
            "FROM pg_roles r WHERE r.rolname = current_user").fetchone()[0]
    if not puede:
        pytest.skip(MOTIVO_SKIP)
    dsn = _dsn_con_lc(h.dsn(), lc)
    mensaje = ""
    with psycopg.connect(dsn, autocommit=True) as c:
        try:
            c.execute("SELECT 1/0")
        except psycopg.errors.DivisionByZero as exc:
            mensaje = exc.diag.message_primary or ""
    assert SONDA[lc] in mensaje, f"lc_messages={lc} fijado pero el servidor responde {mensaje!r}"
    monkeypatch.setenv("GAPTO_TEST_DATABASE_URL", dsn)
    return lc


@pytest.fixture()
def ctx(idioma):
    owner, actor = h.crear_tenant()
    return owner, actor, h.cliente(owner)


def _codigo(r) -> str:
    return r.json().get("codigo")


def _auditorias(owner, cid) -> list[str]:
    return [m for _, m, _ in fh.auditorias(owner, cid)]


def test_aciclicidad_por_trigger_real_se_traduce(ctx):
    """El servicio rechaza antes el descendiente; aqui se llega al trigger
    fn_check_jerarquia_aciclica() con _escribir sobre repo.actualizar."""
    owner, _, _ = ctx
    x = fh.crear_categoria(owner, "X", "GASTO")
    y = fh.crear_categoria(owner, "Y", "GASTO", parent_id=x)
    rechazo = fh.en_transaccion(
        owner, lambda s: servicio._escribir(s, lambda: repo.actualizar(s, x, {"parent_id": y})))
    assert rechazo == servicio.Rechazo(PADRE_NO_VALIDO)
    assert fh.estado(owner, x)[1] is None and fh.rv(owner, x) == 1
    assert fh.auditorias(owner, x) == []


def test_mover_bloqueado_por_presupuesto_congelado_d122_en_cada_idioma(ctx):
    owner, _, cli = ctx
    x, _ = fh.alta(cli, "Alimentacion")
    y, _ = fh.alta(cli, "Super", parent_id=x)
    fh.crear_presupuesto(owner, [(1, [(x, True)])], estado_final="ACTIVO")
    r = fh.cmd(cli, f"{B}/{y}/mover", {"parent_id": None, "row_version": 1})
    assert r.status_code == 409 and _codigo(r) == BLOQUEADO, r.text
    assert fh.estado(owner, y)[1] == x and fh.rv(owner, y) == 1
    assert "F05-01 MOVER" not in _auditorias(owner, y)


def test_mover_que_solapa_bolsas_sin_prioridad_d121_en_cada_idioma(ctx):
    owner, _, cli = ctx
    x, _ = fh.alta(cli, "X")
    y, _ = fh.alta(cli, "Y")
    fh.crear_presupuesto(owner, [(None, [(x, True)]), (None, [(y, True)])])
    r = fh.cmd(cli, f"{B}/{y}/mover", {"parent_id": str(x), "row_version": 1})
    assert r.status_code == 409 and _codigo(r) == BLOQUEADO, r.text
    assert fh.estado(owner, y)[1] is None and fh.rv(owner, y) == 1
    assert "F05-01 MOVER" not in _auditorias(owner, y)
