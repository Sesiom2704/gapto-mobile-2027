# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_02.py
# Ruta: scripts/dev/mutantes_f05_02.py
# Descripcion: Arnes de mutacion de F05-02 B1 (preferencias de registro,
#   F05-D026). Demuestra que tests/api/test_167..170 discriminan cada guarda
#   que afirman (WM 12C.2). Mismo patron que mutantes_f05_01.py (D-181,
#   D-192, D-193):
#     - cada mutante declara su transformacion (sustituciones de texto exacto,
#       cada una con UNA ocurrencia) y su discriminante (fichero o nodeid);
#     - E/S byte a byte; journal durable ANTES de tocar el primer byte, con
#       todos los ficheros que el mutante va a modificar;
#     - al arrancar, si hay journal pendiente: restaura, verifica y aborta;
#     - preflight verde de los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y verifica identidad byte-exacta;
#     - un veredicto unico por mutante: MUERTO | VIVO | NO_CLASIFICABLE.
#   Censo: PF01..PF13 (guardas exigidas por el mandato B1 §3) y PF14..PF28
#   (guardas adicionales del bloque). Sin equivalentes documentados.
#
#   v0.2.0 (F05-02 B1-C, AJ-B1-05/06): test_170 deja de comprobar el diff
#   frente a a44bb34 (pasa a verificar_cierre_f05_02_b1.py). Ningun PF moria
#   solo por esas comprobaciones: PF12 y PF28 siguen con sus garantias
#   permanentes de test_170. Nuevo PF29 (el paquete escribe una tabla de
#   terceros), discriminante: la garantia permanente acotada al paquete.
#   Censo vigente: PF01..PF29.
#   Requiere GAPTO_TEST_DATABASE_URL (base local desechable con la cadena
#   aplicada). No es evidencia de proveedor. No ejecutar en paralelo con otro
#   arnes ni con la suite sobre el mismo arbol (INC-P7-01).
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_02.journal.json"

T154 = "tests/api/test_154_f05_01_inventario_categorias.py"
T167 = "tests/api/test_167_f05_02_resolver.py"
T168 = "tests/api/test_168_f05_02_writers.py"
T169 = "tests/api/test_169_f05_02_concurrencia.py"
T170 = "tests/api/test_170_f05_02_fronteras.py"
REPO = "backend/app/preferencias/repositorio.py"
SERV = "backend/app/preferencias/servicio.py"
RES = "backend/app/preferencias/resolver.py"
LECT = "backend/app/api/lecturas_vs01.py"

CABEZA = (
    '    clave = max((especificidad(p), p["prioridad"]) for p in propias)\n'
    '    cabeza = [p for p in propias if (especificidad(p), p["prioridad"]) == clave]\n'
)
CANDIDATAS = (
    "    candidatas = [\n"
    "        p for p in repo.habilitadas(sesion) if not dimension_diferida(p) and coincide(p, contexto)\n"
    "    ]\n"
)
HERENCIA = (
    "    ancestros = {f[0] for f in sesion.conexion.execute(\n"
    '        "WITH RECURSIVE a(id, parent_id) AS (SELECT id, parent_id FROM gapto.categorias_financieras "\n'
    '        "WHERE id = %s UNION ALL SELECT c.id, c.parent_id FROM a JOIN gapto.categorias_financieras c "\n'
    '        "ON c.id = a.parent_id) SELECT id FROM a", (categoria_id,)).fetchall()}\n'
    "    candidatas = [\n"
    "        p for p in repo.habilitadas(sesion) if not dimension_diferida(p) and (coincide(p, contexto) or (\n"
    '            p["categoria_id"] in ancestros and p["tipo_hecho_id"] in (None, tipo_hecho_id)))\n'
    "    ]\n"
)
PRES = (
    "    presupuestable = None\n"
    '    g = ganadora(candidatas, CAMPOS["presupuestable"])\n'
    "    if isinstance(g, dict):\n"
)
EMPATE_REACTIVAR = (
    "    rechazo = _empate(sesion, fila, preferencia_id)\n"
    "    if rechazo is not None:\n"
    "        return rechazo\n"
)

MUTANTES = [
    # --- guardas exigidas por el mandato B1 §3
    ("PF01", "writers sin advisory (PREFERENCIAS, owner)",
     [(REPO, '    sesion.uno(\n        "SELECT pg_advisory_xact_lock(hashtext(\'gapto:PREFERENCIAS\'), "\n'
             '        "hashtext(current_setting(\'gapto.owner_user_id\')::uuid::text))"\n    )\n',
       "    return None\n")],
     [T169]),
    ("PF02", "sin chequeo de empate",
     [(SERV, "    for q in repo.habilitadas(sesion):\n        if q[\"id\"] == propia",
       "    for q in []:\n        if q[\"id\"] == propia")],
     [T168]),
    ("PF03", "empate solo por clave identica (ignora comodines)",
     [(RES, "    return all(p[d] is None or q[d] is None or p[d] == q[d] for d in DIMENSIONES)",
       "    return all(p[d] == q[d] for d in DIMENSIONES)")],
     [f"{T168}::test_empate_por_comodines"]),
    ("PF04", "acepta tercero/entidad al escribir",
     [(SERV, "    if dimension_diferida(v):\n        return Rechazo(DIMENSION_DIFERIDA)\n", "")],
     [T168]),
    ("PF05", "acepta prioridad distinta de 100",
     [(SERV, "    if v[\"prioridad\"] != PRIORIDAD_V1:\n        return Rechazo(PRIORIDAD_NO_ADMITIDA)\n", "")],
     [T168]),
    ("PF06", "sin control de row_version",
     [(SERV, "    if fila[\"row_version\"] != row_version:\n        return Rechazo(VERSION_DESFASADA)\n", "")],
     [T168]),
    ("PF07", "resolver sin filtro de elegibilidad de la cuenta",
     [(RES, '    if isinstance(g, dict) and g["cuenta_default_id"] in elegibles:',
       "    if isinstance(g, dict):")],
     [T167]),
    ("PF08", "resolver que desciende a la siguiente preferencia si la ganadora no es elegible",
     [(RES, '    g = ganadora(candidatas, CAMPOS["cuenta"])',
       '    g = ganadora([p for p in candidatas if p["cuenta_default_id"] in elegibles], CAMPOS["cuenta"])')],
     [f"{T167}::test_no_elegible_no_desciende_a_la_siguiente_preferencia"]),
    ("PF09", "resolver que ignora la especificidad",
     [(RES, CABEZA, CABEZA.replace("especificidad(p)", "0"))],
     [T167]),
    ("PF10", "resolver con herencia de ancestros de la categoria",
     [(RES, CANDIDATAS, HERENCIA)],
     [f"{T167}::test_categoria_exacta_sin_herencia_de_ancestros"]),
    ("PF11", "resolucion conjunta: un mismo ganador para los dos campos",
     [(RES, PRES, PRES.replace('CAMPOS["presupuestable"]', 'CAMPOS["cuenta"]').replace(
         "    if isinstance(g, dict):\n", '    if isinstance(g, dict) and g["presupuestable_default"] is not None:\n'))],
     [f"{T167}::test_independencia_por_campo"]),
    ("PF12", "resolver que consume filas con tercero_id/entidad_id",
     [(RES, "if not dimension_diferida(p) and coincide(p, contexto)", "if coincide(p, contexto)")],
     [T170]),
    ("PF13", "fallback de cuenta con varias elegibles",
     [(RES, "    elif g != CONTRADICTORIA and len(elegibles) == 1:",
       "    elif g != CONTRADICTORIA and len(elegibles) >= 1:")],
     [T167]),
    # --- guardas adicionales del bloque
    ("PF14", "cabeza contradictoria cae al fallback de cuenta unica",
     [(RES, "    elif g != CONTRADICTORIA and len(elegibles) == 1:", "    elif len(elegibles) == 1:")],
     [f"{T167}::test_cabeza_contradictoria_sin_propuesta_ni_fallback"]),
    ("PF15", "cabeza contradictoria: eleccion arbitraria",
     [(RES, "    if len({p[columna] for p in cabeza}) != 1:\n        return CONTRADICTORIA\n", "")],
     [T167]),
    ("PF16", "prioridad: gana el menor valor",
     [(RES, CABEZA, CABEZA.replace('p["prioridad"]', '-p["prioridad"]'))],
     [f"{T167}::test_mayor_valor_de_prioridad_gana"]),
    ("PF17", "writer sin elegibilidad de la categoria",
     [(SERV, '    if v["categoria_id"] is not None and not _categoria_elegible(sesion, v["categoria_id"]):\n'
             "        return Rechazo(CATEGORIA_NO_ELEGIBLE)\n", "")],
     [T168]),
    ("PF18", "writer sin elegibilidad de la cuenta",
     [(SERV, '    if v["cuenta_default_id"] is not None and v["cuenta_default_id"] not in cuentas_elegibles_registro(',
       '    if False and v["cuenta_default_id"] not in cuentas_elegibles_registro(')],
     [T168]),
    ("PF19", "elegibilidad sin la misma moneda del registro (D1)",
     [(RES, "    return [f[0] for f in cuentas_elegibles(sesion, fecha) if f[2] == MONEDA_REGISTRO]",
       "    return [f[0] for f in cuentas_elegibles(sesion, fecha)]")],
     [T167]),
    ("PF20", "alta sin auditoria",
     [(SERV, '    _auditar(sesion, preferencia_id, "ALTA", None)\n', "")],
     [T168]),
    ("PF21", "edicion sin chequeo de empate",
     [(SERV, '    if fila["enabled"]:\n        # prioridad no es editable', '    if False:\n        # prioridad no es editable')],
     [f"{T168}::test_editar_que_crea_empate_se_rechaza"]),
    ("PF22", "reactivacion sin chequeo de empate",
     [(SERV, EMPATE_REACTIVAR, "")],
     [f"{T168}::test_reactivacion_que_crea_empate_se_rechaza"]),
    ("PF23", "el empate no excluye la propia preferencia",
     [(SERV, '        if q["id"] == propia or dimension_diferida(q):', "        if dimension_diferida(q):")],
     [f"{T168}::test_editar_la_propia_no_choca_consigo_misma"]),
    ("PF24", "contexto «Sin categoria» casa con cualquier categoria",
     [(RES, "    return all(p[d] is None or p[d] == contexto[d] for d in DIMENSIONES)",
       "    return all(p[d] is None or contexto[d] is None or p[d] == contexto[d] for d in DIMENSIONES)")],
     [f"{T167}::test_sin_categoria_solo_coinciden_preferencias_de_categoria_nula"]),
    ("PF25", "extraccion de cuentas_pago que cambia la regla (sin ACTIVO)",
     [(LECT, "            \"AND naturaleza = 'ACTIVO' ORDER BY orden, nombre, id\",\n",
       '            "ORDER BY orden, nombre, id",\n')],
     [f"{T167}::test_regresion_cuentas_pago_tras_la_extraccion"]),
    ("PF26", "el resolver y el empate consideran las desactivadas",
     [(REPO, '        cur.execute(_SELECT + " AND enabled ORDER BY id")', '        cur.execute(_SELECT + " ORDER BY id")')],
     [f"{T167}::test_desactivada_se_ignora"]),
    ("PF27", "CHECK fisico sin traduccion por identidad",
     [(SERV, '    "ck_preferencias_registro__propone_valor": SIN_VALOR,\n', "")],
     [f"{T168}::test_check_fisico_propone_valor_mapeado_por_identidad"]),
    ("PF28", "editar admite cambiar la prioridad persistida",
     [(REPO, '    "tipo_hecho_id", "categoria_id", "cuenta_default_id", "presupuestable_default", "enabled",\n',
       '    "tipo_hecho_id", "categoria_id", "cuenta_default_id", "presupuestable_default", "enabled", "prioridad",\n')],
     [f"{T170}::test_el_writer_no_escribe_dimensiones_diferidas_ni_prioridad"]),
    ("PF29", "el paquete de preferencias escribe una tabla de terceros",
     [(SERV, '    return sesion.uno("SELECT current_date")[0]\n',
       '    sesion.uno("UPDATE gapto.terceros SET nombre = nombre WHERE false")\n'
       '    return sesion.uno("SELECT current_date")[0]\n')],
     [f"{T170}::test_el_paquete_de_preferencias_no_escribe_terceros_ni_otras_tablas"]),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    cmd = [sys.executable, "-m", "pytest", *tests, "-q", "-x", "-p", "no:cacheprovider", "--rootdir=tests/api"]
    return subprocess.run(cmd, cwd=RAIZ, capture_output=True).returncode


def recuperar_si_pendiente() -> bool:
    if not JOURNAL.exists():
        return False
    j = json.loads(JOURNAL.read_text(encoding="utf-8"))
    for f in j["ficheros"]:
        ruta = RAIZ / f["fichero"]
        ruta.write_bytes(bytes.fromhex(f["original_hex"]))
        if sha(ruta.read_bytes()) != f["sha256"]:
            sys.exit(f"RECUPERACION FALLIDA: identidad no verificada en {f['fichero']}")
    JOURNAL.unlink()
    return True


def main() -> None:
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    if correr([T154, T167, T168, T169, T170]) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    veredictos = []
    for mid, desc, cambios, tests in MUTANTES:
        ficheros = sorted({c[0] for c in cambios})
        originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
        textos = {f: b.decode("utf-8") for f, b in originales.items()}
        aplicable = True
        for f, a, b in cambios:
            if textos[f].count(a) != 1:
                aplicable = False
                break
            textos[f] = textos[f].replace(a, b)
        if not aplicable:
            veredictos.append((mid, "NO_CLASIFICABLE", "transformacion no aplicable", desc))
            continue
        JOURNAL.write_text(
            json.dumps({"mutante": mid, "ficheros": [
                {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros
            ]}),
            encoding="utf-8",
        )
        if hasattr(os, "sync"):
            os.sync()
        v = "NO_CLASIFICABLE"
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            v = "MUERTO" if correr(tests) != 0 else "VIVO"
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        veredictos.append((mid, v if ok else "NO_CLASIFICABLE", ",".join(pathlib.Path(t).name for t in tests), desc))
    for v in veredictos:
        print(*v, sep=" | ")
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    print(f"RESUMEN {muertos} / {len(veredictos)} muertos")
    sys.exit(0 if muertos == len(veredictos) else 1)


if __name__ == "__main__":
    main()
