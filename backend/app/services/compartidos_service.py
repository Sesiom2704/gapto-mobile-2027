# ============================================================
# GAPTO MOBILE 2027
# Fichero: compartidos_service.py
# Ruta: backend/app/services/compartidos_service.py
# Descripcion: OP-19. Gasto compartido como operacion COMPUESTA Y ATOMICA
#   (F04-D038 §3, §4, §5, §6).
#
#   UNA LLAMADA, UNA TRANSACCION. El orquestador abre la transaccion y
#   construye los servicios YA CERTIFICADOS de F04-01..F04-03 adscritos a ella
#   mediante `UnidadDeTrabajoAdscrita`. Desde dentro llama a sus metodos
#   publicos tal cual. No hay segunda implementacion de efectos, atribuciones,
#   aportaciones, movimientos ni conciliacion: hay una sola, la de siempre,
#   ejecutandose sin COMMIT propio. Si falla cualquier componente solicitado,
#   cae la invocacion entera.
#
#   CAPTURA PARCIAL NO ES COMMIT PARCIAL. Registrar hoy el hecho, el gasto y
#   el reparto conocido, y manana la tesoreria cuando aparezca el apunte del
#   banco, es conocimiento incompleto legitimo: son dos invocaciones, cada una
#   atomica. Lo prohibido es que UNA invocacion que pidio tesoreria confirme
#   solo lo anterior. Por eso todos los componentes salvo el hecho y sus
#   efectos son opcionales, y por eso ninguno se confirma por separado.
#
#   EL HECHO CONSERVA EL 100 %. No se trocea el ticket. Cada dimension vive en
#   su superficie: el total en `hechos_financieros`, la consecuencia economica
#   en `hecho_efectos`, el reparto en `efecto_atribuciones`, quien estuvo en
#   `hecho_participantes`, quien puso el dinero en `hecho_aportaciones_pago`,
#   la caja en `movimientos_tesoreria` y el puente en
#   `hecho_movimientos_tesoreria`.
#
#   OP-19 NO CREA POSICIONES. Que alguien pagara mas de lo que se le atribuye
#   NO significa que le deban: puede ser un regalo, una devolucion pendiente,
#   un acuerdo previo o nada en absoluto. La deuda o el derecho se materializan
#   con OP-12 y su justificacion explicita, que es una decision economica, no
#   una resta. Esta operacion termina con cero posiciones SIEMPRE.
#
#   ORDEN DE LOS PASOS. Tesoreria va ANTES que aportaciones porque una
#   aportacion puede apuntar a su conciliacion (`hecho_movimiento_tesoreria_id`)
#   y porque la prevalidacion acumulada D-169 de OP-06 compara contra la
#   porcion ya conciliada: invertir el orden la dejaria comparando contra cero.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_efectos import DatosEfecto
from app.core.modelos_tesoreria import (
    DatosAportacion,
    DatosConciliacion,
    DatosMovimiento,
)
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.services.efectos_service import EfectosService
from app.services.hechos_service import HechosService
from app.services.participantes_service import (
    DatosParticipante,
    ParticipantesService,
)
from app.services.tesoreria_service import TesoreriaService


@dataclass(frozen=True, slots=True)
class DatosTesoreria:
    """Un movimiento bancario y su puente con el hecho.

    Viajan juntos porque un movimiento sin conciliar no dice nada sobre este
    gasto, y una conciliacion sin movimiento no existe. Un mismo gasto puede
    llevar varios pares: una cena pagada mitad en efectivo y mitad con tarjeta
    son dos realidades de caja distintas, no una partida en dos trozos.
    """

    movimiento: DatosMovimiento
    conciliacion: DatosConciliacion


@dataclass(frozen=True, slots=True)
class DatosGastoCompartido:
    """Entrada de OP-19.

    Las atribuciones viajan DENTRO de cada efecto, que es como ya las acepta
    OP-04. Enriquecer el reparto mas tarde, cuando se sepa, sigue siendo OP-05
    contra el efecto existente.
    """

    hecho: DatosCreacionHecho
    efectos: Sequence[DatosEfecto]
    participantes: Sequence[DatosParticipante] = ()
    aportaciones: Sequence[DatosAportacion] = ()
    tesoreria: Sequence[DatosTesoreria] = ()


@dataclass(frozen=True, slots=True)
class ResultadoGastoCompartido:
    hecho_id: uuid.UUID
    row_version: int
    efectos_creados: int = 0
    atribuciones_creadas: int = 0
    participantes_creados: int = 0
    aportaciones_creadas: int = 0
    movimientos_creados: int = 0
    conciliaciones_creadas: int = 0
    #: Invariante de la operacion, no un contador: OP-19 nunca crea posiciones.
    posiciones_creadas: int = 0
    movimientos: tuple[uuid.UUID, ...] = field(default_factory=tuple)


class GastosCompartidosService:
    """OP-19. Orquestacion atomica de un gasto compartido."""

    def __init__(
        self,
        unidad: UnidadDeTrabajo,
        *,
        impacto_ancla: Any,
    ) -> None:
        """`impacto_ancla` se propaga a `HechosService`, que lo exige.

        No se duplica aqui ninguna decision sobre previsiones: el orquestador
        solo transporta el colaborador que F04-05 obliga a inyectar.
        """
        self._unidad = unidad
        self._impacto_ancla = impacto_ancla
        self.ultima_traza: Any = None

    # ==================================================================
    # Operacion publica
    # ==================================================================
    def registrar_gasto_compartido(
        self, contexto: ContextoOperacion, datos: DatosGastoCompartido
    ) -> ResultadoGastoCompartido:
        """Registra en UNA transaccion todo lo que el llamante haya aportado."""
        self._validar_entrada(datos)

        def operacion(sesion: SesionMotor) -> ResultadoGastoCompartido:
            adscrita = UnidadDeTrabajoAdscrita(sesion)
            hechos = HechosService(adscrita, impacto_ancla=self._impacto_ancla)
            efectos = EfectosService(adscrita)
            participantes = ParticipantesService(adscrita)
            tesoreria = TesoreriaService(adscrita)

            hecho_id = datos.hecho.hecho_id
            resultado_hecho = hechos.crear_hecho(contexto, datos.hecho)
            version = resultado_hecho.row_version

            resultado_efectos = efectos.registrar_efectos(
                contexto,
                hecho_id=hecho_id,
                row_version_esperada=version,
                efectos=datos.efectos,
            )
            version = resultado_efectos.row_version

            participantes_creados = 0
            if datos.participantes:
                resultado_part = participantes.registrar_participantes(
                    contexto,
                    hecho_id=hecho_id,
                    row_version_esperada=version,
                    participantes=datos.participantes,
                )
                version = resultado_part.row_version
                participantes_creados = resultado_part.participantes_creados

            movimientos: list[uuid.UUID] = []
            conciliaciones = 0
            for pieza in datos.tesoreria:
                resultado_mov = tesoreria.registrar_movimiento(
                    contexto, pieza.movimiento
                )
                resultado_conc = tesoreria.conciliar(
                    contexto,
                    pieza.conciliacion,
                    hecho_row_version_esperada=version,
                    movimiento_row_version_esperada=resultado_mov.row_version,
                )
                version = resultado_conc.hecho_row_version
                movimientos.append(pieza.movimiento.movimiento_id)
                conciliaciones += 1

            aportaciones_creadas = 0
            if datos.aportaciones:
                resultado_aport = tesoreria.registrar_aportaciones(
                    contexto,
                    hecho_id=hecho_id,
                    hecho_row_version_esperada=version,
                    aportaciones=datos.aportaciones,
                )
                version = resultado_aport.hecho_row_version
                aportaciones_creadas = resultado_aport.aportaciones_creadas

            return ResultadoGastoCompartido(
                hecho_id=hecho_id,
                row_version=version,
                efectos_creados=len(resultado_efectos.efectos),
                atribuciones_creadas=resultado_efectos.atribuciones_creadas,
                participantes_creados=participantes_creados,
                aportaciones_creadas=aportaciones_creadas,
                movimientos_creados=len(movimientos),
                conciliaciones_creadas=conciliaciones,
                movimientos=tuple(movimientos),
            )

        resultado = self._unidad.ejecutar_con_traza(
            contexto, operacion, nombre="OP-19 registrar_gasto_compartido"
        )
        self.ultima_traza = resultado.traza
        return resultado.valor

    # ==================================================================
    # Interno
    # ==================================================================
    @staticmethod
    def _validar_entrada(datos: DatosGastoCompartido) -> None:
        """Lo minimo para que exista un gasto: el hecho y su consecuencia.

        Las demas validaciones NO se replican aqui: las hace cada operacion
        interna con su propio contrato. Duplicarlas crearia dos fuentes de
        verdad que divergirian en la primera correccion.
        """
        if datos.hecho is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "OP-19 exige el hecho que conserva el 100 % de la realidad.",
            )
        if not datos.efectos:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "OP-19 exige al menos un efecto: un gasto sin consecuencia "
                "economica no es un gasto.",
            )
        for pieza in datos.tesoreria:
            if pieza.conciliacion.hecho_id != datos.hecho.hecho_id:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "La conciliacion debe referirse al hecho de esta "
                    "operacion.",
                )
            if (
                pieza.conciliacion.movimiento_tesoreria_id
                != pieza.movimiento.movimiento_id
            ):
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "La conciliacion debe referirse al movimiento con el que "
                    "viaja.",
                )
