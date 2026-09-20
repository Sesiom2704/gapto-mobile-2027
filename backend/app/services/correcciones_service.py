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
# Version: 0.5.0
#   0.5.0 (F04-D039): superficie de atribuciones. Un efecto con reparto
#   COMPLETA tenia el importe inmutable: para cuadrar hacian falta dos
#   mutaciones a la vez —el delta y las filas de reparto— y solo una era
#   alcanzable. Ahora OP-21 puede actualizar, retirar y crear atribuciones y
#   corregir `estado_atribucion`, todo en la MISMA transaccion, validando el
#   ESTADO FINAL de cada efecto tocado. OP-05 conserva su contrato ordinario
#   de enriquecimiento: una transicion inversa aqui no es perdida posterior
#   de conocimiento, es correccion historica de un dato que nunca fue cierto.
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
from app.services.efectos_service import EfectosService

TABLA_ATRIBUCIONES = repo_efectos.TABLA_ATRIBUCIONES
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
    {
        "importe_delta",
        "categoria_id",
        "descripcion",
        "tipo_efecto",
        # F04-D039. Corregible SOLO por esta via: OP-05 conserva su
        # progresion ordinaria NO_DISPONIBLE -> PARCIAL -> COMPLETA.
        "estado_atribucion",
    }
)

#: Campos corregibles de una atribucion existente. `actor_id` queda fuera a
#: proposito: cambiar de persona no es corregir un importe, y se expresa como
#: DELETE de la fila falsa mas CREATE de la correcta.
CAMPOS_ATRIBUCION_CORREGIBLES = frozenset(
    {"importe_atribuido", "porcentaje_aplicado", "criterio_atribucion"}
)


@dataclass(frozen=True, slots=True)
class DatosAtribucionNueva:
    """Reparto que debio existir y se omitio (F04-D039).

    Lleva `efecto_id` propio porque una misma correccion puede instalar
    atribuciones en varios efectos del hecho.
    """

    atribucion_id: uuid.UUID
    efecto_id: uuid.UUID
    actor_id: uuid.UUID
    importe_atribuido: decimal.Decimal
    criterio_atribucion: str
    porcentaje_aplicado: decimal.Decimal | None = None


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
    # F04-D039. Superficie de atribuciones.
    atribuciones_a_actualizar: dict[uuid.UUID, dict[str, Any]] = field(
        default_factory=dict
    )
    atribuciones_a_eliminar: tuple[uuid.UUID, ...] = ()
    atribuciones_a_crear: tuple[Any, ...] = ()
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
    atribuciones_actualizadas: int = 0
    atribuciones_eliminadas: int = 0
    atribuciones_creadas: int = 0
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

            # 3bis. F04-D039. Las atribuciones se mutan DESPUES de los efectos
            #     para que un CREATE pueda colgar de un efecto de reemplazo
            #     instalado en esta misma transaccion. El orden interno no
            #     importa para la validez: las constraints diferidas juzgan el
            #     estado final, y por eso se puede pasar por situaciones
            #     transitoriamente descuadradas sin confirmarlas.
            atribuciones_eliminadas = self._eliminar_atribuciones(sesion, datos)
            atribuciones_actualizadas = self._actualizar_atribuciones(sesion, datos)
            atribuciones_creadas = self._crear_atribuciones(sesion, datos)

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

            # 4ter. F04-D039. INV-01 sobre el ESTADO FINAL de cada efecto
            #     TOCADO por esta correccion. Solo los tocados: las reglas de
            #     residual real y de NO_DISPONIBLE sin filas son SRV y el
            #     trigger no las cubre, de modo que validar todo el hecho haria
            #     que OP-21 se negase a corregir un efecto por culpa de otro
            #     que nadie rechaza hoy.
            self._validar_estado_final_atribuciones(sesion, datos)

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
                atribuciones_actualizadas=atribuciones_actualizadas,
                atribuciones_eliminadas=atribuciones_eliminadas,
                atribuciones_creadas=atribuciones_creadas,
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

    # ==================================================================
    # Interno - F04-D039, superficie de atribuciones
    # ==================================================================
    def _eliminar_atribuciones(
        self, sesion: SesionMotor, datos: DatosCorreccion
    ) -> int:
        total = 0
        for atribucion_id in datos.atribuciones_a_eliminar:
            self._exigir_atribucion_del_hecho(sesion, atribucion_id, datos.hecho_id)
            snapshot = repo_corr.eliminar_atribucion(sesion, atribucion_id)
            if snapshot is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "Alguna de las atribuciones a retirar no existe o no es "
                    "accesible.",
                )
            # El snapshot es la UNICA prueba que queda de ese reparto.
            auditoria.registrar(
                sesion,
                tabla=TABLA_ATRIBUCIONES,
                registro_id=atribucion_id,
                accion=auditoria.ACCION_ANULAR,
                datos_antes_json=snapshot,
                motivo=datos.motivo,
            )
            total += 1
        return total

    def _actualizar_atribuciones(
        self, sesion: SesionMotor, datos: DatosCorreccion
    ) -> int:
        total = 0
        for atribucion_id, cambios in datos.atribuciones_a_actualizar.items():
            desconocidos = sorted(set(cambios) - CAMPOS_ATRIBUCION_CORREGIBLES)
            if desconocidos:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    f"Campos no corregibles en una atribucion: {desconocidos}. "
                    "Cambiar de actor no es corregir un importe: se expresa "
                    "retirando la fila falsa y creando la correcta.",
                )
            if not cambios:
                continue
            self._exigir_atribucion_del_hecho(sesion, atribucion_id, datos.hecho_id)
            actualizado = repo_corr.actualizar_atribucion(
                sesion, atribucion_id, cambios
            )
            if actualizado is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "Alguna de las atribuciones a corregir no existe o no es "
                    "accesible.",
                )
            antes, despues = actualizado
            auditoria.registrar(
                sesion,
                tabla=TABLA_ATRIBUCIONES,
                registro_id=atribucion_id,
                accion=auditoria.ACCION_ACTUALIZAR,
                datos_antes_json=antes,
                datos_despues_json=despues,
                motivo=datos.motivo,
            )
            total += 1
        return total

    def _crear_atribuciones(
        self, sesion: SesionMotor, datos: DatosCorreccion
    ) -> int:
        """Reparto que debio existir y se omitio.

        Identidad reservada por el llamante, como en el resto del motor: sin
        ella un reintento tras un COMMIT de resultado desconocido duplicaria
        la fila.
        """
        total = 0
        for atribucion in datos.atribuciones_a_crear:
            self._exigir_efecto_del_hecho(
                sesion, atribucion.efecto_id, datos.hecho_id
            )
            creada = repo_efectos.insertar_atribucion_si_no_existe(
                sesion,
                atribucion_id=atribucion.atribucion_id,
                efecto_id=atribucion.efecto_id,
                actor_id=atribucion.actor_id,
                importe_atribuido=atribucion.importe_atribuido,
                criterio_atribucion=atribucion.criterio_atribucion,
                porcentaje_aplicado=getattr(
                    atribucion, "porcentaje_aplicado", None
                ),
            )
            if creada is None:
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "El identificador de la atribucion de reemplazo ya esta "
                    "en uso con otra intencion.",
                )
            auditoria.registrar(
                sesion,
                tabla=TABLA_ATRIBUCIONES,
                registro_id=atribucion.atribucion_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=creada,
                motivo=datos.motivo,
            )
            total += 1
        return total

    def _validar_estado_final_atribuciones(
        self, sesion: SesionMotor, datos: DatosCorreccion
    ) -> None:
        """INV-01 completa sobre los efectos tocados.

        Se delega en el validador de OP-04/OP-05 en lugar de reescribirlo: es
        la misma invariante, y dos copias divergirian en la primera
        correccion.
        """
        tocados = self._efectos_tocados(sesion, datos)
        if not tocados:
            return
        for fila in repo_corr.estado_de_efectos(sesion, datos.hecho_id, tocados):
            _, delta, estado, filas, suma = fila
            EfectosService._validar_coherencia(
                estado=estado,
                filas=int(filas),
                suma=decimal.Decimal(suma),
                delta=decimal.Decimal(delta),
            )

    def _efectos_tocados(
        self, sesion: SesionMotor, datos: DatosCorreccion
    ) -> list[uuid.UUID]:
        """Efectos cuyo estado final cambia por esta correccion."""
        tocados: set[uuid.UUID] = set(datos.efectos_a_actualizar)
        tocados.update(efecto.efecto_id for efecto in datos.efectos_a_crear)
        tocados.update(
            atribucion.efecto_id for atribucion in datos.atribuciones_a_crear
        )
        for atribucion_id in list(datos.atribuciones_a_actualizar) + list(
            datos.atribuciones_a_eliminar
        ):
            fila = repo_corr.leer_atribucion(sesion, atribucion_id)
            if fila is not None:
                tocados.add(fila[0])
        # Un efecto retirado ya no tiene estado final que validar.
        tocados.difference_update(datos.efectos_a_eliminar)
        return sorted(tocados)

    def _exigir_atribucion_del_hecho(
        self, sesion: SesionMotor, atribucion_id: uuid.UUID, hecho_id: uuid.UUID
    ) -> None:
        fila = repo_corr.leer_atribucion(sesion, atribucion_id)
        if fila is None or fila[1] != hecho_id:
            raise ErrorMotor(
                CodigoError.AGREGADO_NO_ENCONTRADO,
                "La atribucion indicada no pertenece a este hecho o no es "
                "accesible.",
            )

    def _exigir_efecto_del_hecho(
        self, sesion: SesionMotor, efecto_id: uuid.UUID, hecho_id: uuid.UUID
    ) -> None:
        fila = sesion.uno(
            "SELECT hecho_id FROM gapto.hecho_efectos WHERE id = %s::uuid",
            (efecto_id,),
        )
        if fila is None or fila[0] != hecho_id:
            raise ErrorMotor(
                CodigoError.AGREGADO_NO_ENCONTRADO,
                "El efecto de la atribucion no pertenece a este hecho o no es "
                "accesible.",
            )

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
                datos.atribuciones_a_actualizar,
                datos.atribuciones_a_eliminar,
                datos.atribuciones_a_crear,
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
