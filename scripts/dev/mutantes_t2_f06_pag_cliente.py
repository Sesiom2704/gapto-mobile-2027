#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_t2_f06_pag_cliente.py
# Ruta: scripts/dev/mutantes_t2_f06_pag_cliente.py
# Descripcion: Arnes de mutacion del CLIENTE de T2-F06 · PAG «¿Quién pagó?» (mandato PAG §9.3): MC-PAG-01, 03, 05..08
#   (catalogo del laboratorio lab-t2 344b2b3, con textos nuevos sobre el codigo de la rama), MC-PAG-09..15 (mandato) y
#   MC-PAG-16/17 (posiciones_confirmadas = lo mostrado; deuda parcial). Mismo motor que
#   scripts/dev/mutantes_f06_t1_b3_cliente.py (copiado sin cambios de logica): texto exacto con UNA aparicion (si no,
#   NO_CLASIFICABLE y para), journal (marcador con el original) antes del primer byte, restauracion verificada por
#   SHA-256, preflight de los discriminantes (Jest) y veredicto a disco en cuanto se conoce (GAPTO_PAGC_VEREDICTOS).
#   Un mutante solo es MUERTO si cae uno de SUS tests. Con --comprobar solo verifica que cada patron aparece una vez.
# Uso: python scripts/dev/mutantes_t2_f06_pag_cliente.py [--comprobar] [ID ...]
# Version: 0.1.0 (F06 T2-F06 PAG N1)
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
QP = "mobile/src/domain/quien_pago.ts"
DOM = "mobile/src/domain/gasto_propiedad.ts"
PANT = "mobile/src/screens/GastoPropiedadScreen.tsx"
ACT = "mobile/src/domain/actividad.ts"
HOME = "mobile/src/screens/HomeScreen.tsx"
T_QP = "__tests__/quien_pago.test.tsx"
T_GP = "__tests__/gasto_propiedad.test.tsx"
T_RA = "__tests__/reforma_actividad_inicio.test.tsx"
MARCADOR = RAIZ / ".mutante_t2_f06_pag_cliente_en_curso"


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
    Mutante("MC-PAG-01", "«¿Quién pagó?» sin valor por defecto: el usuario lo elige", QP,
            "export const pagoInicial = (): EleccionPago => ({ modo: null,",
            "export const pagoInicial = (): EleccionPago => ({ modo: 'YO_TODO',",
            T_QP, ("antes del reparto",)),
    Mutante("MC-PAG-03", "P3: le debo MI parte (lo que pagué de menos), no lo que el otro pagó de más", QP,
            "      const v = Math.min(saldo, margenLe);\n",
            "      const v = saldo;\n",
            T_QP, ("tres titulares",)),
    Mutante("MC-PAG-05", "Sin deuda propuesta frente a una EMPRESA (Q-PAG-05)", QP,
            "    if (x.naturaleza !== 'PERSONA') continue;\n",
            "",
            T_QP, ("exclusiones",)),
    Mutante("MC-PAG-06", "Con «<cotitular>, todo» no se pide cuenta", QP,
            "export const necesitaCuenta = (e: EleccionPago) => e.modo !== null && e.modo !== 'COTITULAR_TODO';",
            "export const necesitaCuenta = (e: EleccionPago) => e.modo !== null;",
            T_QP, ("Ana, todo",)),
    Mutante("MC-PAG-07", "Fuera de la cuenta compartida se envía C-MEJ-01 v2 (pagos, saldos, posiciones_confirmadas)", PANT,
            "    const cuerpo = compartida\n",
            "    const cuerpo = true\n",
            T_QP, ("Ana, todo", "Cada uno su parte")),
    Mutante("MC-PAG-08", "Detalle: un hecho sin aportaciones es «pago sin declarar»", PANT,
            "{l.pago.declarado ? l.pago.pagos.map(",
            "{true ? l.pago.pagos.map(",
            T_QP, ("tren 1",)),
    Mutante("MC-PAG-09", "El aviso N3 de HT2-01 no sigue visible con «¿Quién pagó?»", PANT,
            '<RotuloGrupo texto="¿Queda algo pendiente?" />',
            '<><RotuloGrupo texto="¿Queda algo pendiente?" /><Text testID="gprop-aviso-a-medias">Si lo pagasteis entre los dos, '
            'todavía no se puede registrar bien.</Text></>',
            T_GP, ("HT2-01 sustituido",)),
    Mutante("MC-PAG-10", "LE_DEBO también preseleccionado (L-08, los dos sentidos)", QP,
            "  return Object.fromEntries(ps.map((x) => [x.actor_id, { marcada: true, importe: x.maximo }]));",
            "  return Object.fromEntries(ps.map((x) => [x.actor_id, { marcada: x.sentido === 'ME_DEBE', importe: x.maximo }]));",
            T_QP, ("L-08", "Ana, todo")),
    Mutante("MC-PAG-11", "No se envía sin la pantalla de confirmación", PANT,
            "onPress={() => setPaso(siguiente[paso])} />",
            "onPress={() => (paso === 'REPARTO' ? void guardar() : setPaso(siguiente[paso]))} />",
            T_QP, ("Ana, todo",)),
    Mutante("MC-PAG-12", "Actividad: «Salió de tu cuenta» cuando difiere de tu parte", ACT,
            "    out.push(Math.round(Number(salida) * 100) === 0 ? 'No salió de tu cuenta' : `Salió de tu cuenta: −${formatearEur(salida)}`);\n",
            "",
            T_RA, ("Salió de tu cuenta",)),
    Mutante("MC-PAG-13", "«Invertido en viviendas» fuera del Resultado y de «Este mes»", HOME,
            "        {/* D-HOME-07 (§4.5): sin línea ni barra de presupuesto mientras F08 no la alimente. */}\n",
            "        {invertido ? <Text testID=\"mes-invertido\">{formatearEur(invertido.invertido)}</Text> : null}\n"
            "        {/* D-HOME-07 (§4.5): sin línea ni barra de presupuesto mientras F08 no la alimente. */}\n",
            T_RA, ("Invertido en viviendas este mes",)),
    Mutante("MC-PAG-14", "«Otra combinación» solo con dos titulares", QP,
            "  if (cotitulares.length === 1) salida.push({ clave: 'mixto',",
            "  if (cotitulares.length >= 1) salida.push({ clave: 'mixto',",
            T_QP, ("tres titulares",)),
    Mutante("MC-PAG-15", "«Corregir la clase» no se ofrece con deuda en cualquier sentido", DOM,
            "export const ofreceCorregir = (l: LecturaGastoPropiedad) => l.intencion_correccion_id !== null;",
            "export const ofreceCorregir = (l: LecturaGastoPropiedad) => l.intencion_correccion_id !== null || "
            "(l.pago?.posiciones ?? []).some((x) => x.sentido === 'LE_DEBO');",
            T_QP, ("detalle: quién pagó",)),
    Mutante("MC-PAG-16", "posiciones_confirmadas = exactamente lo mostrado en la confirmación", PANT,
            "pagosWire(pago, b.importe, partes, b.cuentaId), saldosEnvio, posiciones);",
            "pagosWire(pago, b.importe, partes, b.cuentaId), saldosEnvio, []);",
            T_QP, ("Ana, todo",)),
    Mutante("MC-PAG-17", "Deuda parcial: viaja el importe editado, no el propuesto", QP,
            "{ actor_id: x.actor_id, sentido: p.sentido, importe: importeTexto(d.importe) }",
            "{ actor_id: x.actor_id, sentido: p.sentido, importe: p.maximo }",
            T_QP, ("deuda parcial",)),
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
    destino = os.environ.get("GAPTO_PAGC_VEREDICTOS")
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
