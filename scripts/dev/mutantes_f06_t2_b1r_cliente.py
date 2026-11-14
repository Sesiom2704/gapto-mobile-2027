#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f06_t2_b1r_cliente.py
# Ruta: scripts/dev/mutantes_f06_t2_b1r_cliente.py
# Descripcion: Arnes de mutacion del CLIENTE de B1-R · Correccion del inicio de la titularidad (F06 T2-F06 · B1-R N1;
#   mandato §8.3, MC-B1R-01..08): solo adelantar, cota de la adquisicion, A1 con su condicion, el rechazo renueva la
#   intencion, envio solo tras la confirmacion visible, aviso de adquisicion desconocida, alta con «Desde» <= hoy
#   (L-01b) y la accion de la ficha solo con `inicio_corregible` del servidor.
#   Motor de scripts/dev/mutantes_f06_t1_b3_cliente.py (semilla de los mutantes: laboratorio lab-t2 344b2b3,
#   MC-B1R-01..04, renumerados y reescritos): texto exacto con UNA aparicion (si no, NO_CLASIFICABLE y para), journal
#   (marcador con el original) antes del primer byte, restauracion verificada por SHA-256, preflight de los
#   discriminantes (Jest) y veredicto a disco en cuanto se conoce (GAPTO_B1RC_VEREDICTOS). Un mutante solo es MUERTO
#   si cae uno de SUS tests. Con --comprobar solo verifica que cada patron aparece una vez. Se ejecuta sobre una COPIA
#   independiente del arbol (nunca sobre un worktree con un gate en curso).
# Uso: python scripts/dev/mutantes_f06_t2_b1r_cliente.py [--comprobar] [ID ...]
# Version: 0.1.0 (F06 T2-F06 · B1-R (L-01/L-01b))
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
DOM = "mobile/src/domain/inicio_titularidad.ts"
PANT = "mobile/src/screens/PropiedadInicioScreen.tsx"
ALTA = "mobile/src/screens/PropiedadAltaScreen.tsx"
FICHA = "mobile/src/screens/PropiedadFichaScreen.tsx"
T_IT = "__tests__/inicio_titularidad.test.tsx"
MARCADOR = RAIZ / ".mutante_f06_t2_b1r_cliente_en_curso"


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
    Mutante("MC-B1R-01", "Solo adelantar: una fecha igual al inicio vigente no vale (INICIO_NO_ANTERIOR)", DOM,
            "  if (nuevoIso >= inicioIso) return [", "  if (nuevoIso > inicioIso) return [", T_IT, ("dominio",)),
    Mutante("MC-B1R-02", "Cota de la adquisicion conocida en la correccion", DOM,
            "  if (adquisicionIso && nuevoIso < adquisicionIso) return [",
            "  if (false && adquisicionIso && nuevoIso < adquisicionIso) return [", T_IT, ("dominio", "solo adelantar")),
    Mutante("MC-B1R-03", "A1 solo con «Desde» posterior a la adquisicion", DOM,
            " || desdeIso <= adquisicionIso) return null;", ") return null;", T_IT, ("dominio", "alta A1")),
    Mutante("MC-B1R-04", "Un rechazo de dominio renueva la intencion", PANT,
            "    intencion.current = p.nuevoId();\n    setConfirmando(false);\n", "    setConfirmando(false);\n", T_IT,
            ("indeterminado reintenta",)),
    Mutante("MC-B1R-05", "Sin confirmacion visible no se envia («Continuar» solo abre la confirmacion)", PANT,
            "  const revisar = () => { if (valida) setConfirmando(true); };",
            "  const revisar = () => { if (valida) void enviar(); };", T_IT, ("pantalla: afectados",)),
    Mutante("MC-B1R-06", "Aviso de adquisicion desconocida (la fecha no se presenta como verificada)", PANT,
            "        {adquisicion ? null : (", "        {true ? null : (", T_IT, ("No la sé",)),
    Mutante("MC-B1R-07", "L-01b: el alta no admite «Desde» futuro", ALTA,
            "  const futuro = tit.modo !== null", "  const futuro = false && tit.modo !== null", T_IT, ("alta L-01b",)),
    Mutante("MC-B1R-08", "La accion «Corregir desde cuando» solo con inicio_corregible del servidor", FICHA,
            "v.inicio_titularidad?.inicio_corregible === true && ", "", T_IT, ("ficha",)),
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
    destino = os.environ.get("GAPTO_B1RC_VEREDICTOS")
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
