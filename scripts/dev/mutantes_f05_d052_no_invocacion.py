# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_d052_no_invocacion.py
# Ruta: scripts/dev/mutantes_f05_d052_no_invocacion.py
# Descripcion: Arnes de mutacion de F05-D052 paso 7 (prueba de no invocacion
#   de RVRX-REGLA y recalcular_futuras, AJ-F0507G3-14). Mismo motor que
#   mutantes_f05_d051_g1v2.py (journal durable, preflight verde, restauracion
#   verificada por SHA-256, veredicto a disco en cuanto se conoce), con pytest
#   y sin base de datos. Cada mutante introduce una via de invocacion distinta
#   y exige que test_230 falle:
#     N01 ruta nueva en create_app que llama a crear_version;
#     N02 llamada directa desde el adaptador de una ruta existente;
#     N03 llamada indirecta dentro del servicio alcanzado por una ruta;
#     N04 inyeccion por constructor de un callback (referencia sin llamada);
#     N05 getattr con nombre no constante (despacho dinamico sin revisar);
#     N06 getattr con nombre literal;
#     N07 ruta registrada con add_api_route y endpoint en otro modulo (solo la
#         enumeracion desde la app real la ve: create_app no es raiz del grafo).
#   Uso: python scripts/dev/mutantes_f05_d052_no_invocacion.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-D052 paso 7)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_d052_no_invocacion.journal.json"

APP = "backend/app/api/app.py"
EJP = "backend/app/api/ejecucion_prevision.py"
PREV = "backend/app/services/previsiones_service.py"
T = "tests/api/test_230_f05_d052_no_invocacion_f06.py::"
NEG = T + "test_ninguna_ruta_alcanza_rvrx_regla_ni_recalcular_futuras"
DIN = T + "test_despacho_dinamico_alcanzable_revisado"
SALUD = '    @app.get("/v1/salud", dependencies=[Depends(autorizar)])\n'
OMITIR = "        r = _previsiones(sesion).omitir(\n"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("N01", "ruta nueva en create_app que invoca ReglasService.crear_version",
     [(APP, SALUD,
       '    @app.post("/v1/mutante/regla", dependencies=[Depends(autorizar)])\n'
       '    def mutante_regla() -> dict:\n'
       '        return unidad.ejecutar(contexto(), lambda s: ReglasService(s).crear_version(contexto()), nombre="mut")\n\n'
       + SALUD)],
     [NEG], None),
    ("N02", "adaptador de una ruta existente (omitir) llama a recalcular_futuras",
     [(EJP, OMITIR, "        _previsiones(sesion).recalcular_futuras(contexto)\n" + OMITIR)],
     [NEG], None),
    ("N03", "servicio alcanzado por una ruta (PrevisionesService.omitir) llama a recalcular_futuras",
     [(PREV, "        return self._terminar(\n            contexto,\n            prevision_id=prevision_id,\n"
             "            row_version_esperada=row_version_esperada,\n            estado_destino=OMITIDA,\n",
       "        self.recalcular_futuras(contexto)\n"
       "        return self._terminar(\n            contexto,\n            prevision_id=prevision_id,\n"
       "            row_version_esperada=row_version_esperada,\n            estado_destino=OMITIDA,\n")],
     [NEG], None),
    ("N04", "inyeccion por constructor de un callback corregir_excepcion (sin llamada en el adaptador)",
     [(EJP, "    return PrevisionesService(UnidadDeTrabajoAdscrita(sesion))\n",
       "    return PrevisionesService(UnidadDeTrabajoAdscrita(sesion), al_cerrar=ReglasService.corregir_excepcion)\n")],
     [NEG], None),
    ("N05", "getattr con nombre no constante en el adaptador de una ruta",
     [(EJP, OMITIR, "        r = getattr(_previsiones(sesion), intencion.accion)(\n")],
     [DIN], None),
    ("N06", "getattr con nombre literal recalcular_futuras en el adaptador de una ruta",
     [(EJP, OMITIR, '        r = getattr(_previsiones(sesion), "recalcular_futuras")(\n')],
     [NEG], None),
    ("N07", "ruta registrada con add_api_route y endpoint definido en otro modulo",
     [(APP, SALUD, '    app.add_api_route("/v1/mutante/futuras", ejp.mutante_futuras, methods=["POST"])\n\n' + SALUD),
      (EJP, "def _previsiones(sesion: SesionMotor) -> PrevisionesService:\n",
       "def mutante_futuras() -> None:\n    PrevisionesService.recalcular_futuras(None, None)\n\n\n"
       "def _previsiones(sesion: SesionMotor) -> PrevisionesService:\n")],
     [NEG], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    """pytest de tests/api sin base de datos; rc != 0 si algun discriminante falla o no se recoge."""
    cmd = [sys.executable, "-B", "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider", "--rootdir=tests/api"]
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")
    ultima = (r.stdout.strip().splitlines() or [""])[-1]
    # Un discriminante que no se recoge no discrimina: se trata como fallo de preflight.
    if r.returncode == 0 and f"{len(tests)} passed" not in ultima:
        return 2
    return r.returncode


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
        v = (mid, resultado if ok else "NO_CLASIFICABLE", ",".join(sorted({t.split("::")[1] for t in tests})), nota)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
