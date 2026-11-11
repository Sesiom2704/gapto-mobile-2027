#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_01_b1.py
# Ruta: scripts/mutantes/f06_01_b1.py
# Descripcion: Arnes de mutacion de F06-01 B1 · Propiedad (N1; mandato del
#   lote 12, Parte B.4; contratos R1 v0.8 Parte I y v0.7 C-PROP-01..04).
#   Mutantes por guarda: suma 100, porcentaje > 0, naturaleza del cotitular,
#   tercero ajeno, `desde` >= adquisicion (alta y cambio), replay exacto
#   (nunca inclusion), version (y replay ANTES que version), aislamiento
#   (PK de otro owner), DESCONOCIDA sin filas, YO fuera de DE_OTROS, cierre en
#   desde - 1, retroactivo, segundo programado, vuelta a DESCONOCIDA,
#   titularidad vista (PR1-04), reparto anterior, adquisicion posterior,
#   habitaciones en uso, COMPRA reservada y
#   lecturas (redondeo, futura, fiscal).
#
#   Cada mutante retira o altera UNA guarda y declara sus DISCRIMINANTES
#   (nodos de test_231/test_232 que deben caer); solo se ejecutan esos nodos
#   y el mutante no se da por muerto si no cae ninguno de ellos.
#   Guardas D-181 (como f04d046_r2): E/S byte a byte, patron que aparece
#   EXACTAMENTE una vez, marcador previo con el contenido original para
#   recuperarse de una ejecucion abortada y restauracion verificada por
#   SHA-256 tambien si pytest aborta. Diferencia declarada: el arbol de la
#   rama aun no tiene commit, asi que en vez de exigir `git status` vacio se
#   exige que sea IDENTICO antes y despues y que los ficheros mutados
#   recuperen su SHA-256 de partida.
#   Requiere GAPTO_TEST_DATABASE_URL (base desechable) y, para los
#   discriminantes de test_232, GAPTO_B1_CONCURRENCIA=1.
# Uso:
#   python scripts/mutantes/f06_01_b1.py            # todos
#   python scripts/mutantes/f06_01_b1.py B1-M03     # subconjunto
# Version: 0.1.0 (F06-01 B1, lote 12)
# Version: 0.2.0 (F03 · N1 de 0352, mandato v1.4; Alcance 7): B1-M31 (guarda de C-PROP-02 frente a la
#   declaracion de adquisicion de 0352, AJ-0352-05) y B1-M32 (las seis columnas de 0352 fuera de
#   COLUMNAS_PROPIEDAD, AJ-0352-08), con discriminantes en test_235. Los 30 anteriores no cambian.
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
T231 = "tests/api/test_231_f06_01_b1_propiedades.py"
T232 = "tests/api/test_232_f06_01_b1_concurrencia_serial.py"
T235 = "tests/api/test_235_f06_01_0352_guarda_c_prop_02.py"
REPO = "backend/app/propiedades/repositorio.py"
MARCADOR = RAIZ / ".mutante_f06_01_b1_en_curso"


def neg(caso: str) -> str:
    return f"{T231}::test_alta_negativos_por_capa_con_estado_identico[{caso}]"


def t(nombre: str) -> str:
    return f"{T231}::{nombre}"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    fichero: str
    viejo: str
    nuevo: str
    discriminantes: tuple[str, ...]


MUTANTES = (
    Mutante("B1-M01", "La suma de la titularidad es exactamente 100 (SUMA_NO_CUADRA antes de escribir)", SRV,
            "    if sum((p.porcentaje for p in partes), Decimal(0)) != CIEN:\n",
            "    if False:\n", (neg("suma 99,9999"),)),
    Mutante("B1-M02", "Porcentaje 0 -> PARTICIPACION_NO_POSITIVA", SRV,
            "    if any(p.porcentaje <= 0 for p in partes):\n",
            "    if any(p.porcentaje < 0 for p in partes):\n", (neg("porcentaje 0"),)),
    Mutante("B1-M03", "Naturaleza del cotitular comprobada (Q-10)", SRV,
            "        if t[\"naturaleza\"] not in NATURALEZAS_TITULARIDAD:\n",
            "        if False:\n", (neg("tercero ORGANISMO"), neg("tercero sin naturaleza"))),
    Mutante("B1-M04", "Politica de la titularidad cerrada en PERSONA/EMPRESA", SRV,
            "NATURALEZAS_TITULARIDAD = frozenset({repo_act.NATURALEZA_PERSONA, repo_act.NATURALEZA_EMPRESA})\n",
            "NATURALEZAS_TITULARIDAD = frozenset({repo_act.NATURALEZA_PERSONA, repo_act.NATURALEZA_EMPRESA, "
            "\"ORGANISMO\"})\n", (neg("tercero ORGANISMO"),)),
    Mutante("B1-M05", "Tercero ausente o de otro owner -> TERCERO_NO_DISPONIBLE", SRV,
            "        if t is None or not t[\"enabled\"]:\n",
            "        if t is not None and not t[\"enabled\"]:\n", (neg("tercero de otro owner"),)),
    Mutante("B1-M06", "Alta: desde >= fecha_adquisicion", SRV,
            "    if desde is not None and datos[\"fecha_adquisicion\"] is not None and desde < datos[\"fecha_adquisicion\"]:\n",
            "    if False:\n", (neg("desde anterior a la adquisicion"),)),
    Mutante("B1-M07", "Cambio de titularidad: desde >= fecha_adquisicion", SRV,
            "    if raiz[\"fecha_adquisicion\"] is not None and desde < raiz[\"fecha_adquisicion\"]:\n",
            "    if False:\n", (t("test_titularidad_negativos"),)),
    Mutante("B1-M08", "Replay por igualdad EXACTA del contenido sellado (nunca inclusion)", SRV,
            "        if sellada == {\"operacion\": operacion, \"contenido\": contenido}:\n",
            "        if sellada is not None and sellada.get(\"operacion\") == operacion:\n",
            (t("test_alta_inclusion_no_es_replay"), t("test_alta_idempotencia_por_igualdad_exacta"))),
    Mutante("B1-M09", "Editar: version comprobada", SRV,
            "    if raiz[\"row_version\"] != row_version:\n        return Rechazo(VERSION_DESFASADA)\n"
            "    actual = repo.leer(sesion, entidad_id)\n",
            "    actual = repo.leer(sesion, entidad_id)\n", (t("test_editar_omitido_null_y_version"),)),
    Mutante("B1-M10", "Cambio de titularidad: version comprobada", SRV,
            "    if raiz[\"row_version\"] != row_version:\n        return Rechazo(VERSION_DESFASADA)\n    vigentes_hoy",
            "    vigentes_hoy", (t("test_titularidad_negativos"),)),
    Mutante("B1-M11", "Valoracion: version comprobada", SRV,
            "    if raiz[\"row_version\"] != row_version:\n        return Rechazo(VERSION_DESFASADA)\n"
            "    antes = repo.snapshot(sesion, propiedad_id)\n    try:\n",
            "    antes = repo.snapshot(sesion, propiedad_id)\n    try:\n",
            (t("test_valoraciones_alta_replay_y_negativos"),)),
    Mutante("B1-M12", "Replay ANTES que version, con la version que vio el cliente", SRV,
            "    replay = _replay(sesion, valoracion_id, OP_VALORACION, propiedad_id, contenido)\n",
            "    if raiz[\"row_version\"] != row_version:\n        return Rechazo(VERSION_DESFASADA)\n"
            "    replay = _replay(sesion, valoracion_id, OP_VALORACION, propiedad_id, contenido)\n",
            (t("test_valoraciones_alta_replay_y_negativos"),)),
    Mutante("B1-M13", "Aislamiento: UUID de valoracion de otro owner -> IDENTIDAD_REUTILIZADA (sin revelar)", SRV,
            "        return Rechazo(IDENTIDAD_REUTILIZADA)  # id de otro owner: invisible por RLS, sin revelarlo\n",
            "        raise\n", (t("test_valoraciones_alta_replay_y_negativos"),)),
    Mutante("B1-M14", "Aislamiento: UUID de alta de otro owner -> IDENTIDAD_REUTILIZADA (sin revelar)", SRV,
            "        if exc.diag.constraint_name not in (\"pk_entidades\", \"pk_propiedades\", "
            "\"pk_entidad_participaciones\"):\n            raise\n",
            "        raise\n", (t("test_alta_uuid_de_otra_entidad_otro_owner_y_otra_ruta"),)),
    Mutante("B1-M15", "DESCONOCIDA no crea filas", SRV,
            "    if modo == \"DESCONOCIDA\":\n        return []\n",
            "    if modo == \"DESCONOCIDA\":\n        return [(self_id, CIEN)]\n", (t("test_alta_cuatro_modos"),)),
    Mutante("B1-M16", "YO no puede estar en DE_OTROS", SRV,
            "    if modo == \"DE_OTROS\" and (len(partes) < 1 or hay_yo):\n",
            "    if modo == \"DE_OTROS\" and len(partes) < 1:\n", (neg("de otros con yo"),)),
    Mutante("B1-M17", "Cierre en desde - 1 (no en desde)", SRV,
            "repo.cerrar_participacion(sesion, f[\"id\"], desde - dt.timedelta(days=1))",
            "repo.cerrar_participacion(sesion, f[\"id\"], desde)",
            (t("test_titularidad_frontera_cierre_y_programado"),)),
    Mutante("B1-M18", "Fecha pasada -> CAMBIO_RETROACTIVO_SIN_POLITICA", SRV,
            "    if desde < hoy:\n", "    if False:\n", (t("test_titularidad_negativos"),)),
    Mutante("B1-M19", "Segundo cambio programado rechazado", SRV,
            "    if any(f[\"vigente_desde\"] > hoy for f in filas):\n", "    if False:\n",
            (t("test_titularidad_frontera_cierre_y_programado"), t("test_titularidad_negativos"))),
    Mutante("B1-M20", "No se vuelve a DESCONOCIDA", SRV,
            "            return Rechazo(NO_PERMITIDA_EN_ESTADO)  # no se vuelve a DESCONOCIDA (v0.7 C-PROP-03)\n",
            "            pass\n", (t("test_titularidad_negativos"),)),
    Mutante("B1-M21", "PR1-04: la titularidad vista se compara completa bajo el lock", SRV,
            "    if vigentes_hoy != sorted(vista_cliente):\n", "    if False:\n",
            (t("test_titularidad_vista_desfasada_por_porcentaje"),)),
    Mutante("B1-M22", "El cambio empieza despues del reparto vigente", SRV,
            "    if any(f[\"vigente_desde\"] >= desde for f in abiertas):\n",
            "    if any(f[\"vigente_desde\"] > desde for f in abiertas):\n",
            (t("test_titularidad_frontera_cierre_y_programado"),)),
    Mutante("B1-M23", "Editar: adquisicion posterior a la titularidad rechazada", SRV,
            "        if inicio is not None and cambios[\"fecha_adquisicion\"] > inicio:\n", "        if False:\n",
            (t("test_editar_fecha_adquisicion_y_habitaciones"),)),
    Mutante("B1-M24", "Editar: habitaciones por debajo de un contrato vivo rechazadas", SRV,
            "        if maxima is not None and (cambios[\"habitaciones\"] is None or cambios[\"habitaciones\"] < maxima):\n",
            "        if False:\n", (t("test_editar_fecha_adquisicion_y_habitaciones"),)),
    Mutante("B1-M25", "Editar: campos no anulables con null rechazados", SRV,
            "    if any(campos[c] is None for c in campos if c not in ANULABLES):\n", "    if False:\n",
            (f"{T231}::test_editar_negativos",)),
    Mutante("B1-M26", "COMPRA reservada a la compra", SRV,
            "    if valores.get(\"metodo\") == METODO_COMPRA:\n", "    if False:\n",
            (t("test_valoraciones_alta_replay_y_negativos"),)),
    Mutante("B1-M27", "Cuota: redondeo determinista ROUND_HALF_UP", LEC,
            ".quantize(CENTIMO, rounding=ROUND_HALF_UP)", ".quantize(CENTIMO)",
            (t("test_lecturas_precedencia_y_cuota"),)),
    Mutante("B1-M28", "Una valoracion futura no cuenta", LEC,
            "                  and v[\"fecha_valoracion\"] <= hoy]\n", "                  ]\n",
            (t("test_lecturas_precedencia_y_cuota"),)),
    Mutante("B1-M29", "La referencia fiscal nunca desplaza al estimado", LEC,
            "ESTIMADO = (\"MERCADO\", \"TASACION\", \"MANUAL\")\n",
            "ESTIMADO = (\"MERCADO\", \"TASACION\", \"MANUAL\", \"FISCAL_REFERENCIA\")\n",
            (t("test_lecturas_precedencia_y_cuota"),)),
    Mutante("B1-M30", "Alta concurrente con la misma intencion: replay tras la PK (no rechazo)", SRV,
            "        replay = _replay(sesion, entidad_id, OP_ALTA, entidad_id, contenido)\n        if replay is True:\n"
            "            return Resultado(propiedad=_vista(sesion, entidad_id, hoy), idempotente=True)\n"
            "        return Rechazo(IDENTIDAD_REUTILIZADA)\n",
            "        return Rechazo(IDENTIDAD_REUTILIZADA)\n",
            (f"{T232}::test_k1_dos_altas_misma_intencion",)),
    Mutante("B1-M31", "0352 (AJ-0352-05): fecha de adquisicion posterior al corte declarado rechazada", SRV,
            "        if corte is not None and cambios[\"fecha_adquisicion\"] > corte:\n", "        if False:\n",
            (f"{T235}::test_guarda_rechaza_fecha_posterior_al_corte_sin_escribir_nada",
             f"{T235}::test_guarda_no_aplica_sin_declaracion_de_adquisicion")),
    Mutante("B1-M32", "0352 (AJ-0352-08): las seis columnas de 0352 no se escriben por C-PROP-01/02", REPO,
            "    \"banos\", \"tiene_garaje\", \"tiene_trastero\", \"referencia_catastral\", \"incluir_en_rentabilidad\", \"notas\",\n)\n",
            "    \"banos\", \"tiene_garaje\", \"tiene_trastero\", \"referencia_catastral\", \"incluir_en_rentabilidad\", \"notas\",\n"
            "    \"coste_adquisicion_declarado_completo\",\n)\n",
            (f"{T235}::test_aj0352_08_columnas_fuera_de_editables_y_columnas_propiedad",
             f"{T235}::test_aj0352_08_barrera_servicio_editar[coste_adquisicion_declarado_completo]")),
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
        [sys.executable, "-m", "pytest", *nodos, "-q", "-p", "no:cacheprovider", "--rootdir=tests/api", "-rf"],
        cwd=RAIZ, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return proceso.returncode, proceso.stdout + proceso.stderr


def ejecutar(m: Mutante) -> str:
    ruta = RAIZ / m.fichero
    original = ruta.read_bytes()
    sha_original = _sha(original)
    texto = original.decode("utf-8")
    apariciones = texto.count(m.viejo)
    if apariciones != 1:
        return f"DUDOSO    patron encontrado {apariciones} veces (se exige 1)"
    MARCADOR.write_text(f"{m.fichero}\n{original.hex()}", "ascii")
    try:
        ruta.write_bytes(texto.replace(m.viejo, m.nuevo, 1).encode("utf-8"))
        codigo, salida = _pytest(m.discriminantes)
    finally:
        ruta.write_bytes(original)
        if _sha(ruta.read_bytes()) != sha_original:
            raise SystemExit(f"ABORTADO: restauracion fallida en {m.fichero}")
        MARCADOR.unlink()
    if "passed" not in salida and "failed" not in salida:
        return "DUDOSO    pytest no llego a ejecutarse"
    fallos = [linea for linea in salida.splitlines() if linea.startswith("FAILED")]
    if codigo == 0:
        return "VIVO      ningun discriminante cae"
    nombres = [d.split("::", 1)[1] for d in m.discriminantes]
    if not any(n in linea for n in nombres for linea in fallos):
        return f"DUDOSO    caen {len(fallos)} tests pero no un discriminante"
    return f"MUERTO    fallos={len(fallos)}"


def main(argv: list[str]) -> int:
    _recuperar_si_aborto_previo()
    seleccion = [m for m in MUTANTES if not argv or m.ident in argv]
    arbol = _estado_arbol()
    nodos = tuple(dict.fromkeys(d for m in seleccion for d in m.discriminantes))
    codigo, salida = _pytest(nodos)
    if codigo != 0:
        print(salida[-3000:])
        raise SystemExit("ABORTADO: los discriminantes no estan verdes antes de mutar.")
    print("=== F06-01 B1 · MUTANTES ===")
    resultados, muertos = [], 0
    for m in seleccion:
        veredicto = ejecutar(m)
        muertos += veredicto.startswith("MUERTO")
        resultados.append({"id": m.ident, "invariante": m.invariante, "fichero": m.fichero,
                           "veredicto": veredicto.split()[0], "detalle": veredicto})
        print(f"  {m.ident:7}  {veredicto}   [{m.invariante}]", flush=True)
    if _estado_arbol() != arbol:
        raise SystemExit("ABORTADO: el estado del arbol cambio durante la tirada.")
    salida_json = os.environ.get("GAPTO_B1_MUTANTES_JSON")
    if salida_json:
        pathlib.Path(salida_json).write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"RESULTADO: {muertos}/{len(seleccion)} muertos")
    return 0 if muertos == len(seleccion) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
