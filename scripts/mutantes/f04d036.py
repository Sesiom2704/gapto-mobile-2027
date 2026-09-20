# ============================================================
# GAPTO MOBILE 2027
# Fichero: f04d036.py
# Ruta: scripts/mutantes/f04d036.py
# Descripcion: Arnes de mutacion de F04-D036. Demuestra que la coherencia
#   posicion <-> efecto esta sostenida por los CUATRO caminos que la pueden
#   romper, y no por uno solo que arrastre a los demas.
#
#   Por que cuatro mutantes y no uno: los tres write-paths y la lectura
#   delegan en el MISMO modulo compartido. Mutar solo ese modulo mataria
#   todos los tests a la vez y no demostraria nada sobre cada camino: un
#   arnes asi pasaria igual si manana alguien retirase la llamada de OP-02 y
#   dejase las otras. Por eso cada mutante neutraliza UNA llamada concreta en
#   su fichero, y M5 ataca la calidad del predicado, no su presencia.
#
#   Guardas heredadas de D-181 y de los incidentes de F04-05/F04-06:
#   - SHA-256 antes y despues de mutar: una mutacion que no cambia el fichero
#     es INERTE y se marca DUDOSA, nunca superviviente;
#   - la salida de pytest debe tener forma de resumen: un argumento invalido
#     haria que la suite no llegase a ejecutarse y "cero fallos" pasaria por
#     superviviente;
#   - el DISCRIMINANTE declarado debe estar entre los fallos: si solo caen
#     tests colaterales, el mutante no esta demostrado;
#   - todos los oraculos son DETERMINISTAS. Ninguna carrera participa;
#   - restauracion verificada por SHA-256, tambien si la suite aborta.
#
#   Cualquier guarda incumplida deja el resultado DUDOSO y el codigo de
#   salida deja de ser 0.
#
# Uso:
#   python scripts/mutantes/f04d036.py           # todos
#   python scripts/mutantes/f04d036.py M2 M4     # un subconjunto
#
# Version: 0.2.0
#   0.2.0 (F04-D036, iteracion correctiva): E/S BYTE A BYTE y un solo
#   veredicto por mutante. La version anterior leia y escribia en modo TEXTO:
#   en Windows eso traduce LF a CRLF, de modo que el fichero restaurado tenia
#   el mismo contenido y distinto SHA-256, y la guarda de restauracion —que
#   hizo bien en disparar— marcaba DUDOSO un mutante ya demostrado. Ademas el
#   `finally` ANADIA un segundo veredicto en lugar de corregir el primero, y
#   el recuento salia sobre mas entradas que mutantes. Una herramienta de gate
#   no puede depender del sistema operativo donde se ejecuta (D-181).
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

SRV_POSICIONES = "backend/app/services/posiciones_service.py"
SRV_HECHOS = "backend/app/services/hechos_service.py"
SRV_CORRECCIONES = "backend/app/services/correcciones_service.py"
REPO_POSICIONES = "backend/app/repositories/posiciones_repository.py"

SUITE = "tests/backend/test_121_coherencia_posicion.py"


@dataclass(frozen=True)
class Mutante:
    """Una mutacion contractual.

    `discriminante` es el fragmento del identificador de test que DEBE caer.
    Sin el, un mutante podria darse por muerto por un fallo colateral que no
    tiene nada que ver con la invariante vigilada.
    """

    ident: str
    invariante: str
    descripcion: str
    fichero: str
    viejo: str
    nuevo: str
    discriminante: str


MUTANTES: list[Mutante] = [
    Mutante(
        ident="M1",
        invariante="Un efecto solo entra en el saldo de una posicion de su misma moneda",
        descripcion="no comprueba la moneda al crear el vinculo posicion<->efecto",
        fichero=SRV_POSICIONES,
        viejo="""        posicion_destino = repo_pos.leer_posicion(sesion, entidad_id)
        coherencia_posicion.exigir_moneda_de_vinculo(
            sesion,
            hecho_id=hecho_id,
            moneda_posicion=(
                None if posicion_destino is None else posicion_destino["moneda"]
            ),
            entidad_id=entidad_id,
        )""",
        nuevo="        repo_pos.leer_posicion(sesion, entidad_id)",
        discriminante="test_alta_sobre_hecho_de_otra_moneda_rechazada",
    ),
    Mutante(
        ident="M2",
        invariante="OP-02 no deja el agregado incoherente al corregir la moneda",
        descripcion="permite corregir la moneda de un hecho ya vinculado a una posicion",
        fichero=SRV_HECHOS,
        viejo="""                coherencia_posicion.exigir_moneda_corregible(
                    sesion, hecho_id=hecho_id, moneda_candidata=cambios["moneda"]
                )""",
        nuevo="                pass",
        discriminante="test_op02_no_puede_cambiar_la_moneda_de_un_hecho_vinculado",
    ),
    Mutante(
        ident="M3",
        invariante="La lectura no calcula un saldo sobre un estado invalido",
        descripcion="suma los deltas sin comprobar de que moneda proceden",
        fichero=SRV_POSICIONES,
        viejo="""        coherencia_posicion.exigir_saldo_calculable(
            sesion,
            entidad_id=entidad_id,
            tipo_efecto=EFECTO_DE_POSICION[posicion["tipo"]],
        )""",
        nuevo="        pass",
        discriminante="test_la_lectura_falla_cerrada_ante_un_estado_incoherente",
    ),
    Mutante(
        ident="M4",
        invariante="OP-21 no confirma un vinculo posicion<->efecto incoherente",
        descripcion="no evalua el estado final de los vinculos tras la correccion",
        fichero=SRV_CORRECCIONES,
        viejo="""            coherencia_posicion.exigir_vinculos_coherentes(
                sesion, hecho_id=datos.hecho_id
            )""",
        nuevo="            pass",
        discriminante="test_op21_no_puede_cambiar_la_naturaleza_de_un_efecto_vinculado",
    ),
    Mutante(
        ident="M5",
        invariante="El estado final se juzga por moneda Y por naturaleza",
        descripcion=(
            "conserva la llamada de estado final pero retira del predicado la "
            "dimension de naturaleza"
        ),
        fichero=REPO_POSICIONES,
        viejo="""           AND (
                h.moneda <> p.moneda
             OR ef.tipo_efecto <> CASE p.tipo
                    WHEN 'DERECHO_COBRO' THEN 'DERECHO_COBRO'
                    ELSE 'DEUDA'
                END
           )""",
        nuevo="           AND h.moneda <> p.moneda",
        discriminante="test_op21_no_puede_cambiar_la_naturaleza_de_un_efecto_vinculado",
    ),
]


def sha256(ruta: pathlib.Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def leer(ruta: pathlib.Path) -> bytes:
    """Bytes crudos. Nunca modo texto: traduciria los finales de linea."""
    return ruta.read_bytes()


def escribir(ruta: pathlib.Path, contenido: bytes) -> None:
    ruta.write_bytes(contenido)


def ejecutar_suite() -> tuple[str, list[str]]:
    """Devuelve (forma, tests_fallados). `forma` es INVALIDA si pytest no corrio."""
    proceso = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q", "--tb=no", "-p", "no:cacheprovider"],
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


def correr(lote: list[Mutante]) -> int:
    resultados: list[tuple[str, str]] = []
    for mutante in lote:
        ruta = RAIZ / mutante.fichero
        original = leer(ruta)
        sha_original = sha256(ruta)
        viejo = mutante.viejo.encode("utf-8")
        nuevo = mutante.nuevo.encode("utf-8")
        veredicto = "DUDOSO: sin ejecutar"

        if original.count(viejo) != 1:
            resultados.append((mutante.ident, "DUDOSO: el fragmento no es unico"))
            continue

        escribir(ruta, original.replace(viejo, nuevo))
        try:
            if sha256(ruta) == sha_original:
                veredicto = "DUDOSO: mutacion INERTE"
            else:
                forma, fallados = ejecutar_suite()
                if forma == "INVALIDA":
                    veredicto = "DUDOSO: la suite no llego a correr"
                elif not fallados:
                    veredicto = "SUPERVIVIENTE"
                elif not any(mutante.discriminante in n for n in fallados):
                    veredicto = (
                        f"DUDOSO: cayeron {fallados} pero no el discriminante"
                    )
                else:
                    veredicto = f"MUERTO ({len(fallados)} fallos)"
        finally:
            # La restauracion se verifica SIEMPRE, y si falla degrada el
            # veredicto en vez de anadir una segunda entrada: un mutante
            # produce exactamente un resultado.
            escribir(ruta, original)
            if sha256(ruta) != sha_original:
                veredicto = "DUDOSO: restauracion fallida"
            resultados.append((mutante.ident, veredicto))

    print("=== F04-D036 - MUTANTES ===", flush=True)
    problemas = 0
    for ident, veredicto in resultados:
        mutante = next(m for m in MUTANTES if m.ident == ident)
        print(f"{ident}  {veredicto}")
        print(f"     invariante: {mutante.invariante}")
        print(f"     mutacion:   {mutante.descripcion}")
        if not veredicto.startswith("MUERTO"):
            problemas += 1
    print(f"--- {len(resultados) - problemas}/{len(resultados)} muertos")
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
