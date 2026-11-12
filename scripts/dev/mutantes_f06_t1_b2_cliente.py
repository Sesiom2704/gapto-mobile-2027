#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f06_t1_b2_cliente.py
# Ruta: scripts/dev/mutantes_f06_t1_b2_cliente.py
# Descripcion: Arnes de mutacion del CLIENTE de B2 · Compra (F06 T1-F06 B2 N1; mandato §7.3: M-AC-02, mutante del
#   bloqueo de habilitacion O10.29 en el cliente y guardas de la pantalla de la fecha de escritura y de B3b). Mismo
#   motor que scripts/mutantes/f06_01_b2.py: texto exacto con UNA aparicion (si no, NO_CLASIFICABLE y para), journal
#   antes del primer byte, restauracion verificada por SHA-256, preflight de los discriminantes (Jest) y veredicto a
#   disco en cuanto se conoce (GAPTO_B2C_VEREDICTOS). Un mutante solo es MUERTO si cae uno de SUS tests.
# Uso: python scripts/dev/mutantes_f06_t1_b2_cliente.py [ID ...]
# Version: 0.1.0 (F06 T1-F06 B2 N1)
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
DOM = "mobile/src/domain/compra.ts"
PANT = "mobile/src/screens/CompraScreen.tsx"
TEST = "__tests__/compra.test.tsx"
MARCADOR = RAIZ / ".mutante_f06_t1_b2_cliente_en_curso"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    fichero: str
    viejo: str
    nuevo: str
    tests: tuple[str, ...]


MUTANTES = (
    Mutante("M-AC-02", "«No es gasto del mes» se deriva del tipo del HECHO, nunca del tipo de efecto (HF-14)", DOM,
            "  tipoHecho === 'ADQUISICION_PATRIMONIAL' ? TEXTO_NO_GASTO_MES :",
            "  tipoHecho === 'ADQUISICION_PATRIMONIAL' || tipoHecho === 'VALOR_ACTIVO' ? TEXTO_NO_GASTO_MES :",
            ("HF-14",)),
    Mutante("MC-O10-29", "La declaracion de completitud no se ofrece antes de la certificacion de 0352 (O10.29)", DOM,
            "export const CONSUMIDORES_0352_HABILITADOS = false;", "export const CONSUMIDORES_0352_HABILITADOS = true;",
            ("O10.29",)),
    Mutante("MC-FE-01", "La propuesta de la compra es la de la fecha de ESCRITURA para todo el lote (AJ-TR1-10)", DOM,
            "atribucion: atribucionWire(b.atribucion, propuesta, 'TITULARIDAD_EN_FECHA_ESCRITURA', b.fechaEscritura),",
            "atribucion: atribucionWire(b.atribucion, propuesta, 'TITULARIDAD_EN_FECHA_ESCRITURA', b.gastos[0]?.fechaEconomica ?? b.fechaEscritura),",
            ("O6.22",)),
    Mutante("MC-B3B-01", "B3b: ninguna opcion viene marcada (la titularidad solo propone)", PANT,
            "            eleccion={b.atribucion} actores={actoresDe(p.vista, propuesta)}",
            "            eleccion={b.atribucion ?? { modo: 'TITULARIDAD' }} actores={actoresDe(p.vista, propuesta)}",
            ("B1 → B6",)),
    Mutante("MC-DESF-01", "ATRIBUCION_PROPUESTA_DESFASADA vuelve a B3b sin seleccion", PANT,
            "      setB({ ...b, atribucion: null });\n", "      setB({ ...b });\n",
            ("ATRIBUCION_PROPUESTA_DESFASADA",)),
    Mutante("MC-TEXTO-01", "La pantalla dice «Segun la titularidad de <propiedad> en la escritura (<fecha>)»", DOM,
            "  `Según la titularidad de ${propiedad} en la escritura (${diaMesAnioIso(fechaEscritura)})`;",
            "  `Según la titularidad de ${propiedad}`;",
            ("O6.22", "B1 → B6")),
)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _jest(patrones: tuple[str, ...]) -> tuple[int, str]:
    patron = "|".join(p.replace("(", "\\(").replace(")", "\\)") for p in patrones)
    npx = "npx.cmd" if os.name == "nt" else "npx"
    r = subprocess.run([npx, "jest", TEST, "-t", patron, "--ci"], cwd=MOVIL, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def _recuperar() -> None:
    if MARCADOR.exists():
        ruta_rel, original_hex = MARCADOR.read_text("ascii").split("\n", 1)
        (RAIZ / ruta_rel).write_bytes(bytes.fromhex(original_hex.strip()))
        MARCADOR.unlink()
        raise SystemExit(f"ABORTADO: mutacion a medias en {ruta_rel}; restaurada.")


def _a_disco(reg: dict) -> None:
    destino = os.environ.get("GAPTO_B2C_VEREDICTOS")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")


def main(argv: list[str]) -> int:
    _recuperar()
    sel = [m for m in MUTANTES if not argv or m.ident in argv]
    for m in sel:
        n = (RAIZ / m.fichero).read_bytes().decode("utf-8").count(m.viejo)
        if n != 1:
            raise SystemExit(f"ABORTADO (NO_CLASIFICABLE): {m.ident} patron con {n} apariciones")
    codigo, salida = _jest(tuple(dict.fromkeys(t for m in sel for t in m.tests)))
    if codigo != 0:
        print(salida[-3000:])
        raise SystemExit("ABORTADO: los discriminantes no estan verdes antes de mutar.")
    print("PREFLIGHT VERDE", flush=True)
    muertos = 0
    for m in sel:
        ruta = RAIZ / m.fichero
        original = ruta.read_bytes()
        sha = _sha(original)
        MARCADOR.write_text(f"{m.fichero}\n{original.hex()}", "ascii")
        try:
            ruta.write_bytes(original.decode("utf-8").replace(m.viejo, m.nuevo, 1).encode("utf-8"))
            codigo, salida = _jest(m.tests)
        finally:
            ruta.write_bytes(original)
            if _sha(ruta.read_bytes()) != sha:
                raise SystemExit(f"ABORTADO: restauracion fallida en {m.fichero}")
            MARCADOR.unlink()
        veredicto = "MUERTO" if codigo != 0 and ("failed" in salida) else ("VIVO" if codigo == 0 else "NO_CLASIFICABLE")
        muertos += veredicto == "MUERTO"
        _a_disco({"id": m.ident, "invariante": m.invariante, "fichero": m.fichero, "veredicto": veredicto, "tests": list(m.tests),
                  "sha_restaurado": sha})
        print(f"  {m.ident:12} {veredicto:16} [{m.invariante}]", flush=True)
        if veredicto == "NO_CLASIFICABLE":
            raise SystemExit(f"ABORTADO: {m.ident} NO_CLASIFICABLE")
    print(f"RESULTADO: {muertos}/{len(sel)} muertos")
    return 0 if muertos == len(sel) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
