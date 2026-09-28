# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_01.py
# Ruta: scripts/dev/mutantes_f05_01.py
# Descripcion: Arnes de mutacion de F05-01 backend (S1 guarda, S2 inventario,
#   S3 lecturas). Demuestra que tests/api/test_152..154 discriminan los
#   mecanismos que afirman (WM 12C.2). Cumple D-181/D-192:
#     - cada mutante declara su transformacion (lista de sustituciones de
#       texto exacto, cada una con UNA ocurrencia) y su discriminante (tests);
#     - E/S byte a byte; journal durable ANTES de tocar el primer byte, con
#       todos los ficheros que el mutante va a modificar;
#     - al arrancar, si hay journal pendiente: restaura, verifica y aborta;
#     - preflight verde de los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y verifica identidad byte-exacta;
#     - un veredicto unico por mutante: MUERTO | VIVO | NO_CLASIFICABLE.
#   Mutantes equivalentes documentados (no cuentan en el gate, WM 12C.5):
#     E01 sin comprobacion explicita de owner en la guarda: bajo gapto_runtime
#         la RLS ya oculta la fila ajena; es defensa en profundidad.
#   Requiere GAPTO_TEST_DATABASE_URL (base local desechable 0001..0340).
#   No es evidencia de proveedor.
#
#   v0.2.0 (F05-01, S4/S5): mutantes S01..S18 de la gestion del arbol
#   (advisory global y por comando, normalizacion, NULL-safe, RAMA sobre
#   todo el subarbol, row_version, confirmacion de ambito, cadena de
#   ancestros, idempotencia del alta, traduccion fisica por identidad y
#   matriz de auditoria), mas los discriminantes test_155..157.
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
JOURNAL = RAIZ / ".mutantes_f05_01.journal.json"

T152 = "tests/api/test_152_f05_01_elegibilidad_categoria.py"
T153 = "tests/api/test_153_f05_01_lecturas_categorias.py"
T154 = "tests/api/test_154_f05_01_inventario_categorias.py"
T155 = "tests/api/test_155_f05_01_gestion_categorias.py"
T156 = "tests/api/test_156_f05_01_concurrencia_catalogo.py"
T157 = "tests/api/test_157_f05_01_bolsa_intensional.py"
SERV = "backend/app/categorias/servicio.py"
REPO = "backend/app/categorias/repositorio.py"
NORM = "backend/app/categorias/normalizacion.py"
ELEG = "backend/app/api/elegibilidad_categoria.py"
EJEC = "backend/app/api/ejecucion_gasto_pagado.py"
DTO = "backend/app/api/dto_vs01.py"
TRAD = "backend/app/api/traductor_gasto_pagado.py"
LECT = "backend/app/categorias/lecturas.py"
ANCLA_LECT = "from app.core.unidad_trabajo import SesionMotor\n"

GUARDA_EN_RAMA = (
    "            # 3b. Guarda categorial C-a, solo para seleccion nueva explicita.\n"
    "            if intencion.categoria_id is not None:\n"
    "                rechazo = validar_seleccion_categoria(sesion, intencion.categoria_id, \"GASTO\")\n"
    "                if rechazo is not None:\n"
    "                    return RechazoIntegracion(rechazo)\n"
)
GUARDA_ANTES_IDENTIDAD = (
    "        if intencion.categoria_id is not None:\n"
    "            rechazo = validar_seleccion_categoria(sesion, intencion.categoria_id, \"GASTO\")\n"
    "            if rechazo is not None:\n"
    "                return RechazoIntegracion(rechazo)\n"
)

# (id, descripcion, [(fichero, original, mutado)], [tests discriminantes])
MUTANTES = [
    ("C01", "guarda sin FOR SHARE", [(ELEG, '"WHERE id = %s FOR SHARE",', '"WHERE id = %s",')], [T152]),
    ("C02", "AMBOS = cualquier naturaleza",
     [(ELEG, "    if not AMBITOS_ADMITIDOS.get(tipo_efecto):\n        # Naturaleza sin semantica categorial: ni siquiera se lee la fila.\n        return CODIGO_CATEGORIA_NO_ELEGIBLE\n", ""),
      (ELEG, "    return ambito in AMBITOS_ADMITIDOS.get(tipo_efecto, frozenset())",
       '    return ambito == "AMBOS" or ambito in AMBITOS_ADMITIDOS.get(tipo_efecto, frozenset())')], [T152]),
    ("C03", "sin comprobar enabled", [(ELEG, "    if not fila[1]:\n        return CODIGO_CATEGORIA_NO_ELEGIBLE\n", "")], [T152]),
    ("C04", "sin comprobar ambito",
     [(ELEG, "    if not ambito_compatible(tipo_efecto, fila[2]):\n        return CODIGO_CATEGORIA_NO_ELEGIBLE\n", "")], [T152]),
    ("C05", "guarda antes del reconocimiento de identidad",
     [(EJEC, GUARDA_EN_RAMA, ""),
      (EJEC, "        if not ya_materializada:\n", GUARDA_ANTES_IDENTIDAD + "        if not ya_materializada:\n")],
     [T152, T154]),
    ("C06", "guarda no invocada", [(EJEC, "                if rechazo is not None:\n                    return RechazoIntegracion(rechazo)\n", "")], [T152]),
    ("C07", "sin bloqueo transitorio de magnitudes obligatorias",
     [(ELEG, "    if requiere is not None and requiere[0]:\n", "    if False:\n")], [T152]),
    ("C08", "null explicito aceptado como legacy",
     [(DTO, '        if isinstance(datos, dict) and "categoria" in datos and datos["categoria"] is None:\n',
       "        if False:\n")], [T152]),
    ("C09", "el traductor no sella la categoria",
     [(TRAD, '            estado_atribucion="COMPLETA",\n            categoria_id=intencion.categoria_id,\n',
       '            estado_atribucion="COMPLETA",\n')], [T152]),
    ("C10", "DELETE runtime de categorias_financieras",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "\n\ndef _borrar(sesion, i):\n    sesion.uno(\"DELETE FROM gapto.categorias_financieras WHERE id = %s\", (i,))\n")],
     [T154]),
    ("C11", "segundo llamador de componer sin guarda",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "from app.api.traductor_gasto_pagado import componer\n\n\ndef _atajo(i, a):\n    return componer(i, a)\n")],
     [T154]),
    ("C12", "SQL con tabla dinamica fuera de lista blanca",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "\n\ndef _dinamica(sesion, t):\n    sesion.uno(f\"UPDATE gapto.{t} SET enabled = false\")\n")],
     [T154]),
    ("C13", "la frontera alcanza OP-04 sin OP-22",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "from app.services.efectos_service import EfectosService  # noqa: F401\n")],
     [T154]),
    ("C14", "consumidor de categoria_id sin clasificar",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "\n\ndef _nuevo(sesion, categoria_id):\n    return categoria_id\n")],
     [T154]),
    ("C15", "literal de tabla troceado",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "\n_T = \"categorias_\" + \"financieras\"\n")], [T154]),
    ("C16", "el arbol filtra deshabilitadas",
     [(LECT, "\"WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid \"\n            \"ORDER BY",
       "\"WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid AND enabled \"\n            \"ORDER BY")],
     [T153]),
    ("C17", "el uso cuenta hechos anulados",
     [(LECT, "WHERE e.categoria_id = %s AND h.estado = 'ACTIVO' ", "WHERE e.categoria_id = %s ")], [T153]),
    # ---------------------------------------------------------------- S4 / S5
    ("S01", "advisory vaciado (ningun comando serializa)",
     [(REPO, '    sesion.uno(\n        "SELECT pg_advisory_xact_lock(', '    return None\n    sesion.uno(\n        "SELECT pg_advisory_xact_lock(')],
     [T156]),
    ("S02", "mover sin advisory", [(SERV, "def mover(sesion: SesionMotor, *, categoria_id, parent_id, row_version: int) -> Resultado | Rechazo:\n    repo.tomar_advisory(sesion)\n",
                                    "def mover(sesion: SesionMotor, *, categoria_id, parent_id, row_version: int) -> Resultado | Rechazo:\n")], [T154, T156]),
    ("S03", "desactivar sin advisory", [(SERV, "def desactivar(sesion: SesionMotor, *, categoria_id, modo: str, row_version: int) -> Resultado | Rechazo:\n    repo.tomar_advisory(sesion)\n",
                                         "def desactivar(sesion: SesionMotor, *, categoria_id, modo: str, row_version: int) -> Resultado | Rechazo:\n")], [T154, T156]),
    ("S04", "orden sin advisory", [(SERV, "def ordenar(sesion: SesionMotor, *, categoria_id, orden: int, row_version: int) -> Resultado | Rechazo:\n    repo.tomar_advisory(sesion)\n",
                                    "def ordenar(sesion: SesionMotor, *, categoria_id, orden: int, row_version: int) -> Resultado | Rechazo:\n")], [T154, T156]),
    ("S05", "ambito sin advisory", [(SERV, "                   row_version: int) -> Resultado | Rechazo:\n    repo.tomar_advisory(sesion)\n",
                                     "                   row_version: int) -> Resultado | Rechazo:\n")], [T154, T156]),
    ("S06", "normalizacion sin casefold", [(NORM, "    texto = nombre_visible(nombre).casefold()\n", "    texto = nombre_visible(nombre)\n")], [T155]),
    ("S07", "normalizacion sin quitar diacriticos", [(NORM, 'if unicodedata.category(c) != "Mn"', "if True")], [T155]),
    ("S08", "hermanos con = en vez de IS NOT DISTINCT FROM", [(REPO, "AND parent_id IS NOT DISTINCT FROM %s AND enabled ", "AND parent_id = %s AND enabled ")], [T155]),
    ("S09", "UNIQUE fisica como unica defensa", [(SERV, "    return any(normalizar(n) == clave for _, n in repo.hermanos_activos(sesion, parent_id, excluir))", "    return False")], [T155]),
    ("S10", "RAMA recorre solo nodos habilitados (no atraviesa intermedios deshabilitados)",
     [(REPO, '" SELECT id FROM gapto.categorias_financieras WHERE parent_id = %s"',
       '" SELECT id FROM gapto.categorias_financieras WHERE parent_id = %s AND enabled"'),
      (REPO, '" SELECT c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id = d.id"',
       '" SELECT c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id = d.id AND c.enabled"')], [T155]),
    ("S10b", "RAMA no atraviesa intermedios deshabilitados de nivel >= 2",
     [(REPO, '" SELECT c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id = d.id"',
       '" SELECT c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id = d.id AND c.enabled"')], [T155]),
    ("S11", "sin control de row_version", [(SERV, '    if fila["row_version"] != row_version:\n', "    if False:\n")], [T155]),
    ("S12", "ambito sin confirmacion del uso", [(SERV, "    if dict(confirmacion_uso) != vigente:\n", "    if False:\n")], [T155]),
    ("S13", "solo el padre inmediato, no la cadena de ancestros",
     [(SERV, "    return all(enabled for _, enabled in repo.cadena_ancestros(sesion, parent_id))", "    return repo.cadena_ancestros(sesion, parent_id)[0][1]")], [T155]),
    ("S14", "alta idempotente aunque haya evolucionado", [(SERV, '            existente["row_version"] == 1 and existente["nombre"] == visible', '            existente["nombre"] == visible')], [T155]),
    ("S15", "traduccion por texto libre del error", [(SERV, "            if funcion in diag.context:\n                return codigo\n", "            if funcion in diag.context:\n                return diag.message_primary\n")], [T155]),
    ("S16", "DESACTIVAR auditado con otro motivo valido", [(SERV, 'operacion = "DESACTIVAR_RAMA" if modo == "RAMA" else "DESACTIVAR"', 'operacion = "DESACTIVAR_RAMA" if modo == "RAMA" else "REACTIVAR"')], [T155]),
    ("S17", "DESACTIVAR_RAMA auditado como DESACTIVAR", [(SERV, 'operacion = "DESACTIVAR_RAMA" if modo == "RAMA" else "DESACTIVAR"', 'operacion = "DESACTIVAR"')], [T155]),
    ("S18", "RAMA sin auditar descendientes", [(SERV, "        _auditar(sesion, cid, operacion, antes)\n", "        if cid == categoria_id:\n            _auditar(sesion, cid, operacion, antes)\n")], [T155]),
    ("S19", "request_id distinto por nodo en RAMA",
     [(SERV, "        _auditar(sesion, cid, operacion, antes)\n", "        sesion.uno(\"SELECT set_config('gapto.request_id', gen_random_uuid()::text, true)\")\n        _auditar(sesion, cid, operacion, antes)\n")], [T155]),
    ("S20", "accion fisica incorrecta", [(SERV, "auditoria.ACCION_CREAR if operacion == \"ALTA\" else auditoria.ACCION_ACTUALIZAR", "auditoria.ACCION_CREAR if operacion == \"ALTA\" else \"ANULAR\"")], [T155]),
    ("S21", "reactivacion en cascada",
     [(SERV, '    rechazo = _escribir(sesion, lambda: repo.actualizar(sesion, categoria_id, {"enabled": True}))\n',
       '    rechazo = _escribir(sesion, lambda: [repo.actualizar(sesion, i, {"enabled": True}) for i in [categoria_id] + repo.subarbol(sesion, categoria_id)])\n')], [T155]),
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
    if correr([T152, T153, T154, T155, T156, T157]) != 0:
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
        veredictos.append((mid, v if ok else "NO_CLASIFICABLE", ",".join(pathlib.Path(t).stem for t in tests), desc))
    for v in veredictos:
        print(*v, sep=" | ")
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    print(f"RESUMEN {muertos} / {len(veredictos)} muertos")
    sys.exit(0 if muertos == len(veredictos) else 1)


if __name__ == "__main__":
    main()
