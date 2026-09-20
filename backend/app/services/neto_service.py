# ============================================================
# GAPTO MOBILE 2027
# Fichero: neto_service.py
# Ruta: backend/app/services/neto_service.py
# Descripcion: OP-20. Lectura de posicion neta (F04-D038 §13 a §21).
#
#   LECTURA PURA. No escribe, no audita, no crea hecho, efecto, posicion,
#   movimiento, relacion ni compensacion, y no modifica ni extingue las
#   posiciones consultadas. Leer cuanto me debe alguien no cambia lo que me
#   debe.
#
#   NETEO ANALITICO NO ES COMPENSACION EXTINTIVA. Si tengo un derecho de 15,00
#   por la peluqueria y una obligacion de 44,50 por la cena frente a la misma
#   persona, OP-20 responde -29,50. Las dos posiciones siguen vivas por sus
#   importes intactos: 15,00 y 44,50. Transformarlas en 0 y 29,50 seria un acto
#   de compensacion, que exige acuerdo o ley y permanece fuera de alcance bajo
#   `F04-PEND-COMP-EXT`.
#
#   SEGMENTOS, NO UN NUMERO. Se agrupa por (contraparte, moneda) y nunca se
#   suman monedas distintas: no hay FX, ni conversion por moneda por defecto,
#   ni "neto total" que mezcle EUR y USD. Cada moneda es un segmento propio.
#
#   INDETERMINADO ES UN RESULTADO. Si alguna posicion viva del segmento tiene
#   saldo indeterminado, el segmento entero es INDETERMINADO y su neto es None.
#   Nunca cero, y nunca un neto calculado solo con la parte conocida
#   presentandolo como total. El desglose si conserva lo que se sabe.
#
#   DOS NULL NO SON LA MISMA PERSONA. `contraparte_actor_id = NULL` significa
#   contraparte desconocida. Agrupar todas las posiciones sin contraparte
#   produciria compensaciones entre desconocidos que pueden ser gente
#   distinta, de modo que cada una se devuelve suelta como NO_COMPARABLE,
#   identificada por su propia entidad.
#
#   UN SOLO SNAPSHOT. Todo sale de UNA sentencia. Construir un neto con varias
#   consultas independientes bajo READ COMMITTED permitiria que cada una viese
#   un commit distinto: el resultado seria un neto que nunca existio en ningun
#   instante.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_posicion import Saldo, TIPO_DERECHO
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.repositories import posiciones_repository as repo_pos

DETERMINADO = "DETERMINADO"
INDETERMINADO = "INDETERMINADO"
NO_COMPARABLE = "NO_COMPARABLE"

CAUSA_SALDO_DESCONOCIDO = "SALDO_INDETERMINADO"
CAUSA_CONTRAPARTE_DESCONOCIDA = "CONTRAPARTE_DESCONOCIDA"


@dataclass(frozen=True, slots=True)
class DetallePosicion:
    """Una posicion viva dentro de un segmento.

    `aporte` es lo que esta posicion suma al neto con su signo canonico, o
    None si su saldo no se conoce. Conservar el detalle es lo que permite
    mostrar lo que si se sabe sin fingir que el total esta cerrado.
    """

    entidad_id: uuid.UUID
    nombre: str | None
    tipo: str
    moneda: str
    saldo: Saldo
    aporte: decimal.Decimal | None


@dataclass(frozen=True, slots=True)
class SegmentoNeto:
    """Resultado comparable para una contraparte y una moneda."""

    contraparte_actor_id: uuid.UUID | None
    moneda: str
    estado: str
    neto: decimal.Decimal | None
    posiciones: tuple[DetallePosicion, ...] = field(default_factory=tuple)
    causas: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ResultadoPosicionNeta:
    segmentos: tuple[SegmentoNeto, ...] = field(default_factory=tuple)

    def segmento(
        self, contraparte_actor_id: uuid.UUID, moneda: str
    ) -> SegmentoNeto | None:
        for segmento in self.segmentos:
            if (
                segmento.contraparte_actor_id == contraparte_actor_id
                and segmento.moneda == moneda
            ):
                return segmento
        return None


class NetoService:
    """OP-20. Read-model de posicion neta viva."""

    def __init__(self, unidad: UnidadDeTrabajo) -> None:
        self._unidad = unidad
        self.ultima_traza: Any = None

    def posicion_neta(
        self,
        contexto: ContextoOperacion,
        *,
        contraparte_actor_id: uuid.UUID | None = None,
    ) -> ResultadoPosicionNeta:
        """Neto vivo por (contraparte, moneda). Sin contraparte, todos."""

        def operacion(sesion: SesionMotor) -> ResultadoPosicionNeta:
            filas = repo_pos.posiciones_para_neto(sesion, contraparte_actor_id)
            return ResultadoPosicionNeta(segmentos=self._segmentar(filas))

        resultado = self._unidad.ejecutar_con_traza(
            contexto, operacion, nombre="OP-20 posicion_neta"
        )
        self.ultima_traza = resultado.traza
        return resultado.valor

    # ==================================================================
    # Interno
    # ==================================================================
    def _segmentar(self, filas: list[tuple[Any, ...]]) -> tuple[SegmentoNeto, ...]:
        comparables: dict[tuple[uuid.UUID, str], list[DetallePosicion]] = {}
        sueltas: list[SegmentoNeto] = []

        for fila in filas:
            (
                entidad_id,
                nombre,
                tipo,
                moneda,
                contraparte,
                apertura,
                deltas,
                incoherentes,
            ) = fila

            if incoherentes:
                # F04-D036. El estado guardado es invalido y no se resuelve
                # reintentando: no se ignora la fila ni se suma nominalmente.
                raise ErrorMotor(
                    CodigoError.INVARIANTE_MONETARIA_POSICION_VIOLADA,
                    f"El saldo de la posicion {entidad_id} ({moneda}) no es "
                    "calculable: tiene deltas procedentes de hechos en otra "
                    "moneda.",
                )

            detalle = self._detalle(
                entidad_id, nombre, tipo, moneda, apertura, deltas
            )
            if contraparte is None:
                # §18. Dos desconocidos pueden ser dos personas distintas.
                sueltas.append(
                    SegmentoNeto(
                        contraparte_actor_id=None,
                        moneda=moneda,
                        estado=NO_COMPARABLE,
                        neto=None,
                        posiciones=(detalle,),
                        causas=(CAUSA_CONTRAPARTE_DESCONOCIDA,),
                    )
                )
                continue
            comparables.setdefault((contraparte, moneda), []).append(detalle)

        segmentos = [
            self._cerrar_segmento(contraparte, moneda, detalles)
            for (contraparte, moneda), detalles in comparables.items()
        ]
        return tuple(segmentos + sueltas)

    @staticmethod
    def _detalle(
        entidad_id: uuid.UUID,
        nombre: str | None,
        tipo: str,
        moneda: str,
        apertura: Any,
        deltas: Any,
    ) -> DetallePosicion:
        """Saldo derivado y su aporte con el signo canonico de §14."""
        if apertura is None:
            return DetallePosicion(
                entidad_id=entidad_id,
                nombre=nombre,
                tipo=tipo,
                moneda=moneda,
                saldo=Saldo.indeterminado(),
                aporte=None,
            )
        saldo = Saldo.de(decimal.Decimal(apertura) + decimal.Decimal(deltas))
        signo = 1 if tipo == TIPO_DERECHO else -1
        return DetallePosicion(
            entidad_id=entidad_id,
            nombre=nombre,
            tipo=tipo,
            moneda=moneda,
            saldo=saldo,
            aporte=signo * saldo.importe,
        )

    @staticmethod
    def _cerrar_segmento(
        contraparte: uuid.UUID, moneda: str, detalles: list[DetallePosicion]
    ) -> SegmentoNeto:
        if any(detalle.aporte is None for detalle in detalles):
            # Basta una pieza desconocida para que el total no sea afirmable.
            return SegmentoNeto(
                contraparte_actor_id=contraparte,
                moneda=moneda,
                estado=INDETERMINADO,
                neto=None,
                posiciones=tuple(detalles),
                causas=(CAUSA_SALDO_DESCONOCIDO,),
            )
        neto = sum(
            (detalle.aporte for detalle in detalles), decimal.Decimal("0")
        )
        return SegmentoNeto(
            contraparte_actor_id=contraparte,
            moneda=moneda,
            estado=DETERMINADO,
            neto=neto,
            posiciones=tuple(detalles),
        )
