# ============================================================
# GAPTO MOBILE 2027
# Fichero: correcciones_service.py
# Ruta: backend/app/services/correcciones_service.py
# Descripcion: F04-06 / B5. OP-21 correccion agregada.
#
#   OP-21 CORRIGE LO QUE NUNCA FUE CIERTO. No es un acontecimiento economico
#   posterior: eso es OP-18. No deshace un efecto anterior: eso es OP-13. Aqui
#   se arregla un dato falso, y la diferencia importa porque las tres cosas
#   producen filas perfectamente validas y PostgreSQL no puede distinguirlas.
#
#   TRES VIAS, Y SOLO TRES:
#     UPDATE   el dato existe y es corregible;
#     DELETE   la fila hija o puente NUNCA debio existir y no tiene sustituto;
#     OP-03    la RAIZ COMPLETA nunca debio existir -> ANULADO.
#
#   El GRANT de 0320 no crea una API generica de borrado. `hechos_financieros`
#   y `movimientos_tesoreria` quedaron expresamente fuera de ese GRANT, y este
#   servicio se niega a borrarlos: quien lo pida recibe
#   CORRECCION_REQUIERE_ANULACION_DE_RAIZ en vez de un hard-delete.
#
#   D-187 · ESTADO FINAL. Un hecho ACTIVO cuyo tipo no sea TRANSFERENCIA no
#   puede terminar sin efectos. Puede quedarse en cero DENTRO de la
#   transaccion si antes del COMMIT se instala el reemplazo: la guarda se
#   evalua sobre el estado FINAL, no sobre cada paso. Y nunca se reclasifica a
#   TRANSFERENCIA para salvar la invariante.
#
#   REALIDAD YA CONFIRMADA. F04-06 opera sobre realidad consolidada. El flujo
#   ordinario NO se diseña suponiendo que puede crear y retirar en la misma
#   transaccion una realidad que nunca llego a existir: ese camino choca con
#   los eventos diferidos del alta, como quedo registrado al cerrar F03.
#
#   D-080 · ADVISORY PRIMERO. Si la correccion toca superficies de inversion,
#   el advisory (INVERSIONES, owner) se toma ANTES de cualquier row lock. Los
#   locks genericos no lo sustituyen.
# Version: 0.4.0
#   0.4.0 (F04-D036): guarda de ESTADO FINAL de los vinculos
#   posicion<->efecto. Corregir el `tipo_efecto` de un efecto vinculado
#   llevaba el saldo de la posicion a CERO CONOCIDO sin cobro, sin
#   condonacion y sin cierre.
# Version: 0.3.0
#   0.3.0 (F04-06 B5): revalidacion cruzada con OP-13. Una correccion no puede
#   dejar la capacidad reversible por debajo de lo ya devuelto.
# Version: 0.2.0
#   0.2.0 (F04-06 B5): la lista de campos corregibles de un efecto se valida en
#   la frontera. Antes el repositorio los filtraba en silencio y el servicio
#   devolvia AGREGADO_NO_ENCONTRADO para un efecto que si existe.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import correcciones_repository as repo_corr
from app.repositories import efectos_repository as repo_efectos
from app.repositories import hechos_repository as repo_hechos
from app.repositories import relaciones_repository as repo_rel
from app.services import coherencia_posicion

TIPO_TRANSFERENCIA = "TRANSFERENCIA"

# Campos de un efecto que OP-21 puede corregir. La lista es CERRADA: aceptar
# cualquier columna permitiria reescribir la identidad del efecto o moverlo a
# otro hecho, que no es corregir un dato falso sino falsificar a que realidad
# pertenece. El repositorio vuelve a filtrar por defensa en profundidad, pero
# el error legible se produce aqui.
CAMPOS_EFECTO_CORREGIBLES = frozenset(
    {"importe_delta", "categoria_id", "descripcion", "tipo_efecto"}
)


@dataclass(frozen=True, slots=True)
class DatosCorreccion:
    """Entrada de OP-21.

    `motivo` es obligatorio y no vacio (D-186). Una correccion sin motivo es
    indistinguible de un cambio arbitrario cuando alguien la lea dentro de un
    ano.

    `eliminar_hecho` y `eliminar_movimiento` existen SOLO para rechazarlos con
    un error de dominio: el GRANT de 0320 no alcanza a las raices y este
    servicio tampoco.
    """

    hecho_id: uuid.UUID
    row_version_esperada: int
    motivo: str | None

    efectos_a_actualizar: dict[uuid.UUID, dict[str, Any]] = field(
        default_factory=dict
    )
    efectos_a_eliminar: tuple[uuid.UUID, ...] = ()
    efectos_a_crear: tuple[Any, ...] = ()
    relaciones_a_eliminar: tuple[uuid.UUID, ...] = ()
    conciliaciones_a_eliminar: tuple[uuid.UUID, ...] = ()

    toca_inversion: bool = False

    # Solo para rechazar.
    eliminar_hecho: bool = False
    eliminar_movimiento: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class ResultadoCorreccion:
    hecho_id: uuid.UUID
    hecho_row_version: int
    efectos_actualizados: int = 0
    efectos_eliminados: int = 0
    efectos_creados: int = 0
    relaciones_eliminadas: int = 0
    conciliaciones_eliminadas: int = 0
    efectos_finales: int = 0


class CorreccionesService:
    """OP-21. Correccion agregada de un hecho y sus hijos."""

    __slots__ = ("_unidad", "ultima_traza")

    def __init__(self, unidad: UnidadDeTrabajo) -> None:
        self._unidad = unidad
        self.ultima_traza: Traza | None = None

    # ==================================================================
    # OP-21
    # ==================================================================
    def corregir(
        self, contexto: ContextoOperacion, datos: DatosCorreccion
    ) -> ResultadoCorreccion:
        self._validar(datos)

        def operacion(sesion: SesionMotor) -> ResultadoCorreccion:
            owner = repo_hechos.exigir_contexto(sesion)

            # 1. Advisory ANTES de cualquier fila (D-080).
            if datos.toca_inversion:
                repo_corr.tomar_advisory_inversiones(sesion, owner)

            # 2. Root lock y control optimista.
            if not repo_rel.bloquear_hechos(sesion, [datos.hecho_id]):
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El hecho indicado no existe o no es accesible.",
                )
            nueva_version = repo_hechos.tocar_raiz(
                sesion, datos.hecho_id, datos.row_version_esperada
            )
            if nueva_version is None:
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "El hecho ha cambiado desde la version que conoce el "
                    "llamante.",
                )

            actualizados = self._actualizar_efectos(sesion, datos)
            # 3. Las aportaciones se retiran ANTES que su conciliacion: al
            #    reves quedarian apuntando al vacio (D-169).
            conciliaciones = self._eliminar_conciliaciones(sesion, datos)
            eliminados = self._eliminar_efectos(sesion, datos)
            relaciones = self._eliminar_relaciones(sesion, datos)
            creados = self._crear_efectos(sesion, datos)

            # 4. Revalidacion cruzada con OP-13: retirar o reducir un
            #    efecto puede dejar la capacidad reversible por debajo de lo
            #    que ya se devolvio. Ninguna constraint fisica lo impide y sin
            #    esta guarda el motor confirmaria un estado imposible: haber
            #    devuelto mas de lo que el hecho llego a reconocer.
            self._revalidar_devoluciones(sesion, datos)

            # 4bis. F04-D036. Misma logica que el paso 5: lo que se juzga es
            # el ESTADO FINAL. Una correccion puede retirar y reinstalar un
            # efecto dentro de la transaccion; lo que no puede es confirmar
            # un vinculo cuya naturaleza o moneda ya no case con la posicion.
            coherencia_posicion.exigir_vinculos_coherentes(
                sesion, hecho_id=datos.hecho_id
            )

            # 5. Guarda de estado FINAL (D-187). Se evalua aqui, no paso a
            #    paso: quedarse en cero efectos a mitad de la transaccion es
            #    legitimo si antes del COMMIT se instala el reemplazo.
            finales = repo_corr.efectos_del_hecho(sesion, datos.hecho_id)
            if finales == 0:
                tipo = repo_corr.tipo_de_hecho(sesion, datos.hecho_id)
                if tipo != TIPO_TRANSFERENCIA:
                    raise ErrorMotor(
                        CodigoError.CORRECCION_DEJA_HECHO_SIN_EFECTOS,
                        "Un hecho activo que no es una transferencia no puede "
                        "quedarse sin efectos: si la raiz nunca debio existir, "
                        "la via es anularla.",
                    )

            return ResultadoCorreccion(
                hecho_id=datos.hecho_id,
                hecho_row_version=nueva_version,
                efectos_actualizados=actualizados,
                efectos_eliminados=eliminados,
                efectos_creados=creados,
                relaciones_eliminadas=relaciones,
                conciliaciones_eliminadas=conciliaciones,
                efectos_finales=finales,
            )

        return self._ejecutar(contexto, operacion, "OP-21 corregir_agregado")

    # ==================================================================
    # Interno
    # ==================================================================
    @staticmethod
    def _revalidar_devoluciones(
        sesion: SesionMotor, datos: DatosCorreccion
    ) -> None:
        """Lo ya devuelto no puede superar la capacidad que queda."""
        for naturaleza in repo_rel.naturalezas_devueltas(sesion, datos.hecho_id):
            resumen = repo_rel.capacidad_por_naturaleza(
                sesion, datos.hecho_id, naturaleza
            )
            capacidad = (
                decimal.Decimal(0)
                if resumen is None
                else abs(decimal.Decimal(resumen["neto"]))
            )
            devuelto = decimal.Decimal(
                repo_rel.devuelto_acumulado(sesion, datos.hecho_id, naturaleza)
            )
            if devuelto > capacidad:
                raise ErrorMotor(
                    CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE,
                    "La correccion dejaria devuelto mas de lo que el hecho "
                    "reconoce: primero hay que corregir las devoluciones.",
                )

    def _actualizar_efectos(
        self, sesion: SesionMotor, datos: DatosCorreccion
    ) -> int:
        total = 0
        for efecto_id, cambios in datos.efectos_a_actualizar.items():
            resultado = repo_corr.actualizar_efecto(sesion, efecto_id, cambios)
            if resultado is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "Alguno de los efectos a corregir no existe o no es "
                    "accesible.",
                )
            auditoria.registrar(
                sesion,
                tabla=repo_corr.TABLA_EFECTOS,
                registro_id=efecto_id,
                accion=auditoria.ACCION_ACTUALIZAR,
                datos_antes_json=resultado[0],
                datos_despues_json=resultado[1],
                motivo=datos.motivo,
            )
            total += 1
        return total

    def _eliminar_efectos(self, sesion: SesionMotor, datos: DatosCorreccion) -> int:
        total = 0
        for efecto_id in datos.efectos_a_eliminar:
            snapshot = repo_corr.eliminar_efecto(sesion, efecto_id)
            if snapshot is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "Alguno de los efectos a retirar no existe o no es "
                    "accesible.",
                )
            # El snapshot es la UNICA prueba que queda de esa fila.
            auditoria.registrar(
                sesion,
                tabla=repo_corr.TABLA_EFECTOS,
                registro_id=efecto_id,
                accion=auditoria.ACCION_ANULAR,
                datos_antes_json=snapshot,
                motivo=datos.motivo,
            )
            total += 1
        return total

    def _eliminar_relaciones(
        self, sesion: SesionMotor, datos: DatosCorreccion
    ) -> int:
        total = 0
        for relacion_id in datos.relaciones_a_eliminar:
            snapshot = repo_corr.eliminar_relacion(sesion, relacion_id)
            if snapshot is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "Alguna de las relaciones a retirar no existe o no es "
                    "accesible.",
                )
            auditoria.registrar(
                sesion,
                tabla=repo_corr.TABLA_RELACIONES,
                registro_id=relacion_id,
                accion=auditoria.ACCION_ANULAR,
                datos_antes_json=snapshot,
                motivo=datos.motivo,
            )
            total += 1
        return total

    def _eliminar_conciliaciones(
        self, sesion: SesionMotor, datos: DatosCorreccion
    ) -> int:
        total = 0
        for conciliacion_id in datos.conciliaciones_a_eliminar:
            if repo_corr.aportaciones_de_conciliacion(sesion, conciliacion_id):
                raise ErrorMotor(
                    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                    "Esa conciliacion tiene aportaciones vinculadas: retirarla "
                    "antes dejaria las aportaciones apuntando al vacio.",
                )
            snapshot = repo_corr.eliminar_conciliacion(sesion, conciliacion_id)
            if snapshot is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "Alguna de las conciliaciones a retirar no existe o no es "
                    "accesible.",
                )
            auditoria.registrar(
                sesion,
                tabla=repo_corr.TABLA_CONCILIACIONES,
                registro_id=conciliacion_id,
                accion=auditoria.ACCION_ANULAR,
                datos_antes_json=snapshot,
                motivo=datos.motivo,
            )
            total += 1
        return total

    def _crear_efectos(self, sesion: SesionMotor, datos: DatosCorreccion) -> int:
        """Reemplazo dentro de la MISMA transaccion.

        Es lo que permite retirar el ultimo efecto falso e instalar el correcto
        sin confirmar un estado intermedio que nunca fue cierto.
        """
        total = 0
        for efecto in datos.efectos_a_crear:
            creado = repo_efectos.insertar_efecto_si_no_existe(
                sesion,
                datos.hecho_id,
                efecto_id=efecto.efecto_id,
                tipo_efecto=efecto.tipo_efecto,
                importe_delta=efecto.importe_delta,
                estado_atribucion=efecto.estado_atribucion,
                categoria_id=efecto.categoria_id,
                descripcion=efecto.descripcion,
            )
            if creado is None:
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "El identificador del efecto de reemplazo ya esta en uso "
                    "con otra intencion.",
                )
            auditoria.registrar(
                sesion,
                tabla=repo_corr.TABLA_EFECTOS,
                registro_id=efecto.efecto_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=creado[1],
                motivo=datos.motivo,
            )
            total += 1
        return total

    @staticmethod
    def _validar(datos: DatosCorreccion) -> None:
        if datos.eliminar_hecho:
            raise ErrorMotor(
                CodigoError.CORRECCION_REQUIERE_ANULACION_DE_RAIZ,
                "Un hecho no se borra: si la raiz completa nunca debio "
                "existir, se anula con OP-03 y queda su rastro.",
            )
        if datos.eliminar_movimiento is not None:
            raise ErrorMotor(
                CodigoError.CORRECCION_REQUIERE_ANULACION_DE_RAIZ,
                "Un movimiento no se borra: se lleva a ANULADO por su propio "
                "lifecycle auditado.",
            )
        if not (datos.motivo or "").strip():
            raise ErrorMotor(
                CodigoError.MOTIVO_AUSENTE,
                "Toda correccion agregada exige motivo explicito.",
            )
        for cambios in datos.efectos_a_actualizar.values():
            desconocidos = set(cambios) - CAMPOS_EFECTO_CORREGIBLES
            if desconocidos:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    f"Campos no corregibles en un efecto: {sorted(desconocidos)}.",
                )
        if not any(
            (
                datos.efectos_a_actualizar,
                datos.efectos_a_eliminar,
                datos.efectos_a_crear,
                datos.relaciones_a_eliminar,
                datos.conciliaciones_a_eliminar,
            )
        ):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una correccion debe cambiar al menos una cosa.",
            )

    def _ejecutar(
        self, contexto: ContextoOperacion, operacion: Any, nombre: str
    ) -> ResultadoCorreccion:
        resultado = self._unidad.ejecutar_con_traza(contexto, operacion, nombre=nombre)
        self.ultima_traza = resultado.traza
        return resultado.valor
