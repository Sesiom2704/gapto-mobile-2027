# ============================================================
# GAPTO MOBILE 2027
# Fichero: f0407.py
# Ruta: scripts/mutantes/f0407.py
# Descripcion: Arnes de mutacion de F04-07 y de la superficie de atribuciones
#   de F04-D039.
#
#   ALCANCE. Cubre las propiedades que se sostienen con CODIGO: si se retira
#   la linea que las protege, algo tiene que ponerse rojo. Cada mutante
#   declara su transformacion y su DISCRIMINANTE, y no se da por muerto si
#   solo caen tests colaterales.
#
#   LO QUE ESTE ARNES NO PUEDE CUBRIR. Seis propiedades de F04-D038/D039 son
#   PROPIEDADES POR AUSENCIA: se cumplen porque el motor NO hace algo, no
#   porque una guarda se lo impida. N2 (participante que genera atribucion),
#   N3 (participacion de cuenta que decide reparto), N4 (diferencia que crea
#   posicion), N11 (OP-20 que escribe), N12 (writer que emite PARTE_DE) y M7
#   (OP-21 que confirma por partes). No existe ninguna linea que borrar para
#   provocarlas: habria que ESCRIBIR el comportamiento incorrecto. Sus
#   oraculos existen y son deterministas —estan enumerados abajo—, pero no son
#   mutantes ejecutables y no se declaran equivalentes, porque equivalente
#   significa otra cosa. Se elevan como clasificacion §12C.5.
#
#   Guardas heredadas de D-181 y de la incidencia corregida en f04d036 v0.2.0:
#   E/S byte a byte —nunca modo texto, que en Windows traduce LF a CRLF y
#   cambia el SHA sin cambiar el contenido—, un unico veredicto por mutante,
#   comprobacion de que pytest llego a ejecutarse, y restauracion verificada
#   por SHA-256 tambien cuando la suite aborta.
#
# Uso:
#   python scripts/mutantes/f0407.py           # todos
#   python scripts/mutantes/f0407.py M2 N7     # un subconjunto
#
# Version: 0.2.0
#   0.2.0 — ENDURECIMIENTO tras un incidente real: un timeout externo mato el
#   proceso a mitad de una mutacion y el `finally` nunca corrio, de modo que el
#   arbol quedo con DOS fragmentos mutados. La suite bajo de verde a cuatro
#   fallos; podria haber pasado inadvertido y contaminado una certificacion.
#   Ahora, antes de mutar, se escribe un MARCADOR con el contenido original: si
#   una ejecucion posterior lo encuentra, restaura el fichero desde el y aborta.
#   Y antes de empezar se exige que las suites implicadas esten VERDES: mutar
#   sobre un arbol ya sucio produciria muertes que no demuestran nada.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass

RAIZ = pathlib.Path(__file__).resolve().parents[2]

SRV_COMPARTIDOS = "backend/app/services/compartidos_service.py"
SRV_PARTICIPANTES = "backend/app/services/participantes_service.py"
SRV_NETO = "backend/app/services/neto_service.py"
SRV_CORRECCIONES = "backend/app/services/correcciones_service.py"
REPO_PARTICIPANTES = "backend/app/repositories/participantes_repository.py"
REPO_POSICIONES = "backend/app/repositories/posiciones_repository.py"

SUITE_F0407 = "tests/backend"

#: Suite por mutante. Correr los 687 tests para cada uno costaba seis minutos
#: y fue lo que provoco el timeout del incidente: cada mutante solo necesita la
#: suite donde vive su discriminante.
SUITES: dict[str, str] = {
    "N1": "tests/backend/test_123_op19_gastos_compartidos.py",
    "N5": "tests/backend/test_122_participantes.py",
    "N5b": "tests/backend/test_122_participantes.py",
    "N6": "tests/backend/test_122_participantes.py",
    "P1": "tests/backend/test_122_participantes.py",
    "N7": "tests/backend/test_124_op20_posicion_neta.py",
    "N8": "tests/backend/test_124_op20_posicion_neta.py",
    "N9": "tests/backend/test_124_op20_posicion_neta.py",
    "N10": "tests/backend/test_124_op20_posicion_neta.py",
    "M1": "tests/backend/test_126_op21_atribuciones.py",
    "M2": "tests/backend/test_126_op21_atribuciones.py",
    "M3": "tests/backend/test_126_op21_atribuciones.py",
    "M4": "tests/backend/test_126_op21_atribuciones.py",
    "M5": "tests/backend/test_126_op21_atribuciones.py",
    "M56": "tests/backend/test_126_op21_atribuciones.py",
    "M6": "tests/backend/test_126_op21_atribuciones.py",
    "M7": "tests/backend/test_126_op21_atribuciones.py",
    "M8": "tests/backend/test_126_op21_atribuciones.py",
}

MARCADOR = pathlib.Path(__file__).resolve().parent / ".f0407_en_curso"

#: Propiedades por ausencia y su oraculo determinista. No son mutantes.
PROPIEDADES_POR_AUSENCIA = {
    "N2": (
        "un participante no genera atribucion",
        "test_participar_no_crea_atribucion_ni_aportacion_ni_posicion",
    ),
    "N3": (
        "la participacion de cuenta/entidad no decide el reparto",
        "test_n3_la_participacion_no_materializa_atribuciones_por_si_sola",
    ),
    "N4": (
        "la diferencia atribucion/aportacion no crea posicion",
        "test_a5_pagador_unico_con_atribucion_mitad_y_mitad_sin_posicion",
    ),
    "N11": (
        "OP-20 no escribe nada",
        "test_op20_no_escribe_nada",
    ),
    "N12": (
        "ningun writer emite PARTE_DE, REPERCUSION_DE ni REVERSA_A",
        "test_ningun_writer_emite_relaciones_reservadas",
    ),
    "M7": (
        "OP-21 no confirma por partes",
        "test_r11_fallo_tardio_deshace_efecto_atribuciones_y_auditoria",
    ),
}


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    descripcion: str
    fichero: str
    viejo: str
    nuevo: str
    discriminantes: tuple[str, ...]


MUTANTES: list[Mutante] = [
    # ---------------- F04-D038 · OP-19 ----------------
    Mutante(
        ident="N1",
        invariante="Una llamada OP-19 es UNA transaccion",
        descripcion=(
            "cada operacion interna abre su propia transaccion y confirma por "
            "separado"
        ),
        fichero=SRV_COMPARTIDOS,
        viejo="            adscrita = UnidadDeTrabajoAdscrita(sesion)",
        nuevo="            adscrita = self._unidad",
        discriminantes=("test_n1_fallo_en_tesoreria_deshace_el_hecho_entero",),
    ),
    # ---------------- F04-D038 · participantes ----------------
    Mutante(
        ident="N5",
        invariante="El total declarado no baja de las personas identificadas",
        descripcion="no revalida el recuento tras insertar participantes",
        fichero=SRV_PARTICIPANTES,
        viejo="""            coherencia_participantes.exigir_recuento_coherente(
                sesion, hecho_id=hecho_id
            )
            _, total = repo_part.total_declarado(sesion, hecho_id)
            return ResultadoParticipantes(
                hecho_id=hecho_id,
                row_version=nueva_version,
                participantes_creados=len(normalizados),""",
        nuevo="""            _, total = repo_part.total_declarado(sesion, hecho_id)
            return ResultadoParticipantes(
                hecho_id=hecho_id,
                row_version=nueva_version,
                participantes_creados=len(normalizados),""",
        discriminantes=("test_total_menor_que_identificados_se_rechaza",),
    ),
    Mutante(
        ident="N6",
        invariante="El recuento cuenta PERSONAS distintas, no filas",
        descripcion="cuenta filas de participante en vez de actores distintos",
        fichero=REPO_PARTICIPANTES,
        viejo='        "SELECT count(DISTINCT actor_id) FROM gapto.hecho_participantes "',
        nuevo='        "SELECT count(*) FROM gapto.hecho_participantes "',
        discriminantes=("test_n6_el_recuento_cuenta_personas_no_filas",),
    ),
    Mutante(
        ident="P1",
        invariante="Retirar un participante conserva su snapshot en auditoria",
        descripcion="borra la fila sin auditar el dato retirado",
        fichero=SRV_PARTICIPANTES,
        viejo="""            auditoria.registrar(
                sesion,
                tabla=repo_part.TABLA_PARTICIPANTES,
                registro_id=participante_id,
                accion=auditoria.ACCION_ANULAR,
                datos_antes_json=snapshot,
                motivo=motivo,
            )""",
        nuevo="            pass",
        discriminantes=("test_a17_8_la_auditoria_conserva_el_snapshot_completo",),
    ),
    # ---------------- F04-D038 · OP-20 ----------------
    Mutante(
        ident="N7",
        invariante="Un saldo indeterminado no se convierte en cero",
        descripcion="trata la apertura desconocida como aporte de 0,00",
        fichero=SRV_NETO,
        viejo="""                saldo=Saldo.indeterminado(),
                aporte=None,""",
        nuevo="""                saldo=Saldo.indeterminado(),
                aporte=decimal.Decimal("0"),""",
        discriminantes=("test_a14_segmento_con_saldo_indeterminado",),
    ),
    Mutante(
        ident="N8",
        invariante="Nunca se netean monedas distintas",
        descripcion="agrupa por contraparte ignorando la moneda",
        fichero=SRV_NETO,
        viejo="            comparables.setdefault((contraparte, moneda), []).append(detalle)",
        nuevo="            comparables.setdefault((contraparte, \"*\"), []).append(detalle)",
        discriminantes=("test_a13_misma_contraparte_con_eur_y_usd",),
    ),
    Mutante(
        ident="N9",
        invariante="Dos contrapartes desconocidas no son la misma persona",
        descripcion="agrupa todas las posiciones sin contraparte",
        fichero=SRV_NETO,
        viejo="            if contraparte is None:",
        nuevo="            if False:",
        discriminantes=("test_a15_dos_posiciones_sin_contraparte_no_se_agrupan",),
    ),
    Mutante(
        ident="N10",
        invariante="Las posiciones cerradas no entran en el neto vivo",
        descripcion="incluye las posiciones CERRADAS en el calculo",
        fichero=REPO_POSICIONES,
        viejo="             WHERE p.estado = 'ACTIVA'",
        nuevo="             WHERE p.estado IN ('ACTIVA', 'CERRADA')",
        discriminantes=("test_posicion_cerrada_fuera_del_neto_vivo",),
    ),
    # ---------------- F04-D039 · atribuciones ----------------
    Mutante(
        ident="M1",
        invariante="OP-21 puede corregir `estado_atribucion`",
        descripcion="retira el estado de atribucion de los campos corregibles",
        fichero=SRV_CORRECCIONES,
        viejo="""        # F04-D039. Corregible SOLO por esta via: OP-05 conserva su
        # progresion ordinaria NO_DISPONIBLE -> PARCIAL -> COMPLETA.
        "estado_atribucion",""",
        nuevo="",
        discriminantes=("test_r4_completa_a_parcial",),
    ),
    Mutante(
        ident="M2",
        invariante="OP-21 actualiza atribuciones existentes",
        descripcion="omite el UPDATE de atribuciones",
        fichero=SRV_CORRECCIONES,
        viejo="        for atribucion_id, cambios in datos.atribuciones_a_actualizar.items():",
        nuevo="        for atribucion_id, cambios in {}.items():",
        discriminantes=("test_a18_importe_y_reparto_falsos_se_corrigen_juntos",),
    ),
    Mutante(
        ident="M3",
        invariante="OP-21 retira atribuciones que nunca debieron existir",
        descripcion="omite el DELETE de atribuciones",
        fichero=SRV_CORRECCIONES,
        viejo="        for atribucion_id in datos.atribuciones_a_eliminar:",
        nuevo="        for atribucion_id in ():",
        discriminantes=("test_r2_actor_falso_se_retira_y_se_redistribuye",),
    ),
    Mutante(
        ident="M4",
        invariante="OP-21 crea atribuciones omitidas",
        descripcion="omite el CREATE de atribuciones",
        fichero=SRV_CORRECCIONES,
        viejo="        for atribucion in datos.atribuciones_a_crear:",
        nuevo="        for atribucion in ():",
        discriminantes=("test_r3_actor_omitido_se_crea",),
    ),
    Mutante(
        ident="M5",
        invariante="INV-01 se valida sobre el estado final de la correccion",
        descripcion="no valida el estado final de atribuciones",
        fichero=SRV_CORRECCIONES,
        viejo="            self._validar_estado_final_atribuciones(sesion, datos)",
        nuevo="            pass",
        discriminantes=("test_r7_no_disponible_con_filas_se_rechaza",),
    ),
    Mutante(
        ident="M6",
        invariante="Los efectos tocados se identifican correctamente",
        descripcion="no considera tocado ningun efecto, de modo que nada se valida",
        fichero=SRV_CORRECCIONES,
        viejo="        tocados: set[uuid.UUID] = set(datos.efectos_a_actualizar)",
        nuevo="        tocados: set[uuid.UUID] = set()",
        discriminantes=("test_r8_parcial_que_cubre_el_efecto_se_rechaza",),
    ),
    Mutante(
        ident="M8",
        invariante="La atribucion retirada conserva su snapshot en auditoria",
        descripcion="borra la atribucion sin auditar el reparto retirado",
        fichero=SRV_CORRECCIONES,
        viejo="""            auditoria.registrar(
                sesion,
                tabla=TABLA_ATRIBUCIONES,
                registro_id=atribucion_id,
                accion=auditoria.ACCION_ANULAR,
                datos_antes_json=snapshot,
                motivo=datos.motivo,
            )""",
        nuevo="            pass",
        discriminantes=("test_r2_actor_falso_se_retira_y_se_redistribuye",),
    ),
]


def sha256(ruta: pathlib.Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def ejecutar_suite(suite: str) -> tuple[str, list[str]]:
    proceso = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            suite,
            "-q",
            "--tb=no",
            "-p",
            "no:cacheprovider",
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    salida = proceso.stdout + proceso.stderr
    if not re.search(r"\d+ (passed|failed|error)", salida):
        return "INVALIDA", []
    fallados = re.findall(r"^FAILED ([^\s:]+)::(\S+)", salida, re.MULTILINE)
    if not fallados:
        fallados = re.findall(r"^(\S+)::(\S+)\s+FAILED", salida, re.MULTILINE)
    return "VALIDA", [nombre for _, nombre in fallados]


def restaurar_si_quedo_a_medias() -> bool:
    """Un proceso muerto no ejecuta su `finally`. El marcador si sobrevive."""
    if not MARCADOR.exists():
        return True
    crudo = MARCADOR.read_bytes()
    corte = crudo.index(b"\n")
    destino = RAIZ / crudo[:corte].decode("utf-8")
    destino.write_bytes(crudo[corte + 1 :])
    MARCADOR.unlink()
    print(
        "AVISO: una ejecucion anterior murio con una mutacion aplicada.\n"
        f"       {destino} ha sido RESTAURADO desde el marcador.\n"
        "       Vuelve a lanzar el arnes.",
        flush=True,
    )
    return False


def suites_verdes(lote: list[Mutante]) -> bool:
    """Mutar sobre un arbol sucio produce muertes que no demuestran nada."""
    for suite in sorted({SUITES.get(m.ident, SUITE_F0407) for m in lote}):
        forma, fallados = ejecutar_suite(suite)
        if forma == "INVALIDA" or fallados:
            print(f"ABORTADO: la suite {suite} no esta verde antes de mutar.")
            return False
    return True


def correr(lote: list[Mutante]) -> int:
    if not restaurar_si_quedo_a_medias():
        return 1
    if not suites_verdes(lote):
        return 1
    resultados: list[tuple[str, str]] = []
    for mutante in lote:
        ruta = RAIZ / mutante.fichero
        original = ruta.read_bytes()
        sha_original = sha256(ruta)
        viejo = mutante.viejo.encode("utf-8")
        nuevo = mutante.nuevo.encode("utf-8")
        veredicto = "DUDOSO: sin ejecutar"

        if original.count(viejo) != 1:
            resultados.append((mutante.ident, "DUDOSO: el fragmento no es unico"))
            continue

        ruta.write_bytes(original.replace(viejo, nuevo))
        try:
            if sha256(ruta) == sha_original:
                veredicto = "DUDOSO: mutacion INERTE"
            else:
                forma, fallados = ejecutar_suite(SUITES.get(mutante.ident, SUITE_F0407))
                if forma == "INVALIDA":
                    veredicto = "DUDOSO: la suite no llego a correr"
                elif not fallados:
                    veredicto = "SUPERVIVIENTE"
                elif [
                    d
                    for d in mutante.discriminantes
                    if not any(d in n for n in fallados)
                ]:
                    ausentes = [
                        d
                        for d in mutante.discriminantes
                        if not any(d in n for n in fallados)
                    ]
                    veredicto = (
                        f"DUDOSO: no cayeron los discriminantes {ausentes}"
                    )
                else:
                    veredicto = f"MUERTO ({len(fallados)} fallos)"
        finally:
            ruta.write_bytes(original)
            if sha256(ruta) != sha_original:
                veredicto = "DUDOSO: restauracion fallida"
            resultados.append((mutante.ident, veredicto))

    print("=== F04-07 / F04-D039 - MUTANTES ===", flush=True)
    problemas = 0
    for ident, veredicto in resultados:
        mutante = next(m for m in MUTANTES if m.ident == ident)
        print(f"{ident:3s} {veredicto}")
        print(f"     invariante: {mutante.invariante}")
        print(f"     mutacion:   {mutante.descripcion}")
        if not veredicto.startswith("MUERTO"):
            problemas += 1
    print(f"--- {len(resultados) - problemas}/{len(resultados)} muertos")

    print()
    print("=== PROPIEDADES POR AUSENCIA (no mutables, oraculo determinista) ===")
    for ident, (invariante, oraculo) in PROPIEDADES_POR_AUSENCIA.items():
        print(f"{ident:3s} {invariante}")
        print(f"     oraculo:    {oraculo}")

    return 0 if problemas == 0 else 1


def main() -> int:
    filtro = set(sys.argv[1:])
    lote = [m for m in MUTANTES if not filtro or m.ident in filtro]
    if not lote:
        print("Ningun mutante coincide con el filtro.")
        return 1
    return correr(lote)


if __name__ == "__main__":
    raise SystemExit(main())
