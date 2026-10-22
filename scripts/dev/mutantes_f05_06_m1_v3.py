# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_06_m1_v3.py
# Ruta: scripts/dev/mutantes_f05_06_m1_v3.py
# Descripcion: Arnes de mutacion de F05-06 M1 v1.1 · «Corregir categoria» de
#   V3 (Q9 opcion (a); lista blanca {categoria_id}; 100 % muertos o
#   equivalentes documentados). Mismo motor que mutantes_f05_06_m1.py
#   (journal durable, preflight verde, restauracion verificada por SHA-256,
#   veredicto a disco en cuanto se conoce). Guardas: lista blanca (constante,
#   diccionario hacia OP-21 y DTO estricto), motivo del usuario hasta el
#   motor y su texto, forma de V3 (importado, ACTIVO, un efecto), naturaleza
#   del efecto en C-a, C-a + C07 en el servidor, identidad de la intencion
#   (idempotente y reutilizada) y, en la UI, accion solo si el servidor la
#   trae, categoria distinta y motivo obligatorios, misma intencion tras un
#   fallo y payload de la lista blanca.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable>
#        python scripts/dev/mutantes_f05_06_m1_v3.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-06 M1 v1.1)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_06_m1_v3.journal.json"

DTO = "backend/app/api/dto_edicion.py"
EJV = "backend/app/api/ejecucion_categoria_v3.py"
EH = "backend/app/api/errores_http.py"
EDI = "backend/app/actividad/edicion.py"
COMP = "mobile/src/components/EdicionHecho.tsx"
DOMM = "mobile/src/domain/edicion.ts"
ACT = "mobile/src/screens/ActividadScreen.tsx"
T210 = "tests/api/test_210_f05_06_m1_categoria_v3.py::"
T154 = "tests/api/test_154_f05_01_inventario_categorias.py::"
JEST = "jest:__tests__/edicion_hecho.test.tsx::"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("V01", "lista blanca: la constante admite tambien la descripcion",
     [(EJV, 'CAMPOS_V3_CORREGIBLES = frozenset({"categoria_id"})\n',
       'CAMPOS_V3_CORREGIBLES = frozenset({"categoria_id", "descripcion"})\n')],
     [T154 + "test_i3_v3_excepcion_acotada_a_la_categoria"], None),
    ("V02", "lista blanca: otro campo de efecto viaja a OP-21 junto a la categoria",
     [(EJV, '    cambios = {"categoria_id": intencion.categoria_id}\n',
       '    cambios = {"categoria_id": intencion.categoria_id, "descripcion": "x"}\n')],
     [T210 + "test_corregir_categoria_v3_solo_cambia_la_categoria"], None),
    ("V03", "DTO: la intencion de V3 ignora los campos ajenos en vez de rechazarlos",
     [(DTO, "class IntencionCorregirCategoriaV3(_Estricto):\n", "class IntencionCorregirCategoriaV3(BaseModel):\n")],
     [T210 + "test_corregir_categoria_campo_fuera_de_la_lista_blanca"], None),
    ("V04", "motivo: el adaptador pone un motivo propio en lugar del del usuario",
     [(EJV, "                                motivo=intencion.motivo, efectos_a_actualizar=",
       "                                motivo=\"Correccion de categoria V3\", efectos_a_actualizar=")],
     [T210 + "test_corregir_categoria_sin_motivo"], None),
    ("V05", "texto: el rechazo de V3 no dice el motivo concreto",
     [(EH, "f\"{MOTIVOS_EDICION[detalle['motivo']]} No se ha cambiado nada.\"", "\"No se ha cambiado nada.\"")],
     [T210 + "test_corregir_categoria_no_v3_rechazada_en_servidor"], None),
    ("V06", "forma: un registro no importado se corrige por la via de V3",
     [(EDI, "    if not repo.importado(sesion, [(\"hechos_financieros\", hecho_id)]):\n        return \"NO_IMPORTADO\", None\n", "")],
     [T210 + "test_corregir_categoria_no_v3_rechazada_en_servidor"], None),
    ("V07", "forma: un V3 anulado se ofrece y se intenta corregir",
     [(EDI, "    if hecho[\"estado\"] != \"ACTIVO\":\n        return \"HECHO_ANULADO\", None\n    if hecho[\"tipo\"] not in (\"GASTO\", \"INGRESO\"):\n        return \"TIPO_NO_SOPORTADO\", None\n",
       "    if hecho[\"tipo\"] not in (\"GASTO\", \"INGRESO\"):\n        return \"TIPO_NO_SOPORTADO\", None\n")],
     [T210 + "test_corregir_categoria_v3_anulado_rechazado"], None),
    ("V08", "forma: con varios efectos se corrige el primero",
     [(EDI, "    if len(efectos) != 1:\n        return \"VARIOS_EFECTOS\", None\n", "    if not efectos:\n        return \"VARIOS_EFECTOS\", None\n")],
     [T210 + "test_edicion_v3_varios_efectos_atenuado"], None),
    ("V09", "C-a: la naturaleza del efecto se ignora (siempre GASTO)",
     [(EJV, "intencion.categoria_id, efecto[\"naturaleza\"],", "intencion.categoria_id, \"GASTO\",")],
     [T210 + "test_corregir_categoria_v3_ingreso"], None),
    ("V10", "C-a + C07: el rechazo de la categoria no detiene la correccion",
     [(EJV, "        if rechazo is not None:\n            return RechazoRegistro(rechazo)\n", "")],
     [T210 + "test_corregir_categoria_no_elegible", T210 + "test_corregir_categoria_c07_obligatoria_que_el_hecho_no_tiene"], None),
    ("V11", "C07: no se juzgan las magnitudes (todas declaradas «No lo sé»)",
     [(EJV, "                                                 _magnitudes(sesion, hecho_id), ())\n",
       "                                                 _magnitudes(sesion, hecho_id), [f[0] for f in sesion.conexion.execute(\"SELECT magnitud_id FROM gapto.categoria_magnitudes WHERE categoria_id = %s\", (intencion.categoria_id,)).fetchall()])\n")],
     [T210 + "test_corregir_categoria_c07_obligatoria_que_el_hecho_no_tiene"], None),
    ("V12", "identidad: sin reconocer la intencion (el reintento no es idempotente)",
     [(EJV, "    auditadas = repo.auditorias_de_peticion(sesion, contexto.request_id)\n", "    auditadas = []\n")],
     [T210 + "test_corregir_categoria_reintento_idempotente_y_reutilizada"], None),
    ("V13", "identidad: la misma intencion con otra categoria se da por aplicada",
     [(EJV, " and efecto[0][\"despues\"].get(\"categoria_id\") == str(intencion.categoria_id):", ":")],
     [T210 + "test_corregir_categoria_reintento_idempotente_y_reutilizada"], None),
    # ---------------------------------------------------------------- UI
    ("W01", "UI: «Corregir categoria» se ofrece sin la accion del servidor",
     [(COMP, "      {categoria && p.onCorregirCategoria ? (\n", "      {p.onCorregirCategoria ? (\n"),
      (COMP, "accion={categoria} onPress={p.onCorregirCategoria} />", "accion={categoria ?? { disponible: true, codigo: null, motivo: null }} onPress={p.onCorregirCategoria} />")],
     [JEST + "fuera de V3 no se ofrece"], None),
    ("W02", "UI: guardar con la misma categoria",
     [(DOMM, "  return !!categoriaId && categoriaId !== (e.categoria?.categoria_id ?? null) && !!motivo.trim();\n",
       "  return !!categoriaId && !!motivo.trim();\n")],
     [JEST + "elegir la misma categoría"], None),
    ("W03", "UI: guardar sin motivo",
     [(DOMM, "  return !!categoriaId && categoriaId !== (e.categoria?.categoria_id ?? null) && !!motivo.trim();\n",
       "  return !!categoriaId && categoriaId !== (e.categoria?.categoria_id ?? null);\n")],
     [JEST + "elegir, motivo obligatorio"], None),
    ("W04", "UI: el reintento tras un fallo estrena identidad",
     [(ACT, "    if (r.tipo === 'INDETERMINADO') return setCat(", "    if (r.tipo === 'INDETERMINADO') return intencionCategoria.liberar(), setCat(")],
     [JEST + "tras un fallo de conexión el reintento usa la MISMA intención; un rechazo se explica"], None),
    ("W05", "UI: el payload lleva un campo fuera de la lista blanca",
     [(DOMM, "motivo: motivo.trim(), categoria_id: categoriaId };", "motivo: motivo.trim(), categoria_id: categoriaId, descripcion: '' } as PayloadCorregirCategoria;")],
     [JEST + "dominio: payload de la lista blanca"], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    """pytest por suite (api con su rootdir; backend aparte) y Jest en mobile/. rc != 0 si alguno falla."""
    api = [t for t in tests if t.startswith("tests/api/")]
    resto = [t for t in tests if t.startswith("tests/") and not t.startswith("tests/api/")]
    jest = [t[len("jest:"):] for t in tests if t.startswith("jest:")]
    rc = 0
    for grupo, extra in ((api, ["--rootdir=tests/api"]), (resto, [])):
        if not grupo:
            continue
        cmd = [sys.executable, "-m", "pytest", *grupo, "-q", "-x", "-p", "no:cacheprovider", *extra]
        rc = rc or subprocess.run(cmd, cwd=RAIZ, capture_output=True).returncode
    npx = "npx.cmd" if os.name == "nt" else "npx"
    for t in jest:
        fichero, patron = t.split("::", 1)
        cmd = [npx, "jest", fichero, "-t", patron, "--silent"]
        rc = rc or subprocess.run(cmd, cwd=RAIZ / "mobile", capture_output=True).returncode
    return rc


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


def anotar(salida: pathlib.Path | None, linea: str) -> None:
    print(linea, flush=True)
    if salida is not None:
        with salida.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())


def main() -> None:
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    salida = pathlib.Path(sys.argv[sys.argv.index("--salida") + 1]) if "--salida" in sys.argv else None
    elegidos = [mu for mu in MUTANTES if solo is None or mu[0] in solo]
    preflight = sorted({t for mu in elegidos for t in mu[3]})
    if correr(preflight) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    veredictos = []
    for mid, desc, cambios, tests, equivalencia in elegidos:
        ficheros = sorted({c[0] for c in cambios})
        originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
        textos = {f: b.decode("utf-8") for f, b in originales.items()}
        aplicable = True
        for f, texto, sustituto in cambios:
            if textos[f].count(texto) != 1:
                aplicable = False
                break
            textos[f] = textos[f].replace(texto, sustituto)
        if not aplicable:
            v = (mid, "NO_CLASIFICABLE", "transformacion no aplicable", desc)
            veredictos.append(v)
            anotar(salida, " | ".join(v))
            continue
        JOURNAL.write_text(json.dumps({"mutante": mid, "ficheros": [
            {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros
        ]}), encoding="utf-8")
        resultado = "NO_CLASIFICABLE"
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            resultado = "MUERTO" if correr(tests) != 0 else "VIVO"
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        if resultado == "VIVO" and equivalencia:
            resultado = "EQUIVALENTE"
        nota = f"{desc} [equivalente: {equivalencia}]" if resultado == "EQUIVALENTE" else desc
        v = (mid, resultado if ok else "NO_CLASIFICABLE",
             ",".join(sorted({pathlib.Path(t.split("::")[0].replace("jest:", "")).name for t in tests})), nota)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
