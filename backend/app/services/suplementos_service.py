# ============================================================
# GAPTO MOBILE 2027
# Fichero: suplementos_service.py
# Ruta: backend/app/services/suplementos_service.py
# Descripcion: F04-06 / B4. OP-18 realidad suplementaria / fecha economica.
#
#   LA FRONTERA QUE ESTE SERVICIO DEFIENDE:
#
#     OP-02   corrige lo que NUNCA fue cierto. No crea hecho.
#     OP-13   DESHACE un efecto anterior, con signo contrario.
#     OP-18   AÑADE realidad que si ocurrio, con su propia fecha economica.
#
#   Ninguna garantia fisica las distingue: las tres producen filas validas.
#   Un importe mal tecleado en enero y una revision de alquiler descubierta en
#   junio son indistinguibles para PostgreSQL. La distincion la sostiene este
#   servicio, y por eso el mutante N8 es el mas importante del bloque.
#
#   INV-07 · CORRIGE_A NO ES UN ERROR DE CAPTURA. La relacion representa un
#   ajuste REAL posterior. Pero la frontera entre corregir y suplementar es de
#   OPERACION, no de fechas: la elige quien llama al escoger OP-02/OP-21 o
#   OP-18. El motor no la infiere y no debe inventarse una heuristica temporal
#   para deducirla.
#
#   NO EXISTE NINGUNA REGLA DE ORDEN CRONOLOGICO. Un suplemento puede tener
#   fecha economica ANTERIOR, igual o posterior a la del hecho con el que se
#   relaciona: el 20 de septiembre puede descubrirse un gasto atribuible al 31
#   de agosto, y `fecha_hecho` es la fecha ECONOMICA demostrada, no la de
#   registro —esa es `created_at`—. La relacion expresa significado economico,
#   no secuencia temporal.
#
#   INV-08 · UN HECHO POR PERIODO. Un efecto no tiene fecha propia: la toma de
#   su hecho. Una realidad que abarca varios periodos economicos exige un hecho
#   por periodo, y este servicio crea exactamente uno.
# Version: 0.3.0
#   0.3.0 (F04-D046 R2 · A20/A08-bis): OP-18 deja de fijar
#   `presupuestable=False` y `estado_localizacion="NO_APLICA"`. El suplemento
#   recibe su propia decision historica, sin heredarla del hecho ajustado ni
#   del original: con GASTO/INGRESO es obligatoria y sin default; con
#   DEUDA/DERECHO_COBRO se deriva `false`. Localizacion aplicable sin dato ->
#   DESCONOCIDA. La regla vive en una unica funcion pura compartida con OP-13
#   (`resolver_decision_historica`), de modo que ambas operaciones no pueden
#   divergir. Alta y replay construyen la raiz desde el mismo punto.
# Version: 0.2.0
#   0.2.0 (F04-06, iteracion correctiva): se ELIMINA la regla inventada que
#   exigia fecha posterior a la del hecho ajustado. Contradecia F04-D002 e
#   INV-08: una realidad suplementaria puede pertenecer a un periodo economico
#   anterior.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import re
import uuid
from typing import Any

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_suplemento import (
    CERO,
    DatosSuplemento,
    NATURALEZAS_SUPLEMENTABLES,
    ResultadoSuplemento,
    TIPO_RELACION_CORRIGE,
)
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import efectos_repository as repo_efectos
from app.repositories import hechos_repository as repo_hechos
from app.repositories import relaciones_repository as repo_rel
from app.services.devoluciones_service import resolver_decision_historica

_MONEDA_VALIDA = re.compile(r"^[A-Z]{3}$")


class SuplementosService:
    """OP-18. Realidad que se descubre despues y si ocurrio."""

    __slots__ = ("_unidad", "ultima_traza")

    def __init__(self, unidad: UnidadDeTrabajo) -> None:
        self._unidad = unidad
        self.ultima_traza: Traza | None = None

    # ==================================================================
    # OP-18
    # ==================================================================
    def registrar(
        self, contexto: ContextoOperacion, datos: DatosSuplemento
    ) -> ResultadoSuplemento:
        self._validar(datos)

        def operacion(sesion: SesionMotor) -> ResultadoSuplemento:
            repo_hechos.exigir_contexto(sesion)

            if repo_hechos.leer_estado(sesion, datos.hecho_id) is not None:
                return self._replay(sesion, datos)

            if datos.con_relacion:
                # El hecho ajustado se bloquea ANTES de leer su fecha: la
                # relacion se crea bajo el protocolo de F04-D028 y la lectura
                # posterior al lock es lo unico que la hace fiable.
                if not repo_rel.bloquear_hechos(sesion, [datos.hecho_ajustado_id]):
                    raise ErrorMotor(
                        CodigoError.AGREGADO_NO_ENCONTRADO,
                        "El hecho ajustado no existe o no es accesible.",
                    )

            tipo_hecho_id = repo_hechos.resolver_tipo_hecho(
                sesion, codigo=datos.tipo_hecho_codigo, tipo_hecho_id=None
            )
            creado = repo_hechos.insertar_si_no_existe(
                sesion, self._datos_hecho(datos), tipo_hecho_id
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

            efecto = repo_efectos.insertar_efecto_si_no_existe(
                sesion,
                datos.hecho_id,
                efecto_id=datos.efecto_id,
                tipo_efecto=datos.tipo_efecto,
                importe_delta=datos.importe_delta,
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

            if datos.con_relacion:
                self._crear_relacion(sesion, datos)

            return ResultadoSuplemento(
                hecho_id=datos.hecho_id,
                hecho_row_version=hecho_version,
                efecto_id=datos.efecto_id,
                tipo_efecto=datos.tipo_efecto,
                importe_delta=decimal.Decimal(datos.importe_delta),
                fecha_hecho=datos.fecha_hecho,
                relacion_id=datos.relacion_id if datos.con_relacion else None,
            )

        return self._ejecutar(contexto, operacion, "OP-18 realidad suplementaria")

    # ==================================================================
    # Interno
    # ==================================================================
    def _crear_relacion(self, sesion: SesionMotor, datos: DatosSuplemento) -> None:
        """CORRIGE_A bajo el protocolo de unicidad logica de F04-D028."""
        existente = repo_rel.leer_relacion_logica(
            sesion,
            hecho_origen_id=datos.hecho_id,
            hecho_destino_id=datos.hecho_ajustado_id,
            tipo_relacion=TIPO_RELACION_CORRIGE,
        )
        if existente is not None:
            return
        snapshot = repo_rel.insertar_relacion_si_no_existe(
            sesion,
            relacion_id=datos.relacion_id,
            hecho_origen_id=datos.hecho_id,
            hecho_destino_id=datos.hecho_ajustado_id,
            tipo_relacion=TIPO_RELACION_CORRIGE,
            importe_relacionado=abs(decimal.Decimal(datos.importe_delta)),
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

    def _replay(
        self, sesion: SesionMotor, datos: DatosSuplemento
    ) -> ResultadoSuplemento:
        """Reintento de una OP-18 cuyo COMMIT quedo en resultado desconocido."""
        tipo_hecho_id = repo_hechos.resolver_tipo_hecho(
            sesion, codigo=datos.tipo_hecho_codigo, tipo_hecho_id=None
        )
        coincide = repo_hechos.creacion_previa_coincide(
            sesion, self._datos_hecho(datos), tipo_hecho_id
        )
        if not coincide:
            raise self._conflicto_identidad()
        estado = repo_hechos.leer_estado(sesion, datos.hecho_id)
        assert estado is not None
        return ResultadoSuplemento(
            hecho_id=datos.hecho_id,
            hecho_row_version=estado[0],
            efecto_id=datos.efecto_id,
            tipo_efecto=datos.tipo_efecto,
            importe_delta=decimal.Decimal(datos.importe_delta),
            fecha_hecho=datos.fecha_hecho,
            relacion_id=datos.relacion_id if datos.con_relacion else None,
            idempotente=True,
        )

    @staticmethod
    def _datos_hecho(datos: DatosSuplemento) -> DatosCreacionHecho:
        """Raiz del suplemento, identica en alta y en replay (F04-D046 R2)."""
        decision, estado, localidad = resolver_decision_historica(
            datos.tipo_efecto,
            datos.presupuestable,
            datos.estado_localizacion,
            datos.localidad_id,
        )
        return DatosCreacionHecho(
            hecho_id=datos.hecho_id,
            fecha_hecho=datos.fecha_hecho,
            moneda=datos.moneda,
            presupuestable=decision,
            estado_localizacion=estado,
            localidad_id=localidad,
            tipo_hecho_codigo=datos.tipo_hecho_codigo,
            concepto=datos.concepto,
            importe_total=abs(decimal.Decimal(datos.importe_delta)),
        )

    @staticmethod
    def _conflicto_identidad() -> ErrorMotor:
        return ErrorMotor(
            CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
            "Alguno de los identificadores reservados ya esta en uso con otra "
            "intencion.",
        )

    @staticmethod
    def _validar(datos: DatosSuplemento) -> None:
        if datos.editar_original:
            raise ErrorMotor(
                CodigoError.EDICION_DE_ORIGINAL_NO_PERMITIDA,
                "OP-18 no modifica una realidad anterior: lo que nunca fue "
                "cierto se corrige con OP-02.",
            )
        if not datos.fecha_demostrada:
            raise ErrorMotor(
                CodigoError.FECHA_ECONOMICA_NO_DEMOSTRADA,
                "Una realidad posterior exige fecha economica demostrada: sin "
                "ella no se retrodata nada.",
            )
        if datos.periodo_cerrado and not datos.politica_periodo_cerrado:
            raise ErrorMotor(
                CodigoError.PERIODO_CERRADO_SIN_POLITICA,
                "El periodo economico esta cerrado y no hay politica "
                "aplicable: F04-06 no inventa una.",
            )
        if datos.fecha_hecho is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una realidad suplementaria exige fecha economica.",
            )
        if datos.tipo_efecto not in NATURALEZAS_SUPLEMENTABLES:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Esa naturaleza no admite realidad suplementaria en F04-06.",
            )
        if datos.importe_delta is None or decimal.Decimal(
            datos.importe_delta
        ) == CERO:
            # Un efecto de cero es ademas fisicamente imposible.
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "El efecto suplementario exige un importe distinto de cero.",
            )
        if datos.moneda is None or not _MONEDA_VALIDA.match(datos.moneda):
            raise ErrorMotor(
                CodigoError.MONEDA_INVALIDA,
                "La moneda debe ser un codigo de tres letras mayusculas.",
            )
        if datos.con_relacion and datos.relacion_id is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Relacionar con un hecho anterior exige identidad reservada "
                "para la relacion.",
            )
        if datos.hecho_id == datos.hecho_ajustado_id:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Un hecho no se ajusta a si mismo.",
            )
        # F04-D046 R2. Validacion pura de la decision historica, antes de abrir
        # transaccion.
        resolver_decision_historica(
            datos.tipo_efecto,
            datos.presupuestable,
            datos.estado_localizacion,
            datos.localidad_id,
        )

    def _ejecutar(
        self, contexto: ContextoOperacion, operacion: Any, nombre: str
    ) -> ResultadoSuplemento:
        resultado = self._unidad.ejecutar_con_traza(contexto, operacion, nombre=nombre)
        self.ultima_traza = resultado.traza
        return resultado.valor
