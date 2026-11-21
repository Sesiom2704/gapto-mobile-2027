#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: mant_t3_comparador_h2.py
# Ruta: scripts/mutantes/mant_t3_comparador_h2.py
# Descripcion: Arnes de mutantes del comparador normalizado de constraints (scripts/gates/
#   comparar_constraints_normalizado.py; AJ-T3C-06, decisiones 15 y 16). Cada mutante hace una normalizacion
#   DEMASIADO AMPLIA (una o mas por regla N1-N3), ignora el operador o el cuantificador de N1, ignora la
#   presencia por nombre o ignora los atributos. Se aplica con texto exacto (debe aparecer una sola vez) sobre una
#   COPIA del comparador en la carpeta de salida; el fichero del arbol no se toca (se verifica su SHA-256 antes y
#   despues). Se ejecutan solo los casos P3-P12 de tests/gates/test_comparador_normalizado.py contra la copia
#   (variable GAPTO_COMPARADOR_RUTA): MUERTO si fallan, VIVO si pasan. Antes, control con la copia sin mutar:
#   debe pasar entera. Veredictos a disco (veredictos.json y un log por mutante).
# Uso: python scripts/mutantes/mant_t3_comparador_h2.py --salida <carpeta>
#      rc 0 si el control pasa y todos los mutantes mueren; rc 1 en otro caso.
# Version: 1.0.0 (F06 — T3 · MANT N1 del comparador normalizado de constraints h2; decisiones 15 y 16)
# ============================================================
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
COMPARADOR = RAIZ / "scripts" / "gates" / "comparar_constraints_normalizado.py"
PRUEBAS = RAIZ / "tests" / "gates" / "test_comparador_normalizado.py"
SELECCION = " or ".join(f"test_p{n}_" for n in range(3, 13)) + " or test_p3b_ or test_p5b_ or test_p10b_"

_N1 = "        toks, c = _n1(toks)\n"
MUTANTES = [
    ("MC-N1-CAST", "N1 demasiado amplia: ademas de recolocar, descarta todos los casts (tipo base y final)",
     _N1, _N1 + "        toks = [t for k, t in enumerate(toks) if not (t[0] == 'cast' or (t[0] in ('id', 'ws') and "
                "any(toks[j][0] == 'cast' for j in range(max(0, k - 3), k))))]\n"),
    ("MC-N1-ORDEN", "N1 demasiado amplia: ordena los elementos del ARRAY al recolocar el cast",
     "        for n, (lit, base) in enumerate(elementos):\n",
     "        for n, (lit, base) in enumerate(sorted(elementos, key=lambda e: e[0][1])):\n"),
    ("MC-N1-BASE", "N1 demasiado amplia: no exige el mismo tipo base en todos los elementos",
     "        if len(bases) != 1:                      # todos del MISMO tipo base\n",
     "        if False:                                # todos del MISMO tipo base\n"),
    ("MC-N1-OPERADOR", "N1 ignora el operador delante del cuantificador (decision 16)",
     _N1, "        toks, c = _n1([('op', '=') if t == ('op', '<>') else t for t in toks])\n"),
    ("MC-N1-CUANTIFICADOR", "N1 ignora el cuantificador ANY/ALL (decision 16)",
     _N1, "        toks, c = _n1([('id', 'ANY') if t == ('id', 'ALL') else t for t in toks])\n"),
    ("MC-N2-AMPLIA", "N2 demasiado amplia: quita todos los parentesis, no solo los de un operando unico",
     "        toks, c = _n2(toks)\n", "        toks, c = [t for t in toks if t[1] not in ('(', ')')], True\n"),
    ("MC-N3-LITERALES", "N3 demasiado amplia: quita tambien los espacios dentro de los literales",
     '        sin_ws = [t for t in toks if t[0] != "ws"]\n',
     '        sin_ws = [(k, v.replace(" ", "")) for k, v in toks if k != "ws"]\n'),
    ("MC-N3-MAYUSCULAS", "N3 demasiado amplia: ademas de espacios, ignora mayusculas y minusculas",
     '        sin_ws = [t for t in toks if t[0] != "ws"]\n',
     '        sin_ws = [(k, v.upper()) for k, v in toks if k != "ws"]\n'),
    ("MC-PRESENCIA", "ignora la presencia por nombre (solo compara las comunes)",
     "    for nombre in sorted(set(a) | set(b)):\n", "    for nombre in sorted(set(a) & set(b)):\n"),
    ("MC-ATRIBUTOS", "ignora los atributos (tipo, DEFERRABLE, INITIALLY DEFERRED) de la extraccion",
     "        atributos = [k for k in", "        atributos = [] and [k for k in"),
]


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pytest(copia: pathlib.Path, log: pathlib.Path) -> int:
    env = dict(os.environ, GAPTO_COMPARADOR_RUTA=str(copia), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-m", "pytest", str(PRUEBAS), "-q", "-p", "no:cacheprovider", "-k", SELECCION],
                       cwd=RAIZ, env=env, capture_output=True, text=True)
    log.write_text(r.stdout + "\n--- stderr ---\n" + r.stderr, encoding="utf-8")
    return r.returncode


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    x = ap.parse_args(argv)
    out = pathlib.Path(x.salida)
    out.mkdir(parents=True, exist_ok=True)
    original = COMPARADOR.read_text(encoding="utf-8")
    sha_antes = sha(COMPARADOR)
    res = {"comparador": str(COMPARADOR.relative_to(RAIZ)), "comparador_sha256": sha_antes,
           "pruebas_sha256": sha(PRUEBAS), "seleccion": SELECCION, "mutantes": []}
    control = out / "control_comparador.py"
    control.write_text(original, encoding="utf-8", newline="\n")
    rc = pytest(control, out / "control.log")
    res["control_rc"] = rc
    print(f"control (sin mutar): rc={rc} {'OK' if rc == 0 else 'FALLA'}")
    todos = rc == 0
    for mid, desc, viejo, nuevo in MUTANTES:
        n = original.count(viejo)
        if n != 1:
            res["mutantes"].append({"id": mid, "descripcion": desc, "veredicto": "NO_APLICABLE", "apariciones": n})
            print(f"{mid}: NO_APLICABLE (el texto aparece {n} veces)")
            todos = False
            continue
        copia = out / f"{mid}.py"
        copia.write_text(original.replace(viejo, nuevo), encoding="utf-8", newline="\n")
        rc = pytest(copia, out / f"{mid}.log")
        ultima = ((out / f"{mid}.log").read_text(encoding="utf-8").split("\n--- stderr ---")[0].strip().splitlines()
                  or [""])[-1]
        veredicto = "MUERTO" if rc != 0 else "VIVO"
        todos = todos and veredicto == "MUERTO"
        res["mutantes"].append({"id": mid, "descripcion": desc, "veredicto": veredicto, "rc": rc, "resumen": ultima})
        print(f"{mid}: {veredicto} (rc={rc}; {ultima})")
    res["comparador_sha256_despues"] = sha(COMPARADOR)
    res["arbol_intacto"] = res["comparador_sha256_despues"] == sha_antes
    todos = todos and res["arbol_intacto"]
    res["resultado"] = "TODOS_MUERTOS" if todos else "FALLO"
    (out / "veredictos.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"arbol intacto: {res['arbol_intacto']}; resultado: {res['resultado']}")
    return 0 if todos else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
