# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p6_carga.py
# Ruta: scripts/migration_v3/rv3_p6_carga.py
# Descripcion: RV3 / P6. Carga exacta local del dataset P5 bajo el perfil RV3_IMPORT (gapto_migrator -> SET ROLE
#              gapto_owner, contexto tenant), en UNA transaccion: BEGIN -> carga en el orden de dependencias de P5
#              -> comprobaciones pre-COMMIT (constraints diferidos inmediatos, identidad fila a fila por PK contra el
#              dataset, semillas contractuales, destino polimorfico de los mapeos) -> COMMIT real solo con
#              --commit; sin el flag la transaccion se revierte (ensayo). Falla cerrado (STOP) si el hash del
#              dataset regenerado difiere del autorizado o si la BD no es virgen. No cambia la semantica de P5:
#              reutiliza ORDEN_TABLAS, orden_insercion y TRANSICIONES_CARGA de P5.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import sys
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
# Semillas contractuales presentes en una BD 0330 recien migrada (0150/0160): no son dataset.
SEMILLAS_0330 = {"metricas_definicion": {"AHORRO_NETO_PYL", "APORTACION_INVERSION_NETA", "TRANSFERENCIA_AHORRO_NETA"}}


class StopP6(Exception):
    def __init__(self, codigo: str, detalle: str):
        super().__init__(f"{codigo}: {detalle}")
        self.codigo = codigo


def cargar_p5():
    spec = importlib.util.spec_from_file_location("rv3_p5_transformacion", _AQUI / "rv3_p5_transformacion.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rv3_p5_transformacion"] = mod
    spec.loader.exec_module(mod)
    return mod


def comprobar_hash(obtenido: str, autorizado: str) -> None:
    if obtenido != autorizado:
        raise StopP6("S7_HASH_DATASET_DISTINTO", f"regenerado {obtenido} != autorizado {autorizado}")


def diferencias_ids(esperado: dict, fisico: dict) -> dict:
    """esperado/fisico: tabla -> set de PK. Devuelve solo las tablas con diferencias (faltan/sobran)."""
    out = {}
    for t in sorted(set(esperado) | set(fisico)):
        e, f = set(esperado.get(t, ())), set(fisico.get(t, ()))
        if e != f:
            out[t] = {"faltan": len(e - f), "sobran": len(f - e)}
    return out


def _pk(P5, t):
    return P5.PK.get(t, "id")


def _contexto(c, owner):
    c.execute("SET ROLE gapto_migrator")
    c.execute("SET ROLE gapto_owner")
    c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))


def verificar_virgen(P5, c) -> dict:
    """Dentro de la transaccion y con contexto: toda tabla del dataset vacia salvo las semillas 0330."""
    sucias = {}
    for t in P5.ORDEN_TABLAS:
        if t in SEMILLAS_0330:
            extra = [r[0] for r in c.execute(f"SELECT codigo FROM gapto.{t}").fetchall()
                     if r[0] not in SEMILLAS_0330[t]]
            if extra:
                sucias[t] = len(extra)
            continue
        n = c.execute(f"SELECT count(*) FROM gapto.{t}").fetchone()[0]
        if n:
            sucias[t] = n
    # Alcance: lo visible bajo RLS para el tenant del dataset. La virginidad global se certifica aparte con
    # verificar_virgen_global (lectura de auditoria sin RLS, sin escritura).
    if sucias:
        raise StopP6("S2_BD_NO_VIRGEN", json.dumps(sucias))
    return {"tablas": len(P5.ORDEN_TABLAS), "semillas": {t: sorted(v) for t, v in SEMILLAS_0330.items()}}


def verificar_virgen_global(P5, dsn_auditoria: str) -> dict:
    """Solo lectura con un rol de auditoria sin RLS (laboratorio): ninguna fila fuera de las semillas 0330."""
    import psycopg
    with psycopg.connect(dsn_auditoria) as c:
        c.execute("SET TRANSACTION READ ONLY")
        cuenta = {t: c.execute(f"SELECT count(*) FROM gapto.{t}").fetchone()[0] for t in P5.ORDEN_TABLAS}
        c.rollback()
    sucias = {t: n for t, n in cuenta.items() if n != len(SEMILLAS_0330.get(t, ()))}
    if sucias:
        raise StopP6("S2_BD_NO_VIRGEN", json.dumps(sucias))
    return {"tablas": len(cuenta), "filas_totales": sum(cuenta.values())}


def cargar(P5, c, ds) -> int:
    from psycopg.types.json import Jsonb
    n = 0
    for t in P5.ORDEN_TABLAS:
        for fid in P5.orden_insercion(ds, t):
            f = ds.filas[t][fid]
            if t in P5.TRANSICIONES_CARGA:
                f = {**f, P5.TRANSICIONES_CARGA[t][0]: P5.TRANSICIONES_CARGA[t][1]}
            cols = sorted(f)
            vals = [Jsonb(f[k]) if isinstance(f[k], (dict, list)) else f[k] for k in cols]
            c.execute(f"INSERT INTO gapto.{t} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", vals)
            n += 1
    for t, (col, _ini) in P5.TRANSICIONES_CARGA.items():
        for fid in P5.orden_insercion(ds, t):
            c.execute(f"UPDATE gapto.{t} SET {col} = %s WHERE id = %s", (ds.filas[t][fid][col], fid))
    return n


def comprobar_pre_commit(P5, c, ds) -> dict:
    c.execute("SET CONSTRAINTS ALL IMMEDIATE")  # un fallo diferido aparece aqui, antes del COMMIT
    esperado = {t: set(ds.filas[t]) for t in P5.ORDEN_TABLAS}
    fisico = {}
    for t in P5.ORDEN_TABLAS:
        pk = _pk(P5, t)
        filas = {str(r[0]) for r in c.execute(f"SELECT {pk}::text FROM gapto.{t}").fetchall()}
        if t in SEMILLAS_0330:
            semillas = {str(r[0]) for r in c.execute(
                f"SELECT {pk}::text FROM gapto.{t} WHERE codigo = ANY(%s)", (sorted(SEMILLAS_0330[t]),)).fetchall()}
            filas -= semillas
        fisico[t] = filas
    dif = diferencias_ids(esperado, fisico)
    if dif:
        raise StopP6("S8_CARGA_NO_EXACTA", json.dumps(dif))
    huerfanos = {}
    for t in sorted({m["tabla_destino"] for m in ds.filas["mapeos_importacion"].values() if m["tabla_destino"]}):
        n = c.execute(f"""SELECT count(*) FROM gapto.mapeos_importacion m
                           WHERE m.tabla_destino = %s
                             AND NOT EXISTS (SELECT 1 FROM gapto.{t} d WHERE d.{_pk(P5, t)} = m.registro_destino_id)""",
                      (t,)).fetchone()[0]
        if n:
            huerfanos[t] = n
    if huerfanos:
        raise StopP6("S8_MAPEO_DESTINO_INEXISTENTE", json.dumps(huerfanos))
    sin_origen = c.execute("""SELECT count(*) FROM gapto.mapeos_importacion m WHERE NOT EXISTS
                                (SELECT 1 FROM gapto.registros_origen_importacion r WHERE r.id = m.registro_origen_id)""").fetchone()[0]
    if sin_origen:
        raise StopP6("S8_MAPEO_SIN_ORIGEN", str(sin_origen))
    return {"filas_por_tabla": {t: len(v) for t, v in fisico.items()}, "semillas_intactas": True,
            "mapeos_destino_inexistente": 0, "mapeos_sin_origen": 0}


def ejecutar(P5, ds, dsn: str, commit: bool) -> dict:
    import psycopg
    ev = {"inicio_utc": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    with psycopg.connect(dsn) as c:  # autocommit False: psycopg abre la transaccion en el primer execute
        _contexto(c, ds.owner)
        ev["perfil"] = c.execute("SELECT session_user, current_user").fetchone()
        ev["txid"] = c.execute("SELECT txid_current()").fetchone()[0]
        ev["virgen"] = verificar_virgen(P5, c)
        ev["filas_insertadas"] = cargar(P5, c, ds)
        ev["pre_commit"] = comprobar_pre_commit(P5, c, ds)
        if commit:
            c.commit()
            ev["commit"] = "COMMIT"
        else:
            c.rollback()
            ev["commit"] = "ROLLBACK (ensayo sin --commit)"
    ev["fin_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    if commit:  # lectura posterior en conexion nueva: la transaccion quedo confirmada
        with psycopg.connect(dsn) as c:
            _contexto(c, ds.owner)
            ev["post_commit"] = {t: c.execute(f"SELECT count(*) FROM gapto.{t}").fetchone()[0] for t in P5.ORDEN_TABLAS}
            ev["txid_confirmado"] = c.execute("SELECT txid_status(%s)", (ev["txid"],)).fetchone()[0]
            c.rollback()
    return ev


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RV3 P6: carga exacta local con COMMIT real (perfil RV3_IMPORT)")
    ap.add_argument("--run06", required=True, type=Path)
    ap.add_argument("--decisiones-propietario", required=True, type=Path)
    ap.add_argument("--dsn-import", required=True)
    ap.add_argument("--hash-autorizado", required=True)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--commit", action="store_true", help="confirma la transaccion (sin el flag: ROLLBACK)")
    ap.add_argument("--dsn-auditoria", default=None, help="solo lectura sin RLS para certificar la virginidad global")
    a = ap.parse_args(argv)
    P5 = cargar_p5()
    b0 = P5.fu.cargar_b0(a.run06)
    ds = P5.transformar(b0, P5.fu.p1.sha256_fichero(a.run06), modo_lab=False,
                        decisiones=P5.cargar_decisiones(a.decisiones_propietario))
    h = ds.hash()
    ev = {"p5_version": P5.VERSION, "hash_dataset": h, "hash_autorizado": a.hash_autorizado,
          "pendientes": ds.pendientes, "recuentos_dataset": ds.recuentos()}
    try:
        comprobar_hash(h, a.hash_autorizado)
        if ds.pendientes:
            raise StopP6("S20_PENDIENTES_P5", str(len(ds.pendientes)))
        if a.dsn_auditoria:
            ev["virgen_global"] = verificar_virgen_global(P5, a.dsn_auditoria)
        ev.update(ejecutar(P5, ds, a.dsn_import, a.commit))
        rc = 0
    except StopP6 as e:
        ev["stop"] = {"codigo": e.codigo, "detalle": str(e)}
        rc = 2
    except Exception as e:  # fallo de PostgreSQL: la transaccion se revierte al cerrar la conexion
        ev["error"] = {"tipo": type(e).__name__, "detalle": str(e)[:2000]}
        rc = 3
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "rv3_p6_carga.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1, default=str),
                                                encoding="utf-8")
    print(json.dumps({k: ev.get(k) for k in ("hash_dataset", "commit", "stop", "error", "txid_confirmado")},
                     default=str))
    return rc


if __name__ == "__main__":
    sys.exit(main())
