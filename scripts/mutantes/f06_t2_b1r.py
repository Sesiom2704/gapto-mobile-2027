#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_t2_b1r.py
# Ruta: scripts/mutantes/f06_t2_b1r.py
# Descripcion: Arnes de mutacion de F06 T2-F06 · B1-R (reapertura de B1 por L-01 y L-01b; mandato B1-R §8.3):
#   un mutante por guarda de C-PROP-03bis, de la cota del alta (L-01b) y de la lectura de gastos afectados.
#   Motor copiado sin cambios de logica de scripts/mutantes/f06_01_b3.py (que a su vez es el de f06_01_b2.py):
#   - sustitucion de texto EXACTO que aparece una sola vez (0 o mas de 1 -> NO_CLASIFICABLE y el arnes PARA);
#   - journal (marcador con el contenido original) ANTES del primer byte mutado; si una ejecucion anterior se
#     corto, restaura y aborta;
#   - restauracion verificada por SHA-256 tras cada mutante (tambien si pytest aborta);
#   - preflight: todos los discriminantes verdes antes de mutar;
#   - veredicto escrito a disco en cuanto se conoce (GAPTO_B1R_MUTANTES_VEREDICTOS, una linea JSON por mutante)
#     y salida de pytest de cada mutante (GAPTO_B1R_MUTANTES_SALIDA).
#   Un mutante solo se da por MUERTO si cae al menos uno de SUS discriminantes.
#   Semilla: scripts/mutantes/f06_t2_lab.py del laboratorio (lab-t2 6cb1c6f, M-B1R-01..05 con otra numeracion,
#   DIAG); aqui la numeracion es la del mandato §8.3. Los de cliente (MC-B1R-*) van en
#   scripts/dev/mutantes_f06_t2_b1r_cliente.py.
#   Requiere GAPTO_TEST_DATABASE_URL (base desechable, formato postgresql://) y GAPTO_B1_CONCURRENCIA=1
#   (discriminantes de test_261). Se ejecuta sobre una COPIA del repositorio, nunca sobre el worktree de la rama.
# Uso:
#   python scripts/mutantes/f06_t2_b1r.py              # todos
#   python scripts/mutantes/f06_t2_b1r.py M-B1R-07     # subconjunto
# Version: 0.1.0 (F06 T2-F06 · B1-R N1)
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
SRV = "backend/app/propiedades/servicio.py"
LEC = "backend/app/propiedades/lecturas.py"
REPO = "backend/app/propiedades/repositorio.py"
T260 = "tests/api/test_260_f06_t2_b1r_inicio_titularidad.py"
T261 = "tests/api/test_261_f06_t2_b1r_concurrencia_serial.py"
T233 = "tests/api/test_233_f06_01_b1_rls_acl.py"
MARCADOR = RAIZ / ".mutante_f06_t2_b1r_en_curso"


def n(fichero: str, nombre: str) -> str:
    return f"{fichero}::{nombre}"


def o(nombre: str) -> str:
    return n(T260, nombre)


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    fichero: str
    viejo: str
    nuevo: str
    discriminantes: tuple[str, ...]


RECHAZO_AUDITADO = "        return _auditar(sesion, entidad_id, OP_INICIO, None, contenido) or Rechazo({})\n"

MUTANTES = (
    Mutante("M-B1R-01a", "Guarda 8: solo adelantar (relajada a ==: admite retrasar)", SRV,
            "    if nuevo_desde >= inicio:\n", "    if nuevo_desde == inicio:\n",
            (o("test_o_b1r_05_no_anterior_igual_y_posterior"),)),
    Mutante("M-B1R-01b", "Guarda 8: solo adelantar (quitada)", SRV,
            "    if nuevo_desde >= inicio:\n", "    if False:\n",
            (o("test_o_b1r_05_no_anterior_igual_y_posterior"),)),
    Mutante("M-B1R-02", "Guarda 10: no antes de la adquisicion conocida", SRV,
            '    if raiz["fecha_adquisicion"] is not None and nuevo_desde < raiz["fecha_adquisicion"]:\n',
            "    if False:\n", (o("test_o_b1r_06_anterior_a_la_adquisicion"),)),
    Mutante("M-B1R-03", "Guarda 11: sin cambio programado", SRV,
            '    if any(f["vigente_desde"] > hoy for f in filas if f["vigente_desde"] != inicio):\n',
            "    if False:\n", (o("test_o_b1r_07_cambio_programado"),)),
    Mutante("M-B1R-04a", "Guarda 7: inicio_visto comparado con el inicio vigente", SRV,
            "    if inicio_visto != inicio or sorted(", "    if sorted(",
            (o("test_o_b1r_10a_inicio_visto_desfasado"),)),
    Mutante("M-B1R-04b", "Guarda 7: primera_version_vista comparada con las partes de la primera version", SRV,
            '    if inicio_visto != inicio or sorted((f["actor_id"], f["porcentaje"]) for f in primera) != '
            "sorted(primera_version_vista):\n",
            "    if inicio_visto != inicio:\n", (o("test_o_b1r_10b_primera_version_vista_con_otras_partes"),)),
    Mutante("M-B1R-05", "Se mueven solo las filas de la primera version (no todas)", SRV,
            '    ids = sorted((f["id"] for f in primera), key=str)\n',
            '    ids = sorted((f["id"] for f in filas), key=str)\n',
            (o("test_o_b1r_09_dos_versiones_solo_se_mueve_la_primera"),)),
    Mutante("M-B1R-06", "Se mueven TODAS las filas de la primera version (no solo una)", SRV,
            '    ids = sorted((f["id"] for f in primera), key=str)\n',
            '    ids = sorted((f["id"] for f in primera), key=str)[:1]\n',
            (o("test_o_b1r_02_compartida_todas_las_filas_en_un_unico_update"),)),
    Mutante("M-B1R-07", "0P: C-PROP-03bis toma el advisory de intencion como primer recurso", SRV,
            "    bloquear_intencion_propiedad(sesion, intencion_id)  # 0P, primer recurso (F06-D009; B1-R)\n",
            "    pass  # mutante: sin 0P\n",
            (n(T261, "test_o_b1r_13_misma_intencion_en_dos_propiedades"),
             n(T261, "test_o11_23_corregir_inicio_primer_lock_es_el_0p"),
             n(T233, "test_o11_22_funcion_unica_del_0p_y_cuatro_llamadas_en_primer_lugar"))),
    Mutante("M-B1R-08", "row_version + 1 en la correccion", SRV,
            "    repo.subir_version(sesion, entidad_id)\n    _auditar(sesion, entidad_id, OP_INICIO, antes, contenido, motivo)\n",
            "    _auditar(sesion, entidad_id, OP_INICIO, antes, contenido, motivo)\n",
            (o("test_o_b1r_01_solo_mia_a_la_fecha_de_adquisicion"),
             n(T261, "test_o_b1r_14_corregir_inicio_frente_a_cambio_de_titularidad[A-primero]"))),
    Mutante("M-B1R-09a", "Rechazo sin auditoria (INICIO_NO_ANTERIOR)", SRV,
            "        return Rechazo(INICIO_NO_ANTERIOR)  # solo adelantar (Q-B1R-03)\n",
            RECHAZO_AUDITADO.format("INICIO_NO_ANTERIOR"), (o("test_o_b1r_05_no_anterior_igual_y_posterior"),)),
    Mutante("M-B1R-09b", "Rechazo sin auditoria (FECHA_ANTERIOR_INICIO)", SRV,
            '    if raiz["fecha_adquisicion"] is not None and nuevo_desde < raiz["fecha_adquisicion"]:\n'
            "        return Rechazo(FECHA_ANTERIOR_INICIO)\n",
            '    if raiz["fecha_adquisicion"] is not None and nuevo_desde < raiz["fecha_adquisicion"]:\n'
            + RECHAZO_AUDITADO.format("FECHA_ANTERIOR_INICIO"), (o("test_o_b1r_06_anterior_a_la_adquisicion"),)),
    Mutante("M-B1R-09c", "Rechazo sin auditoria (CAMBIO_PROGRAMADO_EXISTENTE)", SRV,
            "        return Rechazo(CAMBIO_PROGRAMADO)  # la propia primera version no es cambio programado (HT2-17)\n",
            RECHAZO_AUDITADO.format("CAMBIO_PROGRAMADO"), (o("test_o_b1r_07_cambio_programado"),)),
    Mutante("M-B1R-09d", "Rechazo sin auditoria (SIN_TITULARIDAD)", SRV,
            "        return Rechazo(SIN_TITULARIDAD)\n", RECHAZO_AUDITADO.format("SIN_TITULARIDAD"),
            (o("test_o_b1r_08_desconocida"),)),
    Mutante("M-B1R-10", "No reatribuye ni toca hechos existentes en la misma transaccion", SRV,
            "    repo.subir_version(sesion, entidad_id)\n    _auditar(sesion, entidad_id, OP_INICIO, antes, contenido, motivo)\n",
            '    sesion.ejecutar("UPDATE gapto.hechos_financieros SET row_version = row_version + 1 WHERE id IN '
            '(SELECT hecho_id FROM gapto.hecho_entidades WHERE entidad_id = %s)", (entidad_id,))\n'
            "    repo.subir_version(sesion, entidad_id)\n    _auditar(sesion, entidad_id, OP_INICIO, antes, contenido, motivo)\n",
            (o("test_o_b1r_04_no_reatribuye_hechos_registrados"),)),
    Mutante("M-B1R-11", "Guarda 9: FECHA_FUTURA en la correccion", SRV,
            "    if nuevo_desde > hoy:\n        return Rechazo(FECHA_FUTURA)\n",
            "    if False:\n        return Rechazo(FECHA_FUTURA)\n", (o("test_o_b1r_20_fecha_futura"),)),
    Mutante("M-B1R-12", "Guarda 11 excluye la propia primera version (HT2-17)", SRV,
            '    if any(f["vigente_desde"] > hoy for f in filas if f["vigente_desde"] != inicio):\n',
            '    if any(f["vigente_desde"] > hoy for f in filas):\n',
            (o("test_o_b1r_21_primera_version_futura_no_es_cambio_programado"),)),
    Mutante("M-B1R-13", "P0001 de la suma 100 traducido a SUMA_NO_CUADRA (nunca 500)", SRV,
            '    if exc.sqlstate == "P0001" and exc.diag.context and _FIRMA_SUMA_100.search(exc.diag.context):\n',
            "    if False:\n",
            (o("test_o_b1r_19_p0001_traducido_sin_cambios_ni_auditoria[p0001_de_la_base]"),)),
    Mutante("M-B1R-14", "Guarda 6: SIN_TITULARIDAD", SRV,
            "    if not filas:\n        return Rechazo(SIN_TITULARIDAD)\n", "",
            (o("test_o_b1r_08_desconocida"),)),
    Mutante("M-B1R-15", "L-01b: el alta rechaza «Desde» futuro (FECHA_FUTURA)", SRV,
            "    if desde is not None and desde > hoy:\n", "    if False:\n",
            (o("test_o_b1r_22_alta_con_desde_futuro_rechazada"),)),
    Mutante("M-B1R-16a", "Afectados: solo fechas anteriores al inicio vigente", REPO,
            '"WHERE h.fecha_hecho < %(inicio)s AND ', '"WHERE TRUE AND ',
            (o("test_o_b1r_23_lectura_de_gastos_afectados_sin_escrituras"),)),
    Mutante("M-B1R-16b", "Afectados: solo hechos vinculados a esta propiedad", REPO,
            "\"FROM gapto.hecho_entidades x WHERE x.entidad_id = %(p)s AND x.tipo_relacion = 'AFECTA_A' ",
            "\"FROM gapto.hecho_entidades x WHERE %(p)s IS NOT NULL AND x.tipo_relacion = 'AFECTA_A' ",
            (o("test_o_b1r_23_lectura_de_gastos_afectados_sin_escrituras"),)),
    Mutante("M-B1R-17", "Replay por el contenido sellado completo (nuevo_desde incluido)", SRV,
            ', "nuevo_desde": _texto(nuevo_desde),\n', ",\n",
            (o("test_o_b1r_12_misma_intencion_con_otro_contenido"),)),
    Mutante("M-B1R-18", "inicio_corregible lo decide el servidor (falso con cambio programado ajeno)", LEC,
            '    return {"inicio": inicio, "inicio_corregible": not programado,\n',
            '    return {"inicio": inicio, "inicio_corregible": True,\n',
            (o("test_o_b1r_07_cambio_programado"),
             o("test_o_b1r_21_primera_version_futura_no_es_cambio_programado"))),
)


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _recuperar_si_aborto_previo() -> None:
    if MARCADOR.exists():
        ruta_rel, original_hex = MARCADOR.read_text("ascii").split("\n", 1)
        (RAIZ / ruta_rel).write_bytes(bytes.fromhex(original_hex.strip()))
        MARCADOR.unlink()
        raise SystemExit(f"ABORTADO: habia una mutacion a medias en {ruta_rel}; restaurada. "
                         "Revisa el arbol y vuelve a ejecutar.")


def _estado_arbol() -> str:
    return subprocess.run(["git", "status", "--porcelain"], cwd=RAIZ, capture_output=True, text=True).stdout


def _pytest(nodos: tuple[str, ...]) -> tuple[int, str]:
    proceso = subprocess.run(
        [sys.executable, "-m", "pytest", *nodos, "-q", "-p", "no:cacheprovider", "--rootdir=tests/api", "-rfE"],
        cwd=RAIZ, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return proceso.returncode, proceso.stdout + proceso.stderr


def _a_disco(registro: dict) -> None:
    destino = os.environ.get("GAPTO_B1R_MUTANTES_VEREDICTOS")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _guardar_salida(m: Mutante, salida: str) -> None:
    carpeta = os.environ.get("GAPTO_B1R_MUTANTES_SALIDA")
    if carpeta:
        pathlib.Path(carpeta).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(carpeta) / f"{m.ident}.log").write_text(salida, encoding="utf-8")


def comprobar_patrones(seleccion) -> list[str]:
    malos = []
    for m in seleccion:
        apariciones = (RAIZ / m.fichero).read_bytes().decode("utf-8").count(m.viejo)
        if apariciones != 1:
            malos.append(f"{m.ident}: patron encontrado {apariciones} veces en {m.fichero}")
    return malos


def ejecutar(m: Mutante) -> str:
    ruta = RAIZ / m.fichero
    original = ruta.read_bytes()
    sha_original = _sha(original)
    texto = original.decode("utf-8")
    MARCADOR.write_text(f"{m.fichero}\n{original.hex()}", "ascii")          # journal antes del primer byte
    try:
        ruta.write_bytes(texto.replace(m.viejo, m.nuevo, 1).encode("utf-8"))
        codigo, salida = _pytest(m.discriminantes)
        _guardar_salida(m, salida)
    finally:
        ruta.write_bytes(original)
        if _sha(ruta.read_bytes()) != sha_original:
            raise SystemExit(f"ABORTADO: restauracion fallida en {m.fichero}")
        MARCADOR.unlink()
    if "passed" not in salida and "failed" not in salida and "error" not in salida:
        return "NO_CLASIFICABLE pytest no llego a ejecutarse"
    fallos = [linea for linea in salida.splitlines() if linea.startswith(("FAILED", "ERROR"))]
    if codigo == 0:
        return "VIVO      ningun discriminante cae"
    nombres = [d.split("::", 1)[1] for d in m.discriminantes]
    if not any(nm in linea for nm in nombres for linea in fallos):
        return f"NO_CLASIFICABLE caen {len(fallos)} tests pero no un discriminante"
    return f"MUERTO    fallos={len(fallos)}"


def main(argv: list[str]) -> int:
    _recuperar_si_aborto_previo()
    seleccion = [m for m in MUTANTES if not argv or m.ident in argv]
    malos = comprobar_patrones(seleccion)
    if malos:
        print("\n".join(malos))
        raise SystemExit("ABORTADO (NO_CLASIFICABLE): patron con 0 o mas de 1 apariciones; no se muta nada.")
    arbol = _estado_arbol()
    nodos = tuple(dict.fromkeys(d for m in seleccion for d in m.discriminantes))
    codigo, salida = _pytest(nodos)
    if codigo != 0:
        print(salida[-4000:])
        raise SystemExit("ABORTADO: los discriminantes no estan verdes antes de mutar.")
    print(f"PREFLIGHT VERDE: {len(nodos)} discriminantes", flush=True)
    print("=== F06 T2-F06 B1-R · MUTANTES ===", flush=True)
    muertos = 0
    for m in seleccion:
        veredicto = ejecutar(m)
        muertos += veredicto.startswith("MUERTO")
        _a_disco({"id": m.ident, "invariante": m.invariante, "fichero": m.fichero, "veredicto": veredicto.split()[0],
                  "detalle": veredicto, "discriminantes": list(m.discriminantes)})
        print(f"  {m.ident:10}  {veredicto}   [{m.invariante}]", flush=True)
        if veredicto.startswith("NO_CLASIFICABLE"):
            raise SystemExit(f"ABORTADO: {m.ident} NO_CLASIFICABLE")
    if _estado_arbol() != arbol:
        raise SystemExit("ABORTADO: el estado del arbol cambio durante la tirada.")
    print(f"RESULTADO: {muertos}/{len(seleccion)} muertos")
    return 0 if muertos == len(seleccion) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
