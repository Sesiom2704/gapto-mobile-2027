#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f04_d050.py
# Ruta: scripts/mutantes/f04_d050.py
# Descripcion: Arnes de mutacion de F04-D050: idempotencia EXACTA de OP-22
#   (contrato A-E). Mismo motor que f04_r3.py (D-181/D-192): cada mutante
#   aplica 1..N sustituciones (cada patron EXACTAMENTE una vez), declara su
#   DISCRIMINANTE y solo cuenta como muerto si cae ese test; marcador
#   durable antes del primer byte mutado, restauracion verificada por
#   SHA-256, preflight verde y arbol limpio exigidos.
# Uso:
#   GAPTO_TEST_DATABASE_URL=... python scripts/mutantes/f04_d050.py [D050-M1 ...]
# Version: 0.1.0
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
    "tests/backend/test_140_f04_r3_op22.py",
    "tests/backend/test_141_f04_r3_contexto.py",
    "tests/backend/test_143_f04_d050_idempotencia_exacta.py",
)
CMP = "backend/app/services/compuesto_service.py"
REP = "backend/app/repositories/compuesto_repository.py"
MARCADOR = RAIZ / ".mutante_f04_d050_en_curso"
T143 = "test_143_f04_d050_idempotencia_exacta.py::"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    cambios: tuple[tuple[str, str, str], ...]  # (fichero, viejo, nuevo)
    discriminante: str


MUTANTES = (
    Mutante("D050-M1", "Contrato C: sin elementos persistidos no declarados (vuelta a la inclusion)",
            ((CMP, "        comprobaciones.append(\n            repo_comp.identidades_del_agregado(sesion, raiz) == self._identidades_declaradas(d)\n        )\n", ""),),
            T143 + "test_a15_reintento_sin_la_aportacion_es_conflicto_sin_mutaciones"),
    Mutante("D050-M2", "Contrato A: el vinculo de posicion solo se exige con importe inicial",
            ((CMP, "            if alta.importe_inicial is not None:\n                comprobaciones.append(\n                    self._campos(\n                        leer(\"hecho_entidades\", alta.vinculo_id),",
                   "            if True:\n                comprobaciones.append(\n                    self._campos(\n                        leer(\"hecho_entidades\", alta.vinculo_id),"),),
            T143 + "test_identico_con_posicion_sin_importe_inicial_es_idempotente"),
    Mutante("D050-M3", "Contrato A: el efecto causal de la posicion forma parte del agregado declarado",
            ((CMP, "        efectos = {e.efecto_id for e in d.efectos} | {a.efecto_id for a in con_delta}\n",
                   "        efectos = {e.efecto_id for e in d.efectos}\n"),),
            T143 + "test_identico_completo_es_idempotente"),
    Mutante("D050-M4", "Contrato A: la relacion que ORIGINA la raiz suplementaria es del agregado",
            ((REP, "    \"hecho_relaciones\": \"hecho_origen_id = %s\",", "    \"hecho_relaciones\": \"hecho_destino_id = %s\","),),
            T143 + "test_identico_suplemento_con_relacion_es_idempotente"),
    Mutante("D050-M5", "Contrato A: el vinculo con la prevision es del agregado declarado",
            ((CMP, "            \"prevision_hechos\": set() if d.prevision is None else {d.prevision.vinculo_id},",
                   "            \"prevision_hechos\": set(),"),),
            T143 + "test_identico_con_prevision_es_idempotente"),
    Mutante("D050-M6", "Contrato C por familia: etiquetas cubiertas por la igualdad exacta",
            ((REP, "    \"hecho_etiquetas\": \"hecho_id = %s\",\n", ""),
             (CMP, "            \"hecho_etiquetas\": {x.registro_id for x in d.contexto.etiquetas},\n", "")),
            T143 + "test_reduccion_de_cualquier_familia_es_conflicto[sin_etiqueta]"),
    Mutante("D050-M7", "Contrato C por familia: atribuciones cubiertas por la igualdad exacta",
            ((REP, "    \"efecto_atribuciones\": \"efecto_id IN (SELECT id FROM gapto.hecho_efectos WHERE hecho_id = %s)\",\n", ""),
             (CMP, "            \"efecto_atribuciones\": {a.atribucion_id for e in d.efectos for a in e.atribuciones},\n", "")),
            T143 + "test_reduccion_de_cualquier_familia_es_conflicto[sin_atribucion]"),
    Mutante("D050-M8", "Contrato C por familia: participantes cubiertos por la igualdad exacta",
            ((REP, "    \"hecho_participantes\": \"hecho_id = %s\",\n", ""),
             (CMP, "            \"hecho_participantes\": {p.participante_id for p in d.participantes},\n", "")),
            T143 + "test_reduccion_de_cualquier_familia_es_conflicto[sin_participante]"),
)


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
        raise SystemExit("ABORTADO: la suite D050 no esta verde antes de mutar.")
    seleccion = [m for m in MUTANTES if not argv or m.ident in argv]
    print("=== F04-D050 · MUTANTES ===")
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
