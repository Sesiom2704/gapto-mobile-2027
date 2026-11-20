#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_t2_a3_0352.py
# Ruta: scripts/mutantes/f06_t2_a3_0352.py
# Descripcion: Arnes de mutacion de F06 T2-F06 · A3-0352 N1 (habilitacion de los consumidores de 0352; mandato A3-0352
#   v1.1 §7.3; contrato A3-0352 v1.1 §8.1 y §9). Mismo motor que scripts/mutantes/f06_01_b2.py:
#   - sustitucion de texto EXACTO que aparece una sola vez (0 o mas de 1 -> NO_CLASIFICABLE y el arnes PARA);
#   - journal (marcador con el contenido original) ANTES del primer byte mutado; si una ejecucion anterior se corto,
#     restaura y aborta;
#   - restauracion verificada por SHA-256 tras cada mutante (tambien si pytest aborta);
#   - preflight: todos los discriminantes verdes antes de mutar;
#   - veredicto a disco en cuanto se conoce (GAPTO_A3_MUTANTES_VEREDICTOS) y salida de pytest por mutante
#     (GAPTO_A3_MUTANTES_SALIDA).
#   Un mutante solo es MUERTO si cae uno de SUS discriminantes. Un mutante con `equivalente` (razonamiento escrito) que
#   sobrevive se clasifica EQUIVALENTE; si cae, MUERTO (el razonamiento era conservador).
#   Mutantes: M-A3-ENV, M-A3-G1/G1b/G2a/G2b/G3, M-A3-R15-01..15 (con variantes), M-A3-INV y M-A3-TXT. Los de cliente
#   (MC-O10-29 invertido, MC-A3-01..04) van en scripts/dev/mutantes_f06_t1_b2_cliente.py; M-O10-29 invertido, en
#   scripts/mutantes/f06_01_b2.py.
#   Requiere GAPTO_TEST_DATABASE_URL (base desechable, formato postgresql://).
# Uso:
#   python scripts/mutantes/f06_t2_a3_0352.py              # todos
#   python scripts/mutantes/f06_t2_a3_0352.py M-A3-ENV     # subconjunto
# Version: 0.1.0 (F06 T2-F06 A3-0352 N1)
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
COMPRA = "backend/app/patrimonio/compra.py"
COMPL = "backend/app/patrimonio/completitud.py"
COSTE = "backend/app/patrimonio/coste.py"
HAB = "backend/app/patrimonio/habilitacion.py"
RUTAS = "backend/app/patrimonio/rutas.py"
T252 = "tests/api/test_252_f06_01_b2_coste_completitud.py"
T256 = "tests/api/test_256_f06_01_b3_correccion_clase.py"
T283 = "tests/api/test_283_f06_t2_a3_0352_oraculos.py"
MARCADOR = RAIZ / ".mutante_f06_t2_a3_0352_en_curso"

R15_COMPL = ("    if completo and ambito == \"ADQUISICION\" and raiz[\"fecha_adquisicion\"] is None:      # R15-a (A3-0352)\n"
             "        return Rechazo(SIN_FECHA_DE_ADQUISICION)\n")
VERSION_COMPL = "    if raiz[\"row_version\"] != row_version:\n        return Rechazo(VERSION_DESFASADA)\n"
FILA_2 = "    if declarado is not True:\n        return (\"NO_DISPONIBLE\" if n == 0 else \"PARCIAL\"), \"SIN_DECLARACION\"\n"
FILA_2BIS = ("    if sin_fecha:                                                               # fila 2 bis (R15-a)\n"
             "        return \"PARCIAL\", \"SIN_FECHA_DE_ADQUISICION\"\n")
SIN_FECHA_COSTE = "        sin_fecha = habilitada and ambito == \"ADQUISICION\" and fecha is None\n"
R15_ANTES_DE_VERSION = ("    if completitud is not None and completitud[\"completo\"] and raiz[\"fecha_adquisicion\"] is None:\n"
                        "        return Rechazo(SIN_FECHA_DE_ADQUISICION)\n")
VERSION_COMPRA = "    if raiz[\"row_version\"] != canon[\"row_version_esperada\"]:\n"
VALIDAR_03 = ("        rechazo = _validar_declaracion(sesion, propiedad_id, raiz, completitud, [fe], hoy)\n"
              "        if rechazo:\n            return Rechazo(rechazo)\n")
RESTO_03 = ("        # la huella vista es la del conjunto ANTERIOR al alta, leida con a_fecha = corte nuevo (HF-09)\n"
            "        _, huella = repo.conjunto_completitud(sesion, propiedad_id, \"ADQUISICION\", completitud[\"fecha_corte\"])\n"
            "        if huella != huella_vista:\n            return Rechazo(VISTA_DESFASADA)\n"
            "    antes = repo.snapshot(sesion, propiedad_id)\n"
            "    _op22(sesion).registrar_hecho_compuesto(sesion.contexto, composicion_hk(partes))\n")


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
    equivalente: str | None = None


MUTANTES = (
    # ------------------------------------------------------------------ interruptor (O10.29-H)
    Mutante("M-A3-ENV", "La habilitacion es una constante de codigo, nunca leida del entorno (R-RF2-07)", HAB,
            "CONSUMIDORES_0352_HABILITADOS = True\n",
            "CONSUMIDORES_0352_HABILITADOS = __import__(\"os\").environ.get(\"GAPTO_0352\", \"1\") == \"1\"\n",
            (n(T252, "test_o10_29_h_a_constante_de_codigo_habilitada"),)),
    Mutante("M-A3-G1", "La ruta de C-PROP-05 conserva su guarda: apagada, no invoca el servicio", RUTAS,
            "        if not habilitacion.consumidores_0352_habilitados():          # O10.29: ruta inaccesible\n"
            "            return rechazo(habilitacion.FUNCION_NO_HABILITADA)\n", "",
            (n(T252, "test_o10_29_h_c_apagado_ruta_inaccesible_sin_invocar_el_servicio"),)),
    Mutante("M-A3-G1b", "C-PROP-05 (servicio) conserva su guarda propia", COMPL,
            "    if not habilitacion.consumidores_0352_habilitados():\n        return Rechazo(habilitacion.FUNCION_NO_HABILITADA)\n",
            "", (n(T252, "test_o10_29_h_c_apagado_ruta_inaccesible_sin_invocar_el_servicio"),)),
    Mutante("M-A3-G2a", "C-COMPRA-01 conserva la guarda de la declaracion (422 ENTRADA_INVALIDA apagada)", COMPRA,
            "    if completitud is not None and not habilitacion.consumidores_0352_habilitados():\n"
            "        return Rechazo(ENTRADA_INVALIDA)               # consumidor provisional de 0352 no habilitado\n", "",
            (n(T252, "test_o10_29_h_c_apagado_declaracion_en_la_compra_y_en_el_gasto_posterior_es_422"),)),
    Mutante("M-A3-G2b", "C-COMPRA-03 conserva la guarda de la declaracion (422 ENTRADA_INVALIDA apagada)", COMPRA,
            "    if (completitud is not None or huella_vista is not None) and not habilitacion.consumidores_0352_habilitados():\n"
            "        return Rechazo(ENTRADA_INVALIDA)               # consumidor provisional de 0352 no habilitado\n", "",
            (n(T252, "test_o10_29_h_c_apagado_declaracion_en_la_compra_y_en_el_gasto_posterior_es_422"),)),
    Mutante("M-A3-G3", "L-COSTE conserva su guarda: apagada, no ve la declaracion", COSTE,
            "    habilitada = habilitacion.consumidores_0352_habilitados()\n", "    habilitada = True\n",
            (n(T252, "test_o10_29_h_c_apagado_l_coste_sin_declaracion_nunca_completo"),)),
    # ------------------------------------------------------------------ R15-a (contrato §2-§3)
    Mutante("M-A3-R15-01", "C-PROP-05 exige la fecha de adquisicion para declarar ADQUISICION", COMPL, R15_COMPL, "",
            (n(T283, "test_o_a3_r15_01_c_prop_05_sin_fecha_422_sin_escribir"),)),
    Mutante("M-A3-R15-02", "C-COMPRA-01/03 exigen la fecha de adquisicion para declarar", COMPRA,
            "    if raiz[\"fecha_adquisicion\"] is None:                                     # R15-a (A3-0352)\n"
            "        return SIN_FECHA_DE_ADQUISICION\n", "",
            (n(T283, "test_o_a3_r15_05_c_compra_01_sin_fecha_nada_escrito"),
             n(T283, "test_o_a3_r15_06_c_compra_03_sin_fecha_nada_escrito"))),
    Mutante("M-A3-R15-03", "En C-PROP-05, R15-a va DESPUES de la version", COMPL, VERSION_COMPL + R15_COMPL,
            R15_COMPL + VERSION_COMPL,
            (n(T283, "test_o_a3_r15_02_precedencia_en_c_prop_05"),)),
    Mutante("M-A3-R15-04", "Retirar no exige la fecha", COMPL,
            "    if completo and ambito == \"ADQUISICION\" and raiz[\"fecha_adquisicion\"] is None:",
            "    if ambito == \"ADQUISICION\" and raiz[\"fecha_adquisicion\"] is None:",
            (n(T283, "test_o_a3_r15_03_retirar_no_exige_fecha"),)),
    Mutante("M-A3-R15-05a", "MEJORAS no exige la fecha (servicio)", COMPL,
            "    if completo and ambito == \"ADQUISICION\" and raiz[\"fecha_adquisicion\"] is None:",
            "    if completo and raiz[\"fecha_adquisicion\"] is None:",
            (n(T283, "test_o_a3_r15_04_mejoras_con_fecha_null_como_hoy"),)),
    Mutante("M-A3-R15-05b", "La fila 2 bis solo existe en ADQUISICION (lectura)", COSTE, SIN_FECHA_COSTE,
            "        sin_fecha = habilitada and fecha is None\n",
            (n(T283, "test_o_a3_r15_04_mejoras_con_fecha_null_como_hoy"),)),
    Mutante("M-A3-R15-06", "L-COSTE tiene la fila 2 bis (PARCIAL SIN_FECHA_DE_ADQUISICION)", COSTE, FILA_2BIS, "",
            (n(T283, "test_o_a3_r15_07_borrar_la_fecha_da_parcial_sin_fecha_y_conserva_corte_y_huella"),)),
    Mutante("M-A3-R15-07", "La fila 2 bis va DESPUES de la fila 2 (sin declaracion gana)", COSTE, FILA_2 + FILA_2BIS,
            FILA_2BIS + FILA_2,
            (n(T283, "test_o_a3_r15_09_precedencia_de_l_coste"),)),
    Mutante("M-A3-R15-08", "L2 compara las versiones de S0 y S2", COSTE,
            "antes[\"row_version\"] == despues[\"row_version\"]", "True",
            (n(T283, "test_o_a3_r15_10c_agotamiento_nunca_completo"),
             n(T283, "test_o_a3_r15_10d_l2_con_commit_real_entre_s0_y_s2"))),
    Mutante("M-A3-R15-09", "El reintento calcula con la ULTIMA muestra, nunca con la descartada", COSTE,
            "        fecha, filas, estable = muestra\n",
            "        fecha, filas, estable = (muestra[0] if intento == 0 else fecha), muestra[1], muestra[2]\n",
            (n(T283, "test_o_a3_r15_10b_recuperacion_calcula_con_la_segunda_muestra"),)),
    Mutante("M-A3-R15-10a", "En C-COMPRA-01, R15-a va DESPUES de la version (discriminante A)", COMPRA,
            "    # INTENCION NUEVA\n" + VERSION_COMPRA, "    # INTENCION NUEVA\n" + R15_ANTES_DE_VERSION + VERSION_COMPRA,
            (n(T283, "test_o_a3_r15_02c_precedencia_en_c_compra_01"),)),
    Mutante("M-A3-R15-10b", "En C-COMPRA-03, R15-a va DESPUES de la version (discriminante A)", COMPRA,
            "        return _respuesta(sesion, propiedad_id, hechos, movimientos, canon[\"atribucion\"], hoy, True)\n"
            + VERSION_COMPRA,
            "        return _respuesta(sesion, propiedad_id, hechos, movimientos, canon[\"atribucion\"], hoy, True)\n"
            + R15_ANTES_DE_VERSION + VERSION_COMPRA,
            (n(T283, "test_o_a3_r15_02c_precedencia_en_c_compra_03"),)),
    Mutante("M-A3-R15-11", "El agotamiento de L2 nunca deja COMPLETO (discriminante C)", COSTE,
            "        if ambito == \"ADQUISICION\" and not estable and estado == \"COMPLETO\":        # agotamiento conservador\n"
            "            estado, motivo = \"PARCIAL\", \"LECTURA_NO_ESTABLE\"\n", "",
            (n(T283, "test_o_a3_r15_10c_agotamiento_nunca_completo"),)),
    Mutante("M-A3-R15-12", "Con la fecha repuesta se evaluan las filas 3-6 (discriminante D)", COSTE, FILA_2BIS,
            FILA_2BIS + "    if ambito == \"ADQUISICION\":\n        return \"COMPLETO\", None\n",
            (n(T283, "test_o_a3_r15_08_reponer_la_fecha_reevalua_las_filas_3_a_6"),)),
    Mutante("M-A3-R15-13", "En C-COMPRA-03 la declaracion se valida ANTES de escribir (discriminante E)", COMPRA,
            VALIDAR_03 + RESTO_03,
            RESTO_03 + "    if completitud is not None and completitud[\"completo\"]:\n" + VALIDAR_03,
            (n(T283, "test_o_a3_r15_06_c_compra_03_sin_fecha_nada_escrito"),)),
    Mutante("M-A3-R15-14", "Con la fila 2 bis se devuelven el corte y la huella (discriminante F)", COSTE,
            "\"fecha_corte\": corte.isoformat() if (habilitada and corte) else None,",
            "\"fecha_corte\": corte.isoformat() if (habilitada and corte and motivo != \"SIN_FECHA_DE_ADQUISICION\") else None,",
            (n(T283, "test_o_a3_r15_07_borrar_la_fecha_da_parcial_sin_fecha_y_conserva_corte_y_huella"),)),
    Mutante("M-A3-R15-15", "La fila 2 bis exige los consumidores habilitados (discriminante H)", COSTE, SIN_FECHA_COSTE,
            "        sin_fecha = ambito == \"ADQUISICION\" and fecha is None\n",
            (n(T252, "test_o10_29_h_c_apagado_l_coste_sin_declaracion_nunca_completo"),),
            equivalente=("Con el interruptor apagado repo.leer_coste(..., con_declaracion=False) devuelve declarado = NULL "
                         "en todas las filas (repositorio.py, _ambito_coste_sql), y en _regla la fila 2 (declarado is not "
                         "True -> SIN_DECLARACION/NO_DISPONIBLE) precede a la fila 2 bis: `sin_fecha` nunca se consulta con "
                         "habilitada False. La condicion `habilitada` en sin_fecha es defensa redundante; la conducta "
                         "observable (O-A3-R15-11, fila 2 bis nunca aparece) la garantizan G3 y la precedencia (M-A3-R15-07).")),
    # ------------------------------------------------------------------ inventario de forzados y textos
    Mutante("M-A3-INV", "Ningun test fuerza True en el interruptor (O-A3-INV)", T256,
            "def test_o10_14_c_mej_03_desactualiza_la_declaracion_de_mejoras_sin_tocar_la_propiedad(lab, monkeypatch):\n",
            "def test_o10_14_c_mej_03_desactualiza_la_declaracion_de_mejoras_sin_tocar_la_propiedad(lab, monkeypatch):\n"
            "    monkeypatch.setattr(__import__(\"app.patrimonio.habilitacion\", fromlist=[\"x\"]), \"CONSUMIDORES_0352_HABILITADOS\", True)\n",
            (n(T283, "test_o_a3_inv_ningun_test_fuerza_el_interruptor"),)),
    Mutante("M-A3-TXT", "El texto del rechazo del servidor es el del cliente (O-A3-TXT, UX-4)", RUTAS,
            "(422, \"Para marcar el coste como completo, indica antes la fecha de adquisición de la propiedad.\")",
            "(422, \"Revisa los datos.\")",
            (n(T283, "test_o_a3_txt_servidor_y_cliente_coherentes"),
             n(T283, "test_o_a3_r15_01_c_prop_05_sin_fecha_422_sin_escribir"))),
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
    proceso = subprocess.run(
        [sys.executable, "-m", "pytest", *nodos, "-q", "-p", "no:cacheprovider", "--rootdir=tests/api", "-rfE"],
        cwd=RAIZ, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return proceso.returncode, proceso.stdout + proceso.stderr


def _a_disco(registro: dict) -> None:
    destino = os.environ.get("GAPTO_A3_MUTANTES_VEREDICTOS")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _guardar_salida(m: Mutante, salida: str) -> None:
    carpeta = os.environ.get("GAPTO_A3_MUTANTES_SALIDA")
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
        return "EQUIVALENTE razonado" if m.equivalente else "VIVO      ningun discriminante cae"
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
    print("=== F06 T2-F06 A3-0352 · MUTANTES ===", flush=True)
    buenos = 0
    for m in seleccion:
        veredicto = ejecutar(m)
        buenos += veredicto.startswith(("MUERTO", "EQUIVALENTE"))
        _a_disco({"id": m.ident, "invariante": m.invariante, "fichero": m.fichero, "veredicto": veredicto.split()[0],
                  "detalle": veredicto, "discriminantes": list(m.discriminantes), "equivalencia": m.equivalente})
        print(f"  {m.ident:13}  {veredicto}   [{m.invariante}]", flush=True)
        if veredicto.startswith("NO_CLASIFICABLE"):
            raise SystemExit(f"ABORTADO: {m.ident} NO_CLASIFICABLE")
    if _estado_arbol() != arbol:
        raise SystemExit("ABORTADO: el estado del arbol cambio durante la tirada.")
    print(f"RESULTADO: {buenos}/{len(seleccion)} muertos o equivalentes razonados")
    return 0 if buenos == len(seleccion) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
