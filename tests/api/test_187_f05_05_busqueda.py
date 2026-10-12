# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_187_f05_05_busqueda.py
# Ruta: tests/api/test_187_f05_05_busqueda.py
# Descripcion: Busqueda de terceros en servidor y arbol de categorias para la
#   busqueda en el cliente (K2 §1.4; F05 §49.4 A3/A4, §49.5 R10, M5-09).
#   Dominio BUSQUEDA. Casos de §49.9: 9 (3.000 terceros por debajo de 50 ms
#   en local; homonimos por naturaleza y uso), 34 («garcía» encuentra
#   «García»; «garcia» no: sensible a acentos en v1) y 18 (aislamiento).
#   Ademas: inactivos solo con incluir_inactivos, nombre_legal, comodines del
#   usuario literales, limite 50 en orden (nombre normalizado, id), sin `q`
#   la lista de siempre, y el arbol de /v1/categorias con parent_id, ambito,
#   enabled y capturable (A3: la busqueda de categorias es del cliente).
# Version: 0.1.0 (F05-05 K2 §1.4)
# Version: 0.2.0 (MANT-K5, deuda K-5, F05 §50.6 y §52.3): el caso 9 deja de
#   medir la peticion HTTP completa contra un umbral pensado para la busqueda.
#   Se sustituye por 9a (busqueda real del endpoint sobre una conexion ya
#   abierta, mediana < 50 ms, umbral sin cambios) y 9b (peticion HTTP
#   desglosada: mediana HTTP - mediana de apertura de conexion < 50 ms). Los
#   tres valores van al mensaje del assert y, si GAPTO_K5_EVIDENCIA apunta a
#   una carpeta, a un JSON de evidencia. Ningun otro test cambia.
# ============================================================

from __future__ import annotations

import json
import os
import pathlib
import statistics
import time
import uuid
from contextlib import contextmanager

import psycopg
import pytest

import f05_05_helpers as x
import vs01_api_helpers as h
from app.api.app import _proveedor_por_defecto
from app.core.contexto import ContextoOperacion
from app.core.unidad_trabajo import UnidadDeTrabajo
from app.terceros import lecturas as lect_ter

URL = "/v1/terceros"


def buscar(cli, q, inactivos=False):
    params = {"q": q}
    if inactivos:
        params["incluir_inactivos"] = "1"
    r = cli.get(URL, params=params, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()["terceros"]


@pytest.fixture()
def e():
    owner, actor, cli, corriente, ahorro = x.entorno()
    return owner, cli, corriente


def test_caso34_sensible_a_acentos(e):
    _, cli, _ = e
    x.tercero(cli, "Ana García", "PERSONA")
    x.tercero(cli, "Talleres García S.L.", "EMPRESA")
    assert [t["nombre"] for t in buscar(cli, "garcía")] == ["Ana García", "Talleres García S.L."]
    assert [t["nombre"] for t in buscar(cli, "TALLERES")] == ["Talleres García S.L."]  # ILIKE: sin mayusculas (ASCII)
    # Nota (desviacion K2K3 D-BU-1): el plegado de mayusculas NO ASCII de ILIKE («GARCÍA» -> «garcía») depende
    # de la collation de la base (C en los clusters locales); no forma parte del contrato v1 y no se afirma aqui.
    assert buscar(cli, "garcia") == []


def test_caso9_homonimos_por_naturaleza_y_uso(e):
    _, cli, cta = e
    a1, a2 = x.tercero(cli, "Ana García", "PERSONA"), x.tercero(cli, "Ana García", "PERSONA")
    for _ in range(3):
        x.gasto(cli, cta, tercero_id=a1, fecha="2026-10-09")
    x.gasto(cli, cta, tercero_id=a2, fecha="2026-09-02")
    filas = {t["id"]: t for t in buscar(cli, "ana")}
    assert (filas[str(a1)]["naturaleza"], filas[str(a1)]["usos"], filas[str(a1)]["ultimo_uso"]) == ("PERSONA", 3, "2026-10-09")
    assert (filas[str(a2)]["usos"], filas[str(a2)]["ultimo_uso"]) == (1, "2026-09-02")


def test_inactivos_solo_con_incluir_inactivos(e):
    _, cli, _ = e
    norte, sur = x.tercero(cli, "Gimnasio Norte"), x.tercero(cli, "Gimnasio Sur")
    x.desactivar_tercero(cli, sur)
    assert [t["nombre"] for t in buscar(cli, "gimnas")] == ["Gimnasio Norte"]
    filas = buscar(cli, "gimnas", inactivos=True)
    assert [(t["nombre"], t["enabled"]) for t in filas] == [("Gimnasio Norte", True), ("Gimnasio Sur", False)]


def test_busca_tambien_en_nombre_legal(e):
    owner, cli, _ = e
    tid = x.tercero(cli, "Mi gimnasio")
    h.como_owner(owner, "UPDATE gapto.terceros SET nombre_legal='Fitness Iberia S.L.' WHERE id=%s", (tid,))
    assert [t["id"] for t in buscar(cli, "iberia")] == [str(tid)]


def test_comodines_del_usuario_son_literales(e):
    _, cli, _ = e
    x.tercero(cli, "100% Natural")
    x.tercero(cli, "Cien Natural")
    x.tercero(cli, "Uno_Dos")
    x.tercero(cli, "UnoXDos")
    assert [t["nombre"] for t in buscar(cli, "100%")] == ["100% Natural"]
    assert [t["nombre"] for t in buscar(cli, "uno_")] == ["Uno_Dos"]
    assert [t["nombre"] for t in buscar(cli, "%")] == ["100% Natural"]  # literal, no comodin
    assert buscar(cli, "   ") == []


def test_sin_q_la_lista_de_siempre_con_activos_e_inactivos(e):
    _, cli, _ = e
    a, b = x.tercero(cli, "Beta"), x.tercero(cli, "Alfa")
    x.desactivar_tercero(cli, a)
    filas = cli.get(URL, headers=h.AUTH).json()["terceros"]
    assert [(t["nombre"], t["enabled"]) for t in filas] == [("Alfa", True), ("Beta", False)]
    assert all("ultimo_uso" in t for t in filas)


def _masivo(owner, n, prefijo="Comercio"):
    with psycopg.connect(h.dsn()) as c, c.transaction():
        c.execute("SET LOCAL ROLE gapto_owner")
        c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
        with c.cursor() as cur:
            cur.executemany("INSERT INTO gapto.terceros (id, owner_user_id, nombre, naturaleza) VALUES (%s,%s,%s,'EMPRESA')",
                            [(uuid.uuid4(), owner, f"{prefijo} {i:04d}") for i in range(n)])


def test_limite_50_en_orden_normalizado(e):
    owner, cli, _ = e
    _masivo(owner, 80)
    filas = buscar(cli, "comercio")
    assert len(filas) == 50 and [t["nombre"] for t in filas] == [f"Comercio {i:04d}" for i in range(50)]


# ------------------------------------------------------------------ caso 9 (K-5)
# El contrato del caso 9 es la BUSQUEDA (50 ms con 3.000 terceros). La peticion
# HTTP completa abre una conexion PostgreSQL nueva por unidad de trabajo, y ese
# coste es del entorno (≈ 47 ms en local el 2026-10-12, ≈ 277 ms en Neon), no
# de la busqueda. 9a mide la busqueda; 9b mide la peticion HTTP y descuenta la
# apertura de conexion medida por la MISMA via que usa el adaptador.
REPETICIONES = 7
UMBRAL_MS = 50


def _preparar_caso9(owner, cli):
    _masivo(owner, 3000)
    x.tercero(cli, "Mercadona")


def _mediana_ms(fn, n=REPETICIONES):
    fn()  # calentamiento
    tiempos, ultimo = [], None
    for _ in range(n):
        t0 = time.perf_counter()
        ultimo = fn()
        tiempos.append((time.perf_counter() - t0) * 1000)
    return statistics.median(tiempos), tiempos, ultimo


def _evidencia(nombre, datos):
    carpeta = os.getenv("GAPTO_K5_EVIDENCIA")
    if carpeta:
        destino = pathlib.Path(carpeta)
        destino.mkdir(parents=True, exist_ok=True)
        (destino / f"{nombre}.json").write_text(json.dumps(datos, indent=1, ensure_ascii=False), encoding="utf-8")


def test_caso9a_busqueda_con_tres_mil_terceros_por_debajo_de_50_ms(e):
    """Tiempo de pared de la busqueda REAL del endpoint (`lecturas.buscar`, el SQL y el
    orden del modulo de terceros, sin copiar nada) ejecutada por la UnidadDeTrabajo real
    (SET LOCAL ROLE gapto_runtime, GUC del owner, RLS) sobre UNA conexion ya abierta y
    reutilizada. Se elige el tiempo de pared y no EXPLAIN ANALYZE porque incluye lo mismo
    que el endpoint ejecuta despues de abrir la conexion (consulta, filtrado y orden en
    Python), sin la apertura."""
    owner, cli, _ = e
    _preparar_caso9(owner, cli)
    with psycopg.connect(h.dsn()) as abierta:
        @contextmanager
        def reutilizada():
            yield abierta

        unidad = UnidadDeTrabajo(reutilizada, rol_runtime="gapto_runtime")
        contexto = ContextoOperacion.de_usuario(owner)
        mediana, tiempos, filas = _mediana_ms(
            lambda: unidad.ejecutar(contexto, lambda s: lect_ter.buscar(s, "merca", False), nombre="K-5 caso 9a"))
    datos = {"caso": "9a", "consulta_mediana_ms": round(mediana, 2), "consulta_ms": [round(t, 2) for t in tiempos]}
    _evidencia("caso9a", datos)
    assert [t["nombre"] for t in filas] == ["Mercadona"]
    assert mediana < UMBRAL_MS, datos


def test_caso9b_peticion_http_descontando_la_apertura_de_conexion(e):
    """(i) Peticion HTTP completa como el caso 9 original; (ii) apertura de una conexion
    vacia por la MISMA via que la unidad de trabajo del adaptador (`_proveedor_por_defecto`:
    abrir + SELECT 1 + cerrar). La peticion no se omite: lo que excede a la conexion
    debe quedar por debajo del umbral de la busqueda."""
    owner, cli, _ = e
    _preparar_caso9(owner, cli)
    http, t_http, filas = _mediana_ms(lambda: buscar(cli, "merca"))
    abrir = _proveedor_por_defecto(h.dsn())

    def conexion_vacia():
        with abrir() as c:
            c.execute("SELECT 1").fetchone()

    conexion, t_con, _ = _mediana_ms(conexion_vacia)
    datos = {"caso": "9b", "http_mediana_ms": round(http, 2), "conexion_mediana_ms": round(conexion, 2),
             "http_menos_conexion_ms": round(http - conexion, 2),
             "http_ms": [round(t, 2) for t in t_http], "conexion_ms": [round(t, 2) for t in t_con]}
    _evidencia("caso9b", datos)
    assert [t["nombre"] for t in filas] == ["Mercadona"]
    assert http - conexion < UMBRAL_MS, datos


def test_caso18_terceros_de_otro_owner_invisibles(e):
    _, cli, _ = e
    _, _, cli_b, _, _ = x.entorno()
    x.tercero(cli_b, "Solo de B")
    assert buscar(cli, "solo de b", inactivos=True) == []


def test_arbol_de_categorias_trae_lo_necesario_para_buscar_en_el_cliente(e):
    owner, cli, _ = e
    padre = x.categoria(owner, "Alimentación")
    x.categoria(owner, "Supermercados", parent_id=padre)
    x.categoria(owner, "Superávit de ahorro", "INGRESO")
    nodos = cli.get("/v1/categorias", headers=h.AUTH).json()["categorias"]
    assert nodos and all({"id", "parent_id", "nombre", "ambito", "enabled", "capturable"} <= set(n) for n in nodos)
