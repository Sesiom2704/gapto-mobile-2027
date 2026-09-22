# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p7_integridad.py
# Ruta: scripts/migration_v3/rv3_p7_integridad.py
# Descripcion: RV3 / P7. Certificacion de integridad post-carga de la BD material P6, en UNA transaccion
#              READ ONLY (el servidor rechaza cualquier escritura) con rol de auditoria sin RLS para ver todas las
#              filas. Cubre: P7-A R25 huellas D-111 contra la referencia canonica 0330 (run_clean_room.py);
#              P7-B constraints (catalogo validado, NOT NULL, PK/UNIQUE e indices unicos con predicado/expresion/
#              NULLS NOT DISTINCT, FK con MATCH, CHECK, EXCLUDE, constraint triggers habilitados e invariantes de
#              sus funciones re-verificadas por SQL independiente, ausencia de cambios tras la carga por xmin/xmax);
#              P7-C huerfanos (FK + referencias uuid sin FK); P7-D destinos polimorficos; P7-E trazabilidad de
#              importacion. Fail-closed: cualquier violacion o deriva -> veredicto NO_SUPERADO. Parametrizable por
#              esquema para poder discriminarse con esquemas sinteticos en tests.
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import argparse
import ast
import datetime as _dt
import json
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[2]
HUELLAS_CAMPOS = ("h1_columnas", "h2_constraints", "h3_indices", "h4_policies", "h5_triggers", "h6_funciones",
                  "h7_grants", "h8_vistas", "recuentos")
CONTRATO_CONSTRAINTS_0330 = {"f": 175, "c": 296, "u": 41, "p": 80, "x": 11, "t": 41}
TIPOS_SIN_DESTINO = ("OBSOLETO", "IGNORADO")
# columnas uuid sin FK en 0330 y su tratamiento en P7-C/D
REFERENCIAS_SIN_FK = {
    ("auditoria", "registro_id"): "POLIMORFICA",       # (tabla, registro_id): se audita en P7-D
    ("auditoria", "request_id"): "CORRELACION",        # identificador de peticion, no referencia a fila
    ("mapeos_importacion", "registro_destino_id"): "POLIMORFICA",
    ("servicios", "categoria_default_id"): "CATEGORIA",  # sin FK en 0330: se comprueba existencia por SQL
}


def huellas_referencia(head: str = "0330") -> dict:
    """Lee HUELLAS_D111_POR_HEAD de run_clean_room.py sin importarlo (sin efectos laterales)."""
    arbol = ast.parse((_RAIZ / "scripts" / "postgres" / "run_clean_room.py").read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assign) and any(getattr(t, "id", None) == "HUELLAS_D111_POR_HEAD" for t in nodo.targets):
            return ast.literal_eval(nodo.value)[head]
    raise RuntimeError("HUELLAS_D111_POR_HEAD no encontrado")


def huellas(c) -> dict:
    fila = c.execute((_RAIZ / "scripts" / "postgres" / "huellas_d111.sql").read_text(encoding="utf-8")).fetchone()
    return dict(zip(HUELLAS_CAMPOS, fila))


def comparar_huellas(obtenidas: dict, referencia: dict) -> list:
    return sorted(k for k in HUELLAS_CAMPOS if obtenidas.get(k) != referencia.get(k))


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _tablas(c, esq) -> list:
    return [r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY 1", (esq,))]


def check_catalogo(c, esq) -> dict:
    por_tipo = dict(c.execute("""SELECT c.contype, count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
                                 WHERE n.nspname = %s GROUP BY 1""", (esq,)).fetchall())
    no_validadas = c.execute("""SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
                                WHERE n.nspname = %s AND NOT c.convalidated""", (esq,)).fetchone()[0]
    trig = dict(c.execute("""SELECT t.tgenabled, count(*) FROM pg_trigger t JOIN pg_class k ON k.oid = t.tgrelid
                             JOIN pg_namespace n ON n.oid = k.relnamespace WHERE n.nspname = %s AND NOT t.tgisinternal
                             GROUP BY 1""", (esq,)).fetchall())
    return {"por_tipo": por_tipo, "no_validadas": no_validadas, "triggers_por_estado": trig,
            "violaciones": no_validadas + sum(n for e, n in trig.items() if e != "O")}


def check_not_null(c, esq) -> dict:
    cols = c.execute("""SELECT k.relname, a.attname FROM pg_attribute a JOIN pg_class k ON k.oid = a.attrelid
                        JOIN pg_namespace n ON n.oid = k.relnamespace
                        WHERE n.nspname = %s AND k.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped AND a.attnotnull
                        ORDER BY 1, 2""", (esq,)).fetchall()
    viol = {}
    for t, col in cols:
        # num_nulls() evita que el planificador reduzca "col IS NULL" a falso por confiar en attnotnull
        n = c.execute(f"SELECT count(*) FROM {_q(esq)}.{_q(t)} WHERE num_nulls({_q(col)}) > 0").fetchone()[0]
        if n:
            viol[f"{t}.{col}"] = n
    return {"columnas": len(cols), "violaciones": viol}


def check_unicos(c, esq) -> dict:
    idx = c.execute("""SELECT i.indexrelid, k.relname, ic.relname, i.indnkeyatts, i.indnullsnotdistinct,
                              pg_get_expr(i.indpred, i.indrelid)
                         FROM pg_index i JOIN pg_class k ON k.oid = i.indrelid JOIN pg_class ic ON ic.oid = i.indexrelid
                         JOIN pg_namespace n ON n.oid = k.relnamespace
                        WHERE n.nspname = %s AND i.indisunique ORDER BY 2, 3""", (esq,)).fetchall()
    viol = {}
    for oid, t, nombre, nk, nnd, pred in idx:
        exprs = [c.execute("SELECT pg_get_indexdef(%s, %s, true)", (oid, k)).fetchone()[0] for k in range(1, nk + 1)]
        where = [f"({pred})"] if pred else []
        if not nnd:
            where += [f"({e}) IS NOT NULL" for e in exprs]
        sql = (f"SELECT count(*) FROM (SELECT 1 FROM {_q(esq)}.{_q(t)} "
               f"{'WHERE ' + ' AND '.join(where) if where else ''} GROUP BY {', '.join(exprs)} HAVING count(*) > 1) x")
        n = c.execute(sql).fetchone()[0]
        if n:
            viol[nombre] = n
    return {"indices_unicos": len(idx), "violaciones": viol}


def check_fk(c, esq) -> dict:
    fks = c.execute("""SELECT c.conname, c.conrelid::regclass::text, c.confrelid::regclass::text, c.confmatchtype,
                              ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY u(n, o)
                                    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = u.n ORDER BY u.o),
                              ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY u(n, o)
                                    JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = u.n ORDER BY u.o)
                         FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
                        WHERE n.nspname = %s AND c.contype = 'f' ORDER BY 1""", (esq,)).fetchall()
    viol = {}
    for nombre, hijo, padre, match, hc, pc in fks:
        on = " AND ".join(f"p.{_q(b)} = h.{_q(a)}" for a, b in zip(hc, pc))
        if match == "f":  # MATCH FULL: todo NULL o ninguno NULL
            mixto = " OR ".join(f"h.{_q(a)} IS NULL" for a in hc)
            todo = " AND ".join(f"h.{_q(a)} IS NULL" for a in hc)
            filtro = f"NOT ({todo}) AND (({mixto}) OR NOT EXISTS (SELECT 1 FROM {padre} p WHERE {on}))"
        else:  # MATCH SIMPLE: se comprueba solo si ninguna columna es NULL
            nn = " AND ".join(f"h.{_q(a)} IS NOT NULL" for a in hc)
            filtro = f"{nn} AND NOT EXISTS (SELECT 1 FROM {padre} p WHERE {on})"
        n = c.execute(f"SELECT count(*) FROM {hijo} h WHERE {filtro}").fetchone()[0]
        if n:
            viol[nombre] = n
    return {"fk": len(fks), "violaciones": viol}


def check_check(c, esq) -> dict:
    cks = c.execute("""SELECT c.conname, c.conrelid::regclass::text, pg_get_expr(c.conbin, c.conrelid)
                         FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
                        WHERE n.nspname = %s AND c.contype = 'c' ORDER BY 1""", (esq,)).fetchall()
    viol = {}
    for nombre, t, expr in cks:
        n = c.execute(f"SELECT count(*) FROM {t} WHERE ({expr}) IS FALSE").fetchone()[0]
        if n:
            viol[nombre] = n
    return {"check": len(cks), "violaciones": viol}


def check_exclude(c, esq) -> dict:
    exs = c.execute("""SELECT c.conname, c.conrelid::regclass::text, c.conindid, i.indnkeyatts,
                              pg_get_expr(i.indpred, i.indrelid),
                              ARRAY(SELECT o.oprname FROM unnest(c.conexclop) WITH ORDINALITY u(op, ord)
                                    JOIN pg_operator o ON o.oid = u.op ORDER BY u.ord)
                         FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
                         JOIN pg_index i ON i.indexrelid = c.conindid
                        WHERE n.nspname = %s AND c.contype = 'x' ORDER BY 1""", (esq,)).fetchall()
    viol = {}
    for nombre, t, idx, nk, pred, ops in exs:
        exprs = [c.execute("SELECT pg_get_indexdef(%s, %s, true)", (idx, k)).fetchone()[0] for k in range(1, nk + 1)]
        # las expresiones del indice referencian columnas sin cualificar: se evaluan en subconsultas con alias
        conds = [f"a.e{k} {op} b.e{k}" for k, op in enumerate(ops)]
        proy = ", ".join(f"({e}) AS e{k}" for k, e in enumerate(exprs))
        base = f"SELECT ctid AS _ctid, {proy} FROM {t}" + (f" WHERE {pred}" if pred else "")
        n = c.execute(f"SELECT count(*) FROM ({base}) a JOIN ({base}) b ON a._ctid < b._ctid AND "
                      + " AND ".join(conds)).fetchone()[0]
        if n:
            viol[nombre] = n
    return {"exclude": len(exs), "violaciones": viol}


def _sql_suma_100(s: str, t: str, fk: str) -> str:
    """Espejo de fn_check_participacion_suma: puntos = vigente_desde y vigente_hasta + 1 dentro de [min desde,
    max hasta]; en cada punto la suma de filas vigentes debe ser exactamente 100 (0 filas = no modelado)."""
    return f"""WITH puntos AS (SELECT {fk} AS p, vigente_desde AS punto FROM {s}.{t}
                               UNION SELECT {fk}, vigente_hasta + 1 FROM {s}.{t} WHERE vigente_hasta IS NOT NULL),
                limites AS (SELECT {fk} AS p, min(vigente_desde) ini, max(coalesce(vigente_hasta, 'infinity'::date)) fin
                              FROM {s}.{t} GROUP BY 1),
                evaluados AS (SELECT pu.p, pu.punto,
                                     (SELECT coalesce(sum(x.porcentaje), 0) FROM {s}.{t} x WHERE x.{fk} = pu.p
                                         AND x.vigente_desde <= pu.punto
                                         AND (x.vigente_hasta IS NULL OR x.vigente_hasta >= pu.punto)) AS suma
                                FROM puntos pu JOIN limites l ON l.p = pu.p
                               WHERE pu.punto >= l.ini AND pu.punto <= l.fin)
             SELECT count(*) FROM evaluados WHERE suma <> 100"""


def check_invariantes(c, esq) -> dict:
    """Re-verificacion SQL independiente de las invariantes de 7 funciones de constraint trigger."""
    s = _q(esq)
    sub = ("propiedades", "contratos", "servicios", "financiaciones", "inversiones", "derechos_obligaciones_financieras",
           "contextos")
    tipo = {"propiedades": "PROPIEDAD", "contratos": "CONTRATO", "servicios": "SERVICIO",
            "financiaciones": "FINANCIACION", "inversiones": "INVERSION",
            "derechos_obligaciones_financieras": "DERECHO_OBLIGACION", "contextos": "CONTEXTO"}
    total = " + ".join(f"(SELECT count(*) FROM {s}.{t} x WHERE x.entidad_id = e.id)" for t in sub)
    coh = "CASE e.tipo_entidad " + " ".join(
        f"WHEN '{tipo[t]}' THEN (SELECT count(*) FROM {s}.{t} x WHERE x.entidad_id = e.id)" for t in sub) + " ELSE 0 END"
    q = {
        "subtipo_unico (fn_check_entidad_subtipo_unico)":
            f"SELECT count(*) FROM {s}.entidades e WHERE ({coh}) <> 1 OR ({total}) <> 1",
        "subtipo_sin_raiz_coherente":
            "SELECT " + " + ".join(f"(SELECT count(*) FROM {s}.{t} x JOIN {s}.entidades e ON e.id = x.entidad_id "
                       f"WHERE e.tipo_entidad <> '{tipo[t]}')" for t in sub),
        "atribucion_suma (fn_check_atribucion_suma)":
            f"""SELECT count(*) FROM {s}.hecho_efectos e
                 LEFT JOIN (SELECT efecto_id, sum(importe_atribuido) sm FROM {s}.efecto_atribuciones GROUP BY 1) a
                   ON a.efecto_id = e.id
                WHERE (e.estado_atribucion = 'COMPLETA' AND COALESCE(a.sm, 0) <> e.importe_delta)
                   OR (e.estado_atribucion = 'PARCIAL' AND (abs(COALESCE(a.sm, 0)) > abs(e.importe_delta)
                       OR (COALESCE(a.sm, 0) <> 0 AND sign(a.sm) <> sign(e.importe_delta))))""",
        "transferencia_estructura (fn_check_transferencia_estructura)":
            f"""SELECT count(*) FROM {s}.transferencias t
                 JOIN {s}.movimientos_tesoreria ms ON ms.id = t.movimiento_salida_id
                 JOIN {s}.movimientos_tesoreria me ON me.id = t.movimiento_entrada_id
                 JOIN {s}.cuentas cs ON cs.id = ms.cuenta_id JOIN {s}.cuentas ce ON ce.id = me.cuenta_id
                WHERE ms.estado <> 'ACTIVO' OR me.estado <> 'ACTIVO' OR ms.importe >= 0 OR me.importe <= 0
                   OR ms.cuenta_id = me.cuenta_id OR cs.owner_user_id <> ce.owner_user_id
                   OR (cs.moneda = ce.moneda AND abs(ms.importe) <> me.importe)""",
        "participacion_suma_100 (fn_check_participacion_suma: entidades)": _sql_suma_100(s, "entidad_participaciones", "entidad_id"),
        "participacion_suma_100 (fn_check_participacion_suma: cuentas)": _sql_suma_100(s, "cuenta_participaciones", "cuenta_id"),
    }
    for t, col in (("categorias_financieras", "parent_id"), ("clasificaciones_tercero", "parent_id"),
                   ("regiones", "parent_region_id"), ("inversiones", "inversion_padre_entidad_id")):
        pk = "entidad_id" if t == "inversiones" else "id"
        q[f"aciclica {t} (fn_check_jerarquia_aciclica)"] = f"""
            WITH RECURSIVE r(origen, actual, prof) AS (
                SELECT {pk}, {col}, 1 FROM {s}.{t} WHERE {col} IS NOT NULL
                UNION ALL SELECT r.origen, x.{col}, r.prof + 1 FROM r JOIN {s}.{t} x ON x.{pk} = r.actual
                 WHERE x.{col} IS NOT NULL AND r.prof < 1000)
            SELECT count(*) FROM r WHERE actual = origen OR prof >= 1000"""
    viol = {}
    for k, sql in q.items():
        n = c.execute(sql).fetchone()[0]
        if n:
            viol[k] = n
    return {"invariantes": len(q), "violaciones": viol}


SEMILLAS_0330 = {"tipos_hecho": None, "metricas_definicion": ("AHORRO_NETO_PYL", "APORTACION_INVERSION_NETA",
                                                          "TRANSFERENCIA_AHORRO_NETA")}


def check_sin_cambios(c, esq, xid_carga: int) -> dict:
    """Toda fila visible nace en la transaccion de carga, salvo las semillas contractuales de 0330. Una fila
    actualizada despues de la carga tendria xmin posterior; una borrada ya no seria visible y el recuento
    discriminante la delataria. xmax en filas visibles solo puede ser un bloqueo o una transaccion abortada."""
    s = _q(esq)
    otros, xmax_info = {}, {}
    for t in _tablas(c, esq):
        for xmin, n in c.execute(f"SELECT xmin::text::bigint, count(*) FROM {s}.{_q(t)} "
                                 "WHERE xmin::text::bigint <> %s GROUP BY 1", (xid_carga,)).fetchall():
            otros.setdefault(t, {})[xmin] = n
        m = c.execute(f"SELECT count(*) FROM {s}.{_q(t)} WHERE xmax::text::bigint NOT IN (0, %s)",
                      (xid_carga,)).fetchone()[0]
        if m:
            xmax_info[t] = m
    semillas = c.execute(f"SELECT count(*) FROM {s}.tipos_hecho").fetchone()[0] + c.execute(
        f"SELECT count(*) FROM {s}.metricas_definicion WHERE codigo = ANY(%s)",
        (list(SEMILLAS_0330["metricas_definicion"]),)).fetchone()[0]
    ajenas = sum(n for d in otros.values() for n in d.values())
    posteriores = sum(n for d in otros.values() for x, n in d.items() if x > xid_carga)
    fuera_semillas = {t: d for t, d in otros.items() if t not in SEMILLAS_0330}
    siguiente = int(c.execute("SELECT pg_snapshot_xmax(pg_current_snapshot())::text").fetchone()[0])
    stats = c.execute("""SELECT count(*), min(xmin::text::bigint), max(xmin::text::bigint) FROM pg_statistic
                          WHERE xmin::text::bigint > %s""", (xid_carga,)).fetchone()
    viol = {}
    if posteriores:
        viol["filas_con_xmin_posterior_a_la_carga"] = posteriores
    if ajenas != semillas or fuera_semillas:
        viol["filas_ajenas_a_carga_y_semillas"] = {"ajenas": ajenas, "semillas": semillas, "tablas": fuera_semillas}
    return {"xid_carga": xid_carga, "siguiente_xid": siguiente, "filas_fuera_de_la_carga": otros,
            "semillas_0330": semillas, "xmax_no_carga_informativo": xmax_info,
            "pg_statistic_posterior": {"filas": stats[0], "xid_min": stats[1], "xid_max": stats[2]},
            "violaciones": viol}


def check_referencias_sin_fk(c, esq) -> dict:
    s = _q(esq)
    decl = c.execute(f"""
        WITH fk AS (SELECT c.conrelid, unnest(c.conkey) attnum FROM pg_constraint c JOIN pg_namespace n
                    ON n.oid = c.connamespace WHERE n.nspname = %s AND c.contype IN ('f', 'p'))
        SELECT k.relname, a.attname FROM pg_attribute a JOIN pg_class k ON k.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = k.relnamespace
         WHERE n.nspname = %s AND k.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
           AND a.atttypid = 'uuid'::regtype AND a.attname <> 'id'
           AND NOT EXISTS (SELECT 1 FROM fk WHERE fk.conrelid = a.attrelid AND fk.attnum = a.attnum)""",
                     (esq, esq)).fetchall()
    encontradas = {(t, col) for t, col in decl}
    no_clasificadas = sorted(f"{t}.{col}" for t, col in encontradas - set(REFERENCIAS_SIN_FK))
    viol = {}
    if ("servicios", "categoria_default_id") in encontradas:
        n = c.execute(f"""SELECT count(*) FROM {s}.servicios x WHERE x.categoria_default_id IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM {s}.categorias_financieras k WHERE k.id = x.categoria_default_id
                                          AND k.owner_user_id = (SELECT owner_user_id FROM {s}.entidades e
                                                                  WHERE e.id = x.entidad_id))""").fetchone()[0]
        if n:
            viol["servicios.categoria_default_id"] = n
    if no_clasificadas:
        viol["referencias_uuid_sin_fk_no_clasificadas"] = no_clasificadas
    return {"columnas_uuid_sin_fk": sorted(f"{t}.{col}" for t, col in encontradas), "violaciones": viol}


def pk_de(c, esq, tabla) -> str:
    r = c.execute("""SELECT a.attname FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid
                     AND a.attnum = c.conkey[1] JOIN pg_class k ON k.oid = c.conrelid
                     JOIN pg_namespace n ON n.oid = k.relnamespace
                     WHERE n.nspname = %s AND k.relname = %s AND c.contype = 'p' AND cardinality(c.conkey) = 1""",
                  (esq, tabla)).fetchone()
    return r[0] if r else None


def extensiones_1a1(c, esq) -> set:
    """Pares (raiz, extension) donde la PK de una columna de la extension es FK a la PK de la raiz."""
    return set(c.execute("""
        SELECT r.relname, k.relname FROM pg_constraint pk
          JOIN pg_constraint fk ON fk.conrelid = pk.conrelid AND fk.contype = 'f' AND fk.conkey = pk.conkey
          JOIN pg_constraint rpk ON rpk.conrelid = fk.confrelid AND rpk.contype = 'p' AND rpk.conkey = fk.confkey
          JOIN pg_class k ON k.oid = pk.conrelid JOIN pg_class r ON r.oid = fk.confrelid
          JOIN pg_namespace n ON n.oid = k.relnamespace
         WHERE n.nspname = %s AND pk.contype = 'p' AND cardinality(pk.conkey) = 1""", (esq,)).fetchall())


def check_polimorficos(c, esq) -> dict:
    s = _q(esq)
    tablas = set(_tablas(c, esq))
    viol, por_tabla = {}, {}
    destinos = [r[0] for r in c.execute(f"SELECT DISTINCT tabla_destino FROM {s}.mapeos_importacion "
                                        "WHERE tabla_destino IS NOT NULL ORDER BY 1").fetchall()]
    desconocidas = [t for t in destinos if t not in tablas or pk_de(c, esq, t) is None]
    if desconocidas:
        viol["tabla_destino_invalida"] = desconocidas
    for t in destinos:
        if t in desconocidas:
            continue
        pk = pk_de(c, esq, t)
        n, falta = c.execute(f"""SELECT count(*), count(*) FILTER (WHERE NOT EXISTS
                                   (SELECT 1 FROM {s}.{_q(t)} d WHERE d.{_q(pk)} = m.registro_destino_id))
                                 FROM {s}.mapeos_importacion m WHERE m.tabla_destino = %s""", (t,)).fetchone()
        por_tabla[t] = n
        if falta:
            viol[f"destino_inexistente.{t}"] = falta
    # un destino no puede resolverse en mas de una tabla (ambiguedad por identidad compartida)
    union = " UNION ALL ".join(f"SELECT {_q(pk_de(c, esq, t))} AS id, '{t}' AS t FROM {s}.{_q(t)}"
                               for t in sorted(tablas) if pk_de(c, esq, t))
    grupos = c.execute(f"""SELECT tablas, count(*) FROM (
                             SELECT m.id, array_agg(DISTINCT u.t ORDER BY u.t) tablas FROM {s}.mapeos_importacion m
                               JOIN ({union}) u ON u.id = m.registro_destino_id
                              GROUP BY m.id HAVING count(DISTINCT u.t) > 1) x GROUP BY 1 ORDER BY 1""").fetchall()
    # identidad compartida legitima: extension 1:1 cuya PK es a la vez FK a la PK de su raiz (entidades -> 7 subtipos,
    # terceros -> tercero_personas en 0330); tabla_destino resuelve cual de las dos filas es el destino
    legitimos = {tuple(sorted(par)) for par in extensiones_1a1(c, esq)}
    ambiguos_bien_tipados = {"/".join(t): n for t, n in grupos if tuple(t) in legitimos}
    ilegitimos = {"/".join(t): n for t, n in grupos if tuple(t) not in legitimos}
    if ilegitimos:
        viol["identidad_compartida_ambigua"] = ilegitimos
    coherencia = c.execute(f"""SELECT count(*) FROM {s}.mapeos_importacion
                                WHERE (tabla_destino IS NULL) <> (registro_destino_id IS NULL)
                                   OR (tabla_destino IS NULL AND NOT tipo_mapping = ANY(%s))
                                   OR (tabla_destino IS NOT NULL AND tipo_mapping = ANY(%s))""",
                           (list(TIPOS_SIN_DESTINO), list(TIPOS_SIN_DESTINO))).fetchone()[0]
    if coherencia:
        viol["tipo_vs_destino_incoherente"] = coherencia
    efecto_otro_hecho = c.execute(f"""SELECT count(*) FROM {s}.hecho_entidades he JOIN {s}.hecho_efectos e
                                       ON e.id = he.efecto_id WHERE e.hecho_id <> he.hecho_id""").fetchone()[0]
    if efecto_otro_hecho:
        viol["hecho_entidades.efecto_de_otro_hecho"] = efecto_otro_hecho
    aud = c.execute(f"SELECT count(*) FROM {s}.auditoria").fetchone()[0]
    return {"mapeos_por_tabla_destino": por_tabla, "destinos_con_identidad_compartida_resueltos_por_tabla": ambiguos_bien_tipados,
            "auditoria_filas": aud, "violaciones": viol}


def check_trazabilidad(c, esq, esperado: dict) -> dict:
    s = _q(esq)
    r = {"mapeos": c.execute(f"SELECT count(*) FROM {s}.mapeos_importacion").fetchone()[0],
         "registros_origen": c.execute(f"SELECT count(*) FROM {s}.registros_origen_importacion").fetchone()[0],
         "fuentes": c.execute(f"SELECT count(*) FROM {s}.fuentes_importacion").fetchone()[0],
         "hechos": c.execute(f"SELECT count(*) FROM {s}.hechos_financieros").fetchone()[0]}
    viol = {k: {"esperado": v, "obtenido": r[k]} for k, v in esperado.items() if r.get(k) != v}
    sin_origen = c.execute(f"""SELECT count(*) FROM {s}.mapeos_importacion m WHERE NOT EXISTS
                               (SELECT 1 FROM {s}.registros_origen_importacion o WHERE o.id = m.registro_origen_id)""").fetchone()[0]
    origen_sin_fuente = c.execute(f"""SELECT count(*) FROM {s}.registros_origen_importacion o WHERE NOT EXISTS
                                      (SELECT 1 FROM {s}.fuentes_importacion f WHERE f.id = o.fuente_importacion_id)""").fetchone()[0]
    origen_sin_disposicion = c.execute(f"""SELECT count(*) FROM {s}.registros_origen_importacion o WHERE NOT EXISTS
                                           (SELECT 1 FROM {s}.mapeos_importacion m WHERE m.registro_origen_id = o.id)""").fetchone()[0]
    for k, n in (("mapeo_sin_origen", sin_origen), ("origen_sin_fuente", origen_sin_fuente),
                 ("origen_sin_disposicion", origen_sin_disposicion)):
        if n:
            viol[k] = n
    return {**r, "violaciones": viol}


def auditar(dsn: str, esq: str, xid_carga: int, esperado: dict, referencia: dict | None) -> dict:
    import psycopg
    res = {"inicio_utc": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    with psycopg.connect(dsn) as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")  # una sola foto, sin escrituras
        res["transaccion"] = {"read_only": c.execute("SHOW transaction_read_only").fetchone()[0],
                              "rol": c.execute("SELECT current_user").fetchone()[0],
                              "bd": c.execute("SELECT current_database()").fetchone()[0],
                              "version": c.execute("SHOW server_version").fetchone()[0]}
        if referencia is not None:
            h = huellas(c)
            res["R25"] = {"obtenidas": h, "referencia": referencia, "diferencias": comparar_huellas(h, referencia)}
        res["catalogo"] = check_catalogo(c, esq)
        res["not_null"] = check_not_null(c, esq)
        res["unicos"] = check_unicos(c, esq)
        res["fk"] = check_fk(c, esq)
        res["check"] = check_check(c, esq)
        res["exclude"] = check_exclude(c, esq)
        res["invariantes_triggers"] = check_invariantes(c, esq)
        res["sin_cambios"] = check_sin_cambios(c, esq, xid_carga)
        res["referencias_sin_fk"] = check_referencias_sin_fk(c, esq)
        res["polimorficos"] = check_polimorficos(c, esq)
        res["trazabilidad"] = check_trazabilidad(c, esq, esperado)
        res["escritura_asignada"] = c.execute("SELECT pg_current_xact_id_if_assigned()").fetchone()[0]
        c.rollback()
    res["fin_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    fallos = [k for k, v in res.items() if isinstance(v, dict) and v.get("violaciones")]
    if referencia is not None and res["R25"]["diferencias"]:
        fallos.append("R25")
    if res["escritura_asignada"] is not None:
        fallos.append("escritura_asignada")
    res["fallos"] = fallos
    res["veredicto"] = "SUPERADO" if not fallos else "NO_SUPERADO"
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RV3 P7: integridad post-carga (solo lectura)")
    ap.add_argument("--dsn-auditoria", required=True, help="rol de auditoria sin RLS; transaccion READ ONLY")
    ap.add_argument("--esquema", default="gapto")
    ap.add_argument("--xid-carga", required=True, type=int)
    ap.add_argument("--mapeos", required=True, type=int)
    ap.add_argument("--hechos", required=True, type=int)
    ap.add_argument("--registros-origen", required=True, type=int)
    ap.add_argument("--salida", required=True, type=Path)
    a = ap.parse_args(argv)
    res = auditar(a.dsn_auditoria, a.esquema, a.xid_carga,
                  {"mapeos": a.mapeos, "hechos": a.hechos, "registros_origen": a.registros_origen},
                  huellas_referencia("0330"))
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "rv3_p7_integridad.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str),
                                                     encoding="utf-8")
    print(json.dumps({"veredicto": res["veredicto"], "fallos": res["fallos"],
                      "R25": res.get("R25", {}).get("diferencias")}, default=str))
    return 0 if res["veredicto"] == "SUPERADO" else 1


if __name__ == "__main__":
    sys.exit(main())
