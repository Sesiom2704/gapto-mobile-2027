# ============================================================
# GAPTO MOBILE 2027
# Fichero: f08_motor.py
# Ruta: tests/backend/f08_motor.py
# Descripcion: F04-D042. Fachada del motor y utilidades de oraculo para la
#   bateria integral de F04-08.
#
#   SERVICIOS REALES, SIEMPRE. `Motor` construye los servicios certificados
#   sobre la misma unidad de trabajo y los expone juntos. Ningun escenario
#   reconstruye logica de negocio con SQL: si un caso no puede montarse con
#   estos servicios, eso ES el hallazgo (STOP S5), no un motivo para bajar al
#   SQL.
#
#   SQL SOLO PARA TRES COSAS: inspeccion read-only (`contar`, `valor`),
#   fixtures de infraestructura que el motor no escribe —participaciones de
#   cuenta y de entidad, subtipos de entidad— y montaje deliberado de estado
#   invalido o legacy para probar defensas fail-closed. El tercer uso va
#   siempre marcado como laboratorio en el propio escenario.
#
#   LAS AUSENCIAS SON PARTE DEL ORACULO. `exigir_ausencias` existe porque el
#   fallo tipico de un motor financiero no es escribir de menos: es escribir
#   de mas. Un reembolso que ademas crea un INGRESO, un pago de deuda que
#   vuelve a contar el gasto, una diferencia entre atribucion y aportacion que
#   se convierte en deuda. Ninguna de esas cosas lanza excepcion.
# Version: 0.2.0
#   0.2.0 (mandato F04 R1+R2 v0.3 + E01): `hecho()` usa estado_localizacion
#   DESCONOCIDA por defecto (parametro): el NO_APLICA fijo ocultaba la
#   diferencia NO_APLICA/DESCONOCIDA y hoy OP-04 lo rechaza con GASTO/INGRESO.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from dataclasses import dataclass
from typing import Any

import psycopg

from app.core.contexto import ContextoOperacion
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
from app.core.modelos_tesoreria import (
    DatosAportacion,
    DatosConciliacion,
    DatosMovimiento,
)
from app.core.unidad_trabajo import UnidadDeTrabajo

D = decimal.Decimal
FECHA = dt.date(2026, 6, 1)


# ==================================================================
# Fachada de servicios
# ==================================================================

@dataclass(slots=True)
class Motor:
    """Todos los servicios del motor sobre una unica unidad de trabajo."""

    hechos: Any
    efectos: Any
    tesoreria: Any
    posiciones: Any
    transferencias: Any
    devoluciones: Any
    suplementos: Any
    correcciones: Any
    previsiones: Any
    reglas: Any
    participantes: Any
    compartidos: Any
    neto: Any


def construir_motor(unidad: UnidadDeTrabajo) -> Motor:
    from app.services.compartidos_service import GastosCompartidosService
    from app.services.correcciones_service import CorreccionesService
    from app.services.devoluciones_service import DevolucionesService
    from app.services.efectos_service import EfectosService
    from app.services.hechos_service import HechosService
    from app.services.neto_service import NetoService
    from app.services.participantes_service import ParticipantesService
    from app.services.posiciones_service import PosicionesService
    from app.services.previsiones_service import (
        PrevisionesService,
        impacto_correccion_ancla,
    )
    from app.services.reglas_service import ReglasService
    from app.services.suplementos_service import SuplementosService
    from app.services.tesoreria_service import TesoreriaService
    from app.services.transferencias_service import TransferenciasService

    return Motor(
        hechos=HechosService(unidad, impacto_ancla=impacto_correccion_ancla),
        efectos=EfectosService(unidad),
        tesoreria=TesoreriaService(unidad),
        posiciones=PosicionesService(unidad),
        transferencias=TransferenciasService(unidad),
        devoluciones=DevolucionesService(unidad),
        suplementos=SuplementosService(unidad),
        correcciones=CorreccionesService(unidad),
        previsiones=PrevisionesService(unidad),
        reglas=ReglasService(unidad),
        participantes=ParticipantesService(unidad),
        compartidos=GastosCompartidosService(
            unidad, impacto_ancla=impacto_correccion_ancla
        ),
        neto=NetoService(unidad),
    )


# ==================================================================
# Constructores de entrada
# ==================================================================

def hecho(
    *,
    tipo: str = "GASTO",
    concepto: str = "hecho",
    importe_total: decimal.Decimal | None = None,
    fecha: dt.date = FECHA,
    moneda: str = "EUR",
    presupuestable: bool = True,
    participantes_total: int | None = None,
    estado_localizacion: str = "DESCONOCIDA",
    hecho_id: uuid.UUID | None = None,
) -> DatosCreacionHecho:
    return DatosCreacionHecho(
        hecho_id=hecho_id or uuid.uuid4(),
        fecha_hecho=fecha,
        moneda=moneda,
        presupuestable=presupuestable,
        # F04-D046 R2 / mandato v0.3 E01: aplicable pero no conocida. El
        # NO_APLICA fijo ocultaba la diferencia NO_APLICA / DESCONOCIDA.
        estado_localizacion=estado_localizacion,
        tipo_hecho_codigo=tipo,
        concepto=concepto,
        importe_total=importe_total,
        numero_participantes_total=participantes_total,
    )


def efecto(
    tipo_efecto: str,
    importe_delta: decimal.Decimal,
    *,
    estado: str | None = None,
    atribuciones: tuple[DatosAtribucion, ...] = (),
    efecto_id: uuid.UUID | None = None,
    acontecimiento: str | None = None,
) -> DatosEfecto:
    """`acontecimiento` solo lo exige VALOR_ACTIVO, por INV-09."""
    extra = {"acontecimiento": acontecimiento} if acontecimiento else {}
    return DatosEfecto(
        efecto_id=efecto_id or uuid.uuid4(),
        tipo_efecto=tipo_efecto,
        importe_delta=importe_delta,
        estado_atribucion=estado or ("COMPLETA" if atribuciones else "NO_DISPONIBLE"),
        atribuciones=tuple(atribuciones),
        **extra,
    )


def atribucion(
    actor_id: uuid.UUID,
    importe_atribuido: decimal.Decimal,
    *,
    criterio: str = "MANUAL",
) -> DatosAtribucion:
    return DatosAtribucion(
        atribucion_id=uuid.uuid4(),
        actor_id=actor_id,
        importe_atribuido=importe_atribuido,
        criterio_atribucion=criterio,
    )


def movimiento(
    cuenta_id: uuid.UUID,
    importe: decimal.Decimal,
    *,
    fecha: dt.date = FECHA,
    descripcion: str = "movimiento",
    movimiento_id: uuid.UUID | None = None,
) -> DatosMovimiento:
    return DatosMovimiento(
        movimiento_id=movimiento_id or uuid.uuid4(),
        cuenta_id=cuenta_id,
        fecha_movimiento=fecha,
        importe=importe,
        clase_movimiento="OPERACION",
        descripcion=descripcion,
    )


def conciliacion(
    hecho_id: uuid.UUID,
    movimiento_id: uuid.UUID,
    importe_asignado: decimal.Decimal,
) -> DatosConciliacion:
    return DatosConciliacion(
        conciliacion_id=uuid.uuid4(),
        hecho_id=hecho_id,
        movimiento_tesoreria_id=movimiento_id,
        importe_asignado=importe_asignado,
    )


def aportacion(
    importe: decimal.Decimal,
    *,
    actor_id: uuid.UUID | None = None,
    criterio: str = "MANUAL",
    conciliacion_id: uuid.UUID | None = None,
) -> DatosAportacion:
    datos = {
        "aportacion_id": uuid.uuid4(),
        "importe": importe,
        "criterio_aportacion": criterio,
        "actor_id": actor_id,
    }
    if conciliacion_id is not None:
        datos["hecho_movimiento_tesoreria_id"] = conciliacion_id
    return DatosAportacion(**datos)


# ==================================================================
# Inspeccion read-only
# ==================================================================

def valor(
    admin: psycopg.Connection,
    owner: uuid.UUID,
    consulta: str,
    parametros: tuple[Any, ...] = (),
) -> tuple[Any, ...] | None:
    """Lectura de verificacion con contexto de tenant y limpieza posterior.

    Implementada aqui y NO importada de `conftest`: con varios directorios de
    pruebas recolectados en la misma ejecucion, el nombre de modulo
    `conftest` es ambiguo y puede resolverse al del otro directorio. Un
    helper de oraculo no puede depender del orden de recoleccion.
    """
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),)
        )
        try:
            cursor.execute(consulta, parametros)
            return cursor.fetchone()
        finally:
            cursor.execute("RESET ALL")


def contar(
    admin: psycopg.Connection,
    owner: uuid.UUID,
    tabla: str,
    donde: str,
    parametros: tuple[Any, ...] = (),
) -> int:
    fila = valor(
        admin, owner, f"SELECT count(*) FROM gapto.{tabla} WHERE {donde}", parametros
    )
    return 0 if fila is None else int(fila[0])


def efectos_de(
    admin: psycopg.Connection, owner: uuid.UUID, hecho_id: uuid.UUID
) -> dict[str, decimal.Decimal]:
    """Naturaleza -> suma de deltas del hecho. El oraculo economico basico."""
    consulta = (
        "SELECT tipo_efecto, sum(importe_delta) FROM gapto.hecho_efectos "
        "WHERE hecho_id = %s::uuid GROUP BY tipo_efecto"
    )
    with admin.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE gapto_owner")
        try:
            cursor.execute(
                "SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),)
            )
            cursor.execute(consulta, (hecho_id,))
            return {fila[0]: fila[1] for fila in cursor.fetchall()}
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET ALL")


def liquidez(
    admin: psycopg.Connection, owner: uuid.UUID, cuenta_id: uuid.UUID
) -> decimal.Decimal:
    """Saldo DERIVADO de la cuenta: suma de movimientos activos (INV-18).

    Deliberadamente derivado y no leido de una columna: si el motor guardase
    un saldo materializado y se desincronizase, este oraculo lo detectaria.
    """
    fila = valor(
        admin,
        owner,
        "SELECT COALESCE(sum(importe), 0) FROM gapto.movimientos_tesoreria "
        "WHERE cuenta_id = %s::uuid AND estado = 'ACTIVO'",
        (cuenta_id,),
    )
    return D("0") if fila is None else fila[0]


# ==================================================================
# Ausencias obligatorias
# ==================================================================

AUSENCIAS: dict[str, tuple[str, str]] = {
    "posiciones": (
        "derechos_obligaciones_financieras p "
        "JOIN gapto.entidades e ON e.id = p.entidad_id",
        "e.owner_user_id = %s",
    ),
    "movimientos": (
        "movimientos_tesoreria m JOIN gapto.cuentas c ON c.id = m.cuenta_id",
        "c.owner_user_id = %s",
    ),
    "relaciones": (
        "hecho_relaciones r JOIN gapto.hechos_financieros h "
        "ON h.id = r.hecho_origen_id",
        "h.owner_user_id = %s",
    ),
    "transferencias": (
        "transferencias t JOIN gapto.movimientos_tesoreria m "
        "ON m.id = t.movimiento_salida_id JOIN gapto.cuentas c ON c.id = m.cuenta_id",
        "c.owner_user_id = %s",
    ),
}


def exigir_ausencias(
    admin: psycopg.Connection,
    contexto: ContextoOperacion,
    *,
    posiciones: int | None = None,
    movimientos: int | None = None,
    relaciones: int | None = None,
    transferencias: int | None = None,
) -> None:
    """Comprueba lo que NO debe existir en el tenant tras un escenario.

    El recuento esperado se pasa explicito en vez de asumir cero: un escenario
    puede crear legitimamente un movimiento y aun asi deber cero posiciones.
    """
    esperados = {
        "posiciones": posiciones,
        "movimientos": movimientos,
        "relaciones": relaciones,
        "transferencias": transferencias,
    }
    for nombre, esperado in esperados.items():
        if esperado is None:
            continue
        desde, donde = AUSENCIAS[nombre]
        fila = valor(
            admin,
            contexto.owner_user_id,
            f"SELECT count(*) FROM gapto.{desde} WHERE {donde}",
            (contexto.owner_user_id,),
        )
        obtenido = 0 if fila is None else int(fila[0])
        assert obtenido == esperado, (
            f"{nombre}: esperado {esperado}, obtenido {obtenido}"
        )


def sin_naturaleza(
    admin: psycopg.Connection,
    owner: uuid.UUID,
    hecho_id: uuid.UUID,
    naturaleza: str,
) -> None:
    """El hecho NO puede tener efectos de esa naturaleza.

    Es la forma concreta de "cero INGRESO en un reembolso" y "cero GASTO nuevo
    al pagar deuda".
    """
    presentes = efectos_de(admin, owner, hecho_id)
    assert naturaleza not in presentes, (
        f"el hecho {hecho_id} no debe tener efectos {naturaleza}; "
        f"tiene {presentes.get(naturaleza)}"
    )
