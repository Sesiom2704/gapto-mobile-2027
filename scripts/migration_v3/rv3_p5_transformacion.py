# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p5_transformacion.py
# Ruta: scripts/migration_v3/rv3_p5_transformacion.py
# Descripcion: RV3 / P5. Transformacion B0 (y S1 por las mismas reglas) hacia
#              el contrato fisico 0330, por dominios del plan R2:
#                1 tenant/geografia   (IMPLEMENTADO v0.1.0)
#               12 importacion: fuente + registros origen + mapeos (base)
#               2..11 pendientes.
#   Principios aplicados en codigo:
#     - identidad UUIDv5 canonica v3|contenedor|clave|tabla|rol (rv3_fuente);
#     - todo destino creado lleva al menos un mapeo a su registro origen;
#     - colision de identidad o de clave natural -> fallo cerrado (S7);
#     - ausencia/UNKNOWN nunca se convierte en valor; un NOT NULL sin fuente
#       solo se cubre por una regla de ledger declarada y visible;
#     - el dataset se serializa ordenado y se resume en un hash determinista;
#     - pendientes S20 bloquean la fila afectada: se conserva su origen y se
#       registra, sin crear destino.
#   Validacion fisica: carga el dataset en UNA transaccion bajo el perfil
#   RV3_IMPORT (rol login no superusuario -> gapto_migrator -> gapto_owner),
#   fuerza los diferidos con SET CONSTRAINTS ALL IMMEDIATE y hace ROLLBACK.
#   No es P6 (P6 hace COMMIT real).
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

VERSION = "0.1.0"
TRANSFORMACION = "RV3_P5"
_AQUI = Path(__file__).resolve().parent


def _cargar(nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, _AQUI / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


fu = _cargar("rv3_fuente")

# Orden de insercion: padres antes que hijos (FK inmediatas de 0330).
ORDEN_TABLAS = [
    "usuarios", "paises", "regiones", "localidades", "actores_financieros",
    "fuentes_importacion", "registros_origen_importacion", "mapeos_importacion",
]

# Reference data geografica versionada (DB Schema: geografia = reference data
# separada). Decision de ejecucion H-P5-01, PROVISIONAL hasta conformidad.
REF_GEO = "REF_GEO_ISO3166_V1"
REF_PAISES = {"ESPAÑA": ("ES", "ESP")}

# Reglas de ledger declaradas (visibles en el informe).
LEDGER_REGLAS = {
    "H-P5-01": "paises.iso2/iso3 NOT NULL; V3 codigo_iso=141 (ausencia). Se vincula por nombre "
               "exacto a " + REF_GEO + "; literal 141 conservado en origen. PROVISIONAL.",
    "H-P5-02": "regiones V3 mezclan niveles; tipo_region y parent_region_id quedan NULL "
               "(sin jerarquia inventada). PROVISIONAL.",
    "H-P5-03": "usuarios.timezone/locale NOT NULL sin dato V3; se deja actuar el DEFAULT de "
               "configuracion del contrato (no es hecho financiero). PROVISIONAL.",
}


class ErrorP5(Exception):
    """Fallo cerrado tipado."""

    def __init__(self, codigo: str, detalle: str):
        super().__init__(f"{codigo}: {detalle}")
        self.codigo = codigo


@dataclass
class Dataset:
    owner: str
    filas: dict = field(default_factory=lambda: {t: {} for t in ORDEN_TABLAS})
    naturales: dict = field(default_factory=dict)
    ledger: list = field(default_factory=list)
    pendientes: list = field(default_factory=list)

    def add(self, tabla: str, fila: dict, natural: tuple | None = None) -> str:
        fid = fila["id"]
        if fid in self.filas[tabla]:
            if self.filas[tabla][fid] != fila:
                raise ErrorP5("S7_COLISION_UUID", f"{tabla}/{fid}")
            return fid
        if natural is not None:
            k = (tabla,) + natural
            if k in self.naturales and self.naturales[k] != fid:
                raise ErrorP5("S7_COLISION_CLAVE_NATURAL", str(k))
            self.naturales[k] = fid
        self.filas[tabla][fid] = fila
        return fid

    def mapear(self, cont: str, clave: str, tabla: str, destino: str, rol: str,
               tipo: str = "CREADO", confianza: str = "ALTA", notas: str | None = None) -> None:
        origen = fu.uuid_origen(cont, clave)
        mid = fu.uuid_v3(cont, clave, "mapeos_importacion", f"{tabla}.{rol}")
        self.add("mapeos_importacion", {
            "id": mid, "registro_origen_id": origen, "tabla_destino": tabla,
            "registro_destino_id": destino, "tipo_mapping": tipo,
            "transformacion_codigo": f"{TRANSFORMACION}.{tabla}.{rol}",
            "transformacion_version": VERSION, "confianza": confianza, "notas": notas})

    def hash(self) -> str:
        cuerpo = {t: [self.filas[t][k] for k in sorted(self.filas[t])] for t in ORDEN_TABLAS}
        s = json.dumps(cuerpo, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_j)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def recuentos(self) -> dict:
        return {t: len(self.filas[t]) for t in ORDEN_TABLAS}


def _j(o):
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError(type(o))


def _celda(cont, col, fila, ctx):
    return fu.normalizar(cont, col, fila.get(col), fila, ctx)


def _texto(c) -> str | None:
    return None if c.valor is None else str(c.valor).strip() or None


# ------------------------------------------------------------ dominio 12 base
def dominio_12_trazabilidad(ds: Dataset, b0: dict, sha_run06: str) -> str:
    fid = fu.uuid_v3("RUN06", sha_run06, "fuentes_importacion", "fuente")
    ds.add("fuentes_importacion", {
        "id": fid, "owner_user_id": ds.owner, "tipo_fuente": "XLSX",
        "nombre_fuente": "RUN06 B0 snapshot origen (RV3-D002)",
        "version_fuente": "RUN06_v08", "pipeline_version": f"{TRANSFORMACION} {VERSION}",
        "sha256": sha_run06, "estado": "SIMULADA",
        "notas": f"datos_origen_texto = {fu.SEMANTICA_TEXTO}; sha256_registro = {fu.ALGORITMO_HASH_REGISTRO}"})
    for cont in sorted(b0):
        for clave in sorted(b0[cont]):
            r = b0[cont][clave]
            ds.add("registros_origen_importacion", {
                "id": fu.uuid_origen(cont, clave), "fuente_importacion_id": fid,
                "contenedor_origen": cont, "clave_origen": clave,
                "numero_fila_origen": r.numero_fila_origen, "datos_origen": r.datos,
                "datos_origen_texto": r.texto, "sha256_registro": r.sha256_registro},
                natural=(cont, clave))
    return fid


# ------------------------------------------------------------ dominio 1
def owner_de(clave_user: str) -> str:
    return fu.uuid_v3("public.users", clave_user, "usuarios", "tenant")


def dominio_1(ds: Dataset, fuente: dict, ctx: dict) -> None:
    users = fuente["public.users"]
    if len(users) != 1:
        raise ErrorP5("S20_TENANT", f"{len(users)} filas users; RV3 espera un unico tenant")
    (cu, u), = users.items()
    email = _texto(_celda("public.users", "email", u, ctx))
    nombre = _texto(_celda("public.users", "full_name", u, ctx))
    if not email or not nombre:
        raise ErrorP5("S6_TENANT_INCOMPLETO", "email/nombre ausente en users")
    ds.add("usuarios", {"id": ds.owner, "email": email, "nombre": nombre}, natural=(email,))
    ds.mapear("public.users", cu, "usuarios", ds.owner, "tenant")
    ds.ledger.append({"regla": "H-P5-03", "origen": f"public.users/{cu}"})
    # Actor self: obligatorio por contrato (exactamente uno, tercero_id NULL).
    self_id = fu.uuid_v3("public.users", cu, "actores_financieros", "self")
    ds.add("actores_financieros", {"id": self_id, "owner_user_id": ds.owner, "tercero_id": None},
           natural=(ds.owner, None))
    ds.mapear("public.users", cu, "actores_financieros", self_id, "self", tipo="CREADO",
              notas="actor self derivado del tenant (obligatorio por contrato)")

    pais_de = {}
    for cp, p in sorted(fuente.get("public.paises", {}).items()):
        nom = _texto(_celda("public.paises", "nombre", p, ctx))
        iso_c = _celda("public.paises", "codigo_iso", p, ctx)
        if nom not in REF_PAISES:
            raise ErrorP5("S4_PAIS_SIN_REFERENCIA", f"{cp}")
        iso2, iso3 = REF_PAISES[nom]
        if iso_c.estado == fu.CONOCIDO and str(iso_c.valor) not in (iso2, iso3):
            raise ErrorP5("S1_ISO_CONTRADICTORIO", f"{cp}")
        pid = fu.uuid_v3("public.paises", cp, "paises", "pais")
        ds.add("paises", {"id": pid, "iso2": iso2, "iso3": iso3, "nombre": nom}, natural=(iso2,))
        ds.mapear("public.paises", cp, "paises", pid, "pais", confianza="VALIDADA",
                  notas=f"iso desde {REF_GEO} por nombre exacto (H-P5-01)")
        ds.ledger.append({"regla": "H-P5-01", "origen": f"public.paises/{cp}"})
        pais_de[str(p["id"])] = pid

    region_de = {}
    for cr, r in sorted(fuente.get("public.regiones", {}).items()):
        pais = pais_de.get(str(r.get("pais_id")))
        if pais is None:
            raise ErrorP5("S8_HUERFANO", f"public.regiones/{cr} pais_id")
        rid = fu.uuid_v3("public.regiones", cr, "regiones", "region")
        ds.add("regiones", {"id": rid, "pais_id": pais, "parent_region_id": None,
                            "nombre": _texto(_celda("public.regiones", "nombre", r, ctx)),
                            "tipo_region": None, "codigo_oficial": None})
        ds.mapear("public.regiones", cr, "regiones", rid, "region")
        ds.ledger.append({"regla": "H-P5-02", "origen": f"public.regiones/{cr}"})
        region_de[str(r["id"])] = rid

    for cl, loc in sorted(fuente.get("public.localidades", {}).items()):
        reg = region_de.get(str(loc.get("region_id")))
        if reg is None:
            raise ErrorP5("S8_HUERFANO", f"public.localidades/{cl} region_id")
        cpost = _celda("public.localidades", "codigo_postal", loc, ctx)
        codigo = _texto(cpost) if cpost.estado == fu.CONOCIDO else None
        lid = fu.uuid_v3("public.localidades", cl, "localidades", "localidad")
        ds.add("localidades", {"id": lid, "region_id": reg,
                               "nombre": _texto(_celda("public.localidades", "nombre", loc, ctx)),
                               "codigo_oficial": codigo,
                               "codigo_oficial_tipo": "CODIGO_POSTAL" if codigo else None})
        ds.mapear("public.localidades", cl, "localidades", lid, "localidad")


# ------------------------------------------------------------ pipeline
def transformar(b0: dict, sha_run06: str) -> Dataset:
    fuente = fu.fuente_b0(b0)
    ctx = fu.contexto_de(fuente)
    (cu,) = fuente["public.users"].keys()
    ds = Dataset(owner=owner_de(cu))
    dominio_12_trazabilidad(ds, b0, sha_run06)
    dominio_1(ds, fuente, ctx)
    verificar_trazabilidad(ds)
    return ds


def verificar_trazabilidad(ds: Dataset) -> None:
    """R05 parcial: todo destino creado tiene mapeo; todo mapeo apunta a origen existente."""
    origenes = set(ds.filas["registros_origen_importacion"])
    destinos_mapeados = {(m["tabla_destino"], m["registro_destino_id"])
                         for m in ds.filas["mapeos_importacion"].values()}
    for m in ds.filas["mapeos_importacion"].values():
        if m["registro_origen_id"] not in origenes:
            raise ErrorP5("S8_MAPEO_SIN_ORIGEN", m["id"])
    exentas = {"fuentes_importacion", "registros_origen_importacion", "mapeos_importacion"}
    for t in ORDEN_TABLAS:
        if t in exentas:
            continue
        for fid in ds.filas[t]:
            if (t, fid) not in destinos_mapeados:
                raise ErrorP5("S8_DESTINO_SIN_ORIGEN", f"{t}/{fid}")


# ------------------------------------------------------------ validacion fisica
def validar_fisico(ds: Dataset, dsn_import: str) -> dict:
    """Carga en una transaccion bajo RV3_IMPORT y SIEMPRE revierte."""
    import psycopg
    from psycopg.types.json import Jsonb
    res = {}
    with psycopg.connect(dsn_import) as c:
        with c.transaction(force_rollback=True):
            c.execute("SET ROLE gapto_migrator")
            c.execute("SET ROLE gapto_owner")
            c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (ds.owner,))
            for t in ORDEN_TABLAS:
                for fid in sorted(ds.filas[t]):
                    f = ds.filas[t][fid]
                    cols = sorted(f)
                    vals = [Jsonb(f[k]) if isinstance(f[k], (dict, list)) else f[k] for k in cols]
                    c.execute(f"INSERT INTO gapto.{t} ({', '.join(cols)}) VALUES "
                              f"({', '.join(['%s'] * len(cols))})", vals)
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")
            for t in ORDEN_TABLAS:
                res[t] = c.execute(f"SELECT count(*) FROM gapto.{t}").fetchone()[0]
            res["_rol"] = c.execute("SELECT current_user, session_user").fetchone()
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run06", required=True, type=Path)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--dsn-import", default=None, help="DSN del perfil RV3_IMPORT (laboratorio)")
    a = ap.parse_args()
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] [1/3] Carga B0", flush=True)
    b0 = fu.cargar_b0(a.run06)
    sha = fu.p1.sha256_fichero(a.run06)
    print(f"[{time.strftime('%H:%M:%S')}] [2/3] Transformacion P5 v{VERSION}", flush=True)
    ds = transformar(b0, sha)
    h = ds.hash()
    fisico = None
    if a.dsn_import:
        print(f"[{time.strftime('%H:%M:%S')}] [3/3] Validacion fisica RV3_IMPORT (ROLLBACK)", flush=True)
        fisico = validar_fisico(ds, a.dsn_import)
    informe = {"version": VERSION, "hash_dataset": h, "recuentos": ds.recuentos(),
               "ledger_reglas": LEDGER_REGLAS, "ledger": ds.ledger, "pendientes": ds.pendientes,
               "fisico": fisico, "dominios": {"implementados": [1, "12-base"], "pendientes": list(range(2, 12))},
               "ts": datetime.now(timezone.utc).isoformat()}
    a.salida.mkdir(parents=True, exist_ok=True)
    p = a.salida / f"rv3_p5_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    p.write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"      hash_dataset={h}\n      recuentos={ds.recuentos()}\n      fisico={fisico}\n"
          f"      informe={p.name} ({time.time() - t0:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
