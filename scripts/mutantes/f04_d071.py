#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f04_d071.py
# Ruta: scripts/mutantes/f04_d071.py
# Descripcion: Arnes de mutacion de F04-D071 (MANT de OP-21): orden de
#   retirada de R-L12-01 (atribuciones antes que efectos) y de R-L17-01
#   (vinculos hecho_entidades de nivel efecto antes que efectos; opcion A).
#
#   Cada mutante aplica 1..N sustituciones (cada patron debe aparecer
#   EXACTAMENTE una vez en su fichero) y declara su DISCRIMINANTE: el test
#   concreto que debe caer. No se da por muerto si solo caen tests
#   colaterales.
#
#   Guardas D-181/D-192 (motor copiado de f04_r3.py): E/S byte a byte;
#   marcador DURABLE con el contenido original de todos los ficheros tocados
#   escrito ANTES del primer byte mutado; al arrancar, si hay marcador, se
#   restaura, se verifica y se aborta no-PASS; restauracion verificada por
#   SHA-256 tras cada mutante; preflight verde de la suite antes del primer
#   mutante; arbol limpio exigido; un unico veredicto por mutante.
# Uso:
#   GAPTO_TEST_DATABASE_URL=... python scripts/mutantes/f04_d071.py [D071-M1 ...]
# Version: 0.1.0
#   0.1.0 (F04-D071, MANT N1 de OP-21; AJ-MOP21-05 y R-L17-01 opcion A).
# ============================================================
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
from dataclasses import dataclass

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SUITE = (
    "tests/backend/test_14m_mant_op21_retirada_atribuciones.py",
    "tests/backend/test_126_op21_atribuciones.py",
)
COR = "backend/app/services/correcciones_service.py"
MARCADOR = RAIZ / ".mutante_f04_d071_en_curso"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    cambios: tuple[tuple[str, str, str], ...]  # (fichero, viejo, nuevo)
    discriminante: str


ATRIBUCIONES_ANTES = "            atribuciones_eliminadas = self._eliminar_atribuciones(sesion, datos)\n"
RELACIONES = "            relaciones = self._eliminar_relaciones(sesion, datos)\n"

MUTANTES = [
    # Restaura el orden de 3d85aec: atribuciones despues de los efectos.
    Mutante("D071-M1", "Atribuciones retiradas antes que su efecto (R-L12-01)",
            ((COR, ATRIBUCIONES_ANTES, ""),
             (COR, RELACIONES, RELACIONES + ATRIBUCIONES_ANTES)),
            "test_t1_positivo_completo_efecto_y_reparto_reemplazados"),
    # Sin el paso 3b los vinculos de nivel efecto vuelven a salir en 3ter,
    # despues de su efecto.
    Mutante("D071-M2", "Vinculos de nivel efecto retirados antes que su efecto (R-L17-01)",
            ((COR, "            vinculos_de_efecto = self._eliminar_vinculos_de_efecto(sesion, datos)\n",
              "            vinculos_de_efecto = frozenset()\n"),),
            "test_e1_vinculo_de_efecto_retirado_con_su_efecto"),
    # Un id repetido no puede colarse como ya retirado.
    Mutante("D071-M3", "Un vinculo repetido sigue siendo AGREGADO_NO_ENCONTRADO",
            ((COR, "                pendientes_3b.discard(registro_id)\n", "                pass\n"),),
            "test_e4_vinculo_de_efecto_repetido_sigue_siendo_no_encontrado"),
]


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _recuperar_si_aborto_previo() -> None:
    if MARCADOR.exists():
        guardado = json.loads(MARCADOR.read_text("ascii"))
        for ruta_rel, (hexa, sha) in guardado.items():
            (RAIZ / ruta_rel).write_bytes(bytes.fromhex(hexa))
            if _sha((RAIZ / ruta_rel).read_bytes()) != sha:
                raise SystemExit(f"ABORTADO: restauracion no verificada en {ruta_rel}")
        MARCADOR.unlink()
        raise SystemExit("ABORTADO: habia una mutacion a medias; restaurada y verificada. Vuelve a ejecutar.")


def _arbol_limpio() -> None:
    salida = subprocess.run(["git", "status", "--porcelain"], cwd=RAIZ, capture_output=True, text=True).stdout.strip()
    if salida:
        raise SystemExit("ABORTADO: el arbol de trabajo no esta limpio.")


def _pytest() -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", *SUITE, "-q", "-p", "no:cacheprovider", "-rf", "--timeout", "90"],
                       cwd=RAIZ, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def ejecutar(m: Mutante) -> str:
    originales: dict[str, bytes] = {}
    for fichero, viejo, _ in m.cambios:
        if fichero not in originales:
            originales[fichero] = (RAIZ / fichero).read_bytes()
    textos = {f: b.decode("utf-8") for f, b in originales.items()}
    for fichero, viejo, nuevo in m.cambios:
        n = textos[fichero].count(viejo)
        if n != 1:
            return f"DUDOSO    patron encontrado {n} veces en {fichero} (se exige 1)"
        textos[fichero] = textos[fichero].replace(viejo, nuevo, 1)
    MARCADOR.write_text(json.dumps({f: (b.hex(), _sha(b)) for f, b in originales.items()}), "ascii")
    try:
        for fichero, texto in textos.items():
            (RAIZ / fichero).write_bytes(texto.encode("utf-8"))
        codigo, salida = _pytest()
    finally:
        for fichero, original in originales.items():
            (RAIZ / fichero).write_bytes(original)
            if _sha((RAIZ / fichero).read_bytes()) != _sha(original):
                raise SystemExit(f"ABORTADO: restauracion fallida en {fichero}")
        MARCADOR.unlink()
    if "passed" not in salida and "failed" not in salida and "error" not in salida:
        return "DUDOSO    pytest no llego a ejecutarse"
    fallos = [l for l in salida.splitlines() if l.startswith(("FAILED", "ERROR"))]
    if codigo == 0:
        return "VIVO      ningun test cae"
    if not any(m.discriminante in l for l in fallos):
        return f"DUDOSO    caen {len(fallos)} tests pero no el discriminante"
    return f"MUERTO    fallos={len(fallos)}"


def main(argv: list[str]) -> int:
    _recuperar_si_aborto_previo()
    _arbol_limpio()
    codigo, _ = _pytest()
    if codigo != 0:
        raise SystemExit("ABORTADO: la suite de F04-D071 no esta verde antes de mutar.")
    seleccion = [m for m in MUTANTES if not argv or m.ident in argv]
    print("=== F04-D071 · MUTANTES (MANT de OP-21) ===")
    muertos = 0
    for m in seleccion:
        veredicto = ejecutar(m)
        muertos += veredicto.startswith("MUERTO")
        print(f"  {m.ident:7}  {veredicto}   [{m.invariante}] -> {m.discriminante}")
    _arbol_limpio()
    print(f"RESULTADO: {muertos}/{len(seleccion)} muertos")
    return 0 if muertos == len(seleccion) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
