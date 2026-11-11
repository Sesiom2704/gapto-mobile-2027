# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_235_f06_01_0352_guarda_c_prop_02.py
# Ruta: tests/api/test_235_f06_01_0352_guarda_c_prop_02.py
# Descripcion: N1 de 0352 (mandato v1.4), Alcance 5 y 6. Por HTTP, como gapto_runtime con RLS (adaptador real):
#   - Guarda de C-PROP-02 (AJ-0352-05; extension de B1 autorizada prospectivamente por F06-D006, expediente F06
#     0.5 §1.5): con la adquisicion declarada completa, `editar` rechaza una fecha_adquisicion POSTERIOR al corte
#     con ADQUISICION_POSTERIOR_AL_CORTE_DECLARADO (422), sin escribir nada (huella global, row_version,
#     auditoria y declaracion intactas); igual o anterior al corte se acepta; sin declaracion (o con solo la de
#     mejoras) no aplica; precedencia: replay identico -> VERSION_DESFASADA -> guarda.
#   - AJ-0352-08: las seis columnas de 0352 no se escriben por C-PROP-01/02. Barrera HTTP: el DTO las rechaza
#     (422) en el alta y en editar. Barrera de servicio: `editar` con cualquiera de ellas da ENTRADA_INVALIDA sin
#     escribir y `alta` las ignora (quedan NULL). Inventario: ningun modulo de backend/app las nombra salvo la
#     lectura del corte (repositorio.corte_adquisicion_declarado).
#   Las declaraciones se siembran por SQL bajo gapto_owner con la GUC de tenant, porque su writer (C-PROP-05) es
#   de B2-B3 (Alcance 9) y no existe en este N1. La concurrencia con una declaracion simultanea esta en
#   test_236 (bateria serie, GAPTO_0352_CONCURRENCIA=1).
# Version: 0.1.0 (F03 · N1 de 0352, mandato v1.4)
# ============================================================

from __future__ import annotations

import datetime as dt
import pathlib
import re
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import f06_01_b1_helpers as b
import vs01_api_helpers as h
from app.core.contexto import ContextoOperacion
from app.propiedades import servicio as serv

CODIGO = "ADQUISICION_POSTERIOR_AL_CORTE_DECLARADO"
SEIS = ("coste_adquisicion_declarado_completo", "coste_adquisicion_declarado_en", "coste_adquisicion_conjunto_declarado",
        "mejoras_declaradas_completas", "mejoras_declaradas_en", "mejoras_conjunto_declarado")
VALOR_SEIS = {"coste_adquisicion_declarado_completo": True, "coste_adquisicion_declarado_en": "2026-02-01",
              "coste_adquisicion_conjunto_declarado": [], "mejoras_declaradas_completas": True,
              "mejoras_declaradas_en": "2026-02-01", "mejoras_conjunto_declarado": []}
RAIZ = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture()
def t():
    return b.entorno()


def ruta(pid, sufijo: str = "") -> str:
    return f"/v1/propiedades/{pid}{sufijo}"


def declarar(owner, pid, *, adquisicion: str | None = None, mejoras: str | None = None) -> None:
    """Siembra una declaracion de completitud (lo que hara C-PROP-05 en B2-B3), sin tocar row_version."""
    with psycopg.connect(h.dsn()) as c, c.transaction():
        c.execute("SET LOCAL ROLE gapto_owner")
        c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
        if adquisicion:
            c.execute("UPDATE gapto.propiedades SET coste_adquisicion_declarado_completo = true, "
                      "coste_adquisicion_declarado_en = %s, coste_adquisicion_conjunto_declarado = '[]'::jsonb "
                      "WHERE entidad_id = %s", (adquisicion, pid))
        if mejoras:
            c.execute("UPDATE gapto.propiedades SET mejoras_declaradas_completas = true, mejoras_declaradas_en = %s, "
                      "mejoras_conjunto_declarado = '[]'::jsonb WHERE entidad_id = %s", (mejoras, pid))


def declaracion(owner, pid):
    return h.leer(owner, "SELECT " + ", ".join(SEIS) + " FROM gapto.propiedades WHERE entidad_id = %s", (pid,))[0]


def editar(cli, pid, version, intencion=None, **campos):
    return b.post(cli, ruta(pid, "/editar"), {"intencion_id": str(intencion or uuid.uuid4()), "row_version_esperada": version, **campos})


def auditorias(owner, intencion) -> list:
    return h.leer(owner, "SELECT accion FROM gapto.auditoria WHERE request_id = %s", (str(intencion),))


def _rechazo(r, status: int, codigo: str):
    assert r.status_code == status, r.text
    assert r.json()["codigo"] == codigo, r.text


# ================================================================== guarda de C-PROP-02 (Alcance 5)
def test_guarda_rechaza_fecha_posterior_al_corte_sin_escribir_nada(t):
    owner, _, cli = t
    p = b.crear(cli, b.alta(fecha_adquisicion="2025-06-01"))
    declarar(owner, p["id"], adquisicion="2025-12-31")
    decl = declaracion(owner, p["id"])
    antes = b.huella()
    intencion = uuid.uuid4()
    r = editar(cli, p["id"], 1, intencion, fecha_adquisicion="2026-01-01")
    _rechazo(r, 422, CODIGO)
    assert r.json()["mensaje"] and r.json()["reintentable"] is False
    assert b.huella() == antes                                         # nada escrito (propiedad, version, auditoria)
    assert b.leer(cli, p["id"])["row_version"] == 1 and b.leer(cli, p["id"])["fecha_adquisicion"] == "2025-06-01"
    assert auditorias(owner, intencion) == []
    assert declaracion(owner, p["id"]) == decl                         # la declaracion se conserva


@pytest.mark.parametrize("fecha", ["2025-12-31", "2025-09-15"], ids=["igual_al_corte", "anterior_al_corte"])
def test_guarda_admite_fecha_igual_o_anterior_al_corte(t, fecha):
    owner, _, cli = t
    p = b.crear(cli, b.alta(fecha_adquisicion="2025-06-01"))
    declarar(owner, p["id"], adquisicion="2025-12-31")
    r = editar(cli, p["id"], 1, fecha_adquisicion=fecha)
    assert r.status_code == 200, r.text
    assert r.json()["propiedad"]["fecha_adquisicion"] == fecha and r.json()["propiedad"]["row_version"] == 2


def test_guarda_no_aplica_sin_declaracion_de_adquisicion(t):
    # 2025-12-20 es anterior al inicio de la titularidad del alta por defecto (2026-01-01): solo puede actuar la guarda
    owner, _, cli = t
    con = b.crear(cli, b.alta(nombre="Piso con declaracion", fecha_adquisicion="2025-06-01"))
    declarar(owner, con["id"], adquisicion="2025-11-30")
    _rechazo(editar(cli, con["id"], 1, fecha_adquisicion="2025-12-20"), 422, CODIGO)   # contraste: con declaracion, rechazo
    sin = b.crear(cli, b.alta(fecha_adquisicion="2025-06-01"))
    r = editar(cli, sin["id"], 1, fecha_adquisicion="2025-12-20")
    assert r.status_code == 200, r.text
    solo_mejoras = b.crear(cli, b.alta(nombre="Piso mejoras", fecha_adquisicion="2025-06-01"))
    declarar(owner, solo_mejoras["id"], mejoras="2025-07-01")
    r = editar(cli, solo_mejoras["id"], 1, fecha_adquisicion="2025-12-20")
    assert r.status_code == 200, r.text                                 # la declaracion de mejoras no limita la adquisicion


def test_guarda_solo_mira_fecha_adquisicion(t):
    owner, _, cli = t
    p = b.crear(cli, b.alta(fecha_adquisicion="2025-06-01"))
    declarar(owner, p["id"], adquisicion="2025-12-31")
    r = editar(cli, p["id"], 1, notas="Reformado", habitaciones=3)
    assert r.status_code == 200, r.text
    assert r.json()["propiedad"]["row_version"] == 2


def test_precedencia_version_desfasada_antes_que_la_guarda(t):
    owner, _, cli = t
    p = b.crear(cli, b.alta(fecha_adquisicion="2025-06-01"))
    assert editar(cli, p["id"], 1, notas="v2").status_code == 200        # version 2
    declarar(owner, p["id"], adquisicion="2025-12-31")
    antes = b.huella()
    _rechazo(editar(cli, p["id"], 1, fecha_adquisicion="2026-01-01"), 409, "VERSION_DESFASADA")
    assert b.huella() == antes


def test_precedencia_replay_identico_antes_que_version_y_guarda(t):
    owner, _, cli = t
    p = b.crear(cli, b.alta(fecha_adquisicion="2025-06-01"))
    intencion = uuid.uuid4()
    assert editar(cli, p["id"], 1, intencion, fecha_adquisicion="2025-10-01").status_code == 200
    declarar(owner, p["id"], adquisicion="2025-10-01")
    r = editar(cli, p["id"], 1, intencion, fecha_adquisicion="2025-10-01")   # replay con version superada
    assert r.status_code == 200 and r.json()["idempotente"] is True, r.text


def test_guarda_con_fecha_borrada_queda_fuera_de_su_alcance(t):
    # La autorizacion prospectiva (F06-D006 §1.5, punto 4) solo cubre la fecha POSTERIOR al corte. Borrar la fecha
    # (null) no es una fecha posterior: la guarda no la rechaza y el CHECK de corte la admite (NULL). Se documenta
    # el comportamiento sin crear una regla nueva; ver handoff (pregunta para la orquestacion).
    owner, _, cli = t
    p = b.crear(cli, b.alta(fecha_adquisicion="2025-06-01"))
    declarar(owner, p["id"], adquisicion="2025-12-31")
    r = editar(cli, p["id"], 1, fecha_adquisicion=None)
    assert r.status_code == 200, r.text
    assert r.json()["propiedad"]["fecha_adquisicion"] is None


def test_codigo_en_el_catalogo_http_sin_cambiar_otros():
    from app.api import errores_http as e
    assert e._RECHAZOS_PROPIEDAD[CODIGO][0] == 422
    assert e._RECHAZOS_PROPIEDAD["ADQUISICION_POSTERIOR_A_TITULARIDAD"][0] == 422
    assert e._RECHAZOS_PROPIEDAD["VERSION_DESFASADA"][0] == 409


# ================================================================== AJ-0352-08 (Alcance 6)
@pytest.mark.parametrize("columna", SEIS)
def test_aj0352_08_barrera_http_alta_y_editar(t, columna):
    owner, _, cli = t
    antes = b.huella()
    _rechazo(b.post(cli, "/v1/propiedades", {**b.alta(), columna: VALOR_SEIS[columna]}), 422, "ENTRADA_INVALIDA")
    assert b.huella() == antes
    p = b.crear(cli, b.alta(nombre=f"Piso {columna}"))
    antes = b.huella()
    _rechazo(editar(cli, p["id"], 1, **{columna: VALOR_SEIS[columna]}), 422, "ENTRADA_INVALIDA")
    assert b.huella() == antes
    assert all(v is None for v in declaracion(owner, p["id"]))


def _ejecutar(owner, operacion):
    ctx = ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())
    return fh.unidad().ejecutar(ctx, operacion, nombre="test 0352 AJ-0352-08")


@pytest.mark.parametrize("columna", SEIS)
def test_aj0352_08_barrera_servicio_editar(t, columna):
    owner, _, cli = t
    p = b.crear(cli, b.alta(nombre=f"Piso servicio {columna}"))
    antes = b.huella()
    valor = dt.date(2026, 2, 1) if columna.endswith("_en") else VALOR_SEIS[columna]
    r = _ejecutar(owner, lambda s: serv.editar(s, entidad_id=uuid.UUID(p["id"]), intencion_id=uuid.uuid4(), row_version=1,
                                               campos={columna: valor}))
    assert isinstance(r, serv.Rechazo) and r.codigo == "ENTRADA_INVALIDA"
    assert b.huella() == antes


def test_aj0352_08_barrera_servicio_alta_ignora_las_seis(t):
    owner, _, cli = t
    pid = uuid.uuid4()
    datos = {"tipo_propiedad": "VIVIENDA", **{c: (dt.date(2026, 2, 1) if c.endswith("_en") else v) for c, v in VALOR_SEIS.items()}}
    r = _ejecutar(owner, lambda s: serv.alta(s, entidad_id=pid, nombre="Piso alta servicio", datos=datos, modo="DESCONOCIDA",
                                             desde=None, partes=None))
    assert not isinstance(r, serv.Rechazo), r
    assert all(v is None for v in declaracion(owner, str(pid)))         # oraculo: columnas NULL tras el alta


def test_aj0352_08_columnas_fuera_de_editables_y_columnas_propiedad():
    from app.propiedades import repositorio as repo
    assert not set(SEIS) & set(repo.COLUMNAS_PROPIEDAD)
    assert not set(SEIS) & set(serv.EDITABLES)


def test_aj0352_08_inventario_de_escritura_en_backend():
    """Solo la lectura del corte nombra columnas de 0352 en backend/app (ninguna escritura)."""
    hallados = {}
    for f in (RAIZ / "backend" / "app").rglob("*.py"):
        texto = "\n".join(linea.split("#", 1)[0] for linea in f.read_text(encoding="utf-8").splitlines())   # sin comentarios
        nombres = sorted({c for c in SEIS if re.search(r"\b" + c + r"\b", texto)})
        if nombres:
            hallados[f.relative_to(RAIZ).as_posix()] = nombres
    assert hallados == {"backend/app/propiedades/repositorio.py": ["coste_adquisicion_declarado_completo",
                                                                   "coste_adquisicion_declarado_en"]}, hallados
    repo_txt = (RAIZ / "backend" / "app" / "propiedades" / "repositorio.py").read_text(encoding="utf-8")
    assert not re.search(r"(UPDATE|INSERT)[^;\"]*coste_adquisicion_declarado", repo_txt)
