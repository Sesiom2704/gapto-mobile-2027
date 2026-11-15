#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f06_t2_cat_viv_cliente.py
# Ruta: scripts/dev/mutantes_f06_t2_cat_viv_cliente.py
# Descripcion: Arnes de mutacion del CLIENTE de T2-F06 · CAT-VIV (mandato CAT-VIV §9.4): MC-CV-01..05. Mismo motor que
#   scripts/dev/mutantes_t2_f06_pag_cliente.py (copiado sin cambios de logica): texto exacto con UNA aparicion (si no,
#   NO_CLASIFICABLE y para), journal (marcador con el original) antes del primer byte, restauracion verificada por
#   SHA-256, preflight de los discriminantes (Jest) y veredicto a disco en cuanto se conoce (GAPTO_CATVIVC_VEREDICTOS).
#   Un mutante solo es MUERTO si cae uno de SUS tests. Con --comprobar solo verifica que cada patron aparece una vez.
# Uso: python scripts/dev/mutantes_f06_t2_cat_viv_cliente.py [--comprobar] [ID ...]
# Version: 0.1.0 (F06 T2-F06 CAT-VIV N1 (L-04, lamina SET-CAT/REG-CAT v1.0))
# ============================================================
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass

RAIZ = pathlib.Path(__file__).resolve().parents[2]
MOVIL = RAIZ / "mobile"
DOM = "mobile/src/domain/propiedad_registro.ts"
AJU = "mobile/src/screens/CategoriasAjustesScreen.tsx"
PREV = "mobile/src/screens/PrevisionRegistroScreen.tsx"
ACTV = "mobile/src/screens/ActividadScreen.tsx"
T_CV = "__tests__/cat_viv.test.tsx"
MARCADOR = RAIZ / ".mutante_f06_t2_cat_viv_cliente_en_curso"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    fichero: str
    viejo: str
    nuevo: str
    test: str
    tests: tuple[str, ...]


MUTANTES = (
    Mutante("MC-CV-01", "Sin marca, el formulario no cambia (O-CV-12)", DOM,
            "tipo === 'GASTO' && nodo?.asociada_vivienda === true;",
            "tipo === 'GASTO' && nodo?.asociada_vivienda !== undefined;",
            T_CV, ("sin marca el formulario no cambia",)),
    Mutante("MC-CV-02", "Con marca, «Propiedad» es obligatoria (O-CV-12, R01)", DOM,
            "  if (!s) return [TEXTO_FALTA_PROPIEDAD];\n",
            "  if (!s) return [];\n",
            T_CV, ("con marca, «Propiedad» obligatoria",)),
    Mutante("MC-CV-03", "El interruptor no recarga la pantalla: relectura silenciosa (O-CV-17, VP-1)", AJU,
            "    const leido = await cargar(true);\n",
            "    const leido = await cargar();\n",
            T_CV, ("O-CV-17",)),
    Mutante("MC-CV-04", "La confirmacion de una prevision que crea el gasto pide la propiedad (R06, OBL-VIV-01.4)", PREV,
            "  const conVivienda = tipoReg === 'GASTO' && conCategoria && marcaVivienda;\n",
            "  const conVivienda = tipoReg === 'GASTO' && conCategoria && marcaVivienda && false;\n",
            T_CV, ("R06 / M5",)),
    Mutante("MC-CV-05", "El aviso de la correccion de categoria se muestra en la lectura (R07, OBL-VIV-01.6)", ACTV,
            "      {d.aviso_vivienda_sin_propiedad ? (\n",
            "      {false ? (\n",
            T_CV, ("R07",)),
)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _jest(test: str, patrones: tuple[str, ...]) -> tuple[int, str]:
    patron = "|".join(p.replace("(", "\\(").replace(")", "\\)").replace("+", "\\+").replace(".", "\\.") for p in patrones)
    # node + jest.js directamente: con npx.cmd, cmd.exe interpreta el «|» del patron (ruta no encontrada).
    jest = str(MOVIL / "node_modules" / "jest" / "bin" / "jest.js")
    r = subprocess.run(["node", jest, test, "-t", patron, "--ci"], cwd=MOVIL, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def _recuperar() -> None:
    if MARCADOR.exists():
        ruta_rel, original_hex = MARCADOR.read_text("ascii").split("\n", 1)
        (RAIZ / ruta_rel).write_bytes(bytes.fromhex(original_hex.strip()))
        MARCADOR.unlink()
        raise SystemExit(f"ABORTADO: mutacion a medias en {ruta_rel}; restaurada.")


def _a_disco(reg: dict) -> None:
    destino = os.environ.get("GAPTO_CATVIVC_VEREDICTOS")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")


def _utf8() -> None:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass


def main(argv: list[str]) -> int:
    _utf8()
    comprobar = "--comprobar" in argv
    argv = [a for a in argv if a != "--comprobar"]
    _recuperar()
    sel = [m for m in MUTANTES if not argv or m.ident in argv]
    for m in sel:
        n = (RAIZ / m.fichero).read_bytes().decode("utf-8").count(m.viejo)
        if n != 1:
            raise SystemExit(f"ABORTADO (NO_CLASIFICABLE): {m.ident} patron con {n} apariciones")
    if comprobar:
        print(f"PATRONES OK: {len(sel)} mutantes con una sola aparicion")
        return 0
    por_test: dict[str, list[str]] = {}
    for m in sel:
        por_test.setdefault(m.test, []).extend(m.tests)
    for test, pats in por_test.items():
        codigo, salida = _jest(test, tuple(dict.fromkeys(pats)))
        if codigo != 0:
            print(salida[-3000:])
            raise SystemExit(f"ABORTADO: los discriminantes de {test} no estan verdes antes de mutar.")
    print("PREFLIGHT VERDE", flush=True)
    muertos = 0
    for m in sel:
        ruta = RAIZ / m.fichero
        original = ruta.read_bytes()
        sha = _sha(original)
        MARCADOR.write_text(f"{m.fichero}\n{original.hex()}", "ascii")
        try:
            ruta.write_bytes(original.decode("utf-8").replace(m.viejo, m.nuevo, 1).encode("utf-8"))
            codigo, salida = _jest(m.test, m.tests)
        finally:
            ruta.write_bytes(original)
            if _sha(ruta.read_bytes()) != sha:
                raise SystemExit(f"ABORTADO: restauracion fallida en {m.fichero}")
            MARCADOR.unlink()
        veredicto = "MUERTO" if codigo != 0 and ("failed" in salida) else ("VIVO" if codigo == 0 else "NO_CLASIFICABLE")
        muertos += veredicto == "MUERTO"
        _a_disco({"id": m.ident, "invariante": m.invariante, "fichero": m.fichero, "veredicto": veredicto, "test": m.test,
                  "tests": list(m.tests), "sha_restaurado": sha})
        print(f"  {m.ident:12} {veredicto:16} [{m.invariante}]", flush=True)
        if veredicto == "NO_CLASIFICABLE":
            raise SystemExit(f"ABORTADO: {m.ident} NO_CLASIFICABLE")
    print(f"RESULTADO: {muertos}/{len(sel)} muertos")
    return 0 if muertos == len(sel) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
