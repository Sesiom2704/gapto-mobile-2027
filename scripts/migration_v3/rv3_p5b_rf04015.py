# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p5b_rf04015.py
# Ruta: scripts/migration_v3/rv3_p5b_rf04015.py
# Descripcion: RV3 / P5b (contrato RV3 §13, D-D). Auditoria ESTATICA de R-F04-015 sobre el dataset P5, antes de
#              cualquier carga material: por cada entidad importada, referencias RESTRICT que impiden que un DELETE
#              de gapto.entidades la destruya por CASCADE (7 subtipos). Clasificacion:
#                PROTEGIDA     = al menos un protector que gapto_runtime NO puede borrar (sin privilegio DELETE);
#                NO_PROTEGIDA  = solo protectores que runtime puede borrar, o ninguno;
#                INDETERMINADA = falta evidencia (entidad sin tipo conocido).
#              Ademas informa la EVASION POR UPDATE: protector cuya columna FK runtime puede reapuntar (UPDATE),
#              lo que permitiria vaciar la entidad y borrarla en varios pasos. No se crean vinculos para proteger.
#              El mapa FK/ACL de 0330 se declara aqui y un test lo contrasta con el catalogo fisico (deriva = fallo).
#              P9 confirmara las PROTEGIDAS con DELETE real bajo gapto_runtime en ROLLBACK (esperado 23503).
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import collections

# Subtipos de gapto.entidades con FK ON DELETE CASCADE (0330)
SUBTIPO_POR_TIPO = {"FINANCIACION": "financiaciones", "DERECHO_OBLIGACION": "derechos_obligaciones_financieras",
                    "INVERSION": "inversiones", "PROPIEDAD": "propiedades", "CONTRATO": "contratos",
                    "CONTEXTO": "contextos", "SERVICIO": "servicios"}
POSICIONES_FINANCIERAS = {"FINANCIACION", "DERECHO_OBLIGACION", "INVERSION"}
# Referencias RESTRICT hacia entidades(id): tabla -> columnas (0330)
RESTRICT_ENTIDAD = {
    "cierre_posiciones_entidad": ("entidad_id",), "documento_vinculos": ("entidad_id",),
    "entidad_participaciones": ("entidad_id",), "entidad_relaciones": ("entidad_origen_id", "entidad_destino_id"),
    "hecho_entidades": ("entidad_id",), "inversion_asignaciones_efecto": ("inversion_entidad_id",),
    "plantillas_registro": ("entidad_id",), "preferencias_registro": ("entidad_id",),
    "presupuesto_linea_alcances": ("entidad_id",), "previsiones": ("entidad_id",),
    "reglas_financieras": ("entidad_origen_id",)}
# Referencias RESTRICT hacia cada subtipo (bloquean la cascada): subtipo -> {tabla: columnas} (0330)
RESTRICT_SUBTIPO = {
    "contratos": {"contrato_participantes": ("contrato_entidad_id",),
                  "contrato_revision_renta_versiones": ("contrato_entidad_id",),
                  "contrato_servicios": ("contrato_entidad_id",)},
    "financiaciones": {"financiacion_condiciones_versiones": ("financiacion_entidad_id",),
                       "financiacion_cuotas": ("financiacion_entidad_id",)},
    "inversiones": {"inversion_asignaciones_efecto": ("inversion_entidad_id",),
                    "inversion_objetivos_versiones": ("inversion_entidad_id",),
                    "inversion_valoraciones": ("inversion_entidad_id",),
                    "inversiones": ("inversion_padre_entidad_id",)},
    "propiedades": {"contratos": ("propiedad_entidad_id",), "propiedad_servicios": ("propiedad_entidad_id",),
                    "propiedad_valoraciones": ("propiedad_entidad_id",)},
    "servicios": {"contrato_servicios": ("servicio_entidad_id",), "propiedad_servicios": ("servicio_entidad_id",)},
    "contextos": {}, "derechos_obligaciones_financieras": {}}
# gapto_runtime: tablas protectoras SIN privilegio DELETE en 0330
RUNTIME_SIN_DELETE = {"cierre_posiciones_entidad", "entidad_participaciones", "contrato_participantes",
                      "contrato_revision_renta_versiones", "financiacion_condiciones_versiones", "financiacion_cuotas",
                      "inversion_objetivos_versiones", "inversion_valoraciones", "inversiones", "contratos",
                      "propiedad_valoraciones"}
# gapto_runtime: columnas FK protectoras que el PRIVILEGIO permite reapuntar por UPDATE (0330, has_column_privilege).
# Solo cierre_posiciones_entidad (append-only) no es reapuntable. Si un trigger lo impide en la practica lo decide P9.
RUNTIME_UPDATE_FK = {("contrato_participantes", "contrato_entidad_id"),
                     ("contrato_revision_renta_versiones", "contrato_entidad_id"),
                     ("contratos", "propiedad_entidad_id"), ("entidad_participaciones", "entidad_id"),
                     ("financiacion_condiciones_versiones", "financiacion_entidad_id"),
                     ("financiacion_cuotas", "financiacion_entidad_id"),
                     ("inversion_objetivos_versiones", "inversion_entidad_id"),
                     ("inversion_valoraciones", "inversion_entidad_id"), ("inversiones", "inversion_padre_entidad_id"),
                     ("propiedad_valoraciones", "propiedad_entidad_id")}


def auditar(ds) -> dict:
    F = ds.filas
    prot = collections.defaultdict(list)  # entidad -> [(tabla, columna, via)]
    for t, cols in RESTRICT_ENTIDAD.items():
        for r in F.get(t, {}).values():
            for c in cols:
                if r.get(c):
                    prot[r[c]].append((t, c, "entidad"))
    for st, m in RESTRICT_SUBTIPO.items():
        for t, cols in m.items():
            for r in F.get(t, {}).values():
                for c in cols:
                    if r.get(c):
                        prot[r[c]].append((t, c, st))
    filas, resumen = [], collections.Counter()
    for e in sorted(F["entidades"].values(), key=lambda x: (x["tipo_entidad"], x["id"])):
        tipo = e["tipo_entidad"]
        ps = prot.get(e["id"], [])
        durables = sorted({(t, c) for t, c, _ in ps if t in RUNTIME_SIN_DELETE})
        if tipo not in SUBTIPO_POR_TIPO:
            clase = "INDETERMINADA"
        else:
            clase = "PROTEGIDA" if durables else "NO_PROTEGIDA"
        evadible = bool(durables) and all((t, c) in RUNTIME_UPDATE_FK for t, c in durables)
        fila = {"entidad_id": e["id"], "tipo": tipo, "nombre": e.get("nombre"),
                "financiera": tipo in POSICIONES_FINANCIERAS, "clase": clase,
                "protectores": dict(collections.Counter(t for t, _, _ in ps)),
                "protectores_durables": [f"{t}.{c}" for t, c in durables],
                "evadible_por_update": evadible}
        filas.append(fila)
        resumen[(tipo, clase, evadible)] += 1
    fin = [f for f in filas if f["financiera"]]
    bloquea = [f["entidad_id"] for f in fin if f["clase"] != "PROTEGIDA"]
    return {"entidades": len(filas), "financieras": len(fin),
            "resumen": {f"{t}|{c}|{'evadible' if ev else 'no_evadible'}": n for (t, c, ev), n in sorted(resumen.items())},
            "financieras_no_protegidas": bloquea,
            "financieras_evadibles_por_update": [f["entidad_id"] for f in fin if f["evadible_por_update"]],
            "no_financieras_no_protegidas_R_RV3_003": [f["entidad_id"] for f in filas
                                                      if not f["financiera"] and f["clase"] != "PROTEGIDA"],
            "veredicto": "BLOQUEA_CARGA" if bloquea else "SIN_BLOQUEO_POR_DELETE_DIRECTO",
            "detalle": filas}


def main(argv=None) -> int:
    import argparse
    import importlib.util
    import json
    import sys
    from pathlib import Path
    ap = argparse.ArgumentParser(description="RV3 P5b: auditoria estatica R-F04-015 sobre el dataset P5")
    ap.add_argument("--run06", required=True, type=Path)
    ap.add_argument("--decisiones-propietario", required=True, type=Path)
    ap.add_argument("--salida", required=True, type=Path)
    a = ap.parse_args(argv)
    spec = importlib.util.spec_from_file_location("rv3_p5_transformacion",
                                                  Path(__file__).resolve().parent / "rv3_p5_transformacion.py")
    P5 = importlib.util.module_from_spec(spec)
    sys.modules["rv3_p5_transformacion"] = P5
    spec.loader.exec_module(P5)
    b0 = P5.fu.cargar_b0(a.run06)
    ds = P5.transformar(b0, P5.fu.p1.sha256_fichero(a.run06), modo_lab=False,
                        decisiones=P5.cargar_decisiones(a.decisiones_propietario))
    r = auditar(ds)
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "rv3_p5b_rf04015.json").write_text(
        json.dumps({"p5_version": P5.VERSION, "hash_dataset": ds.hash(), **r}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    for k, n in r["resumen"].items():
        print(f"{n:4d}  {k}")
    print("veredicto:", r["veredicto"], "| financieras evadibles por UPDATE:", len(r["financieras_evadibles_por_update"]))
    return 0 if r["veredicto"] != "BLOQUEA_CARGA" else 1


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main())
