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
#
#   v0.3.0 (F05-03/F05-04 J2 §1.5; F05 §46.4 R6, §46.5 E2/E3; F05-D032 C4;
#   decision OPCION A2 del STOP 2): textos protegidos actualizados al
#   resolver/writer v0.2.0 (CANDIDATAS, HERENCIA, PF23, PF28). Reapuntados:
#   PF04 «acepta entidad al escribir» (entidad_id es la unica dimension
#   diferida), PF12 «resolver que consume filas con entidad_id» y PF24 (su
#   discriminante usa «Todos los gastos»). Nuevos PF30..PF38: writer sin
#   PREFERENCIA_SIN_TIPO, sin PREFERENCIA_AMBITO_NO_ADMITIDO, sin
#   elegibilidad del tercero; resolver que consume filas sin tipo o que no
#   usa el tercero; reactivacion de filas sin tipo; conversion C4 sin
#   advisory, que toca filas con tipo o sin auditoria. Preflight con test_173.
#   El «29/29» de §1.5 pasa a ser el conteo vigente PF01..PF38.
#
#   v0.4.0 (F05-03/F05-04 J2 §1.1; F05-D031 E1/A10, F05 §46.4 R1, F05-D032
#   C1; decision OPCION A del STOP 1): PF25 se reescribe sobre la guarda de
#   capacidad del contrato unico (comun/elegibilidad_cuentas.py): la linea
#   protegida `naturaleza = 'ACTIVO'` ya no existe; mismo discriminante
#   (regresion de cuentas_pago, ahora con oraculo R1). PF19 pasa a la guarda
#   MONEDA de la regla unica: el filtro EUR del resolver queda como defensa
#   redundante (un mutante sobre el seria equivalente).
# Version: 0.4.0
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
T173 = "tests/api/test_173_f05_03_conversion_preferencias.py"
REPO = "backend/app/preferencias/repositorio.py"
SERV = "backend/app/preferencias/servicio.py"
RES = "backend/app/preferencias/resolver.py"
ELEG = "backend/app/comun/elegibilidad_cuentas.py"

CABEZA = (
    '    clave = max((especificidad(p), p["prioridad"]) for p in propias)\n'
    '    cabeza = [p for p in propias if (especificidad(p), p["prioridad"]) == clave]\n'
)
CANDIDATAS = (
    "    candidatas = [p for p in repo.habilitadas(sesion) if consumible(p) and coincide(p, contexto)]\n"
)
HERENCIA = (
    "    ancestros = {f[0] for f in sesion.conexion.execute(\n"
    '        "WITH RECURSIVE a(id, parent_id) AS (SELECT id, parent_id FROM gapto.categorias_financieras "\n'
    '        "WHERE id = %s UNION ALL SELECT c.id, c.parent_id FROM a JOIN gapto.categorias_financieras c "\n'
    '        "ON c.id = a.parent_id) SELECT id FROM a", (categoria_id,)).fetchall()}\n'
    "    candidatas = [\n"
    "        p for p in repo.habilitadas(sesion) if consumible(p) and (coincide(p, contexto) or (\n"
    '            p["categoria_id"] in ancestros and p["tipo_hecho_id"] == tipo_hecho_id))\n'
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
    ("PF04", "acepta entidad al escribir (dimension diferida vigente)",
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
    ("PF12", "resolver que consume filas con entidad_id",
     [(RES, "    return not dimension_diferida(p) and not sin_tipo(p)", "    return not sin_tipo(p)")],
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
    ("PF19", "elegibilidad sin la misma moneda del registro (D1; guarda MONEDA de la regla unica R1)",
     [(ELEG, "    if moneda != MONEDA_REGISTRO:\n        return MONEDA\n", "")],
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
     [(SERV, '        if q["id"] == propia or not consumible(q):', "        if not consumible(q):")],
     [f"{T168}::test_editar_la_propia_no_choca_consigo_misma"]),
    ("PF24", "contexto «Sin categoria» casa con cualquier categoria (sobre «Todos los gastos»)",
     [(RES, "    return all(p[d] is None or p[d] == contexto[d] for d in DIMENSIONES)",
       "    return all(p[d] is None or contexto[d] is None or p[d] == contexto[d] for d in DIMENSIONES)")],
     [f"{T167}::test_sin_categoria_solo_coinciden_preferencias_de_categoria_nula"]),
    ("PF25", "regla de cuentas sin la guarda de capacidad (R1/C1)",
     [(ELEG, "    if not capacidad:\n        return SIN_CAPACIDAD\n", "")],
     [f"{T167}::test_regresion_cuentas_pago_tras_la_extraccion"]),
    ("PF26", "el resolver y el empate consideran las desactivadas",
     [(REPO, '        cur.execute(_SELECT + " AND enabled ORDER BY id")', '        cur.execute(_SELECT + " ORDER BY id")')],
     [f"{T167}::test_desactivada_se_ignora"]),
    ("PF27", "CHECK fisico sin traduccion por identidad",
     [(SERV, '    "ck_preferencias_registro__propone_valor": SIN_VALOR,\n', "")],
     [f"{T168}::test_check_fisico_propone_valor_mapeado_por_identidad"]),
    ("PF28", "editar admite cambiar la prioridad persistida",
     [(REPO, '    "tipo_hecho_id", "categoria_id", "tercero_id", "cuenta_default_id", "presupuestable_default", "enabled",\n',
       '    "tipo_hecho_id", "categoria_id", "tercero_id", "cuenta_default_id", "presupuestable_default", "enabled",'
       ' "prioridad",\n')],
     [f"{T170}::test_el_writer_no_escribe_dimensiones_diferidas_ni_prioridad"]),
    ("PF29", "el paquete de preferencias escribe una tabla de terceros",
     [(SERV, '    return sesion.uno("SELECT current_date")[0]\n',
       '    sesion.uno("UPDATE gapto.terceros SET nombre = nombre WHERE false")\n'
       '    return sesion.uno("SELECT current_date")[0]\n')],
     [f"{T170}::test_el_paquete_de_preferencias_no_escribe_terceros_ni_otras_tablas"]),
    # --- F05-03/F05-04 J2 §1.5 (R6, E2/E3, C4)
    ("PF30", "writer admite preferencias sin tipo (E3)",
     [(SERV, '    if v["tipo_hecho_id"] is None:\n        return Rechazo(SIN_TIPO)\n', "")],
     [f"{T168}::test_alta_sin_tipo_rechazada"]),
    ("PF31", "writer admite categoria + tercero (R6)",
     [(SERV, '    if v["categoria_id"] is not None and v["tercero_id"] is not None:\n'
             "        return Rechazo(AMBITO_NO_ADMITIDO)\n", "")],
     [f"{T168}::test_dimension_diferida_en_alta"]),
    ("PF32", "resolver que consume filas sin tipo (E3)",
     [(RES, "    return not dimension_diferida(p) and not sin_tipo(p)", "    return not dimension_diferida(p)")],
     [f"{T167}::test_fila_sin_tipo_se_ignora"]),
    ("PF33", "resolver sin la dimension tercero (E2)",
     [(RES, 'DIMENSIONES = ("tipo_hecho_id", "categoria_id", "tercero_id")',
       'DIMENSIONES = ("tipo_hecho_id", "categoria_id")')],
     [f"{T167}::test_tipo_mas_tercero_solo_coincide_con_ese_tercero"]),
    ("PF34", "writer sin elegibilidad del tercero",
     [(SERV, '    if v["tercero_id"] is not None and not _tercero_elegible(sesion, v["tercero_id"]):\n'
             "        return Rechazo(TERCERO_NO_ELEGIBLE)\n", "")],
     [f"{T168}::test_tercero_no_elegible"]),
    ("PF35", "reactivacion de una fila sin tipo",
     [(SERV, "    if sin_tipo(fila):\n        return Rechazo(SIN_TIPO)\n", "")],
     [f"{T168}::test_reactivar_fila_con_dimension_diferida_se_rechaza"]),
    ("PF36", "conversion C4 sin advisory",
     [(SERV, "    repo.tomar_advisory(sesion)\n    filas = repo.sin_tipo_bloqueadas(sesion)\n",
       "    filas = repo.sin_tipo_bloqueadas(sesion)\n")],
     [f"{T173}::test_la_conversion_espera_el_advisory"]),
    ("PF37", "conversion C4 que toca filas con tipo",
     [(REPO, '        cur.execute(_SELECT + " AND tipo_hecho_id IS NULL ORDER BY id FOR NO KEY UPDATE")',
       '        cur.execute(_SELECT + " ORDER BY id FOR NO KEY UPDATE")')],
     [f"{T173}::test_convierte_todas_las_filas_sin_tipo_y_audita"]),
    ("PF38", "conversion C4 sin auditoria por fila",
     [(SERV, '        _auditar(sesion, f["id"], "CONVERTIR_SIN_TIPO", antes)\n', "")],
     [f"{T173}::test_convierte_todas_las_filas_sin_tipo_y_audita"]),
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
    if correr([T154, T167, T168, T169, T170, T173]) != 0:
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
