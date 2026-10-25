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
# Version: 0.3.0 (MANT-K5-AJ; dictamen AJ-MK5-02/-03): guarda de la via real de
#   conexion (9b solo descuenta la apertura si el endpoint abre por
#   `_proveedor_por_defecto` y por ninguna otra via); evidencia con entorno
#   (plataforma, server_version, lc_collate), numero de muestras y todas las
#   muestras; en 9b una diferencia negativa es MUESTRA INCOHERENTE: se repite una
#   vez y, si persiste, el test falla. 9a sigue siendo la asercion principal.
# Version: 0.4.0 (F05-07/GATE adenda 2, MANT-PRE-GATE test_187; F05-D050 §64.3,
#   DEU-T187-LATENCIA, AJ-05): oraculo fijado del caso 9. 9a afirma < 50 ms sobre
#   servidor (EXPLAIN ANALYZE, plan + ejecucion, de cada sentencia capturada de la
#   busqueda REAL de GET /v1/terceros bajo gapto_runtime y RLS) + aplicacion
#   (pared de lecturas.buscar sin la espera de E/S de BD), informadas por
#   separado. Guarda nueva del numero de sentencias (SENTENCIAS_BUSQUEDA, N+1).
#   9b pasa a diagnostica (apertura, red, total; solo coherencia) y deja de
#   restar la apertura de conexion. Sin resta por RTT de SELECT 1. Arnes:
#   scripts/dev/mutantes_mant_pre_gate_t187.py.
# ============================================================

from __future__ import annotations

import json
import os
import pathlib
import platform
import statistics
import time
import uuid
from contextlib import contextmanager

import psycopg
import pytest

import f05_05_helpers as x
import vs01_api_helpers as h
import app.api.app as adaptador
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


# ------------------------------------------------------------------ caso 9 (K-5; F05-D050 §64.3, AJ-05)
# El contrato del caso 9 es la BUSQUEDA (50 ms con 3.000 terceros). Oraculo
# FIJADO por F05-D050 §64.3 (no se reinterpreta aqui):
#
# 9a (ASERCION PRINCIPAL). Magnitud por muestra = SERVIDOR + APLICACION, mediana
#   < 50 ms (umbral sin cambios):
#   - SERVIDOR: suma de `Planning Time` + `Execution Time` de EXPLAIN (ANALYZE,
#     FORMAT JSON) de CADA sentencia capturada de la busqueda real. La captura
#     se hace sobre la peticion HTTP real `GET /v1/terceros?q=merca`: la
#     conexion del adaptador (abierta por su via, `_proveedor_por_defecto`)
#     recibe un cursor instrumentado; las sentencias de la busqueda son las que
#     ejecuta `lecturas.buscar` (la operacion del endpoint) dentro de la
#     UnidadDeTrabajo real, ya con SET LOCAL ROLE gapto_runtime, la GUC del
#     owner y RLS. El EXPLAIN (ANALYZE) se lanza en la MISMA transaccion y el
#     MISMO backend, justo ANTES de la ejecucion real (conservador: lleva el
#     primer contacto del backend con el catalogo), con los mismos parametros,
#     y comprueba current_user = gapto_runtime y row_security = on.
#   - APLICACION: tiempo de pared de `lecturas.buscar` MENOS la espera de E/S de
#     base de datos (las llamadas `execute` de sus sentencias) y menos la propia
#     instrumentacion (el EXPLAIN). Queda la logica de la busqueda en Python:
#     patron, conversion de filas, filtrado de inactivos, orden normalizado y
#     limite.
#   Las dos componentes se informan por separado (mensaje del assert y JSON de
#   evidencia si GAPTO_K5_EVIDENCIA apunta a una carpeta).
#   PROHIBIDO (F05-D050): descontar el RTT de un `SELECT 1` como oraculo.
# Guarda del numero de sentencias (independiente de 9a): la busqueda ejecuta
#   exactamente SENTENCIAS_BUSQUEDA sentencias, tanto con 1 fila como con 50
#   (discriminante N+1).
# 9b (DIAGNOSTICA). Peticion HTTP extremo a extremo: registra apertura de
#   conexion, red (espera de E/S de las sentencias de la peticion: ida y vuelta,
#   servidor incluido) y total; SOLO afirma coherencia (componentes >= 0 y
#   apertura + red <= total). No afirma rendimiento del motor.
# Guarda de via (AJ-MK5-02): `test_caso9b_guarda_via_de_conexion` comprueba que
#   el endpoint abre su conexion por `_proveedor_por_defecto` y por ninguna
#   otra via; si cambia (pooling, otra fabrica), la apertura que registra 9b
#   deja de ser la del endpoint y el caso 9 ha de revisarse.
REPETICIONES = 7
UMBRAL_MS = 50
SENTENCIAS_BUSQUEDA = 1
INCOHERENTE = "muestra incoherente: revisar el entorno o la via de conexion"


def _preparar_caso9(owner, cli):
    _masivo(owner, 3000)
    x.tercero(cli, "Mercadona")


class _Medicion:
    """Estado de la instrumentacion de UNA peticion (se reinicia por muestra)."""

    def __init__(self, explicar: bool):
        self.explicar = explicar
        self.reiniciar()

    def reiniciar(self):
        self.sentencias = []
        self.aperturas_ms = []
        self.en_busqueda = False
        self.aplicacion_ms = None

    def busqueda(self):
        return [s for s in self.sentencias if s["fase"] == "busqueda"]


def _instrumentar(monkeypatch, explicar: bool) -> _Medicion:
    """Instala la instrumentacion SIN sustituir comportamiento: `psycopg.connect`
    mide la apertura y asigna un cursor que registra cada sentencia (y, si
    `explicar`, su EXPLAIN (ANALYZE) previo); `lecturas.buscar` marca la fase de
    la busqueda y mide su tiempo de pared. El endpoint y su SQL son los reales."""
    med = _Medicion(explicar)
    connect_original, buscar_original = psycopg.connect, lect_ter.buscar

    class CursorMedido(psycopg.Cursor):
        def execute(self, query, params=None, **kw):
            fase = "busqueda" if med.en_busqueda else "contexto"
            texto = query if isinstance(query, str) else query.as_string(self.connection)
            fila = {"fase": fase, "sql": texto}
            t0 = time.perf_counter()
            if med.explicar and fase == "busqueda":
                with psycopg.Cursor(self.connection) as ex:
                    plan = ex.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + texto, params).fetchone()[0][0]
                    rol, rls = ex.execute("SELECT current_user, current_setting('row_security')").fetchone()
                fila.update(plan_ms=plan["Planning Time"], ejecucion_ms=plan["Execution Time"], rol=rol, row_security=rls)
            t1 = time.perf_counter()
            try:
                return super().execute(query, params, **kw)
            finally:
                fila.update(instrumentacion_ms=(t1 - t0) * 1000, espera_ms=(time.perf_counter() - t1) * 1000)
                med.sentencias.append(fila)

    def connect_medido(*a, **k):
        t0 = time.perf_counter()
        conexion = connect_original(*a, **k)
        med.aperturas_ms.append((time.perf_counter() - t0) * 1000)
        conexion.cursor_factory = CursorMedido
        return conexion

    def buscar_medido(sesion, texto, incluir_inactivos):
        previas = len(med.sentencias)
        med.en_busqueda = True
        t0 = time.perf_counter()
        try:
            return buscar_original(sesion, texto, incluir_inactivos)
        finally:
            pared = (time.perf_counter() - t0) * 1000
            med.en_busqueda = False
            excluido = sum(s["espera_ms"] + s["instrumentacion_ms"] for s in med.sentencias[previas:])
            med.aplicacion_ms = pared - excluido

    monkeypatch.setattr(psycopg, "connect", connect_medido)
    monkeypatch.setattr(lect_ter, "buscar", buscar_medido)
    return med


def _entorno_medida() -> dict:
    with psycopg.connect(h.dsn()) as c:
        version = c.execute("SHOW server_version").fetchone()[0]
        collate = c.execute("SELECT datcollate FROM pg_database WHERE datname = current_database()").fetchone()[0]
    return {"platform": platform.platform(), "python": platform.python_version(),
            "server_version": version, "lc_collate": collate}


def _evidencia(nombre, datos):
    carpeta = os.getenv("GAPTO_K5_EVIDENCIA")
    if carpeta:
        destino = pathlib.Path(carpeta)
        destino.mkdir(parents=True, exist_ok=True)
        (destino / f"{nombre}.json").write_text(json.dumps(datos, indent=1, ensure_ascii=False), encoding="utf-8")


def _r(v):
    return round(v, 3)


def test_caso9a_busqueda_con_tres_mil_terceros_por_debajo_de_50_ms(e, monkeypatch):
    """Oraculo F05-D050 §64.3: mediana de (servidor + aplicacion) < 50 ms, ambas
    componentes informadas por separado. Ver el bloque de comentarios del caso 9."""
    owner, cli, _ = e
    entorno = _entorno_medida()
    _preparar_caso9(owner, cli)
    med = _instrumentar(monkeypatch, explicar=True)
    muestras = []
    for i in range(REPETICIONES + 1):  # la primera es calentamiento y no cuenta
        med.reiniciar()
        filas = buscar(cli, "merca")
        assert [t["nombre"] for t in filas] == ["Mercadona"]
        sent = med.busqueda()
        assert sent and med.aplicacion_ms is not None, ("sin sentencias de busqueda capturadas", med.sentencias)
        assert all((s["rol"], s["row_security"]) == ("gapto_runtime", "on") for s in sent), sent
        servidor = sum(s["plan_ms"] + s["ejecucion_ms"] for s in sent)
        if i:
            muestras.append({"servidor_ms": _r(servidor), "aplicacion_ms": _r(med.aplicacion_ms),
                             "total_ms": _r(servidor + med.aplicacion_ms),
                             "plan_ms": [_r(s["plan_ms"]) for s in sent],
                             "ejecucion_ms": [_r(s["ejecucion_ms"]) for s in sent]})
    mediana = statistics.median(m["total_ms"] for m in muestras)
    datos = {"caso": "9a", "oraculo": "F05-D050 §64.3: servidor (EXPLAIN ANALYZE plan+ejecucion) + aplicacion",
             "entorno": entorno, "muestras": len(muestras), "umbral_ms": UMBRAL_MS,
             "mediana_ms": _r(mediana),
             "servidor_mediana_ms": _r(statistics.median(m["servidor_ms"] for m in muestras)),
             "aplicacion_mediana_ms": _r(statistics.median(m["aplicacion_ms"] for m in muestras)),
             "sentencias_busqueda": [s["sql"] for s in med.busqueda()],
             "sentencias_contexto": len([s for s in med.sentencias if s["fase"] == "contexto"]),
             "detalle": muestras}
    _evidencia("caso9a", datos)
    assert mediana < UMBRAL_MS, datos


def test_caso9a_guarda_numero_de_sentencias(e, monkeypatch):
    """Guarda independiente de 9a: la busqueda real ejecuta exactamente
    SENTENCIAS_BUSQUEDA sentencias con 1 fila («merca») y con 50 filas
    («comercio», limite): una consulta por fila (N+1) o una sentencia adicional
    la rompen aunque el tiempo siga por debajo del umbral."""
    owner, cli, _ = e
    _preparar_caso9(owner, cli)
    med = _instrumentar(monkeypatch, explicar=False)
    cuentas = {}
    for q, n in (("merca", 1), ("comercio", 50)):
        med.reiniciar()
        assert len(buscar(cli, q)) == n
        cuentas[q] = [s["sql"] for s in med.busqueda()]
    _evidencia("caso9a_guarda_sentencias", {"caso": "9a-guarda", "constante": SENTENCIAS_BUSQUEDA, "sentencias": cuentas})
    assert {q: len(s) for q, s in cuentas.items()} == {"merca": SENTENCIAS_BUSQUEDA, "comercio": SENTENCIAS_BUSQUEDA}, cuentas


def test_caso9b_peticion_http_diagnostica(e, monkeypatch):
    """Diagnostico HTTP extremo a extremo (no afirma rendimiento del motor). Por
    muestra: apertura de conexion (psycopg.connect del adaptador), red (espera de
    E/S de las sentencias de la peticion: ida y vuelta, servidor incluido), total
    y resto = total - apertura - red (BEGIN/COMMIT, aplicacion y HTTP en proceso).
    Solo afirma coherencia: al menos una apertura, componentes >= 0 y
    apertura + red <= total. Una ronda incoherente se repite UNA vez; si persiste,
    falla."""
    owner, cli, _ = e
    entorno = _entorno_medida()
    _preparar_caso9(owner, cli)
    med = _instrumentar(monkeypatch, explicar=False)
    rondas = []
    for _ in range(2):
        muestras = []
        for i in range(REPETICIONES + 1):
            med.reiniciar()
            t0 = time.perf_counter()
            filas = buscar(cli, "merca")
            total = (time.perf_counter() - t0) * 1000
            assert [t["nombre"] for t in filas] == ["Mercadona"]
            apertura, red = sum(med.aperturas_ms), sum(s["espera_ms"] for s in med.sentencias)
            if i:
                muestras.append({"aperturas": len(med.aperturas_ms), "apertura_conexion_ms": _r(apertura),
                                 "red_ms": _r(red), "total_ms": _r(total), "resto_ms": _r(total - apertura - red)})
        incoherentes = [m for m in muestras
                        if m["aperturas"] < 1 or m["apertura_conexion_ms"] < 0 or m["red_ms"] < 0 or m["resto_ms"] < 0]
        rondas.append({"muestras": muestras, "incoherentes": len(incoherentes)})
        if not incoherentes:
            break
    ultima = rondas[-1]["muestras"]
    datos = {"caso": "9b", "diagnostico": True, "entorno": entorno, "muestras": len(ultima),
             "repeticiones": len(rondas), "muestra_incoherente": rondas[-1]["incoherentes"] > 0,
             **{f"{k}_mediana": _r(statistics.median(m[k] for m in ultima))
                for k in ("apertura_conexion_ms", "red_ms", "total_ms", "resto_ms")},
             "rondas": rondas}
    _evidencia("caso9b", datos)
    assert not datos["muestra_incoherente"], (INCOHERENTE, datos)


def test_caso9b_guarda_via_de_conexion(e, monkeypatch):
    """AJ-MK5-02. El cliente se construye como el de 9a/9b (configuracion por defecto, sin
    `proveedor_conexion` inyectado) DESPUES de instalar dos espias: uno sobre
    `app.api.app._proveedor_por_defecto` y otro sobre `psycopg.connect`. Durante
    `GET /v1/terceros?q=merca` toda conexion abierta debe pasar por el proveedor por
    defecto (al menos una, y ninguna por otra via)."""
    owner, _, _ = e
    aperturas = {"proveedor": 0, "connect": 0}
    original_proveedor, original_connect = adaptador._proveedor_por_defecto, psycopg.connect

    def proveedor_espia(dsn):
        abrir = original_proveedor(dsn)

        @contextmanager
        def _abrir():
            aperturas["proveedor"] += 1
            with abrir() as c:
                yield c
        return _abrir

    def connect_espia(*a, **k):
        aperturas["connect"] += 1
        return original_connect(*a, **k)

    monkeypatch.setattr(adaptador, "_proveedor_por_defecto", proveedor_espia)
    monkeypatch.setattr(psycopg, "connect", connect_espia)
    cli = h.cliente(owner, reloj=x.reloj())  # misma construccion que el cliente de 9a/9b (x.entorno)
    x.tercero(cli, "Mercadona")
    aperturas.update(proveedor=0, connect=0)
    filas = buscar(cli, "merca")
    assert [t["nombre"] for t in filas] == ["Mercadona"]
    assert aperturas["proveedor"] >= 1 and aperturas["connect"] == aperturas["proveedor"], (
        "El endpoint ya no abre su conexion (solo) por app.api.app._proveedor_por_defecto: el caso 9 ha de "
        f"revisarse antes de reutilizar su certificacion (AJ-MK5-02). Aperturas: {aperturas}")


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
