# ============================================================
# GAPTO MOBILE 2027
# Fichero: transferencias_service.py
# Ruta: backend/app/services/transferencias_service.py
# Descripcion: F04-06 / B1. OP-10 transferencia propia.
#
#   UNA SOLA TRANSACCION, SEIS FILAS. El hecho, los dos movimientos, la fila de
#   `transferencias` y las dos conciliaciones nacen juntos o no nace ninguno.
#   Por eso este servicio usa los REPOSITORIOS directamente y no llama a
#   HechosService ni a TesoreriaService: cada uno de ellos abre su propia
#   UnidadDeTrabajo, y encadenarlos produciria cinco transacciones separadas
#   donde el contrato exige una. No es duplicar capa, es respetar la
#   atomicidad.
#
#   NEUTRA POR AUSENCIA DE EFECTOS. El hecho TRANSFERENCIA no recibe ningun
#   `hecho_efectos`. No se insertan efectos de importe cero, que ademas son
#   fisicamente imposibles porque `ck_hecho_efectos__importe_delta` exige
#   distinto de cero. Mover dinero entre cuentas propias no empobrece ni
#   enriquece: cambia donde esta.
#
#   ORDEN DE LOCKS IMPUESTO POR EL FISICO. `trg_transferencias__estructura` y
#   la revalidacion parent-side de 0270 bloquean ambas patas con
#   FOR NO KEY UPDATE en orden LEAST/GREATEST. La prevalidacion de este
#   servicio toma EXACTAMENTE ese orden. Elegir otro introduciria un ciclo de
#   espera con los triggers que cierran la operacion al COMMIT.
#
#   TOPOLOGIA H<->M VIVA (R-F04-007). Al COMMIT coexisten locks sobre hechos y
#   sobre movimientos. No se intenta eliminar el riesgo: se asume y se responde
#   con retry de TRANSACCION COMPLETA conservando las seis identidades. Nunca
#   retry parcial, nunca dentro de un trigger.
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
from app.core.modelos_transferencia import (
    CERO,
    CLASE_OPERACION,
    DatosTransferencia,
    ResultadoTransferencia,
    TIPO_HECHO_TRANSFERENCIA,
)
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import hechos_repository as repo_hechos
from app.repositories import tesoreria_repository as repo_tes
from app.repositories import transferencias_repository as repo_transf

_MONEDA_VALIDA = re.compile(r"^[A-Z]{3}$")


class TransferenciasService:
    """OP-10. Traslado de dinero entre dos cuentas del mismo propietario."""

    __slots__ = ("_unidad", "ultima_traza")

    def __init__(self, unidad: UnidadDeTrabajo) -> None:
        self._unidad = unidad
        self.ultima_traza: Traza | None = None

    # ==================================================================
    # OP-10
    # ==================================================================
    def transferir(
        self, contexto: ContextoOperacion, datos: DatosTransferencia
    ) -> ResultadoTransferencia:
        """Materializa una transferencia propia completa.

        Prevalida para producir errores funcionales legibles, pero la autoridad
        sigue siendo PostgreSQL: `trg_transferencias__estructura` vuelve a
        comprobar signos, cuentas, owner e igualdad de importes al COMMIT. Si
        la prevalidacion y el trigger divergieran, manda el trigger.
        """
        self._validar(datos)

        def operacion(sesion: SesionMotor) -> ResultadoTransferencia:
            repo_hechos.exigir_contexto(sesion)

            existentes = self._identidades_existentes(sesion, datos)
            if existentes:
                return self._replay(sesion, datos, existentes)

            self._exigir_cuentas(sesion, datos)
            tipo_hecho_id = self._exigir_tipo_transferencia(sesion)

            # 1. El hecho, sin efectos.
            creado = repo_hechos.insertar_si_no_existe(
                sesion,
                DatosCreacionHecho(
                    hecho_id=datos.hecho_id,
                    fecha_hecho=datos.fecha_hecho,
                    moneda=datos.moneda,
                    presupuestable=False,
                    estado_localizacion="NO_APLICA",
                    tipo_hecho_codigo=TIPO_HECHO_TRANSFERENCIA,
                    concepto=datos.concepto,
                    importe_total=datos.importe_salida,
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

            # 2. Las dos patas. El motor pone el signo; el llamante declara
            #    magnitudes. Se insertan en orden de UUID para que dos OP-10
            #    concurrentes no se crucen.
            patas = sorted(
                (
                    (datos.movimiento_salida_id, datos.cuenta_origen_id,
                     -decimal.Decimal(datos.importe_salida),
                     datos.descripcion_salida),
                    (datos.movimiento_entrada_id, datos.cuenta_destino_id,
                     decimal.Decimal(datos.importe_entrada),
                     datos.descripcion_entrada),
                ),
                key=lambda p: str(p[0]),
            )
            versiones: dict[uuid.UUID, int] = {}
            for movimiento_id, cuenta_id, importe, descripcion in patas:
                resultado = repo_tes.insertar_movimiento_si_no_existe(
                    sesion,
                    movimiento_id=movimiento_id,
                    cuenta_id=cuenta_id,
                    fecha_movimiento=datos.fecha_movimiento,
                    importe=importe,
                    clase_movimiento=CLASE_OPERACION,
                    descripcion=descripcion,
                    confirmado_at=dt.datetime.now(dt.timezone.utc),
                )
                if resultado is None:
                    raise self._conflicto_identidad()
                versiones[movimiento_id] = resultado[0]
                auditoria.registrar(
                    sesion,
                    tabla=repo_tes.TABLA_MOVIMIENTOS,
                    registro_id=movimiento_id,
                    accion=auditoria.ACCION_CREAR,
                    datos_despues_json=resultado[1],
                )

            # 3. Prevalidacion de estructura con los movimientos ya escritos y
            #    bloqueados en el orden del trigger.
            self._prevalidar_estructura(sesion, datos)

            # 4. La fila de transferencias.
            snapshot_transf = repo_transf.insertar_si_no_existe(
                sesion,
                transferencia_id=datos.transferencia_id,
                movimiento_salida_id=datos.movimiento_salida_id,
                movimiento_entrada_id=datos.movimiento_entrada_id,
                notas=datos.notas,
            )
            if snapshot_transf is None:
                raise self._conflicto_identidad()
            auditoria.registrar(
                sesion,
                tabla=repo_transf.TABLA,
                registro_id=datos.transferencia_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=snapshot_transf,
            )

            # 5. Las dos conciliaciones. El importe asignado conserva el signo
            #    de su movimiento: una conciliacion no cambia el sentido del
            #    dinero, solo declara que ese apunte pertenece a este hecho.
            conciliaciones = (
                (datos.conciliacion_salida_id, datos.movimiento_salida_id,
                 -decimal.Decimal(datos.importe_salida)),
                (datos.conciliacion_entrada_id, datos.movimiento_entrada_id,
                 decimal.Decimal(datos.importe_entrada)),
            )
            for conciliacion_id, movimiento_id, importe in conciliaciones:
                snapshot = repo_tes.insertar_conciliacion_si_no_existe(
                    sesion,
                    {
                        "id": conciliacion_id,
                        "hecho_id": datos.hecho_id,
                        "movimiento_tesoreria_id": movimiento_id,
                        "importe_asignado": importe,
                    },
                )
                if snapshot is None:
                    raise self._conflicto_identidad()
                auditoria.registrar(
                    sesion,
                    tabla=repo_tes.TABLA_CONCILIACIONES,
                    registro_id=conciliacion_id,
                    accion=auditoria.ACCION_CREAR,
                    datos_despues_json=snapshot,
                )

            return ResultadoTransferencia(
                transferencia_id=datos.transferencia_id,
                hecho_id=datos.hecho_id,
                hecho_row_version=hecho_version,
                movimiento_salida_id=datos.movimiento_salida_id,
                movimiento_salida_row_version=versiones[datos.movimiento_salida_id],
                movimiento_entrada_id=datos.movimiento_entrada_id,
                movimiento_entrada_row_version=versiones[datos.movimiento_entrada_id],
            )

        return self._ejecutar(contexto, operacion, "OP-10 transferir")

    # ==================================================================
    # Interno
    # ==================================================================
    @staticmethod
    def _identidades_existentes(
        sesion: SesionMotor, datos: DatosTransferencia
    ) -> set[uuid.UUID]:
        """Cuales de las seis identidades reservadas ya estan ocupadas.

        Se consulta el lote COMPLETO antes de escribir nada. Un subconjunto
        ocupado significa que la reserva se mezclo con otra operacion, y eso no
        se completa a medias.
        """
        ocupadas: set[uuid.UUID] = set()
        if repo_hechos.leer_estado(sesion, datos.hecho_id) is not None:
            ocupadas.add(datos.hecho_id)
        for movimiento_id in (datos.movimiento_salida_id, datos.movimiento_entrada_id):
            if repo_tes.leer_movimiento(sesion, movimiento_id) is not None:
                ocupadas.add(movimiento_id)
        if repo_transf.leer(sesion, datos.transferencia_id) is not None:
            ocupadas.add(datos.transferencia_id)
        for conciliacion_id in (
            datos.conciliacion_salida_id,
            datos.conciliacion_entrada_id,
        ):
            if repo_tes.leer_conciliacion(sesion, conciliacion_id) is not None:
                ocupadas.add(conciliacion_id)
        return ocupadas

    def _replay(
        self,
        sesion: SesionMotor,
        datos: DatosTransferencia,
        existentes: set[uuid.UUID],
    ) -> ResultadoTransferencia:
        """Reintento de una OP-10 cuyo COMMIT quedo en resultado desconocido.

        Todo-o-nada: si falta alguna de las seis, o si la transferencia
        existente describe otro par de movimientos, es conflicto de identidad y
        no se completa el resto.
        """
        if set(datos.identidades) != existentes:
            raise self._conflicto_identidad()
        if not repo_transf.creacion_previa_coincide(
            sesion,
            transferencia_id=datos.transferencia_id,
            movimiento_salida_id=datos.movimiento_salida_id,
            movimiento_entrada_id=datos.movimiento_entrada_id,
        ):
            raise self._conflicto_identidad()

        estado = repo_hechos.leer_estado(sesion, datos.hecho_id)
        salida = repo_tes.leer_movimiento(sesion, datos.movimiento_salida_id)
        entrada = repo_tes.leer_movimiento(sesion, datos.movimiento_entrada_id)
        assert estado is not None and salida is not None and entrada is not None
        return ResultadoTransferencia(
            transferencia_id=datos.transferencia_id,
            hecho_id=datos.hecho_id,
            hecho_row_version=estado[0],
            movimiento_salida_id=datos.movimiento_salida_id,
            movimiento_salida_row_version=salida[0],
            movimiento_entrada_id=datos.movimiento_entrada_id,
            movimiento_entrada_row_version=entrada[0],
            idempotente=True,
        )

    @staticmethod
    def _exigir_cuentas(sesion: SesionMotor, datos: DatosTransferencia) -> None:
        for cuenta_id in (datos.cuenta_origen_id, datos.cuenta_destino_id):
            if repo_tes.leer_cuenta(sesion, cuenta_id) is None:
                raise ErrorMotor(
                    CodigoError.CUENTA_DESCONOCIDA,
                    "Alguna de las cuentas indicadas no existe o no es "
                    "accesible.",
                )

    @staticmethod
    def _exigir_tipo_transferencia(sesion: SesionMotor) -> uuid.UUID:
        """El repositorio ya lanza TIPO_HECHO_DESCONOCIDO si falta.

        No se envuelve en una guarda propia: seria codigo muerto y una segunda
        fuente del mismo error.
        """
        return repo_hechos.resolver_tipo_hecho(
            sesion, codigo=TIPO_HECHO_TRANSFERENCIA, tipo_hecho_id=None
        )

    def _prevalidar_estructura(
        self, sesion: SesionMotor, datos: DatosTransferencia
    ) -> None:
        """Comprueba lo que el trigger comprobara al COMMIT, para poder
        devolver un error funcional en vez de un fallo tecnico.

        No sustituye al trigger. Si alguna vez divergieran, la operacion
        seguiria fallando: simplemente lo haria con un mensaje peor.
        """
        contexto = repo_transf.contexto_de_movimientos(
            sesion, datos.movimiento_salida_id, datos.movimiento_entrada_id
        )
        if contexto is None:  # pragma: no cover - las patas se acaban de crear
            raise self._conflicto_identidad()
        salida, entrada = contexto["salida"], contexto["entrada"]

        if salida["importe"] >= CERO or entrada["importe"] <= CERO:
            raise ErrorMotor(
                CodigoError.SIGNOS_INCORRECTOS,
                "La pata de salida debe ser negativa y la de entrada positiva.",
            )
        if salida["cuenta_id"] == entrada["cuenta_id"]:
            raise ErrorMotor(
                CodigoError.MISMA_CUENTA,
                "Origen y destino deben ser cuentas distintas: mover dinero a "
                "la misma cuenta no es una transferencia.",
            )
        if salida["owner_user_id"] != entrada["owner_user_id"]:
            raise ErrorMotor(
                CodigoError.OWNER_DISTINTO,
                "Ambas cuentas deben pertenecer al mismo propietario.",
            )
        if salida["moneda"] == entrada["moneda"] and abs(
            salida["importe"]
        ) != entrada["importe"]:
            raise ErrorMotor(
                CodigoError.IMPORTES_NO_COINCIDEN,
                "En la misma moneda, lo que sale debe igualar a lo que entra.",
            )

    @staticmethod
    def _conflicto_identidad() -> ErrorMotor:
        return ErrorMotor(
            CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
            "Alguno de los identificadores reservados de la transferencia ya "
            "esta en uso con otra intencion.",
        )

    @staticmethod
    def _validar(datos: DatosTransferencia) -> None:
        if datos.comision is not None:
            raise ErrorMotor(
                CodigoError.COMISION_EMBEBIDA,
                "Una comision real es su propia realidad economica, con su "
                "hecho y su efecto: no se esconde dentro de la transferencia.",
            )
        if len(set(datos.identidades)) != 6:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Las seis identidades reservadas deben ser distintas entre si.",
            )
        if datos.cuenta_origen_id == datos.cuenta_destino_id:
            raise ErrorMotor(
                CodigoError.MISMA_CUENTA,
                "Origen y destino deben ser cuentas distintas.",
            )
        for importe in (datos.importe_salida, datos.importe_entrada):
            if importe is None:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "Una transferencia exige importe de salida y de entrada.",
                )
            if decimal.Decimal(importe) <= CERO:
                # El llamante declara MAGNITUDES; el signo lo pone el motor.
                raise ErrorMotor(
                    CodigoError.SIGNOS_INCORRECTOS,
                    "Los importes se declaran como magnitudes positivas: el "
                    "signo de cada pata lo pone el motor.",
                )
        if datos.moneda is None or not _MONEDA_VALIDA.match(datos.moneda):
            raise ErrorMotor(
                CodigoError.MONEDA_INVALIDA,
                "La moneda debe ser un codigo de tres letras mayusculas.",
            )
        if datos.fecha_movimiento is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Ambas patas exigen fecha de movimiento.",
            )

    def _ejecutar(
        self, contexto: ContextoOperacion, operacion: Any, nombre: str
    ) -> ResultadoTransferencia:
        resultado = self._unidad.ejecutar_con_traza(contexto, operacion, nombre=nombre)
        self.ultima_traza = resultado.traza
        return resultado.valor
