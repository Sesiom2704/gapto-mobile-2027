# ============================================================
# GAPTO MOBILE 2027
# Fichero: f08_cobertura.py
# Ruta: tests/backend/f08_cobertura.py
# Descripcion: F04-D042. Registro de cobertura y utilidades de la bateria
#   integral de F04-08.
#
#   POR QUE UN REGISTRO Y NO UNA TABLA A MANO. El criterio de cierre exige
#   demostrar 22/22 casos, 20/20 operaciones, 21/21 invariantes, 6/6
#   naturalezas y 8/8 dimensiones. Una matriz escrita a mano en un documento
#   envejece mal: afirma cobertura que nadie vuelve a comprobar. Aqui cada
#   escenario DECLARA lo que cubre mediante `@cubre`, el registro se llena al
#   importar los modulos de prueba y un test-gate compara lo declarado con lo
#   exigido. Si alguien borra un escenario, el gate cae.
#
#   LO QUE EL REGISTRO NO HACE. Declarar cobertura no es demostrarla: el
#   oraculo de cada escenario sigue siendo su propio `assert`. El registro
#   responde "¿existe un escenario que afirme cubrir C-07?", no "¿lo cubre
#   bien?". Por eso `@cubre` se aplica al test y no a un diccionario suelto:
#   un escenario que falla no aporta su cobertura, porque la suite no pasa.
#
#   LOS 40 ESCENARIOS HISTORICOS NO SE RECONSTRUYEN. F04-D042 resolvio el
#   §5.2 por la opcion (b): el inventario exacto de F04-00-A no es
#   recuperable, permanece como dato historico agregado y queda PROHIBIDO
#   reconstruirlo por inferencia. Este registro no contiene ninguna entrada
#   de escenario historico y el gate no comprueba 40/40.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Iterable, TypeVar

# ==================================================================
# Universos exigidos por el criterio de cierre
# ==================================================================

#: Los 22 casos reales canonicos cerrados por F04-00-A.
CASOS: dict[str, str] = {
    "C-01": "Supermercado",
    "C-02": "Luz recurrente",
    "C-03": "Gasoil reembolsable",
    "C-04": "Devolucion parcial",
    "C-05": "Transferencia propia",
    "C-06": "Hipoteca",
    "C-07": "Intereses de poliza",
    "C-08": "Compra financiada",
    "C-09": "Alquiler con revision",
    "C-10": "Propiedad compartida",
    "C-11": "Cena compartida",
    "C-12": "Neteo peluqueria + cena (gate)",
    "C-13": "Cuenta compartida",
    "C-14": "Nomina",
    "C-15": "Inversion",
    "C-16": "Activo patrimonial",
    "C-17": "Conciliacion parcial",
    "C-18": "Aportacion no vinculada",
    "C-19": "Conciliaciones multiples",
    "C-20": "Multidivisa",
    "C-21": "Aportaciones multi-actor",
    "C-22": "Transferencia prevista",
}

#: Las 20 operaciones internas de F04-00-C.
OPERACIONES: dict[str, str] = {
    "OP-01": "Crear hecho",
    "OP-02": "Editar error de captura",
    "OP-03": "Anular hecho que nunca debio existir",
    "OP-04": "Registrar efectos",
    "OP-05": "Atribuir efectos",
    "OP-06": "Registrar aportaciones",
    "OP-07": "Vincular aportacion a conciliacion",
    "OP-08": "Registrar movimiento",
    "OP-09": "Conciliar hecho <-> movimiento",
    "OP-10": "Transferencia propia",
    "OP-11": "Reversion de tesoreria",
    "OP-12": "Crear/reducir derecho u obligacion",
    "OP-13": "Devolucion",
    "OP-14": "Reembolso",
    "OP-15": "Compra financiada",
    "OP-16": "Pago de financiacion",
    "OP-17": "Materializar prevision",
    "OP-18": "Realidad suplementaria",
    "OP-19": "Gastos compartidos",
    "OP-20": "Lectura de posicion neta",
}

#: Operaciones incorporadas DESPUES del catalogo de F04-00-C. El criterio de
#: cierre exige 20/20 sobre las anteriores; estas se aceptan y se registran,
#: pero no forman parte del recuento exigido: ampliar el universo del gate
#: cambiaria el criterio que arquitectura fijo.
OPERACIONES_POSTERIORES: dict[str, str] = {
    "OP-21": "Correccion agregada (F04-06)",
}

#: Las 21 invariantes de F04-00-B.
INVARIANTES: dict[str, str] = {
    "INV-01": "Estados de atribucion",
    "INV-02": "NO_DISPONIBLE no es cero ni NO_APLICA",
    "INV-03": "Atribucion no es aportacion",
    "INV-04": "No inferir posiciones",
    "INV-05": "Devolucion no es reembolso",
    "INV-06": "Exceso sobre cargo no es devolucion automatica",
    "INV-07": "Correccion no es realidad suplementaria",
    "INV-08": "Fecha economica no es fecha de captura",
    "INV-09": "VALOR_ACTIVO no es valoracion",
    "INV-10": "Neteo no es compensacion extintiva",
    "INV-11": "Presupuestabilidad",
    "INV-12": "Prohibicion de doble conteo",
    "INV-13": "Aportacion hacia conciliacion correcta",
    "INV-14": "Magnitud y comparabilidad D-169/D-170",
    "INV-15": "Transferencia neutral",
    "INV-16": "Prevision no es realidad",
    "INV-17": "Saldo determinado no es indeterminado",
    "INV-18": "Saldo de cuenta derivado",
    "INV-19": "Liquidez atribuible y redondeo",
    "INV-20": "Idempotencia",
    "INV-21": "Retry completo ante 40P01/40001",
}

#: Las seis naturalezas de efecto vigentes.
NATURALEZAS: tuple[str, ...] = (
    "GASTO",
    "INGRESO",
    "DEUDA",
    "DERECHO_COBRO",
    "INVERSION",
    "VALOR_ACTIVO",
)

#: Las ocho dimensiones nucleares.
#:
#: PROCEDENCIA DECLARADA. F04-00-A registro cobertura "8/8 de dimensiones"
#: sin conservar su enumeracion, igual que ocurrio con los 40 escenarios.
#: Estas ocho NO se deducen de aquel agregado perdido: se toman literalmente
#: de la lista "Guardar por separado" de Working Method §7, que si esta
#: enumerada y vigente, mas la independencia de participaciones que el mismo
#: §7 declara a continuacion. La equivalencia con el 8/8 historico no se
#: afirma; se declara la fuente que se usa aqui.
DIMENSIONES: dict[str, str] = {
    "D1": "Importe total del hecho",
    "D2": "Efecto economico (naturaleza y delta)",
    "D3": "Atribucion economica por actor",
    "D4": "Cuenta/fuente esperada",
    "D5": "Financiacion/aportacion real por actor",
    "D6": "Movimiento de tesoreria",
    "D7": "Impacto atribuible en liquidez",
    "D8": "Participacion de propiedad y de cuenta (independientes)",
}

#: Escenarios de excepcion y cruzados exigidos por el mandato.
EXCEPCIONES: tuple[str, ...] = ("E-01", "E-02", "E-03")
CRUZADOS: tuple[str, ...] = tuple(f"X-{n:02d}" for n in range(1, 13))
PROPIEDADES: tuple[str, ...] = tuple(f"P-F08-{n:02d}" for n in range(1, 29))


# ==================================================================
# Registro
# ==================================================================

REGISTRO: dict[str, set[str]] = defaultdict(set)

T = TypeVar("T", bound=Callable[..., object])


def cubre(
    *,
    casos: Iterable[str] = (),
    operaciones: Iterable[str] = (),
    invariantes: Iterable[str] = (),
    naturalezas: Iterable[str] = (),
    dimensiones: Iterable[str] = (),
    excepciones: Iterable[str] = (),
    cruzados: Iterable[str] = (),
    propiedades: Iterable[str] = (),
) -> Callable[[T], T]:
    """Declara que este escenario cubre los elementos indicados.

    Se valida en el momento de la decoracion que cada identificador exista en
    su universo: una errata como `INV-22` o `C-23` falla al importar el
    modulo, no en el gate final, donde seria mucho mas dificil de localizar.
    """

    def _registrar(funcion: T) -> T:
        for etiqueta, valores, universo in (
            ("casos", casos, CASOS),
            ("operaciones", operaciones, {**OPERACIONES, **OPERACIONES_POSTERIORES}),
            ("invariantes", invariantes, INVARIANTES),
            ("naturalezas", naturalezas, NATURALEZAS),
            ("dimensiones", dimensiones, DIMENSIONES),
            ("excepciones", excepciones, EXCEPCIONES),
            ("cruzados", cruzados, CRUZADOS),
            ("propiedades", propiedades, PROPIEDADES),
        ):
            for valor in valores:
                if valor not in universo:
                    raise AssertionError(
                        f"{valor} no pertenece al universo '{etiqueta}' de F04-08"
                    )
                REGISTRO[etiqueta].add(valor)
        return funcion

    return _registrar


def faltantes(etiqueta: str, universo: Iterable[str]) -> list[str]:
    """Elementos del universo que ningun escenario declara cubrir."""
    return sorted(set(universo) - REGISTRO.get(etiqueta, set()))
