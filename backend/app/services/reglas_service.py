# ============================================================
# GAPTO MOBILE 2027
# Fichero: reglas_service.py
# Ruta: backend/app/services/reglas_service.py
# Descripcion: F04-05. Configuracion de reglas financieras: alta, versionado,
#   pausa y excepciones por ocurrencia.
#
#   SEPARACION CONFIGURACION / GENERACION. Todo lo que hay aqui CAMBIA la
#   configuracion de la regla, y por eso incrementa `reglas_financieras.
#   row_version` exactamente una vez. Generar previsiones NO es configuracion:
#   vive en `previsiones_service`, se serializa con el mismo lock y no
#   incrementa nada de la regla. Mezclar las dos cosas haria que cada
#   generacion invalidase la version que el llamante conoce.
#
#   UNA REGLA NO TIENE LIFECYCLE PROPIO. No hay `enabled`. Una regla esta
#   operativa cuando existe una version vigente, y una pausa es literalmente un
#   HUECO sin version: no genera, no acumula backlog y no se recupera al
#   reanudar. Por eso cerrar una version y abrir otra mas tarde es toda la
#   expresion que necesita una pausa.
#
#   VERSIONADO FORWARD-ONLY. Una condicion real nueva se expresa cerrando la
#   version anterior y creando otra. Editar una version historica se reserva a
#   corregir un dato que NUNCA fue cierto, y no debe usarse para representar un
#   cambio real: eso reescribiria el pasado.
#
#   AUTORIDAD FISICA. `ex_regla_versiones__regla` es la autoridad del
#   no-solapamiento y `uq_regla_excepciones__regla_fecha` la de una excepcion
#   por identidad. Aqui se TRADUCEN sus violaciones a errores de dominio; no se
#   reimplementan como segunda fuente de verdad, que podria divergir.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid
from typing import Any

import psycopg
from psycopg import errors as pgerr

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_prevision import (
    ANCLAJES,
    CERO,
    Cadencia,
    DatosExcepcion,
    DatosRegla,
    DatosVersionRegla,
    FECHA_MODOS,
    FLUJOS,
    IMPORTE_FIJO,
    IMPORTE_MODOS,
    IMPORTE_SALDO_OBJETIVO,
    PERIODICIDADES,
    ResultadoRegla,
)
from app.core.recurrencia import exigir_anclaje_compatible
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import hechos_repository as repo_hechos
from app.repositories import reglas_repository as repo_reglas

_MONEDA_VALIDA = re.compile(r"^[A-Z]{3}$")


class ReglasService:
    """Casos de uso de configuracion de reglas."""

    __slots__ = ("_unidad", "ultima_traza")

    def __init__(self, unidad: UnidadDeTrabajo) -> None:
        self._unidad = unidad
        self.ultima_traza: Traza | None = None

    # ==================================================================
    # Alta de regla
    # ==================================================================
    def crear_regla(
        self,
        contexto: ContextoOperacion,
        datos: DatosRegla,
        primera_version: DatosVersionRegla | None = None,
    ) -> ResultadoRegla:
        """Crea la regla y, si viene en el comando, su primera version.

        Las dos en la MISMA transaccion: una regla sin ninguna version no esta
        operativa, y confirmar ese estado intermedio dejaria una regla que no
        genera nada y que nadie sabe si esta pausada o a medio crear.
        """
        self._validar_regla(datos)
        if primera_version is not None:
            self._validar_version(primera_version)

        def operacion(sesion: SesionMotor) -> ResultadoRegla:
            repo_hechos.exigir_contexto(sesion)

            if repo_reglas.leer_regla(sesion, datos.regla_id) is not None:
                return self._replay_regla(sesion, datos, primera_version)

            creada = repo_reglas.insertar_regla_si_no_existe(
                sesion,
                regla_id=datos.regla_id,
                nombre=(datos.nombre or "").strip(),
                entidad_origen_id=datos.entidad_origen_id,
            )
            if creada is None:
                raise self._conflicto_identidad()
            row_version, snapshot = creada
            auditoria.registrar(
                sesion,
                tabla=repo_reglas.TABLA_REGLAS,
                registro_id=datos.regla_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=snapshot,
            )

            version_id: uuid.UUID | None = None
            if primera_version is not None:
                version_id = self._insertar_version(
                    sesion, datos.regla_id, primera_version
                )

            return ResultadoRegla(
                regla_id=datos.regla_id,
                regla_row_version=row_version,
                version_id=version_id,
            )

        return self._ejecutar(contexto, operacion, "crear_regla")

    # ==================================================================
    # Versionado
    # ==================================================================
    def crear_version(
        self,
        contexto: ContextoOperacion,
        *,
        regla_id: uuid.UUID,
        regla_row_version_esperada: int,
        version: DatosVersionRegla,
        cerrar_version_id: uuid.UUID | None = None,
        cerrar_vigente_hasta: dt.date | None = None,
    ) -> ResultadoRegla:
        """Cierra la version anterior y abre la nueva, en una transaccion.

        Si se dejase la nueva sin cerrar la anterior, el EXCLUDE fisico
        rechazaria el solape; y si se cerrase la anterior sin abrir la nueva en
        la misma transaccion, quedaria una pausa involuntaria confirmada.

        Una pausa DELIBERADA se expresa cerrando la version y creando la
        siguiente mas tarde, con `vigente_desde` posterior: el hueco no genera
        nada y no se recupera.
        """
        self._validar_version(version)
        if (cerrar_version_id is None) != (cerrar_vigente_hasta is None):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Cerrar una version exige su identidad y su fecha de fin.",
            )
        if (
            cerrar_vigente_hasta is not None
            and version.vigente_desde is not None
            and cerrar_vigente_hasta >= version.vigente_desde
        ):
            # La vigencia es INCLUSIVA en los dos extremos: si A termina el
            # mismo dia en que empieza B, ese dia lo gobiernan las dos.
            raise ErrorMotor(
                CodigoError.VERSION_REGLA_SOLAPADA,
                "La version anterior debe cerrarse ANTES del inicio de la "
                "nueva: la vigencia es inclusiva en ambos extremos.",
            )

        def operacion(sesion: SesionMotor) -> ResultadoRegla:
            repo_hechos.exigir_contexto(sesion)
            self._exigir_regla(sesion, regla_id)

            nueva_version = repo_reglas.tocar_regla(
                sesion, regla_id, regla_row_version_esperada
            )
            if nueva_version is None:
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "La regla ha cambiado desde la version que conoce el "
                    "llamante.",
                )

            if cerrar_version_id is not None:
                cerrada = repo_reglas.cerrar_version(
                    sesion, cerrar_version_id, cerrar_vigente_hasta
                )
                if cerrada is None:
                    raise ErrorMotor(
                        CodigoError.AGREGADO_NO_ENCONTRADO,
                        "La version a cerrar no existe o no es accesible.",
                    )
                auditoria.registrar(
                    sesion,
                    tabla=repo_reglas.TABLA_VERSIONES,
                    registro_id=cerrar_version_id,
                    accion=auditoria.ACCION_ACTUALIZAR,
                    datos_antes_json=cerrada[0],
                    datos_despues_json=cerrada[1],
                    motivo="cierre de vigencia por nueva version",
                )

            version_id = self._insertar_version(sesion, regla_id, version)
            return ResultadoRegla(
                regla_id=regla_id,
                regla_row_version=nueva_version,
                version_id=version_id,
            )

        return self._ejecutar(contexto, operacion, "crear_version")

    # ==================================================================
    # Excepciones
    # ==================================================================
    def registrar_excepcion(
        self,
        contexto: ContextoOperacion,
        *,
        regla_id: uuid.UUID,
        regla_row_version_esperada: int,
        excepcion: DatosExcepcion,
    ) -> ResultadoRegla:
        """Excepcion por identidad de ocurrencia: omitir y/o ajustar.

        `omitida=True` hace irrelevantes los overrides y se rechaza combinarlos:
        si la ocurrencia no va a existir, no hay importe ni fecha que ajustar,
        y admitir ambos dejaria una fila cuya intencion nadie sabria leer.
        """
        self._validar_excepcion(excepcion)

        def operacion(sesion: SesionMotor) -> ResultadoRegla:
            repo_hechos.exigir_contexto(sesion)
            self._exigir_regla(sesion, regla_id)

            existente = repo_reglas.leer_excepcion(
                sesion, regla_id, excepcion.fecha_objetivo
            )
            if existente is not None:
                raise ErrorMotor(
                    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                    "Ya existe una excepcion para esa ocurrencia; corregirla "
                    "es otra operacion.",
                )

            nueva_version = repo_reglas.tocar_regla(
                sesion, regla_id, regla_row_version_esperada
            )
            if nueva_version is None:
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "La regla ha cambiado desde la version que conoce el "
                    "llamante.",
                )

            snapshot = repo_reglas.insertar_excepcion(
                sesion,
                {
                    "id": excepcion.excepcion_id,
                    "regla_id": regla_id,
                    "fecha_objetivo": excepcion.fecha_objetivo,
                    "omitida": excepcion.omitida,
                    "importe_override": excepcion.importe_override,
                    "fecha_override": excepcion.fecha_override,
                    "motivo": excepcion.motivo,
                },
            )
            if snapshot is None:
                raise self._conflicto_identidad()
            auditoria.registrar(
                sesion,
                tabla=repo_reglas.TABLA_EXCEPCIONES,
                registro_id=excepcion.excepcion_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=snapshot,
                motivo=excepcion.motivo,
            )
            return ResultadoRegla(
                regla_id=regla_id, regla_row_version=nueva_version
            )

        return self._ejecutar(contexto, operacion, "registrar_excepcion")

    def corregir_excepcion(
        self,
        contexto: ContextoOperacion,
        *,
        regla_id: uuid.UUID,
        regla_row_version_esperada: int,
        excepcion_id: uuid.UUID,
        cambios: dict[str, Any],
        motivo: str | None = None,
    ) -> ResultadoRegla:
        """Correccion auditada de una excepcion existente."""
        permitidos = {"omitida", "importe_override", "fecha_override", "motivo"}
        desconocidos = set(cambios) - permitidos
        if desconocidos:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                f"Campos no corregibles en una excepcion: {sorted(desconocidos)}.",
            )
        if not cambios:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una correccion debe cambiar al menos un campo.",
            )
        if cambios.get("importe_override") is not None and decimal.Decimal(
            cambios["importe_override"]
        ) <= CERO:
            raise ErrorMotor(
                CodigoError.IMPORTE_NO_POSITIVO,
                "importe_override debe ser mayor que cero.",
            )

        def operacion(sesion: SesionMotor) -> ResultadoRegla:
            repo_hechos.exigir_contexto(sesion)
            self._exigir_regla(sesion, regla_id)

            nueva_version = repo_reglas.tocar_regla(
                sesion, regla_id, regla_row_version_esperada
            )
            if nueva_version is None:
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "La regla ha cambiado desde la version que conoce el "
                    "llamante.",
                )

            actualizada = repo_reglas.actualizar_excepcion(
                sesion, excepcion_id, cambios
            )
            if actualizada is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "La excepcion indicada no existe o no es accesible.",
                )
            auditoria.registrar(
                sesion,
                tabla=repo_reglas.TABLA_EXCEPCIONES,
                registro_id=excepcion_id,
                accion=auditoria.ACCION_ACTUALIZAR,
                datos_antes_json=actualizada[0],
                datos_despues_json=actualizada[1],
                motivo=motivo,
            )
            return ResultadoRegla(
                regla_id=regla_id, regla_row_version=nueva_version
            )

        return self._ejecutar(contexto, operacion, "corregir_excepcion")

    # ==================================================================
    # Interno
    # ==================================================================
    def _insertar_version(
        self, sesion: SesionMotor, regla_id: uuid.UUID, version: DatosVersionRegla
    ) -> uuid.UUID:
        tipo_hecho_id = repo_reglas.resolver_tipo_hecho(
            sesion, version.tipo_hecho_codigo
        )
        if tipo_hecho_id is None:
            raise ErrorMotor(
                CodigoError.TIPO_HECHO_DESCONOCIDO,
                "El tipo de hecho indicado no existe en el catalogo.",
            )

        valores = {
            "id": version.version_id,
            "regla_id": regla_id,
            "vigente_desde": version.vigente_desde,
            "vigente_hasta": version.vigente_hasta,
            "tipo_hecho_id": tipo_hecho_id,
            "flujo_tesoreria_esperado": version.flujo_tesoreria_esperado,
            "categoria_id": version.categoria_id,
            "tercero_id": version.tercero_id,
            "cuenta_salida_esperada_id": version.cuenta_salida_esperada_id,
            "cuenta_entrada_esperada_id": version.cuenta_entrada_esperada_id,
            "moneda": version.moneda,
            "importe_referencia_lado": version.importe_referencia_lado,
            "periodicidad": version.cadencia.periodicidad,
            "intervalo": version.cadencia.intervalo,
            "fecha_modo": version.fecha_modo,
            "dia_desde": version.dia_desde,
            "dia_hasta": version.dia_hasta,
            "importe_modo": version.importe_modo,
            "importe_fijo": version.importe_fijo,
            "cuenta_calculo_id": version.cuenta_calculo_id,
            "saldo_objetivo": version.saldo_objetivo,
            "meses_historico": version.meses_historico,
            "presupuestable": version.presupuestable,
            "anclaje_recurrencia": version.cadencia.anclaje,
        }
        try:
            snapshot = repo_reglas.insertar_version(sesion, valores)
        except pgerr.ExclusionViolation as error:
            # `ex_regla_versiones__regla` es la autoridad del no-solapamiento.
            # Se traduce a error de dominio sin exponer el nombre del
            # constraint ni el SQLSTATE.
            raise ErrorMotor(
                CodigoError.VERSION_REGLA_SOLAPADA,
                "La vigencia de la nueva version se solapa con otra existente.",
                causa=error,
                sqlstate=getattr(error, "sqlstate", None),
            ) from error
        if snapshot is None:
            raise self._conflicto_identidad()
        auditoria.registrar(
            sesion,
            tabla=repo_reglas.TABLA_VERSIONES,
            registro_id=version.version_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=snapshot,
        )
        return version.version_id

    def _replay_regla(
        self,
        sesion: SesionMotor,
        datos: DatosRegla,
        primera_version: DatosVersionRegla | None,
    ) -> ResultadoRegla:
        """Reintento de un alta cuyo COMMIT quedo en resultado desconocido."""
        coincide = repo_reglas.creacion_previa_coincide(
            sesion,
            repo_reglas.TABLA_REGLAS,
            datos.regla_id,
            {
                "id": datos.regla_id,
                "nombre": (datos.nombre or "").strip(),
                "entidad_origen_id": datos.entidad_origen_id,
            },
            repo_reglas.TIPOS_SQL_REGLA,
        )
        if not coincide:
            raise self._conflicto_identidad()
        regla = repo_reglas.leer_regla(sesion, datos.regla_id)
        assert regla is not None
        return ResultadoRegla(
            regla_id=datos.regla_id,
            regla_row_version=regla["row_version"],
            version_id=None if primera_version is None else primera_version.version_id,
            idempotente=True,
        )

    @staticmethod
    def _exigir_regla(sesion: SesionMotor, regla_id: uuid.UUID) -> int:
        """Bloquea la regla y devuelve su version.

        Se bloquea incluso para cambios de configuracion: asi una generacion
        concurrente no puede leer una configuracion a medio cambiar.
        """
        version = repo_reglas.bloquear_regla(sesion, regla_id)
        if version is None:
            raise ErrorMotor(
                CodigoError.REGLA_NO_ENCONTRADA,
                "La regla indicada no existe o no es accesible.",
            )
        return version

    @staticmethod
    def _conflicto_identidad() -> ErrorMotor:
        return ErrorMotor(
            CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
            "Alguno de los identificadores reservados ya esta en uso con otra "
            "intencion.",
        )

    @staticmethod
    def _validar_regla(datos: DatosRegla) -> None:
        if not (datos.nombre or "").strip():
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA, "La regla exige nombre."
            )

    @staticmethod
    def _validar_version(version: DatosVersionRegla) -> None:
        if version.vigente_desde is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una version exige fecha de inicio de vigencia.",
            )
        if (
            version.vigente_hasta is not None
            and version.vigente_hasta < version.vigente_desde
        ):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "La vigencia no puede terminar antes de empezar.",
            )
        if version.moneda is None or not _MONEDA_VALIDA.match(version.moneda):
            raise ErrorMotor(
                CodigoError.MONEDA_INVALIDA,
                "La moneda debe ser un codigo de tres letras mayusculas.",
            )
        if version.flujo_tesoreria_esperado not in FLUJOS:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA, "flujo_tesoreria_esperado invalido."
            )
        if version.fecha_modo not in FECHA_MODOS:
            raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "fecha_modo invalido.")
        if version.importe_modo not in IMPORTE_MODOS:
            raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "importe_modo invalido.")
        if version.presupuestable is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "`presupuestable` no tiene default: debe indicarse.",
            )

        cadencia = version.cadencia
        # El contrato fisico ata periodicidad y anclaje: o los dos o ninguno.
        if (cadencia.periodicidad is None) != (cadencia.anclaje is None):
            raise ErrorMotor(
                CodigoError.CADENCIA_INVALIDA,
                "periodicidad y anclaje_recurrencia van juntos: o ambos o "
                "ninguno.",
            )
        if cadencia.periodicidad is not None:
            if cadencia.periodicidad not in PERIODICIDADES:
                raise ErrorMotor(
                    CodigoError.CADENCIA_INVALIDA, "Periodicidad no soportada."
                )
            if cadencia.anclaje not in ANCLAJES:
                raise ErrorMotor(
                    CodigoError.ANCLAJE_INVALIDO, "Anclaje no soportado."
                )
            if cadencia.intervalo is None or cadencia.intervalo < 1:
                raise ErrorMotor(
                    CodigoError.CADENCIA_INVALIDA,
                    "El intervalo de una cadencia debe ser al menos 1.",
                )
            exigir_anclaje_compatible(cadencia, version.fecha_modo)

        if version.importe_modo == IMPORTE_FIJO and (
            version.importe_fijo is None
            or decimal.Decimal(version.importe_fijo) <= CERO
        ):
            raise ErrorMotor(
                CodigoError.IMPORTE_NO_POSITIVO,
                "importe_modo=FIJO exige un importe fijo mayor que cero.",
            )
        if version.importe_modo == IMPORTE_SALDO_OBJETIVO and (
            version.cuenta_calculo_id is None or version.saldo_objetivo is None
        ):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "importe_modo=SALDO_OBJETIVO exige cuenta de calculo y saldo "
                "objetivo.",
            )
        if version.meses_historico is not None and version.meses_historico <= 0:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA, "meses_historico debe ser positivo."
            )

    @staticmethod
    def _validar_excepcion(excepcion: DatosExcepcion) -> None:
        if excepcion.fecha_objetivo is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una excepcion se identifica por su fecha objetivo.",
            )
        if excepcion.omitida and excepcion.tiene_overrides:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una ocurrencia omitida no admite overrides: si no va a "
                "existir, no hay importe ni fecha que ajustar.",
            )
        if excepcion.importe_override is not None and decimal.Decimal(
            excepcion.importe_override
        ) <= CERO:
            raise ErrorMotor(
                CodigoError.IMPORTE_NO_POSITIVO,
                "importe_override debe ser mayor que cero.",
            )
        if not excepcion.omitida and not excepcion.tiene_overrides:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una excepcion debe omitir la ocurrencia o ajustar algo.",
            )

    def _ejecutar(
        self, contexto: ContextoOperacion, operacion: Any, nombre: str
    ) -> ResultadoRegla:
        resultado = self._unidad.ejecutar_con_traza(contexto, operacion, nombre=nombre)
        self.ultima_traza = resultado.traza
        return resultado.valor
