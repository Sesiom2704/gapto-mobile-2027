# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p9_runtime.py
# Ruta: scripts/migration_v3/rv3_p9_runtime.py
# Descripcion: RV3 / P9. Sondas runtime con el perfil RV3_RUNTIME_PROBE (SET ROLE gapto_runtime + contexto tenant)
#              sobre la carga P6, SIEMPRE en transacciones que terminan en ROLLBACK:
#                - ACL: matriz S/I/U/D de gapto_runtime frente al contrato 0330 (80/74/68/48) y FORCE RLS (75);
#                - RLS: visibilidad completa con el tenant propio, nula con un tenant ajeno y sin contexto;
#                  escritura con owner ajeno rechazada;
#                - R-RV3-016 Probe A: DELETE directo de cada posicion financiera importada (esperado 23503);
#                - R-RV3-016 Probe B: secuencia adversarial reapuntar/borrar protectores -> DELETE de la raiz ->
#                  SET CONSTRAINTS ALL IMMEDIATE, ejecutada de verdad, clasificando EVADIDA / BLOQUEADA(paso,
#                  SQLSTATE). Los mapas de protectores proceden de P5b (rv3_p5b_rf04015).
#              Tras cada sonda se verifica que la carga no cambio (recuentos). No hay COMMIT.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import sys
import uuid
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
CONTRATO_ACL = {"SELECT": 80, "INSERT": 74, "UPDATE": 68, "DELETE": 48}
CONTRATO_FORCE_RLS = 75
FINANCIERAS = ("FINANCIACION", "DERECHO_OBLIGACION", "INVERSION")


def _p5b():
    spec = importlib.util.spec_from_file_location("rv3_p5b_rf04015", _AQUI / "rv3_p5b_rf04015.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rv3_p5b_rf04015"] = mod
    spec.loader.exec_module(mod)
    return mod


def _runtime(c, owner):
    c.execute("SET LOCAL ROLE gapto_runtime")
    c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (owner,))


def _error(e) -> dict:
    d = getattr(e, "diag", None)
    return {"sqlstate": getattr(e, "sqlstate", None), "constraint": getattr(d, "constraint_name", None),
            "tabla": getattr(d, "table_name", None), "mensaje": str(e).split("\n")[0][:300]}


def sonda_acl(c) -> dict:
    fila = c.execute("""SELECT count(*) FILTER (WHERE has_table_privilege('gapto_runtime', k.oid, 'SELECT')),
                               count(*) FILTER (WHERE has_table_privilege('gapto_runtime', k.oid, 'INSERT')),
                               count(*) FILTER (WHERE has_table_privilege('gapto_runtime', k.oid, 'UPDATE')),
                               count(*) FILTER (WHERE has_table_privilege('gapto_runtime', k.oid, 'DELETE')),
                               count(*) FILTER (WHERE k.relforcerowsecurity)
                          FROM pg_class k JOIN pg_namespace n ON n.oid = k.relnamespace
                         WHERE n.nspname = 'gapto' AND k.relkind = 'r'""").fetchone()
    obt = dict(zip(("SELECT", "INSERT", "UPDATE", "DELETE"), fila[:4]))
    rol = c.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'gapto_runtime'").fetchone()
    ok = obt == CONTRATO_ACL and fila[4] == CONTRATO_FORCE_RLS and rol == (False, False)
    return {"matriz": obt, "force_rls": fila[4], "runtime_super_bypassrls": rol, "resultado": "PASS" if ok else "FAIL"}


def _tablas_tenant(c) -> list:
    return [r[0] for r in c.execute("""SELECT k.relname FROM pg_class k JOIN pg_namespace n ON n.oid = k.relnamespace
                                       WHERE n.nspname = 'gapto' AND k.relkind = 'r' AND k.relforcerowsecurity
                                       ORDER BY 1""").fetchall()]


def sonda_rls(c, owner) -> dict:
    tablas = _tablas_tenant(c)
    reales = {t: c.execute(f"SELECT count(*) FROM gapto.{t}").fetchone()[0] for t in tablas}  # auditoria sin RLS
    res = {}
    for nombre, ctx in (("propio", owner), ("ajeno", str(uuid.uuid4())), ("sin_contexto", None)):
        with c.transaction(force_rollback=True):
            c.execute("SET LOCAL ROLE gapto_runtime")
            if ctx:
                c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (ctx,))
            vis, err = {}, {}
            for t in tablas:
                try:
                    with c.transaction():
                        vis[t] = c.execute(f"SELECT count(*) FROM gapto.{t}").fetchone()[0]
                except Exception as e:  # sin privilegio SELECT o error de contexto: se registra
                    err[t] = _error(e)
            res[nombre] = {"visibles": sum(vis.values()), "errores": len(err),
                           "tablas_con_filas": sorted(t for t, n in vis.items() if n)}
    total = sum(reales.values())
    escritura = {}
    with c.transaction(force_rollback=True):
        _runtime(c, owner)
        try:
            with c.transaction():
                c.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
                          "VALUES (%s, %s, 'CONTEXTO', 'sonda P9')", (str(uuid.uuid4()), str(uuid.uuid4())))
            escritura = {"resultado": "ACEPTADA"}
        except Exception as e:
            escritura = {"resultado": "RECHAZADA", **_error(e)}
    ok = (res["propio"]["visibles"] == total and res["ajeno"]["visibles"] == 0
          and res["sin_contexto"]["visibles"] == 0 and escritura.get("resultado") == "RECHAZADA")
    return {"filas_tenant_reales": total, "por_contexto": res, "escritura_owner_ajeno": escritura,
            "resultado": "PASS" if ok else "FAIL"}


def _posiciones(c) -> list:
    return [(str(r[0]), r[1]) for r in c.execute(
        "SELECT id, tipo_entidad FROM gapto.entidades WHERE tipo_entidad = ANY(%s) ORDER BY 2, 1",
        (list(FINANCIERAS),)).fetchall()]


def probe_a(c, owner, posiciones) -> dict:
    """DELETE directo de la raiz de cada posicion financiera bajo gapto_runtime."""
    det = []
    for eid, tipo in posiciones:
        with c.transaction(force_rollback=True):
            _runtime(c, owner)
            sql = "DELETE FROM gapto.entidades WHERE id = %s"
            try:
                with c.transaction():
                    n = c.execute(sql, (eid,)).rowcount
                    c.execute("SET CONSTRAINTS ALL IMMEDIATE")
                det.append({"entidad": eid, "tipo": tipo, "resultado": "BORRADA", "filas": n})
            except Exception as e:
                det.append({"entidad": eid, "tipo": tipo, "resultado": "RECHAZADA", **_error(e)})
    bloq = [d for d in det if d["resultado"] == "RECHAZADA" and d["sqlstate"] == "23503"]
    return {"sql": "DELETE FROM gapto.entidades WHERE id = $1", "rol": "gapto_runtime",
            "contexto": "gapto.owner_user_id = owner de la carga", "posiciones": len(det),
            "rechazadas_23503": len(bloq), "detalle": det,
            "resultado": "PASS" if len(bloq) == len(det) and det else "FAIL"}


def _protectores(c, P5B, eid, tipo) -> list:
    """(tabla, columna, n_filas) que referencian la entidad o su subtipo."""
    sub = P5B.SUBTIPO_POR_TIPO[tipo]
    pares = [(t, col) for t, cols in P5B.RESTRICT_ENTIDAD.items() for col in cols]
    pares += [(t, col) for t, cols in P5B.RESTRICT_SUBTIPO.get(sub, {}).items() for col in cols]
    out = []
    for t, col in pares:
        n = c.execute(f"SELECT count(*) FROM gapto.{t} WHERE {col} = %s", (eid,)).fetchone()[0]
        if n:
            out.append((t, col, n))
    return out


def _clonar(c, eid, tipo, sub) -> str:
    """Entidad destino del reapuntado: clon de la raiz y de su fila de subtipo, bajo gapto_runtime."""
    nuevo = str(uuid.uuid4())
    c.execute("""INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre)
                 SELECT %s, owner_user_id, tipo_entidad, 'sonda P9 ' || left(nombre, 40) FROM gapto.entidades
                  WHERE id = %s""", (nuevo, eid))
    cols = [r[0] for r in c.execute("""SELECT column_name FROM information_schema.columns
                                       WHERE table_schema = 'gapto' AND table_name = %s AND column_name <> 'entidad_id'
                                         AND is_generated = 'NEVER' ORDER BY ordinal_position""", (sub,)).fetchall()]
    lista = ", ".join(cols)
    c.execute(f"INSERT INTO gapto.{sub} (entidad_id, {lista}) SELECT %s, {lista} FROM gapto.{sub} "
              f"WHERE entidad_id = %s", (nuevo, eid))
    return nuevo


def probe_b(c, owner, posiciones, P5B) -> dict:
    """Secuencia adversarial: clon destino -> reapuntar (UPDATE) o borrar (DELETE) cada protector segun el
    privilegio de gapto_runtime -> DELETE de la raiz -> constraints diferidos inmediatos."""
    det = []
    for eid, tipo in posiciones:
        sub = P5B.SUBTIPO_POR_TIPO[tipo]
        pasos, estado = [], None
        with c.transaction(force_rollback=True):
            prot = _protectores(c, P5B, eid, tipo)  # inventario con el rol de auditoria, antes de SET ROLE
            _runtime(c, owner)
            try:
                with c.transaction():
                    destino = _clonar(c, eid, tipo, sub)
                    pasos.append(f"clon {sub}")
                    for t, col, n in prot:
                        upd = c.execute("SELECT has_column_privilege('gapto_runtime', %s, %s, 'UPDATE')",
                                        (f"gapto.{t}", col)).fetchone()[0]
                        if upd:
                            c.execute(f"UPDATE gapto.{t} SET {col} = %s WHERE {col} = %s", (destino, eid))
                            pasos.append(f"UPDATE {t}.{col} ({n})")
                        else:
                            c.execute(f"DELETE FROM gapto.{t} WHERE {col} = %s", (eid,))
                            pasos.append(f"DELETE {t} ({n})")
                    c.execute("DELETE FROM gapto.entidades WHERE id = %s", (eid,))
                    pasos.append("DELETE entidades (raiz)")
                    c.execute("SET CONSTRAINTS ALL IMMEDIATE")
                    pasos.append("SET CONSTRAINTS ALL IMMEDIATE")
                    queda = c.execute(f"SELECT count(*) FROM gapto.{sub} WHERE entidad_id = %s", (eid,)).fetchone()[0]
                estado = {"resultado": "EVADIDA", "subtipo_restante": queda}
            except Exception as e:
                estado = {"resultado": "BLOQUEADA", "paso_bloqueado": len(pasos) + 1, **_error(e)}
        det.append({"entidad": eid, "tipo": tipo, "protectores": [f"{t}.{col}={n}" for t, col, n in prot],
                    "pasos": pasos, **estado})
    ev = [d for d in det if d["resultado"] == "EVADIDA"]
    return {"posiciones": len(det), "evadidas": len(ev), "bloqueadas": len(det) - len(ev),
            "por_tipo": {t: {"evadidas": sum(1 for d in ev if d["tipo"] == t),
                             "total": sum(1 for d in det if d["tipo"] == t)} for t in FINANCIERAS},
            "detalle": det}


def recuentos(c) -> dict:
    return {t: c.execute(f"SELECT count(*) FROM gapto.{t}").fetchone()[0]
            for t in ("entidades", "mapeos_importacion", "hechos_financieros", "entidad_participaciones",
                      "hecho_entidades", "financiacion_cuotas")}


def ejecutar(dsn: str, owner: str) -> dict:
    import psycopg
    P5B = _p5b()
    ev = {"inicio_utc": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    with psycopg.connect(dsn, autocommit=True) as c:  # cada sonda abre su propia transaccion revertida
        ev["perfil"] = "RV3_RUNTIME_PROBE: SET LOCAL ROLE gapto_runtime + set_config('gapto.owner_user_id')"
        ev["recuentos_antes"] = recuentos(c)
        ev["xid_antes"] = c.execute("SELECT pg_snapshot_xmax(pg_current_snapshot())::text").fetchone()[0]
        ev["acl"] = sonda_acl(c)
        ev["rls"] = sonda_rls(c, owner)
        pos = _posiciones(c)
        ev["R_RV3_016"] = {"probe_A_delete_directo": probe_a(c, owner, pos),
                           "probe_B_update_mas_delete": probe_b(c, owner, pos, P5B)}
        ev["recuentos_despues"] = recuentos(c)
        ev["xid_despues"] = c.execute("SELECT pg_snapshot_xmax(pg_current_snapshot())::text").fetchone()[0]
    b = ev["R_RV3_016"]["probe_B_update_mas_delete"]
    ev["R_RV3_016"]["clasificacion"] = (
        "PROTEGIDA_FRENTE_A_DELETE_DIRECTO; EVASION_UPDATE_DELETE_MATERIAL_CONFIRMADA" if b["evadidas"]
        else "PROTEGIDA_FRENTE_A_DELETE_DIRECTO; EVASION_UPDATE_DELETE_NO_ALCANZABLE")
    ev["carga_intacta"] = ev["recuentos_antes"] == ev["recuentos_despues"]
    ok = (ev["acl"]["resultado"] == "PASS" and ev["rls"]["resultado"] == "PASS"
          and ev["R_RV3_016"]["probe_A_delete_directo"]["resultado"] == "PASS" and ev["carga_intacta"])
    ev["fin_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    ev["veredicto"] = "SUPERADO" if ok else "NO_SUPERADO"
    return ev


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RV3 P9: sondas runtime (ROLLBACK)")
    ap.add_argument("--dsn", required=True, help="sesion de laboratorio que puede asumir gapto_runtime")
    ap.add_argument("--owner", required=True)
    ap.add_argument("--salida", required=True, type=Path)
    a = ap.parse_args(argv)
    ev = ejecutar(a.dsn, a.owner)
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "rv3_p9_runtime.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1, default=str),
                                                  encoding="utf-8")
    b = ev["R_RV3_016"]["probe_B_update_mas_delete"]
    print(json.dumps({"veredicto": ev["veredicto"], "acl": ev["acl"]["resultado"], "rls": ev["rls"]["resultado"],
                      "probe_A": ev["R_RV3_016"]["probe_A_delete_directo"]["rechazadas_23503"],
                      "probe_B": {"evadidas": b["evadidas"], "bloqueadas": b["bloqueadas"]},
                      "clasificacion": ev["R_RV3_016"]["clasificacion"], "carga_intacta": ev["carga_intacta"]}))
    return 0 if ev["veredicto"] == "SUPERADO" else 1


if __name__ == "__main__":
    sys.exit(main())
