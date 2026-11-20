#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_t2_cat_viv.py
# Ruta: scripts/mutantes/f06_t2_cat_viv.py
# Descripcion: Arnes de mutacion de T2-F06 · CAT-VIV (N1 con 0353; mandato v1.1 §9.4: un mutante por guarda).
#   Mismo motor que scripts/mutantes/t2_f06_pag.py (copiado sin cambios de logica salvo que los discriminantes se
#   ejecutan agrupados por suite, cada grupo con su --rootdir: tests/api y tests/database):
#   - sustitucion de texto EXACTO que aparece una sola vez (0 o mas de 1 -> NO_CLASIFICABLE y el arnes PARA);
#   - journal (marcador con el contenido original) ANTES del primer byte mutado; si una ejecucion anterior se
#     corto, restaura y aborta;
#   - restauracion verificada por SHA-256 tras cada mutante (tambien si pytest aborta);
#   - preflight: todos los discriminantes verdes antes de mutar;
#   - veredicto escrito a disco en cuanto se conoce (GAPTO_CATVIV_MUTANTES_VEREDICTOS, una linea JSON por
#     mutante) y salida de pytest de cada mutante (GAPTO_CATVIV_MUTANTES_SALIDA).
#   Un mutante solo se da por MUERTO si cae al menos uno de SUS discriminantes.
#   Mutantes: M-CV-01..16 (salvo M-CV-11, EQUIVALENTE razonado en el handoff: exigir_propiedad se invoca SIEMPRE
#   despues de C-a, que ya tiene la fila FOR SHARE en la misma transaccion; el inventario test_281 lo exige) y
#   M-0353-01..04. Los de 0353 mutan el fichero de la migration y mueren en la aplicacion simulada de test_048.
#   Requiere GAPTO_TEST_DATABASE_URL (base desechable en 0353, formato postgresql://) y GAPTO_CATVIV_CONCURRENCIA=1
#   (discriminante de la bateria serie de M-CV-14).
# Uso:
#   python scripts/mutantes/f06_t2_cat_viv.py              # todos
#   python scripts/mutantes/f06_t2_cat_viv.py M-CV-01      # subconjunto
# Version: 0.1.0 (F06 T2-F06 CAT-VIV N1)
# Version: 0.2.0 (F06 T3 · MANT N1 arneses, AJ-03 del 19-11; enmienda 01): base limpia por mutante (cada llamada a correr clona la plantilla de GAPTO_TEST_DATABASE_URL y la elimina al terminar) y clasificacion de la muerte, con scripts/dev/base_limpia_mutante.py; sin cambios en mutaciones, discriminantes ni restauracion.
# ============================================================
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'dev'))  # MANT N1 arneses
import base_limpia_mutante  # noqa: E402  MANT N1 arneses, AJ-03 del 19-11

RAIZ = pathlib.Path(__file__).resolve().parents[2]
ELE = "backend/app/api/elegibilidad_categoria.py"
VS01 = "backend/app/api/ejecucion_gasto_pagado.py"
REP = "backend/app/api/ejecucion_reparto.py"
REG = "backend/app/api/ejecucion_registro.py"
V3 = "backend/app/api/ejecucion_categoria_v3.py"
PR = "backend/app/api/propiedad_registro.py"
SERV = "backend/app/categorias/servicio.py"
MIG = "migrations/0353_f06_01_categoria_asociada_vivienda.sql"
T280 = "tests/api/test_280_f06_t2_cat_viv_oraculos.py"
T281 = "tests/api/test_281_f06_t2_cat_viv_inventario.py"
T282 = "tests/api/test_282_f06_t2_cat_viv_concurrencia_serial.py"
T154 = "tests/api/test_154_f05_01_inventario_categorias.py"
T048 = "tests/database/test_048_f06_cat_viv_0353.py"
MARCADOR = RAIZ / ".mutante_f06_t2_cat_viv_en_curso"
APLICADA = "test_0353_aplicada_sobre_filas_preexistentes_las_deja_intactas_y_en_false"


def n(fichero: str, nombre: str) -> str:
    return f"{fichero}::{nombre}"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    fichero: str
    viejo: str
    nuevo: str
    discriminantes: tuple[str, ...]


MUTANTES = (
    Mutante("M-CV-01", "la guarda lee la marca", ELE,
            "    if fila is not None and fila[0] and propiedad_id is None:\n",
            "    if False:\n",
            (n(T280, "test_o_cv_05_gasto_pagado_marcado_sin_propiedad_422_sin_escritura"),
             n(T280, "test_o_cv_09_marca_cambiada_entre_abrir_y_enviar"))),
    Mutante("M-CV-02", "marcar no toca los hechos anteriores", SERV,
            '    _auditar(sesion, categoria_id, "VIVIENDA", antes)\n',
            '    _auditar(sesion, categoria_id, "VIVIENDA", antes)\n'
            '    sesion.uno("UPDATE gapto.hecho_efectos SET descripcion = coalesce(descripcion, \'\') || \'*\' '
            'WHERE categoria_id = %s AND %s RETURNING 1", (categoria_id, asociada))\n',
            (n(T280, "test_o_cv_03_y_04_marcar_y_desmarcar_no_reinterpretan_nada"),)),
    Mutante("M-CV-03", "desmarcar no retira vinculos", SERV,
            '    _auditar(sesion, categoria_id, "VIVIENDA", antes)\n',
            '    _auditar(sesion, categoria_id, "VIVIENDA", antes)\n'
            '    sesion.uno("UPDATE gapto.hecho_entidades SET principal = false WHERE tipo_relacion = \'AFECTA_A\' '
            'AND NOT %s AND efecto_id IN (SELECT id FROM gapto.hecho_efectos WHERE categoria_id = %s) RETURNING 1", '
            '(asociada, categoria_id))\n',
            (n(T280, "test_o_cv_03_y_04_marcar_y_desmarcar_no_reinterpretan_nada"),)),
    Mutante("M-CV-04", "el gasto de vivienda no entra en L-COSTE (no es MEJORA)", PR,
            "    return afecta_a(datos, iid, b.propiedad_id)\n",
            "    return afecta_a(dataclasses.replace(datos, hecho=dataclasses.replace(\n"
            "        datos.hecho, tipo_hecho_codigo=\"MEJORA_PATRIMONIAL\")), iid, b.propiedad_id)\n",
            (n(T280, "test_o_cv_06_vs01_con_propiedad_50_50_cuenta_mia_deuda_confirmada"),
             n(T280, "test_o_cv_18_mueble_de_250_cuenta_en_el_mes_y_no_en_el_coste"))),
    Mutante("M-CV-05", "la marca no alcanza a los ingresos (Q-CV-11)", REG,
            "    rechazo = validar_seleccion_categoria(sesion, categoria_id, tipo)\n",
            "    rechazo = validar_seleccion_categoria(sesion, categoria_id, tipo) or __import__(\n"
            "        \"app.api.elegibilidad_categoria\", fromlist=[\"x\"]).exigir_propiedad(sesion, categoria_id, \"GASTO\", None)\n",
            (n(T280, "test_o_cv_08_ingreso_con_categoria_ambos_marcada_sin_propiedad"),)),
    Mutante("M-CV-06", "la marca sube row_version", SERV,
            '    rechazo = _escribir(sesion, lambda: repo.actualizar(sesion, categoria_id, {"asociada_vivienda": asociada}))\n',
            '    rechazo = _escribir(sesion, lambda: sesion.uno("UPDATE gapto.categorias_financieras SET asociada_vivienda'
            ' = %s WHERE id = %s RETURNING id", (asociada, categoria_id)))\n',
            (n(T280, "test_o_cv_02_marcar_y_desmarcar_row_version_auditoria_e_idempotencia"),)),
    Mutante("M-CV-07", "(invertido) la confirmacion de previsiones llama a exigir_propiedad", VS01,
            "                                           intencion.propiedad.propiedad_id if con_propiedad else None)\n",
            "                                           intencion.propiedad.propiedad_id if con_propiedad else (\n"
            "                                               None if intencion.prevision is None else intencion.intencion_id))\n",
            (n(T280, "test_o_cv_10_confirmar_prevision_que_crea_el_hecho_sin_propiedad"),)),
    Mutante("M-CV-08", "0353 restaura FORCE", MIG,
            "ALTER TABLE gapto.categorias_financieras FORCE ROW LEVEL SECURITY;\n\nCOMMENT",
            "COMMENT",
            (n(T048, APLICADA), n(T048, "test_0353_force_rls_restaurado"))),
    Mutante("M-CV-09", "sin parametro de exencion (admite_sin_propiedad)", ELE,
            "                     propiedad_id: uuid.UUID | None) -> str | None:\n",
            "                     propiedad_id: uuid.UUID | None, admite_sin_propiedad: bool = True) -> str | None:\n"
            "    if admite_sin_propiedad:\n        return None\n",
            (n(T281, "test_exigir_propiedad_firma_cerrada_sin_exencion"),
             n(T280, "test_o_cv_10_confirmar_prevision_que_crea_el_hecho_sin_propiedad"))),
    Mutante("M-CV-10", "la correccion de categoria no crea AFECTA_A", V3,
            "        return CategoriaCorregida(hecho_id=hecho_id, hecho_row_version=resultado.hecho_row_version, "
            "idempotente=False)\n",
            "        sesion.uno(\"INSERT INTO gapto.hecho_entidades (hecho_id, entidad_id, tipo_relacion, principal, "
            "owner_user_id) SELECT %s, e.id, 'AFECTA_A', false, e.owner_user_id FROM gapto.entidades e WHERE "
            "e.tipo_entidad = 'PROPIEDAD' LIMIT 1 RETURNING 1\", (hecho_id,))\n"
            "        return CategoriaCorregida(hecho_id=hecho_id, hecho_row_version=resultado.hecho_row_version, "
            "idempotente=False)\n",
            (n(T280, "test_o_cv_13_corregir_categoria_v3_hacia_una_marcada_con_aviso"),)),
    Mutante("M-CV-12", "M3 llama a exigir_propiedad", REP,
            '            rechazo = exigir_propiedad(sesion, intencion.categoria_id, "GASTO",\n'
            "                                       None if bloque is None else bloque.propiedad_id)\n",
            "            rechazo = None\n",
            (n(T280, "test_o_cv_05b_m3_compartido_y_reembolsable_sin_propiedad_422"),
             n(T281, "test_obl_viv_01_inventario_de_writers_de_hechos_cerrado_y_conforme"))),
    Mutante("M-CV-13", "el bloque propiedad conserva C07", VS01,
            "                                             intencion.magnitudes_desconocidas)\n",
            "                                             intencion.magnitudes_desconocidas) if not con_propiedad else None\n",
            (n(T280, "test_o_cv_15_conservacion_c07_tercero_contexto_magnitudes_con_propiedad"),)),
    Mutante("M-CV-14", "marcar_vivienda toma el advisory CATEGORIAS", SERV,
            "    repo.tomar_advisory(sesion)\n    nodo = _nodo(sesion, categoria_id, row_version)\n"
            "    if isinstance(nodo, Rechazo):\n        return nodo\n    if asociada and",
            "    nodo = _nodo(sesion, categoria_id, row_version)\n"
            "    if isinstance(nodo, Rechazo):\n        return nodo\n    if asociada and",
            (n(T154, "test_i8_todo_comando_toma_el_advisory_primero"),
             n(T282, "test_s_cv_05_marcar_frente_a_marcar_misma_version"))),
    Mutante("M-CV-15", "marcar_vivienda audita", SERV,
            '    _auditar(sesion, categoria_id, "VIVIENDA", antes)\n',
            "    pass\n",
            (n(T280, "test_o_cv_02_marcar_y_desmarcar_row_version_auditoria_e_idempotencia"),)),
    Mutante("M-CV-16", "sin bloque, VS-01 no toma INVERSIONES (orden de locks)", VS01,
            "        if intencion.contexto_id is not None or con_propiedad:\n",
            "        if True:\n",
            (n(T280, "test_o_cv_20_sin_bloque_ni_marca_vs01_no_toma_inversiones_ni_propiedad"),)),
    Mutante("M-0353-01", "0353: NOT NULL", MIG,
            "    ADD COLUMN asociada_vivienda boolean NOT NULL DEFAULT false;\n",
            "    ADD COLUMN asociada_vivienda boolean DEFAULT false;\n",
            (n(T048, APLICADA),)),
    Mutante("M-0353-02", "0353: DEFAULT false", MIG,
            "    ADD COLUMN asociada_vivienda boolean NOT NULL DEFAULT false;\n",
            "    ADD COLUMN asociada_vivienda boolean NOT NULL DEFAULT true;\n",
            (n(T048, APLICADA),)),
    Mutante("M-0353-03", "0353: sin GRANT de columna propio", MIG,
            "RESET ROLE;\n\nDO $postcheck_0353$",
            "GRANT SELECT (asociada_vivienda) ON gapto.categorias_financieras TO gapto_backup;\n\n"
            "RESET ROLE;\n\nDO $postcheck_0353$",
            (n(T048, APLICADA),)),
    Mutante("M-0353-04", "0353: el precheck exige el head 0352", MIG,
            "    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a\n"
            "                    WHERE a.attrelid = 'gapto.propiedades'::pg_catalog.regclass\n",
            "    IF FALSE AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a\n"
            "                    WHERE a.attrelid = 'gapto.propiedades'::pg_catalog.regclass\n",
            (n(T048, "test_0353_precheck_exige_la_marca_de_0352"),)),
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


@base_limpia_mutante.por_llamada
def _pytest(nodos: tuple[str, ...]) -> tuple[int, str]:
    """Un pytest por suite (tests/api y tests/database), cada uno con su rootdir; rc != 0 si alguno falla."""
    codigo, salida = 0, ""
    for suite in ("tests/api", "tests/database"):
        grupo = [x for x in nodos if x.startswith(suite + "/")]
        if not grupo:
            continue
        p = subprocess.run(
            [sys.executable, "-m", "pytest", *grupo, "-q", "-p", "no:cacheprovider", f"--rootdir={suite}", "-rfE"],
            cwd=RAIZ, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        codigo = codigo or p.returncode
        salida += p.stdout + p.stderr
    return codigo, salida


def _a_disco(registro: dict) -> None:
    destino = os.environ.get("GAPTO_CATVIV_MUTANTES_VEREDICTOS")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _guardar_salida(m: Mutante, salida: str) -> None:
    carpeta = os.environ.get("GAPTO_CATVIV_MUTANTES_SALIDA")
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
    print("=== T2-F06 CAT-VIV · MUTANTES ===", flush=True)
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
