# ============================================================
# GAPTO MOBILE 2027
# Fichero: devoluciones_service.py
# Ruta: backend/app/services/devoluciones_service.py
# Descripcion: F04-06 / B3. OP-13 devolucion economica.
#
#   UNA DEVOLUCION NO ES UNA REVERSION NI UNA CORRECCION. Crea un hecho NUEVO
#   con un efecto de la MISMA naturaleza y signo contrario, mas la relacion
#   DEVOLUCION_DE. El original sigue siendo cierto: no se edita, no se anula y
#   no se le quita nada.
#
#   INV-05 · NUNCA INGRESO. Devolver un gasto de 120 produce un GASTO de -45,
#   jamas un INGRESO de 45. Que el dinero entre en la cuenta no convierte el
#   acontecimiento en un ingreso: la naturaleza la fija el original.
#
#   F04-D030 · CAPACIDAD AGREGADA POR NATURALEZA. `hecho_relaciones` une
#   hechos, no efectos, de modo que no existe trazabilidad hacia un
#   `hecho_efectos.id` concreto. La capacidad reversible es la suma FIRMADA de
#   los efectos de esa naturaleza. Si los signos se mezclan, la base no
#   determina univocamente cuanto puede revertirse y se falla cerrado. No se
#   escoge un efecto, no se reparte proporcionalmente y no se inventa
#   trazabilidad.
#
#   EL LOCK ES LA UNICA DEFENSA. No existe constraint fisica sobre el acumulado
#   devuelto. El hecho ORIGINAL se bloquea con FOR NO KEY UPDATE antes de leer
#   cuanto se ha devuelto ya, y esa es toda la proteccion frente a dos
#   devoluciones simultaneas. Es el mismo patron de R-F04-017: sin el lock, dos
#   transacciones leen la misma capacidad y la agotan dos veces sin que nada
#   las detenga.
#
#   F04-D033 · COEXISTE CON OP-17. Que el hecho original materializara una
#   previsión sigue siendo cierto despues de la devolucion. Este servicio NO
#   lee para escribir ni modifica `prevision_hechos`; solo informa de cuantos
#   vinculos tiene el original.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid
from typing import Any

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_devolucion import (
    CERO,
    DatosDevolucion,
    NATURALEZAS_DEVOLUBLES,
    ResultadoDevolucion,
    TIPO_RELACION_DEVOLUCION,
)
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import efectos_repository as repo_efectos
from app.repositories import hechos_repository as repo_hechos
from app.repositories import relaciones_repository as repo_rel
from app.repositories import tesoreria_repository as repo_tes

_MONEDA_VALIDA = re.compile(r"^[A-Z]{3}$")
TIPO_HECHO_POR_NATURALEZA = {
    "GASTO": "GASTO",
    "INGRESO": "INGRESO",
    "DEUDA": "GASTO",
    "DERECHO_COBRO": "INGRESO",
}


class DevolucionesService:
    """OP-13. Realidad economica posterior que reduce un efecto anterior."""

    __slots__ = ("_unidad", "ultima_traza")

    def __init__(self, unidad: UnidadDeTrabajo) -> None:
        self._unidad = unidad
        self.ultima_traza: Traza | None = None

    # ==================================================================
    # OP-13
    # ==================================================================
    def devolver(
        self, contexto: ContextoOperacion, datos: DatosDevolucion
    ) -> ResultadoDevolucion:
        self._validar(datos)

        def operacion(sesion: SesionMotor) -> ResultadoDevolucion:
            repo_hechos.exigir_contexto(sesion)

            if repo_hechos.leer_estado(sesion, datos.hecho_id) is not None:
                return self._replay(sesion, datos)

            # 1. El lock del ORIGINAL va primero y antes de leer nada: es lo
            #    unico que serializa dos devoluciones concurrentes.
            if not repo_rel.bloquear_hechos(sesion, [datos.hecho_original_id]):
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El hecho original no existe o no es accesible.",
                )
            estado_original = repo_hechos.leer_estado(sesion, datos.hecho_original_id)
            assert estado_original is not None
            if estado_original[1] != "ACTIVO":
                raise ErrorMotor(
                    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                    "Un hecho anulado no es realidad: no hay nada que devolver.",
                )

            self._exigir_moneda_comparable(sesion, datos)
            capacidad, neto = self._capacidad(sesion, datos)

            devuelto = decimal.Decimal(
                repo_rel.devuelto_acumulado(
                    sesion, datos.hecho_original_id, datos.tipo_efecto
                )
            )
            magnitud = decimal.Decimal(datos.importe)
            if devuelto + magnitud > capacidad:
                raise ErrorMotor(
                    CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE,
                    "Lo devuelto no puede superar lo que el hecho original "
                    "reconocio para esa naturaleza.",
                )

            # 2. El signo lo deriva el motor del neto del original.
            signo = -1 if neto > CERO else 1
            importe_delta = magnitud * signo

            # 3. El hecho de la devolucion.
            tipo_hecho_id = repo_hechos.resolver_tipo_hecho(
                sesion,
                codigo=TIPO_HECHO_POR_NATURALEZA[datos.tipo_efecto],
                tipo_hecho_id=None,
            )
            creado = repo_hechos.insertar_si_no_existe(
                sesion,
                DatosCreacionHecho(
                    hecho_id=datos.hecho_id,
                    fecha_hecho=datos.fecha_hecho,
                    moneda=datos.moneda,
                    presupuestable=False,
                    estado_localizacion="NO_APLICA",
                    tipo_hecho_codigo=TIPO_HECHO_POR_NATURALEZA[datos.tipo_efecto],
                    concepto=datos.concepto,
                    importe_total=magnitud,
                ),
                tipo_hecho_id,
            )
            if creado is None:
                raise self._conflicto_identidad()
            hecho_version, _, snapshot_hecho = creado
            auditoria.registrar(
                sesion,
                tabla=repo_hechos.TABLA,
                registro_id=datos.hecho_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=snapshot_hecho,
            )

            # 4. Su efecto: misma naturaleza, signo contrario.
            efecto = repo_efectos.insertar_efecto_si_no_existe(
                sesion,
                datos.hecho_id,
                efecto_id=datos.efecto_id,
                tipo_efecto=datos.tipo_efecto,
                importe_delta=importe_delta,
                estado_atribucion=datos.estado_atribucion,
                categoria_id=datos.categoria_id,
                descripcion=datos.concepto,
            )
            if efecto is None:
                raise self._conflicto_identidad()
            auditoria.registrar(
                sesion,
                tabla=repo_efectos.TABLA_EFECTOS,
                registro_id=datos.efecto_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=efecto[1],
            )

            # 5. La relacion, bajo el protocolo de unicidad logica F04-D028.
            self._crear_relacion(sesion, datos, magnitud)

            # 6. La caja, si la hay. Es opcional a proposito: el efecto puede
            #    preceder al dinero.
            if datos.con_caja:
                self._registrar_caja(sesion, datos, importe_delta)

            return ResultadoDevolucion(
                hecho_id=datos.hecho_id,
                hecho_row_version=hecho_version,
                efecto_id=datos.efecto_id,
                relacion_id=datos.relacion_id,
                tipo_efecto=datos.tipo_efecto,
                importe_delta=importe_delta,
                capacidad=capacidad,
                devuelto_acumulado=devuelto + magnitud,
                pendiente=capacidad - devuelto - magnitud,
                previsiones_del_original=repo_rel.vinculos_de_prevision(
                    sesion, datos.hecho_original_id
                ),
                movimiento_id=datos.movimiento_id,
            )

        return self._ejecutar(contexto, operacion, "OP-13 devolver")

    # ==================================================================
    # Interno
    # ==================================================================
    def _capacidad(
        self, sesion: SesionMotor, datos: DatosDevolucion
    ) -> tuple[decimal.Decimal, decimal.Decimal]:
        """Capacidad reversible de la naturaleza pedida (F04-D030)."""
        resumen = repo_rel.capacidad_por_naturaleza(
            sesion, datos.hecho_original_id, datos.tipo_efecto
        )
        if resumen is None:
            raise ErrorMotor(
                CodigoError.NATURALEZA_DISTINTA_DEL_ORIGEN,
                "El hecho original no reconocio ningun efecto de esa "
                "naturaleza: no hay nada de ese tipo que devolver.",
            )
        if resumen["signos_distintos"] > 1:
            # Con signos mezclados la base no determina univocamente cuanto
            # puede revertirse. Repartir o escoger un efecto seria inventar
            # una trazabilidad que el modelo no conserva.
            raise ErrorMotor(
                CodigoError.CAPACIDAD_REVERSIBLE_NO_DEMOSTRABLE,
                "Los efectos de esa naturaleza en el hecho original mezclan "
                "signos: la capacidad reversible no es demostrable.",
            )
        neto = decimal.Decimal(resumen["neto"])
        return abs(neto), neto

    def _crear_relacion(
        self,
        sesion: SesionMotor,
        datos: DatosDevolucion,
        magnitud: decimal.Decimal,
    ) -> None:
        """Protocolo de unicidad logica de F04-D028.

        Los dos hechos ya estan bloqueados —el original antes de todo, el nuevo
        por haberlo creado en esta transaccion— y la relectura ocurre DESPUES.
        Sin UNIQUE fisica, leer antes del lock no probaria nada.

        La direccion es la de F04-D030: origen = hecho NUEVO de devolucion,
        destino = hecho ORIGINAL reducido.
        """
        existente = repo_rel.leer_relacion_logica(
            sesion,
            hecho_origen_id=datos.hecho_id,
            hecho_destino_id=datos.hecho_original_id,
            tipo_relacion=TIPO_RELACION_DEVOLUCION,
        )
        if existente is not None:
            if decimal.Decimal(existente["importe_relacionado"]) != magnitud:
                raise ErrorMotor(
                    CodigoError.RELACION_DUPLICADA_CON_OTRA_INTENCION,
                    "Ya existe esa relacion entre los dos hechos con otra "
                    "porcion: no se crea una segunda fila.",
                )
            return

        snapshot = repo_rel.insertar_relacion_si_no_existe(
            sesion,
            relacion_id=datos.relacion_id,
            hecho_origen_id=datos.hecho_id,
            hecho_destino_id=datos.hecho_original_id,
            tipo_relacion=TIPO_RELACION_DEVOLUCION,
            importe_relacionado=magnitud,
            notas=datos.notas,
        )
        if snapshot is None:
            raise self._conflicto_identidad()
        auditoria.registrar(
            sesion,
            tabla=repo_rel.TABLA,
            registro_id=datos.relacion_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=snapshot,
        )

    def _registrar_caja(
        self,
        sesion: SesionMotor,
        datos: DatosDevolucion,
        importe_delta: decimal.Decimal,
    ) -> None:
        """Movimiento y conciliacion de la devolucion.

        El movimiento lleva el signo CONTRARIO al del efecto: devolver un gasto
        produce un efecto negativo y una entrada de dinero.
        """
        if repo_tes.leer_cuenta(sesion, datos.cuenta_id) is None:
            raise ErrorMotor(
                CodigoError.CUENTA_DESCONOCIDA,
                "La cuenta indicada no existe o no es accesible.",
            )
        importe_movimiento = -importe_delta
        creado = repo_tes.insertar_movimiento_si_no_existe(
            sesion,
            movimiento_id=datos.movimiento_id,
            cuenta_id=datos.cuenta_id,
            fecha_movimiento=datos.fecha_movimiento or datos.fecha_hecho,
            importe=importe_movimiento,
            clase_movimiento="OPERACION",
            descripcion=datos.concepto,
            confirmado_at=dt.datetime.now(dt.timezone.utc),
        )
        if creado is None:
            raise self._conflicto_identidad()
        auditoria.registrar(
            sesion,
            tabla=repo_tes.TABLA_MOVIMIENTOS,
            registro_id=datos.movimiento_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=creado[1],
        )
        snapshot = repo_tes.insertar_conciliacion_si_no_existe(
            sesion,
            {
                "id": datos.conciliacion_id,
                "hecho_id": datos.hecho_id,
                "movimiento_tesoreria_id": datos.movimiento_id,
                "importe_asignado": importe_movimiento,
            },
        )
        if snapshot is None:
            raise self._conflicto_identidad()
        auditoria.registrar(
            sesion,
            tabla=repo_tes.TABLA_CONCILIACIONES,
            registro_id=datos.conciliacion_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=snapshot,
        )

    @staticmethod
    def _exigir_moneda_comparable(
        sesion: SesionMotor, datos: DatosDevolucion
    ) -> None:
        """Sin equivalencia declarada no se compara nominalmente.

        Acumular 45 USD contra una capacidad de 120 EUR seria inventar un tipo
        de cambio de 1:1, que es exactamente el FX implicito que el mandato
        prohibe.
        """
        moneda_original = repo_rel.moneda_de_hecho(sesion, datos.hecho_original_id)
        if moneda_original != datos.moneda and not datos.equivalencia_declarada:
            raise ErrorMotor(
                CodigoError.DEVOLUCION_MULTIDIVISA_NO_DEMOSTRADA,
                "La devolucion esta en otra moneda: la equivalencia debe "
                "declararse explicitamente, no se infiere.",
            )

    def _replay(
        self, sesion: SesionMotor, datos: DatosDevolucion
    ) -> ResultadoDevolucion:
        """Reintento de una OP-13 cuyo COMMIT quedo en resultado desconocido."""
        relacion = repo_rel.leer_relacion(sesion, datos.relacion_id)
        if (
            relacion is None
            or relacion["hecho_origen_id"] != datos.hecho_id
            or relacion["hecho_destino_id"] != datos.hecho_original_id
            or decimal.Decimal(relacion["importe_relacionado"])
            != decimal.Decimal(datos.importe)
        ):
            raise self._conflicto_identidad()
        estado = repo_hechos.leer_estado(sesion, datos.hecho_id)
        assert estado is not None
        capacidad, neto = self._capacidad(sesion, datos)
        devuelto = decimal.Decimal(
            repo_rel.devuelto_acumulado(
                sesion, datos.hecho_original_id, datos.tipo_efecto
            )
        )
        signo = -1 if neto > CERO else 1
        return ResultadoDevolucion(
            hecho_id=datos.hecho_id,
            hecho_row_version=estado[0],
            efecto_id=datos.efecto_id,
            relacion_id=datos.relacion_id,
            tipo_efecto=datos.tipo_efecto,
            importe_delta=decimal.Decimal(datos.importe) * signo,
            capacidad=capacidad,
            devuelto_acumulado=devuelto,
            pendiente=capacidad - devuelto,
            previsiones_del_original=repo_rel.vinculos_de_prevision(
                sesion, datos.hecho_original_id
            ),
            movimiento_id=datos.movimiento_id,
            idempotente=True,
        )

    @staticmethod
    def _conflicto_identidad() -> ErrorMotor:
        return ErrorMotor(
            CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
            "Alguno de los identificadores reservados de la devolucion ya "
            "esta en uso con otra intencion.",
        )

    @staticmethod
    def _validar(datos: DatosDevolucion) -> None:
        if datos.hecho_id == datos.hecho_original_id:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Un hecho no se devuelve a si mismo.",
            )
        if datos.tipo_efecto not in NATURALEZAS_DEVOLUBLES:
            raise ErrorMotor(
                CodigoError.NATURALEZA_DISTINTA_DEL_ORIGEN,
                "Esa naturaleza no admite devolucion en F04-06.",
            )
        if datos.tipo_efecto_devolucion is not None and (
            datos.tipo_efecto_devolucion != datos.tipo_efecto
        ):
            if datos.tipo_efecto_devolucion == "INGRESO":
                raise ErrorMotor(
                    CodigoError.INGRESO_NO_PERMITIDO,
                    "Devolver un gasto produce un gasto negativo, nunca un "
                    "ingreso: que el dinero entre no cambia la naturaleza.",
                )
            raise ErrorMotor(
                CodigoError.NATURALEZA_DISTINTA_DEL_ORIGEN,
                "Una devolucion conserva la naturaleza del hecho original.",
            )
        if datos.importe is None or decimal.Decimal(datos.importe) <= CERO:
            raise ErrorMotor(
                CodigoError.IMPORTE_NO_POSITIVO,
                "El importe devuelto se declara como magnitud positiva.",
            )
        if datos.moneda is None or not _MONEDA_VALIDA.match(datos.moneda):
            raise ErrorMotor(
                CodigoError.MONEDA_INVALIDA,
                "La moneda debe ser un codigo de tres letras mayusculas.",
            )
        if datos.fecha_hecho is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una devolucion exige fecha economica.",
            )
        if datos.con_caja and (
            datos.conciliacion_id is None or datos.cuenta_id is None
        ):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Con movimiento hacen falta tambien cuenta y conciliacion: "
                "dinero sin conciliar dejaria el hecho sin su caja.",
            )
        identidades = [datos.hecho_id, datos.efecto_id, datos.relacion_id]
        if datos.con_caja:
            identidades += [datos.movimiento_id, datos.conciliacion_id]
        if len(set(identidades)) != len(identidades):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Las identidades reservadas deben ser distintas entre si.",
            )

    def _ejecutar(
        self, contexto: ContextoOperacion, operacion: Any, nombre: str
    ) -> ResultadoDevolucion:
        resultado = self._unidad.ejecutar_con_traza(contexto, operacion, nombre=nombre)
        self.ultima_traza = resultado.traza
        return resultado.valor
