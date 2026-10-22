# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_06_m1.py
# Ruta: scripts/dev/mutantes_f05_06_m1.py
# Descripcion: Arnes de mutacion de F05-06 M1 (CONTRATO_M1 v0.1 §3; F05 §61.2
#   F05-D047; un mutante por guarda nueva de la capa API/UI; 100 % muertos o
#   equivalentes documentados). Mismo motor que mutantes_f05_06_m5b.py
#   (journal durable, preflight verde, restauracion verificada por SHA-256,
#   veredicto a disco en cuanto se conoce). Guardas: declaracion explicita de
#   duplicado (DTO y traduccion a movimiento_en_banco), declaracion de error de
#   registro, rechazo de campos ajenos, intencion = request_id (reintento
#   idempotente), VERSION_DESFASADA con la edicion releida, texto del motivo,
#   elegibilidad visible (V3 limitado, reparto, dependencias) y, en la UI,
#   accion no elegible no enviada, declaracion y motivo obligatorios y misma
#   identidad tras un fallo. Sin lista blanca de V3: Q9 en STOP.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable>
#        python scripts/dev/mutantes_f05_06_m1.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-06 M1)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_06_m1.journal.json"

DTO = "backend/app/api/dto_edicion.py"
EJA = "backend/app/api/ejecucion_anulacion.py"
APP = "backend/app/api/app.py"
EH = "backend/app/api/errores_http.py"
EDI = "backend/app/actividad/edicion.py"
COMP = "mobile/src/components/EdicionHecho.tsx"
DOMM = "mobile/src/domain/edicion.ts"
ACT = "mobile/src/screens/ActividadScreen.tsx"
T209 = "tests/api/test_209_f05_06_m1_corregir_anular.py::"
JEST = "jest:__tests__/edicion_hecho.test.tsx::"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("E01", "anulacion: sin declaracion el motor recibe igualmente movimiento_en_banco=false",
     [(EJA, "movimiento_en_banco=False if intencion.duplicado_declarado is True else None))",
       "movimiento_en_banco=False))")],
     [T209 + "test_anular_duplicado_sin_declaracion"], None),
    ("E02", "DTO: declaracion de duplicado con valor por defecto",
     [(DTO, "    duplicado_declarado: StrictBool  # sin defecto: declaracion explicita\n",
       "    duplicado_declarado: StrictBool = True  # sin defecto: declaracion explicita\n")],
     [T209 + "test_anular_duplicado_sin_declaracion"], None),
    ("E03", "DTO: error_de_registro con valor por defecto (OP-21P)",
     [(DTO, "    movimiento_row_version: int = Field(ge=1)\n    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)\n"
            "    error_de_registro: StrictBool\n",
       "    movimiento_row_version: int = Field(ge=1)\n    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)\n"
       "    error_de_registro: StrictBool = True\n")],
     [T209 + "test_corregir_pago_sin_declaracion_de_error"], None),
    ("E04", "DTO: campos ajenos ignorados en vez de rechazados",
     [(DTO, '    model_config = ConfigDict(extra="forbid", frozen=True)\n', '    model_config = ConfigDict(extra="ignore", frozen=True)\n')],
     [T209 + "test_corregir_pago_campos_ajenos_rechazados"], None),
    ("E05", "ruta: request_id nuevo en cada intento (reintento no idempotente)",
     [(APP, "ContextoOperacion.de_usuario(cfg.owner_user_id, request_id=intencion.intencion_id)",
       "ContextoOperacion.de_usuario(cfg.owner_user_id, request_id=uuid.uuid4())")],
     [T209 + "test_corregir_pago_importe_con_su_movimiento"], None),
    ("E06", "ruta: VERSION_DESFASADA sin la edicion releida",
     [(APP, "            if exc.codigo is CodigoError.VERSION_DESFASADA:\n                cuerpo = {**cuerpo, \"detalle\": {**cuerpo.get(\"detalle\", {}), \"edicion\": jsonable_encoder(",
       "            if False:\n                cuerpo = {**cuerpo, \"detalle\": {**cuerpo.get(\"detalle\", {}), \"edicion\": jsonable_encoder(")],
     [T209 + "test_corregir_pago_version_desfasada_sin_pisar"], None),
    ("E07", "errores: el motivo concreto del motor no sustituye al texto generico",
     [(EH, "    if motivo in MOTIVOS_EDICION:\n        cuerpo = {**cuerpo, \"mensaje\": MOTIVOS_EDICION[motivo]}\n", "")],
     [T209 + "test_edicion_v3_limitado_y_rechazo_en_servidor"], None),
    ("E08", "elegibilidad: V3 (importado) no se detecta",
     [(EDI, "    if repo.importado(sesion, destinos):\n        return \"ORIGEN_IMPORTADO\"\n", "")],
     [T209 + "test_edicion_v3_limitado_y_rechazo_en_servidor"], None),
    ("E09", "elegibilidad: reparto con otras personas ofrecido como corregible",
     [(EDI, "        if _con_reparto(sesion, hecho_id):\n            return \"REPARTO\"\n", "")],
     [T209 + "test_edicion_gasto_con_reparto_no_se_corrige_aqui"], None),
    ("E10", "elegibilidad: anular ofrecido con dependencias activas",
     [(EDI, "    if repo_hechos.dependencias_activas(sesion, hecho_id):\n        return \"DEPENDENCIAS_ACTIVAS\"\n", "")],
     [T209 + "test_edicion_compra_con_devolucion"], None),
    # ---------------------------------------------------------------- UI
    ("U01", "UI: accion no elegible pulsable y enviada",
     [(COMP, "        disabled={!ok} onPress={ok ? p.onPress : undefined}\n", "        disabled={false} onPress={p.onPress}\n")],
     [JEST + "lo no admitido"], None),
    ("U02", "UI: anular sin la declaracion",
     [(COMP, "  const listo = p.declarado && !!p.motivo.trim() && !p.enviando;\n", "  const listo = !!p.motivo.trim() && !p.enviando;\n"),
      (ACT, "    if (!anular.declarado || !anular.motivo.trim() || anular.enviando) return;\n",
       "    if (!anular.motivo.trim() || anular.enviando) return;\n")],
     [JEST + "anular exige la declaración"], None),
    ("U03", "UI: anular sin motivo",
     [(COMP, "  const listo = p.declarado && !!p.motivo.trim() && !p.enviando;\n", "  const listo = p.declarado && !p.enviando;\n"),
      (ACT, "    if (!anular.declarado || !anular.motivo.trim() || anular.enviando) return;\n",
       "    if (!anular.declarado || anular.enviando) return;\n")],
     [JEST + "anular exige la declaración"], None),
    ("U04", "UI: corregir sin motivo",
     [(DOMM, "  if (motivo !== null && !motivo.trim()) falta.push('el motivo');\n", "")],
     [JEST + "precargado"], None),
    ("U05", "UI: el reintento de anular tras un fallo estrena identidad",
     [(ACT, "    if (r.tipo === 'INDETERMINADO') return setAnular(", "    if (r.tipo === 'INDETERMINADO') return intencionAnular.liberar(), setAnular(")],
     [JEST + "MISMA intención; un rechazo"], None),
    ("U06", "UI: la declaracion se envia siempre como true",
     [(DOMM, "    duplicado_declarado: declarado,\n", "    duplicado_declarado: true,\n")],
     [JEST + "anulación: la declaración viaja"], None),
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
