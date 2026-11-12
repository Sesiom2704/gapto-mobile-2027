#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f06_t1_b3_cliente.py
# Ruta: scripts/dev/mutantes_f06_t1_b3_cliente.py
# Descripcion: Arnes de mutacion del CLIENTE de B3 · Obras y gastos de una propiedad (F06 T1-F06 B3 N1; mandato §7.3:
#   M-DM02-14 «Corregir clase» ofrecida con deuda, la fila patrimonial de Actividad y las guardas de cliente de
#   §III.1bis 3-5, 8bis y 8ter: M-DM02-01, 04, 05, 06, 08, 09, 10, 11, 12 y 16, M-ID-13 y las de la correccion de clase).
#   Mismo motor que scripts/dev/mutantes_f06_t1_b2_cliente.py: texto exacto con UNA aparicion (si no,
#   NO_CLASIFICABLE y para), journal (marcador con el original) antes del primer byte, restauracion verificada por
#   SHA-256, preflight de los discriminantes (Jest) y veredicto a disco en cuanto se conoce (GAPTO_B3C_VEREDICTOS).
#   Un mutante solo es MUERTO si cae uno de SUS tests. Con --comprobar solo verifica que cada patron aparece una vez
#   (sin mutar ni ejecutar Jest).
# Uso: python scripts/dev/mutantes_f06_t1_b3_cliente.py [--comprobar] [ID ...]
# Version: 0.1.0 (F06 T1-F06 B3 N1)
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
DOM = "mobile/src/domain/gasto_propiedad.ts"
PANT = "mobile/src/screens/GastoPropiedadScreen.tsx"
ACT = "mobile/src/domain/actividad.ts"
TIT = "mobile/src/domain/titulos_dia.ts"
ACTP = "mobile/src/screens/ActividadScreen.tsx"
T_GP = "__tests__/gasto_propiedad.test.tsx"
T_CC = "__tests__/correccion_clase.test.tsx"
T_AP = "__tests__/actividad_patrimonial.test.tsx"
MARCADOR = RAIZ / ".mutante_f06_t1_b3_cliente_en_curso"


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
    Mutante("M-DM02-14", "Con deuda (o sin intencion vigente) no se ofrece «Corregir la clase» (8quater, O9.17)", PANT,
            "{ofreceCorregir(l) ? <BotonTexto",
            "{ofreceCorregir(l) || l.con_deuda ? <BotonTexto",
            T_CC, ("O9.17",)),
    Mutante("M-ID-13c", "El cliente solo ofrece corregir con intencion_correccion_id (O5.33)", DOM,
            "export const ofreceCorregir = (l: LecturaGastoPropiedad) => l.intencion_correccion_id !== null;",
            "export const ofreceCorregir = (l: LecturaGastoPropiedad) => l.estado === 'ACTIVO';",
            T_CC, ("O5.33",)),
    Mutante("M-DM02-16", "derechos_confirmados = exactamente lo mostrado en la confirmacion (8bis, O9.23)", DOM,
            "    derechos_confirmados: mostrados.map((d) => ({ actor_id: d.actor_id, importe: d.importe })),",
            "    derechos_confirmados: partes.filter((x) => !x.yo).map((x) => ({ actor_id: x.actor_id, importe: repartirImporte(b.importe, partes)[x.actor_id] })),",
            T_GP, ("O9.15", "O9.18")),
    Mutante("M-DM02-06", "Deuda por defecto «Si» con cuenta solo tuya y persona (DM-02/DM-07, O9.14)", DOM,
            "return prop?.cuenta?.solo_mia ? { me_debe: 'SI', importe: '' } : { me_debe: null, importe: '' };",
            "return prop?.cuenta?.solo_mia ? { me_debe: 'NO', importe: '' } : { me_debe: null, importe: '' };",
            T_GP, ("O9.14",)),
    Mutante("M-DM02-08", "Cuenta compartida: sin preseleccion de la deuda (8ter, O9.16)", DOM,
            "return prop?.cuenta?.solo_mia ? { me_debe: 'SI', importe: '' } : { me_debe: null, importe: '' };",
            "return prop?.cuenta ? { me_debe: 'SI', importe: '' } : { me_debe: null, importe: '' };",
            T_GP, ("O9.16",)),
    Mutante("M-DM02-10", "Cuenta compartida: el importe del derecho se teclea, sin valor previo (8ter, O9.16)", PANT,
            "valor={b.deuda[x.actor_id]?.importe ?? ''}",
            "valor={b.deuda[x.actor_id]?.importe || (imp[x.actor_id] ?? '')}",
            T_GP, ("O9.16",)),
    Mutante("M-DM02-09", "El derecho es por la parte del cotitular, no por el total (O9.14)", DOM,
            "importe: cuentaCompartida(prop) ? importeTexto(b.deuda[x.actor_id].importe) : imp[x.actor_id] }));",
            "importe: cuentaCompartida(prop) ? importeTexto(b.deuda[x.actor_id].importe) : importeTexto(b.importe) }));",
            T_GP, ("O9.14",)),
    Mutante("M-DM02-01", "La propuesta es la titularidad de la PROPIEDAD; la cuenta pagadora no entra (O9.8)", DOM,
            "partes: (prop?.partes ?? []).map((x) => ({ actor_id: x.actor_id, porcentaje: x.porcentaje })) } };",
            "partes: [...(prop?.partes ?? []).map((x) => ({ actor_id: x.actor_id, porcentaje: x.porcentaje })), ...(prop?.cuenta?.compartida_con ?? []).map((a) => ({ actor_id: a, porcentaje: '50.0000' }))] } };",
            T_GP, ("O9.8",)),
    Mutante("M-DM02-04", "Si el usuario cambia el reparto no se envia SEGUN_TITULARIDAD_ACEPTADA (O9.10)", DOM,
            "  if (e === null || e.modo === 'NO_LO_SE') return { modo: 'NO_LO_SE' };\n  if (e.modo === 'MANUAL')\n",
            "  if (e === null) return { modo: 'NO_LO_SE' };\n  if (e.modo === 'MANUAL')\n",
            T_GP, ("O9.10",)),
    Mutante("M-DM02-05", "Sin titularidad en la fecha no se preselecciona nada, nunca YO 100 (O9.12)", DOM,
            "(hayPropuesta(prop) ? { modo: 'TITULARIDAD' } : null);",
            "(hayPropuesta(prop) ? { modo: 'TITULARIDAD' } : { modo: 'MANUAL', partes: { yo: '100' } });",
            T_GP, ("O9.12",)),
    Mutante("M-DM02-11c", "«Te debe su parte» no se ofrece a una EMPRESA (8ter, O9.18)", DOM,
            "  if (x.naturaleza !== 'PERSONA') return false;\n",
            "  if (x.naturaleza === null) return false;\n",
            T_GP, ("O9.18",)),
    Mutante("M-DM02-12c", "La mejora historica (sin pago) no lleva deuda (8ter, O9.20)", DOM,
            "    atribucion: atribucionWire(e, prop, fecha) };",
            "    atribucion: atribucionWire(e, prop, fecha), deuda: (prop?.partes ?? []).filter((x) => !x.yo).map((x) => ({ actor_id: x.actor_id, me_debe: 'SI' })) } as PayloadMejoraHistorica;",
            T_GP, ("O9.20",)),
    Mutante("MC-DESF-03", "ATRIBUCION_PROPUESTA_DESFASADA: intencion nueva y propuesta releida", PANT,
            "      intencion.current = p.nuevoId();\n      setB((x) => ({ ...x, repartoTocado: false, deudaTocada: false }));\n",
            "      setB((x) => ({ ...x, repartoTocado: false, deudaTocada: false }));\n",
            T_GP, ("ATRIBUCION_PROPUESTA_DESFASADA",)),
    Mutante("MC-CC-01", "Correccion: «¿Cuenta para el presupuesto?» sin valor previo (AJ-05)", DOM,
            "export const seleccionInicial = (): SeleccionCorreccion => ({ clase: null, categoriaId: null, presupuestable: null, motivo: '' });",
            "export const seleccionInicial = (): SeleccionCorreccion => ({ clase: null, categoriaId: null, presupuestable: true, motivo: '' });",
            T_CC, ("L-5",)),
    Mutante("MC-CC-02", "Correccion: comparacion_vista = la leida (AJ-08)", DOM,
            "presupuestable: gasto ? s.presupuestable : null, comparacion_vista: comparacion };",
            "presupuestable: gasto ? s.presupuestable : null, comparacion_vista: { ...comparacion, resultado_mes_delta_despues: '0.00' } };",
            T_CC, ("L-5", "dominio")),
    Mutante("MC-ACT-01", "Actividad: la fila patrimonial lleva signo «−» (R1 v0.8 §II.5)", ACT,
            "  if (esPatrimonial(r.tipo)) return importePatrimonial(r.importe_total ?? '0');\n",
            "",
            T_AP, ("signo",)),
    Mutante("MC-ACT-02", "Actividad: nombre propio de la compra, del gasto de la compra y de la mejora", TIT,
            "  if (patrimonial) return patrimonial;\n",
            "",
            T_AP, ("nombre",)),
    Mutante("MC-ACT-03", "Actividad: «no es gasto del mes» por el tipo del HECHO (HF-14)", ACT,
            "  } else if (esPatrimonial(r.tipo)) {\n",
            "  } else if (esPatrimonial(r.tipo) && false) {\n",
            T_AP, ("etiqueta",)),
    Mutante("MC-ACT-04", "Actividad: icono de propiedad en la fila patrimonial", ACTP,
            "  const patrimonial = iconoPatrimonial(f.tipo);\n",
            "  const patrimonial = null as string | null;\n",
            T_AP, ("pantalla",)),
)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _jest(test: str, patrones: tuple[str, ...]) -> tuple[int, str]:
    patron = "|".join(p.replace("(", "\\(").replace(")", "\\)").replace("+", "\\+").replace(".", "\\.") for p in patrones)
    npx = "npx.cmd" if os.name == "nt" else "npx"
    r = subprocess.run([npx, "jest", test, "-t", patron, "--ci"], cwd=MOVIL, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def _recuperar() -> None:
    if MARCADOR.exists():
        ruta_rel, original_hex = MARCADOR.read_text("ascii").split("\n", 1)
        (RAIZ / ruta_rel).write_bytes(bytes.fromhex(original_hex.strip()))
        MARCADOR.unlink()
        raise SystemExit(f"ABORTADO: mutacion a medias en {ruta_rel}; restaurada.")


def _a_disco(reg: dict) -> None:
    destino = os.environ.get("GAPTO_B3C_VEREDICTOS")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")


def main(argv: list[str]) -> int:
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
