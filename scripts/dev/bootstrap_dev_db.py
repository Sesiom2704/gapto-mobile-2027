# ============================================================
# GAPTO MOBILE 2027
# Fichero: bootstrap_dev_db.py
# Ruta: scripts/dev/bootstrap_dev_db.py
# Descripcion: Crea/recrea la base LOCAL de desarrollo de F05-00-B
#   (`gapto2027_dev`) aplicando la cadena 0001..HEAD_AUTORIZADO_ENVDEV del
#   repositorio y
#   carga FIXTURES SINTETICOS minimos para VS-01 (sin PII, sin datos V3):
#     - usuario sintetico (email @example.invalid);
#     - actor self;
#     - una cuenta CORRIENTE EUR con participacion vigente 100 % del self.
#   Solo para PostgreSQL LOCAL de desarrollo. Protecciones:
#     - rechaza cualquier host que no sea socket local o localhost/127.0.0.1;
#     - la base destino se llama SIEMPRE `gapto2027_dev`;
#     - `--recrear` es obligatorio para destruir una base existente.
#   Nunca usar contra Neon ni Supabase (D-179; Neon dev no autorizado).
#   No es un runner de certificacion (no sustituye a run_clean_room.py).
#
#   HEAD AUTORIZADO (revision del P0 de 0340, D-197). Publicar una migration en
#   main NO la autoriza en ENV-DEV. La cadena se corta SIEMPRE en
#   HEAD_AUTORIZADO_ENVDEV; las migrations posteriores presentes en el
#   repositorio no se aplican y se listan en la salida. Subir el head de
#   ENV-DEV exige cambiar esa constante en un commit revisado: no hay opcion de
#   linea de comandos para superarlo. La cadena se valida ANTES de crear o
#   destruir la base, de modo que un repositorio incoherente (head ausente o
#   duplicado, nombre de migration fuera de patron) aborta sin tocar nada.
#
#   Uso:
#     python scripts/dev/bootstrap_dev_db.py --admin-dsn "host=/tmp port=5433 user=postgres" [--recrear]
#   Imprime GAPTO_DEV_OWNER_USER_ID para configurar el adaptador.
#
#   MODO --seed-categorias (F05 §26.4 Q8; AJ-C07-10): catalogo SINTETICO de
#   categorias de ENV-DEV sobre una `gapto2027_dev` ya creada (no la crea ni
#   la recrea). Orden, que resuelve la dependencia de FK sin salir de §26.4:
#     (1) SQL bajo SET LOCAL ROLE gapto_owner: `magnitudes` con ids
#         uuid5(NS, "seed.magnitud.<clave>"), INSERT ... WHERE NOT EXISTS
#         (nunca UPDATE de filas existentes);
#     (2) categorias por la API HTTP (POST /v1/categorias) con
#         id = uuid5(NS, "seed.categoria.<clave>") e icon_key del catalogo; la
#         idempotencia la da AJ-S4-05 (mismo id + mismo contenido ->
#         idempotente); IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION aborta y se
#         explica, nunca se corrige;
#     (3) SQL `categoria_magnitudes` idempotente (WHERE NOT EXISTS por
#         (categoria_id, magnitud_id));
#     (4) POST /v1/categorias/{id}/desactivar (SOLO_SI_SIN_HIJOS_ACTIVOS, con
#         el row_version leido de GET /v1/categorias) de la categoria marcada
#         DESACTIVADA (E1 hace idempotente la repeticion).
#   Protecciones: --dev-dsn LOCAL (_exigir_local) y base SIEMPRE
#   gapto2027_dev; --api-url solo loopback o red privada (10/8, 172.16/12,
#   192.168/16); el token SOLO de la variable de entorno GAPTO_DEV_TOKEN (nunca
#   argumento ni salida); owner = OWNER del script (mismo namespace NS). Los dos
#   writers SQL estan registrados en test_154 como clase SEED_DEV, sin valor
#   certificador. El estado «padre deshabilitado con hijo activo» NO se siembra
#   (inalcanzable por API, AJ-S4-03): lo cubren fixtures del cliente.
#   Uso:
#     set GAPTO_DEV_TOKEN=<token de ENV-DEV>
#     python scripts/dev/bootstrap_dev_db.py --seed-categorias \
#       --dev-dsn "host=127.0.0.1 port=5434 dbname=gapto2027_dev user=<rol>" \
#       --api-url http://192.168.1.10:8027
# Version: 0.5.0  -- F05-01 S7-MAG (F05-D020 D-MAG-06, D-S7-04): el seed cubre
#                   los cinco huecos de §34.1 sin categorias nuevas (siguen 23):
#                   (1) Luz con obligatoria + opcionales; (2) Kilometros
#                   compartida por Combustible y Transporte publico; (3) `orden`
#                   explicito 0..n-1 (la tupla de asociacion incluye el orden);
#                   (4) opcional deshabilitada en Agua que NO la hace no
#                   capturable; (5) precisiones 0 (Kilometros) y 6 (Precio del
#                   kWh). Sigue idempotente (INSERT ... WHERE NOT EXISTS, nunca
#                   UPDATE) y SEED_DEV sin valor certificador.
# Version: 0.4.0  -- F05-01 S6-WIRE+UI (este mandato): modo --seed-categorias
#                   (F05 §26.4). El modo de creacion no cambia.
# Version: 0.3.0  -- D-197: HEAD_AUTORIZADO_ENVDEV pasa de "0330" a "0340"
#                   tras la evidencia de 0340 (replica local D-189, Neon test,
#                   PASS_BASE_CLEANROOM_F03_0002_0340, mutation gate 10/10 y
#                   recertificacion RV3 diferencial). ENV-DEV no certifica.
# Version: 0.2.0  -- D-197 / revision P0 0340 (hallazgo 1): techo de head
#                   fail-closed HEAD_AUTORIZADO_ENVDEV = "0330"; validacion de la
#                   cadena antes de CREATE/DROP DATABASE; la salida lista las
#                   migrations omitidas y el head aplicado.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

BASE_DEV = "gapto2027_dev"
RAIZ = pathlib.Path(__file__).resolve().parents[2]
NS = uuid.UUID("6f1c9a52-5f0e-4b8b-9a51-0b2a3d6c7e01")  # namespace fijo de fixtures dev
OWNER = uuid.uuid5(NS, "vs01.owner")
ACTOR_SELF = uuid.uuid5(NS, "vs01.actor.self")
CUENTA = uuid.uuid5(NS, "vs01.cuenta.corriente")
PARTICIPACION = uuid.uuid5(NS, "vs01.cuenta.corriente.participacion")
HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}

# Head maximo que ENV-DEV puede materializar. Cambiarlo es una decision
# revisada (commit propio), nunca un efecto lateral de publicar migrations.
HEAD_AUTORIZADO_ENVDEV = "0340"
PATRON_MIGRATION = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def seleccionar_cadena(ficheros: list[pathlib.Path], head: str = HEAD_AUTORIZADO_ENVDEV
                       ) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """Devuelve (a_aplicar, omitidas). Fail-closed: aborta si algun nombre no
    sigue el patron NNNN_nombre.sql, si un numero se repite o si el head
    autorizado no existe exactamente una vez."""
    numeros: dict[str, pathlib.Path] = {}
    for f in ficheros:
        m = PATRON_MIGRATION.match(f.name)
        if not m:
            sys.exit(f"RECHAZADO: migration con nombre fuera de patron: {f.name}")
        if m.group(1) in numeros:
            sys.exit(f"RECHAZADO: numero de migration duplicado {m.group(1)}: "
                     f"{numeros[m.group(1)].name} y {f.name}")
        numeros[m.group(1)] = f
    if head not in numeros:
        sys.exit(f"RECHAZADO: el head autorizado {head} no esta en migrations/.")
    ordenadas = [numeros[n] for n in sorted(numeros)]
    a_aplicar = [f for f in ordenadas if PATRON_MIGRATION.match(f.name).group(1) <= head]
    omitidas = [f for f in ordenadas if PATRON_MIGRATION.match(f.name).group(1) > head]
    return a_aplicar, omitidas


def _exigir_local(dsn: str) -> dict:
    partes = conninfo_to_dict(dsn)
    host = partes.get("host", "")
    if not (host.startswith("/") or host in HOSTS_LOCALES):
        sys.exit(f"RECHAZADO: host '{host}' no es local. Este script solo opera en PostgreSQL local.")
    return partes


def _crear_base(admin_dsn: str, recrear: bool) -> None:
    partes = _exigir_local(admin_dsn)
    partes["dbname"] = partes.get("dbname") or "postgres"
    with psycopg.connect(make_conninfo(**partes), autocommit=True) as c:
        existe = c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (BASE_DEV,)).fetchone()
        if existe and not recrear:
            sys.exit(f"{BASE_DEV} ya existe. Usa --recrear para destruirla y rehacerla.")
        if existe:
            c.execute(f"DROP DATABASE {BASE_DEV} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {BASE_DEV}")
        roles = c.execute("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'gapto\\_%'").fetchone()[0]
    return roles


def _aplicar_cadena(dsn_dev: str, roles_existentes: int, ficheros: list[pathlib.Path]) -> str:
    with psycopg.connect(dsn_dev, autocommit=True) as c:
        for f in ficheros:
            if f.name.startswith("0001_") and roles_existentes:
                # Roles de instancia ya provisionados (cluster-scoped): 0001 no se repite.
                continue
            c.execute(f.read_text(encoding="utf-8"))
    return ficheros[-1].name


def _fixtures(dsn_dev: str) -> None:
    with psycopg.connect(dsn_dev) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET LOCAL ROLE gapto_owner")
            cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(OWNER),))
            cur.execute(
                "INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, %s)",
                (OWNER, "vs01.dev@example.invalid", "Usuario sintetico VS-01"),
            )
            cur.execute(
                "INSERT INTO gapto.actores_financieros (id, owner_user_id) VALUES (%s, %s)",
                (ACTOR_SELF, OWNER),
            )
            cur.execute(
                "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, moneda, "
                "computa_liquidez, computa_patrimonio, permite_negativo) "
                "VALUES (%s, %s, 'Cuenta corriente (sintética)', 'CORRIENTE', 'ACTIVO', 'EUR', "
                "true, true, false)",
                (CUENTA, OWNER),
            )
            cur.execute(
                "INSERT INTO gapto.cuenta_participaciones (id, cuenta_id, actor_id, porcentaje, "
                "vigente_desde) VALUES (%s, %s, %s, 100, DATE '2026-01-01')",
                (PARTICIPACION, CUENTA, ACTOR_SELF),
            )


# ------------------------------------------------------------------ seed de categorias (F05 §26.4)
#: (clave, nombre, unidad, precision, enabled)
SEED_MAGNITUDES = (
    ("consumo_electrico", "Consumo eléctrico", "kWh", 2, True),
    ("consumo_agua", "Consumo de agua", "m3", 3, True),
    ("consumo_gas", "Consumo de gas", "kWh", 2, False),  # deshabilitada: Gas NO capturable
    ("litros", "Litros", "l", 2, True),
    # S7-MAG (D-MAG-06): huecos (1), (2), (4) y (5).
    ("potencia_contratada", "Potencia contratada", "kW", 1, True),
    ("precio_kwh", "Precio del kWh", "€/kWh", 6, True),  # precision 6
    ("lectura_contador", "Lectura del contador", "m3", 3, False),  # opcional deshabilitada
    ("kilometros", "Kilómetros", "km", 0, True),  # precision 0; compartida
)
#: (clave, nombre, clave del padre, ambito, icon_key) en orden de alta (padres antes que hijos).
SEED_CATEGORIAS = (
    ("alimentacion", "Alimentación", None, "GASTO", "compras.cesta"),
    ("supermercado", "Supermercado", "alimentacion", "GASTO", "compras.carrito"),
    ("restaurantes", "Restaurantes", "alimentacion", "GASTO", "comida.restaurante"),
    ("cafe", "Café", "alimentacion", "GASTO", "comida.cafe"),
    ("hogar", "Hogar", None, "GASTO", "hogar.casa"),
    ("luz", "Luz", "hogar", "GASTO", "hogar.luz"),
    ("agua", "Agua", "hogar", "GASTO", "hogar.agua"),
    ("gas", "Gas", "hogar", "GASTO", "hogar.gas"),
    ("reparaciones", "Reparaciones", "hogar", "GASTO", None),  # sin icono: reserva visible
    ("transporte", "Transporte", None, "GASTO", "transporte.coche"),
    ("combustible", "Combustible", "transporte", "GASTO", None),
    ("transporte_publico", "Transporte público", "transporte", "GASTO", "transporte.bus"),
    ("salud", "Salud", None, "GASTO", "salud.corazon"),
    ("farmacia", "Farmacia", "salud", "GASTO", "salud.farmacia"),
    ("ocio", "Ocio", None, "GASTO", "ocio.cine"),
    ("cine", "Cine", "ocio", "GASTO", "ocio.cine"),
    ("libros", "Libros", "ocio", "GASTO", "ocio.libro"),
    ("suscripciones", "Suscripciones", None, "GASTO", "finanzas.suscripcion"),
    ("regalos", "Regalos", None, "AMBOS", "ocio.regalo"),
    ("trabajo", "Trabajo", None, "INGRESO", "finanzas.dinero"),
    ("nomina", "Nómina", "trabajo", "INGRESO", None),
    ("gastos_profesionales", "Gastos profesionales", "trabajo", "GASTO", "transporte.viaje"),
    ("viajes_2025", "Viajes 2025", None, "GASTO", "transporte.viaje"),
)
#: (clave de categoria, clave de magnitud, obligatoria, orden). Invariante D-S7-04:
#: en cada categoria, `orden` contiguo 0..n-1.
SEED_ASOCIACIONES = (
    ("luz", "consumo_electrico", True, 0),
    ("luz", "potencia_contratada", False, 1),
    ("luz", "precio_kwh", False, 2),
    ("agua", "consumo_agua", False, 0),
    ("agua", "lectura_contador", False, 1),
    ("gas", "consumo_gas", True, 0),
    ("combustible", "litros", True, 0),
    ("combustible", "kilometros", False, 1),
    ("transporte_publico", "kilometros", False, 0),
)
SEED_DESACTIVADAS = ("viajes_2025",)
REDES_API = tuple(ipaddress.ip_network(r) for r in ("127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def id_magnitud(clave: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"seed.magnitud.{clave}")


def id_categoria(clave: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"seed.categoria.{clave}")


def presupuestable_por_defecto(ambito: str) -> bool:
    # Decision de ejecucion del seed (el catalogo no la fija): GASTO/AMBOS si, INGRESO no.
    return ambito != "INGRESO"


def _exigir_api_privada(url: str) -> str:
    partes = urllib.parse.urlsplit(url)
    if partes.scheme != "http" or not partes.hostname:
        sys.exit("RECHAZADO: --api-url debe ser http://<ip o localhost>:<puerto>.")
    host = "127.0.0.1" if partes.hostname == "localhost" else partes.hostname
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        sys.exit(f"RECHAZADO: --api-url debe usar una IP (o localhost), no '{partes.hostname}'.")
    if not any(ip in red for red in REDES_API):
        sys.exit(f"RECHAZADO: {ip} no es loopback ni red privada (10/8, 172.16/12, 192.168/16).")
    return url.rstrip("/")


def _dsn_seed(dev_dsn: str) -> str:
    partes = _exigir_local(dev_dsn)
    if partes.get("dbname", BASE_DEV) != BASE_DEV:
        sys.exit(f"RECHAZADO: el seed solo opera sobre {BASE_DEV}.")
    partes["dbname"] = BASE_DEV
    return make_conninfo(**partes)


def _seed_magnitudes(dsn_dev: str) -> list[str]:
    """Writer SQL SEED_DEV de `magnitudes`: solo INSERT si no existe."""
    salida = []
    with psycopg.connect(dsn_dev) as c, c.transaction():
        cur = c.cursor()
        cur.execute("SET LOCAL ROLE gapto_owner")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(OWNER),))
        for clave, nombre, unidad, precision, enabled in SEED_MAGNITUDES:
            cur.execute(
                "INSERT INTO gapto.magnitudes (id, owner_user_id, nombre, unidad_default, precision_decimales, enabled) "
                "SELECT %s, %s, %s, %s, %s, %s WHERE NOT EXISTS (SELECT 1 FROM gapto.magnitudes WHERE id = %s)",
                (id_magnitud(clave), OWNER, nombre, unidad, precision, enabled, id_magnitud(clave)),
            )
            salida.append(f"MAGNITUD {clave}: {'creada' if cur.rowcount == 1 else 'ya existia (sin cambios)'}")
    return salida


def _seed_asociaciones(dsn_dev: str) -> list[str]:
    """Writer SQL SEED_DEV de `categoria_magnitudes`: solo INSERT si no existe la pareja."""
    salida = []
    with psycopg.connect(dsn_dev) as c, c.transaction():
        cur = c.cursor()
        cur.execute("SET LOCAL ROLE gapto_owner")
        cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(OWNER),))
        for cat, mag, obligatoria, orden in SEED_ASOCIACIONES:
            cur.execute(
                "INSERT INTO gapto.categoria_magnitudes (id, categoria_id, magnitud_id, obligatoria, orden) "
                "SELECT %s, %s, %s, %s, %s WHERE NOT EXISTS (SELECT 1 FROM gapto.categoria_magnitudes "
                "WHERE categoria_id = %s AND magnitud_id = %s)",
                (uuid.uuid5(NS, f"seed.asociacion.{cat}.{mag}"), id_categoria(cat), id_magnitud(mag), obligatoria,
                 orden, id_categoria(cat), id_magnitud(mag)),
            )
            salida.append(f"ASOCIACION {cat}->{mag}: {'creada' if cur.rowcount == 1 else 'ya existia (sin cambios)'}")
    return salida


def _api(api: str, token: str, metodo: str, ruta: str, cuerpo: dict | None = None) -> tuple[int, dict]:
    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    req = urllib.request.Request(f"{api}{ruta}", data=datos, method=metodo,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            return e.code, {}


def _seed_categorias_api(api: str, token: str) -> list[str]:
    status, arbol = _api(api, token, "GET", "/v1/categorias")
    if status != 200:
        sys.exit(f"ABORTADO: GET /v1/categorias devolvio HTTP {status}")
    existentes = {c["id"]: c for c in arbol["categorias"]}
    salida = []
    for clave, nombre, padre, ambito, icono in SEED_CATEGORIAS:
        previa = existentes.get(str(id_categoria(clave)))
        if clave in SEED_DESACTIVADAS and previa is not None and not previa["enabled"]:
            # La desactivo el propio seed (paso 4): su alta ya no es idempotente (row_version > 1).
            salida.append(f"CATEGORIA {clave}: ya existia desactivada por el seed (sin cambios)")
            continue
        alta = {"id": str(id_categoria(clave)), "nombre": nombre,
                "parent_id": None if padre is None else str(id_categoria(padre)), "ambito": ambito,
                "presupuestable_default": presupuestable_por_defecto(ambito), "icon_key": icono}
        status, cuerpo = _api(api, token, "POST", "/v1/categorias", alta)
        if status == 200:
            salida.append(f"CATEGORIA {clave}: {'ya existia (idempotente)' if cuerpo.get('idempotente') else 'creada'}")
            continue
        codigo = cuerpo.get("codigo")
        if codigo == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION":
            sys.exit(f"ABORTADO en {clave}: la categoria sembrada ya existe con otro contenido (AJ-S4-05; se "
                     "renombro, movio, desactivo u ordeno en ENV-DEV). El seed no la corrige: decide si "
                     "recrear gapto2027_dev con --recrear o dejarla como esta.")
        sys.exit(f"ABORTADO en {clave}: HTTP {status} {codigo or ''}".rstrip())
    return salida


def _seed_desactivar(api: str, token: str) -> list[str]:
    status, arbol = _api(api, token, "GET", "/v1/categorias")
    if status != 200:
        sys.exit(f"ABORTADO: GET /v1/categorias devolvio HTTP {status}")
    por_id = {c["id"]: c for c in arbol["categorias"]}
    salida = []
    for clave in SEED_DESACTIVADAS:
        nodo = por_id.get(str(id_categoria(clave)))
        if nodo is None:
            sys.exit(f"ABORTADO: {clave} no esta en el arbol")
        status, cuerpo = _api(api, token, "POST", f"/v1/categorias/{nodo['id']}/desactivar",
                              {"modo": "SOLO_SI_SIN_HIJOS_ACTIVOS", "row_version": nodo["row_version"]})
        if status != 200:
            sys.exit(f"ABORTADO al desactivar {clave}: HTTP {status} {cuerpo.get('codigo', '')}".rstrip())
        salida.append(f"DESACTIVADA {clave}: {'ya lo estaba (idempotente)' if cuerpo.get('idempotente') else 'desactivada'}")
    return salida


def seed_categorias(dev_dsn: str, api_url: str) -> None:
    dsn_dev = _dsn_seed(dev_dsn)
    api = _exigir_api_privada(api_url)
    token = os.environ.get("GAPTO_DEV_TOKEN", "").strip()
    if not token:
        sys.exit("Falta la variable de entorno GAPTO_DEV_TOKEN (nunca se pasa por argumento).")
    lineas = _seed_magnitudes(dsn_dev)
    lineas += _seed_categorias_api(api, token)
    lineas += _seed_asociaciones(dsn_dev)
    lineas += _seed_desactivar(api, token)
    for linea in lineas:
        print(linea)
    print(f"OK seed-categorias {BASE_DEV} owner={OWNER}: {len(SEED_CATEGORIAS)} categorias, "
          f"{len(SEED_MAGNITUDES)} magnitudes, {len(SEED_ASOCIACIONES)} asociaciones, "
          f"{len(SEED_DESACTIVADAS)} desactivada(s)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--admin-dsn", help="DSN administrativo LOCAL (sin dbname o con postgres)")
    ap.add_argument("--recrear", action="store_true")
    ap.add_argument("--seed-categorias", action="store_true", help="siembra el catalogo sintetico de categorias (F05 §26.4)")
    ap.add_argument("--dev-dsn", help="DSN LOCAL de gapto2027_dev (solo --seed-categorias)")
    ap.add_argument("--api-url", help="API de ENV-DEV, loopback o red privada (solo --seed-categorias)")
    a = ap.parse_args()
    if a.seed_categorias:
        if not a.dev_dsn or not a.api_url:
            sys.exit("--seed-categorias exige --dev-dsn y --api-url.")
        return seed_categorias(a.dev_dsn, a.api_url)
    if not a.admin_dsn:
        sys.exit("Falta --admin-dsn.")
    # Validacion de la cadena ANTES de tocar ninguna base.
    a_aplicar, omitidas = seleccionar_cadena(sorted((RAIZ / "migrations").glob("0*.sql")))
    roles = _crear_base(a.admin_dsn, a.recrear)
    partes = _exigir_local(a.admin_dsn)
    partes["dbname"] = BASE_DEV
    dsn_dev = make_conninfo(**partes)
    head = _aplicar_cadena(dsn_dev, roles, a_aplicar)
    _fixtures(dsn_dev)
    print(f"OK {BASE_DEV} head={head} (autorizado {HEAD_AUTORIZADO_ENVDEV})")
    for f in omitidas:
        print(f"OMITIDA por encima del head autorizado: {f.name}")
    print(f"GAPTO_DEV_OWNER_USER_ID={OWNER}")
    print(f"CUENTA_SINTETICA={CUENTA}")


if __name__ == "__main__":
    main()
