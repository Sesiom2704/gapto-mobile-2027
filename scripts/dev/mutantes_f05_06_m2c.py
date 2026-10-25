# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_06_m2c.py
# Ruta: scripts/dev/mutantes_f05_06_m2c.py
# Descripcion: Arnes de mutacion de F05-06 M2-C (pista visual O-1 del swipe
#   «Cobrado» de la devolucion: la fila sigue al dedo, deja ver la franja de la
#   accion, marca el umbral y vuelve al soltar). Procede del arnes historico
#   C:/DEV/evidencia_f0506_m2/m2c/mutantes_m2c.py (HUECO-05), que importaba
#   scripts/dev/mutantes_f05_06_m2.py y le sustituia en memoria la lista
#   MUTANTES. Aqui es autonomo: mismo motor que mutantes_f05_06_m2.py (D-181,
#   D-192, D-193, WM 12C.2): sustituciones de texto exacto (UNA ocurrencia),
#   journal durable antes del primer byte, preflight verde, restauracion
#   verificada por SHA-256 y veredicto MUERTO | VIVO | EQUIVALENTE |
#   NO_CLASIFICABLE.
#   Guardas (todas en el componente comun del swipe desde F05-06 M5 SWIPE:
#   mobile/src/components/AccionRapida.tsx, FilaDeslizable; la fila de la
#   devolucion ya no tiene gesto propio en ActividadScreen.tsx):
#     MC01 sin franja de la accion al arrastrar;
#     MC02 la fila no se desplaza con el dedo;
#     MC03 sin senal de umbral (el circulo no crece pasado el umbral);
#     MC04 la fila no vuelve a su sitio al soltar.
#   Discriminante: mobile/__tests__/devolucion.test.tsx (Jest, en serie).
#   MU01..MU04, que el historico reejecutaba como regresion, viven en
#   mutantes_f05_06_m2.py y no se duplican aqui.
#   Uso: python scripts/dev/mutantes_f05_06_m2c.py [--solo ID,ID]
#   Solo Jest: no necesita base de datos. No ejecutar en paralelo con otro
#   arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-06 M2-C, fuera del repo: evidencia_f0506_m2/m2c)
# Version: 0.2.0 (F05-07/GATE adenda 2, MANT-PRE-GATE arneses, HUECO-05; F05
#   §63.6 (1)): pasa a scripts/dev/, autonomo y sin sustituciones en memoria;
#   la raiz se deduce del propio fichero. Reanclaje (los textos de 0.1.0 ya no
#   anclan en 5e39673: el gesto se movio de ActividadScreen.tsx a
#   AccionRapida.tsx en F05-06 M5 SWIPE/SWIPE2/SWIPE3):
#     MC01 `{fase !== 'reposo' ? (` -> la condicion vigente de la franja
#       `{fase !== 'reposo' && l && direccion && col ? (`;
#     MC02 mismo texto `transform: [{ translateX: desplazamiento }]`, ahora en
#       AccionRapida.tsx;
#     MC03 la franja que pasaba de `accentSurface` a `accent` pasado el umbral
#       no existe desde la lamina SWIPE-01 v0.2 (estilo C: el fondo es el tono
#       suave fijo y el umbral lo marca el circulo que crece, `circuloTotal`,
#       ademas de la vibracion, cubierta por MS29 de mutantes_f05_06_m5_swipe.py).
#       El mutante quita el crecimiento del circulo; devolucion.test.tsx 0.8.0
#       lo afirma en O-1 (antes ningun test lo discriminaba);
#     MC04 la vuelta al soltar es ahora `mover(0, true)` dentro de `cerrar`.
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_06_m2c.journal.json"

M_SWIPE = "mobile/src/components/AccionRapida.tsx"
J_DEV = "mobile/__tests__/devolucion.test.tsx"

#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    ("MC01", "M2-C: sin franja de la accion al arrastrar (O-1)",
     [(M_SWIPE, "      {fase !== 'reposo' && l && direccion && col ? (", "      {false ? (")], [J_DEV], None),
    ("MC02", "M2-C: la fila no se desplaza con el dedo (O-1)",
     [(M_SWIPE, "transform: [{ translateX: desplazamiento }]", "transform: [{ translateX: 0 }]")], [J_DEV], None),
    ("MC03", "M2-C: sin senal de umbral (el circulo no crece pasado el umbral) (O-1, SWIPE-01 v0.2)",
     [(M_SWIPE, "fase === 'total' && s.circuloTotal]", "false && s.circuloTotal]")], [J_DEV], None),
    ("MC04", "M2-C: la fila no vuelve a su sitio al soltar (O-1)",
     [(M_SWIPE, "    setDireccion(null);\n    mover(0, true);\n  }, []);", "    setDireccion(null);\n  }, []);")],
     [J_DEV], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    js = [t.removeprefix("mobile/") for t in tests]
    npx = shutil.which("npx") or "npx"
    return subprocess.run([npx, "jest", "--silent", "--runInBand", *js], cwd=RAIZ / "mobile", capture_output=True).returncode


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
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    elegidos = [m for m in MUTANTES if solo is None or m[0] in solo]
    preflight = sorted({t for m in elegidos for t in m[3]})
    if correr(preflight) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    veredictos = []
    for mid, desc, cambios, tests, equivalencia in elegidos:
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
        if v == "VIVO" and equivalencia:
            v = "EQUIVALENTE"
        nota = f"{desc} [equivalente: {equivalencia}]" if v == "EQUIVALENTE" else desc
        veredictos.append((mid, v if ok else "NO_CLASIFICABLE", ",".join(pathlib.Path(t).name for t in tests), nota))
    for v in veredictos:
        print(*v, sep=" | ")
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    print(f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
          f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
