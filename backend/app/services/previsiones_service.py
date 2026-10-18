# ============================================================
# GAPTO MOBILE 2027
# Fichero: previsiones_service.py
# Ruta: backend/app/services/previsiones_service.py
# Descripcion: F04-05. Previsiones manuales, generacion CALENDARIO y RODANTE,
#   algoritmos de importe, lifecycle, OP-17 y AMB-009.
#
#   INV-16 · UNA PREVISION NO ES REALIDAD. Este servicio no crea hechos, ni
#   efectos, ni movimientos, ni aportaciones, ni posiciones. Materializa
#   EXPECTATIVA y la vincula a una realidad que ya existe. OP-17 solo vincula.
#
#   R-F04-017 · EL PROTOCOLO DEL LOCK NO ES NEGOCIABLE. No hay UNIQUE fisico
#   sobre la identidad logica de ocurrencia, y no podria anadirse
#   mecanicamente. El orden es SIEMPRE:
#
#       bloquear_regla -> releer version y cabeza -> calcular candidato
#                      -> comprobar identidad/tombstone/excepcion -> insertar
#
#   Calcular el candidato ANTES del lock produce dos ocurrencias y PostgreSQL
#   no lo detecta. Por eso `_generar` recibe la sesion ya con la regla
#   bloqueada y ninguna funcion de calculo se llama fuera de ese ambito.
#
#   F04-D018 · AMB-009. Solo los hechos ACTIVOS cuentan como realidad. Una
#   REALIZADA que pierde su ultima realidad activa NO pasa a ABIERTA, ni a
#   OMITIDA, ni a CANCELADA: conserva REALIZADA y se expone como
#   REALIZADA_SIN_REALIDAD_ACTIVA, con la cadena bloqueada para revision. El
#   objetivo canonico NUNCA se usa como respaldo de una realidad que ya no
#   existe.
#
#   F04-D019 · La parcialidad es DERIVADA. Previsto 1.000 con 400 realizados
#   sigue siendo ABIERTA: no hay estado PARCIAL persistido. Y el primer hecho
#   ACTIVO congela la expectativa poniendo `recalculo_automatico=false`, de
#   modo que una version posterior de la regla ya no reescribe ese importe.
# Version: 0.9.0
#   0.9.0 (MANT DEU-F04-VINCULO-ANULADO, R-R2C-01; dictamen 2026-10-18 Q8):
#   `corregir_vinculo` no corrige el importe de un vinculo que sigue en un hecho
#   ANULADO. Bajo el lock del hecho que ya toma la ruta (hechos por UUID ->
#   reglas -> prevision; el orden global no cambia), si la correccion cambia el
#   importe SIN reasignar el hecho y el hecho actual no esta ACTIVO ->
#   OPERACION_NO_PERMITIDA_EN_ESTADO (motivo HECHO_DEL_VINCULO_ANULADO).
#   Reasignar el vinculo al hecho correcto (AMB-009 / F04-D021, test_113) o a
#   otra prevision (preparacion C1 de F04-R1, test_139) sigue admitido.
# Version: 0.8.0
#   0.8.0 (F04-R2 R2-C; contrato F04-R2 v0.9 §2.3.2 bis, AJ-R2C-CONTRATO-02):
#   la propagacion F04-D022 se separa, SIN cambio semantico, en
#   `adquirir_impacto_ancla` (calcular el conjunto sin lock, adquirir reglas FU
#   -> previsiones por UUID y revalidar; si cambio, ConjuntoCambiado) y
#   `aplicar_impacto_ancla` (procesar en el orden cronologico de siempre sobre
#   lo ya bloqueado, sin adquirir nada nuevo). `impacto_correccion_ancla` =
#   aplicar(adquirir): OP-02, OP-03, OP-21P y OP-21T no cambian. OP-03P adquiere
#   en el nivel 5 (antes de los movimientos) y aplica en W6.
# Version: 0.7.0
#   0.7.0 (F04-R2 R2-B; contrato F04-R2 v0.8 §6.1 niveles 5 y 6, §6.6):
#   `conjunto_impacto_correccion_ancla` expone, SIN lock, las reglas y los
#   sucesores que `impacto_correccion_ancla` bloqueara para un hecho. OP-21P y
#   OP-21T corrigen la fecha de un hecho que retiene ya sus movimientos (nivel
#   6); para no pedir reglas ni previsiones (nivel 5) despues, adquieren ese
#   conjunto ANTES de los movimientos. `impacto_correccion_ancla` no cambia:
#   vuelve a bloquear (ya poseido), relee y lanza ConjuntoCambiado si difiere.
# Version: 0.6.0
#   0.6.0 (F04-D060 · F04-R2 R2-A; contrato F04-R2 v0.6 §7.4): IDENTIDAD EN
#   retirar_vinculo. El llamante pasa tambien `prevision_id_esperada`: la
#   `row_version` es de la previsión y una coincidencia de versiones entre
#   previsiones distintas no acredita que sea la que el llamante queria (ni
#   tras un reintento por ConjuntoCambiado). Tras los locks (regla ->
#   previsión, G-R1-D) y DESPUES de la guarda de version (precedencia IL4 de
#   F04-R1), el vinculo RELEIDO debe tener `prevision_id` =
#   `prevision_id_esperada` y el `hecho_id` leido antes de los locks; si no ->
#   VERSION_DESFASADA sin escribir. Owner: RLS y `exigir_contexto`. Sin
#   cambios en el orden de adquisicion ni en la auditoria.
# Version: 0.5.1
#   0.5.1 (F04-R1 CORR; STOP_F04-R1_F6, IL4): OP-17 recupera la precedencia de
#   errores de la base (5536bb3) sin perder la relectura de G-R1-D. El estado
#   que decide ESTADO_PREVISION_INCOMPATIBLE es el de la lectura PREVIA (como en
#   la base); la version se compara con la previsión RELEIDA tras el lock y en
#   el mismo punto de la cadena de guardas que en la base (justo antes de
#   tocar); el estado releido solo se comprueba DESPUES de la version, como
#   defensa. Un perdedor concurrente (IL4) vuelve a recibir VERSION_DESFASADA y
#   el caso secuencial (version obsoleta sobre una REALIZADA) sigue en
#   ESTADO_PREVISION_INCOMPATIBLE. Sin cambios en el orden de adquisicion.
#   Mismo patron (auditoria 3.1, misma causa) en corregir_vinculo y
#   retirar_vinculo: la guarda de version (sobre las previsiones bloqueadas, en
#   el punto de la base) va ANTES de la relectura del vinculo. Un perdedor cuyo
#   vinculo otro writer movio o retiro vuelve a recibir VERSION_DESFASADA (como
#   en la base) en lugar de ENTRADA_INVALIDA/AGREGADO_NO_ENCONTRADO tras un
#   reintento; ConjuntoCambiado queda solo para un cambio que no movio ninguna
#   version (defensa).
# Version: 0.5.0
#   0.5.0 (F04-R1 G-R1-D; F04-D058, AJ-F04R1-V11-01/02/04): ORDEN GLOBAL DE
#   ADQUISICION, separado del de procesamiento: advisory INVERSIONES -> hechos
#   (NKU, UUID) -> posiciones (NKU, id) -> reglas (FU, UUID; TODAS las
#   implicadas) -> previsiones (FU, UUID). Primero se adquiere todo y despues
#   se procesa en el orden semantico.
#     - OP-17: hecho -> regla -> previsión; relee la previsión y el estado del
#       hecho tras el lock.
#     - corregir_vinculo: vinculo sin lock -> hechos viejo y nuevo -> reglas
#       de origen y destino -> previsiones de origen y destino -> RELEE el
#       vinculo y las reglas. Si cambio el hecho, la previsión o el conjunto de
#       reglas: `ConjuntoCambiado` (reintento COMPLETO de la transaccion).
#     - retirar_vinculo: vinculo -> regla -> previsión -> relee el vinculo.
#     - impacto_correccion_ancla (OP-02/OP-03): conjunto de sucesores y
#       reglas SIN lock -> reglas -> previsiones por UUID -> relee el conjunto
#       (si cambio: `ConjuntoCambiado`) -> procesa en el orden CRONOLOGICO de
#       siempre. `tocar_prevision` en conflicto ya no se ignora (conflicto,
#       nunca exito) y `actualizar_prevision` solo sigue a un tocar correcto.
#   `ConjuntoCambiado` lleva sqlstate 40001: la UnidadDeTrabajo reintenta la
#   transaccion completa y, agotados los intentos, responde
#   CONFLICTO_CONCURRENCIA («nada se ha persistido»). Nunca se continua con una
#   proteccion incompleta. Resultados financieros identicos (oraculos F1).
# Version: 0.4.0
#   0.4.0 (F04-R1 G-R1-C; F04-D058): porcion acumulada de un hecho entre
#   previsiones en OP-17 (y por tanto OP-22) y en corregir_vinculo
#   (`exigir_porcion`). Tope = importe_total bruto; Σ = todos los vinculos del
#   hecho, sea cual sea el estado de su previsión. Clasificacion sobre el
#   estado POSTERIOR completo: se rechaza crear o agravar exceso; mantener,
#   reducir y la igualdad se admiten. En un traslado, origen y destino se
#   evaluan por separado, sin compensacion. Rama NO_DETERMINABLE (importe NULL
#   o vinculo en otra moneda en el estado posterior): sin comparacion
#   numerica; a lo sumo un vinculo por hecho; con mas de uno preexistente,
#   nada que aumente su numero o un importe; retirar siempre. Codigo
#   PORCION_DE_REALIDAD_EXCEDIDA. retirar_vinculo solo reduce: no se evalua.
# Version: 0.3.0
#   0.3.0 (F04-05, remediacion): OP-17 rechaza la pareja repetida con su codigo
#   canonico PREVISION_YA_MATERIALIZADA_POR_ESTA_REALIDAD en vez de uno
#   generico; la correccion terminal admite las TRES terminales (F04-D024.3) y
#   rechaza el tramo con TRAMO_RODANTE_REQUIERE_REVISION (F04-D024.9); AMB-009
#   bloquea la generacion aunque exista sucesor abierto (F04-D018.4).
# Version: 0.2.0
#   0.2.0 (F04-05): F04-D022 expone la revision como lectura derivada y falla
#   cerrada en el write-path; F04-D023 ancla la transicion CALENDARIO -> RODANTE
#   en la ultima terminal del SEGMENTO anterior; F04-D024 anade la correccion
#   de estado terminal.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_prevision import (
    ABIERTA,
    CALENDARIO,
    CANCELADA,
    CERO,
    Cadencia,
    DatosPrevisionManual,
    DatosVinculo,
    ESTADOS_TERMINALES,
    FECHA_ANCLA,
    IMPORTE_FIJO,
    IMPORTE_MANUAL,
    IMPORTE_MEDIA,
    IMPORTE_MEDIANA,
    IMPORTE_MODOS_HISTORICOS,
    IMPORTE_SALDO_OBJETIVO,
    IMPORTE_ULTIMO,
    MOTIVO_SALDO_OBJETIVO_CUMPLIDO,
    OMITIDA,
    OcurrenciaHistorica,
    REALIZADA,
    REALIZADA_SIN_REALIDAD_ACTIVA,
    REQUIERE_REVISION,
    RODANTE,
    ResultadoGeneracion,
    ResultadoPrevision,
    ResultadoRecalculo,
)
from app.core import recurrencia as rec
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import hechos_repository as repo_hechos
from app.repositories import previsiones_repository as repo_prev
from app.repositories import reglas_repository as repo_reglas
from app.repositories import relaciones_repository as repo_rel

_MONEDA_VALIDA = re.compile(r"^[A-Z]{3}$")


class ConjuntoCambiado(Exception):
    """F04-R1 G-R1-D: el conjunto de filas protegido cambio entre su lectura
    y su adquisicion (vinculo movido de hecho o de previsión, reglas o
    sucesores distintos). No se sigue con una proteccion incompleta: el
    sqlstate 40001 hace que la UnidadDeTrabajo reintente la transaccion
    COMPLETA, que vuelve a leer el conjunto y a adquirirlo en el orden global."""

    sqlstate = "40001"


def _bloquear_reglas(sesion: SesionMotor, reglas: Sequence[uuid.UUID]) -> None:
    for regla_id in sorted(set(reglas), key=str):
        repo_reglas.bloquear_regla(sesion, regla_id)


def _regla_de(sesion: SesionMotor, prevision_id: uuid.UUID) -> uuid.UUID | None:
    prevision = repo_prev.leer_prevision(sesion, prevision_id)
    return None if prevision is None else prevision["regla_id"]


class PrevisionesService:
    """Casos de uso de previsiones y materializacion."""

    __slots__ = ("_unidad", "ultima_traza")

    def __init__(self, unidad: UnidadDeTrabajo) -> None:
        self._unidad = unidad
        self.ultima_traza: Traza | None = None

    # ==================================================================
    # Previsión manual
    # ==================================================================
    def crear_manual(
        self, contexto: ContextoOperacion, datos: DatosPrevisionManual
    ) -> ResultadoPrevision:
        """Previsión sin regla. Nunca entra en cadena CALENDARIO ni RODANTE.

        `regla_version_id` y `fecha_objetivo_regla` quedan a NULL y
        `recalculo_automatico` a False: no hay regla que la regobierne, de modo
        que dejarla recalculable seria prometer algo que nadie va a cumplir.
        """
        self._validar_manual(datos)

        def operacion(sesion: SesionMotor) -> ResultadoPrevision:
            repo_hechos.exigir_contexto(sesion)
            existente = repo_prev.leer_prevision(sesion, datos.prevision_id)
            if existente is not None:
                return self._replay_manual(sesion, datos, existente)

            tipo_hecho_id = self._exigir_tipo_hecho(sesion, datos.tipo_hecho_codigo)
            valores = {
                "id": datos.prevision_id,
                "regla_version_id": None,
                "fecha_objetivo_regla": None,
                "concepto": (datos.concepto or "").strip(),
                "tipo_hecho_id": tipo_hecho_id,
                "categoria_id": datos.categoria_id,
                "tercero_id": datos.tercero_id,
                "entidad_id": datos.entidad_id,
                "fecha_esperada_desde": datos.fecha_esperada_desde,
                "fecha_esperada_hasta": datos.fecha_esperada_hasta,
                "flujo_tesoreria_esperado": datos.flujo_tesoreria_esperado,
                "moneda": datos.moneda,
                "importe_esperado": datos.importe_esperado,
                "importe_referencia_lado": datos.importe_referencia_lado,
                "cuenta_salida_esperada_id": datos.cuenta_salida_esperada_id,
                "cuenta_entrada_esperada_id": datos.cuenta_entrada_esperada_id,
                "presupuestable": datos.presupuestable,
                "estado": ABIERTA,
                "recalculo_automatico": False,
                "motivo_ajuste": None,
            }
            creada = repo_prev.insertar_prevision(sesion, valores)
            if creada is None:
                raise self._conflicto_identidad()
            row_version, snapshot = creada
            auditoria.registrar(
                sesion,
                tabla=repo_prev.TABLA_PREVISIONES,
                registro_id=datos.prevision_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=snapshot,
            )
            return ResultadoPrevision(
                prevision_id=datos.prevision_id,
                row_version=row_version,
                estado=ABIERTA,
                importe_esperado=datos.importe_esperado,
                recalculo_automatico=False,
            )

        return self._ejecutar(contexto, operacion, "crear_prevision_manual")

    # ==================================================================
    # Generacion CALENDARIO
    # ==================================================================
    def generar_calendario(
        self,
        contexto: ContextoOperacion,
        *,
        regla_id: uuid.UUID,
        uuids_por_objetivo: dict[dt.date, uuid.UUID],
        hasta_fecha: dt.date | None = None,
        max_ocurrencias: int | None = None,
        desde_fecha: dt.date | None = None,
    ) -> ResultadoGeneracion:
        """Materializa las ocurrencias del horizonte indicado.

        El horizonte es OBLIGATORIAMENTE finito. Y repetir la misma generacion
        produce cero filas nuevas: cada identidad ya existente se devuelve
        como existente, no se duplica.

        `uuids_por_objetivo` asocia cada fecha objetivo con su identidad
        reservada. Es un mapa y no una lista porque debe ser ESTABLE entre
        reintentos: el mismo horizonte produce las mismas fechas y por tanto
        las mismas identidades.
        """

        if hasta_fecha is None and max_ocurrencias is None:
            # Se valida en la FRONTERA y no solo en la aritmetica: el limite
            # por segmento cortocircuita antes de llegar a `ocurrencias_hasta`,
            # y sin esta guarda una generacion sin horizonte devolveria cero
            # ocurrencias en silencio en vez de exigir el horizonte.
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "La generacion exige un horizonte explicito finito: "
                "hasta_fecha o max_ocurrencias.",
            )

        def operacion(sesion: SesionMotor) -> ResultadoGeneracion:
            repo_hechos.exigir_contexto(sesion)
            # PRIMERO el lock. Nada de calcular candidatos antes.
            if repo_reglas.bloquear_regla(sesion, regla_id) is None:
                raise ErrorMotor(
                    CodigoError.REGLA_NO_ENCONTRADA,
                    "La regla indicada no existe o no es accesible.",
                )
            return self._generar_calendario(
                sesion,
                regla_id,
                uuids_por_objetivo,
                hasta_fecha=hasta_fecha,
                max_ocurrencias=max_ocurrencias,
                desde_fecha=desde_fecha,
            )

        return self._ejecutar(contexto, operacion, "generar_calendario")

    def _generar_calendario(
        self,
        sesion: SesionMotor,
        regla_id: uuid.UUID,
        uuids_por_objetivo: dict[dt.date, uuid.UUID],
        *,
        hasta_fecha: dt.date | None,
        max_ocurrencias: int | None,
        desde_fecha: dt.date | None,
    ) -> ResultadoGeneracion:
        versiones = repo_reglas.listar_versiones(sesion, regla_id)
        if not versiones:
            raise ErrorMotor(
                CodigoError.REGLA_NO_ENCONTRADA,
                "La regla no tiene ninguna version: no esta operativa.",
            )

        creadas: list[uuid.UUID] = []
        existentes: list[uuid.UUID] = []
        omitidas: list[dt.date] = []
        tombstones: list[dt.date] = []
        tumbas = repo_prev.identidades_consumidas(sesion, regla_id, (CANCELADA,))

        for segmento in self._segmentos(versiones, self._resolver_ancla(sesion)):
            cadencia = segmento["cadencia"]
            if cadencia.anclaje != CALENDARIO:
                continue
            origen = segmento["origen"]
            limite = self._limite_del_segmento(segmento, hasta_fecha)
            if limite is None:
                continue
            fechas = rec.ocurrencias_hasta(
                origen,
                cadencia,
                hasta_fecha=limite,
                max_ocurrencias=max_ocurrencias,
                desde_fecha=max(
                    [f for f in (segmento["desde"], desde_fecha) if f is not None]
                ),
            )
            for objetivo in fechas:
                # Una pausa es un hueco sin version: no genera y no acumula.
                version_id = repo_reglas.version_vigente_en(sesion, regla_id, objetivo)
                if version_id is None:
                    continue
                resultado = self._materializar_ocurrencia(
                    sesion,
                    regla_id=regla_id,
                    version_id=version_id,
                    objetivo=objetivo,
                    uuid_reservado=uuids_por_objetivo.get(objetivo),
                    tumbas=tumbas,
                )
                if resultado["tipo"] == "CREADA":
                    creadas.append(resultado["id"])
                elif resultado["tipo"] == "EXISTENTE":
                    existentes.append(resultado["id"])
                elif resultado["tipo"] == "OMITIDA":
                    omitidas.append(objetivo)
                else:
                    tombstones.append(objetivo)

        return ResultadoGeneracion(
            regla_id=regla_id,
            creadas=tuple(creadas),
            existentes=tuple(existentes),
            omitidas_por_excepcion=tuple(omitidas),
            canceladas_encontradas=tuple(tombstones),
        )

    # ==================================================================
    # Generacion RODANTE
    # ==================================================================
    def generar_rodante(
        self,
        contexto: ContextoOperacion,
        *,
        regla_id: uuid.UUID,
        uuid_nuevo: uuid.UUID,
    ) -> ResultadoGeneracion:
        """Crea como maximo UNA cabeza.

        La siguiente ocurrencia solo nace cuando la cabeza anterior ha
        terminado. Si sigue ABIERTA —incluso parcialmente realizada— no hay
        sucesor: anticiparlo materializaria una expectativa que todavia puede
        cambiar.
        """

        def operacion(sesion: SesionMotor) -> ResultadoGeneracion:
            repo_hechos.exigir_contexto(sesion)
            if repo_reglas.bloquear_regla(sesion, regla_id) is None:
                raise ErrorMotor(
                    CodigoError.REGLA_NO_ENCONTRADA,
                    "La regla indicada no existe o no es accesible.",
                )
            return self._generar_rodante(sesion, regla_id, uuid_nuevo)

        return self._ejecutar(contexto, operacion, "generar_rodante")

    def _generar_rodante(
        self, sesion: SesionMotor, regla_id: uuid.UUID, uuid_nuevo: uuid.UUID
    ) -> ResultadoGeneracion:
        versiones = repo_reglas.listar_versiones(sesion, regla_id)
        segmentos = [
            s
            for s in self._segmentos(versiones, self._resolver_ancla(sesion))
            if s["cadencia"].anclaje == RODANTE
        ]
        if not segmentos:
            raise ErrorMotor(
                CodigoError.ANCLAJE_INVALIDO,
                "La regla no tiene ningun segmento RODANTE vigente.",
            )
        segmento = segmentos[-1]
        cadencia = segmento["cadencia"]

        # F04-D018.4 y F04-D023.6. Una REALIZADA sin realidad ACTIVA bloquea
        # la generacion automatica de la cadena ENTERA, exista o no un sucesor
        # ya materializado: no aporta ancla y la inconsistencia debe resolverse
        # con una decision explicita antes de continuar.
        rota = repo_prev.realizada_sin_realidad_activa(sesion, regla_id)
        if rota is not None:
            raise ErrorMotor(
                CodigoError.CABEZA_RODANTE_BLOQUEADA,
                "La cadena tiene una ocurrencia REALIZADA que perdio su "
                "realidad ACTIVA: queda bloqueada hasta revision explicita.",
            )

        cabeza = repo_prev.cabeza_rodante(sesion, regla_id)
        if cabeza is not None and cabeza["abiertas"] > 1:
            # No hay UNIQUE fisico que lo impida: si esto salta, el lock no
            # actuo y hay un defecto de serializacion, no un caso de uso.
            raise ErrorMotor(
                CodigoError.CABEZA_RODANTE_DUPLICADA,
                "La cadena tiene mas de una cabeza abierta.",
            )
        if cabeza is not None:
            return ResultadoGeneracion(
                regla_id=regla_id, existentes=(cabeza["id"],)
            )

        terminal = repo_prev.ultima_terminal(sesion, regla_id)
        if terminal is None:
            origen = segmento["origen"]
        else:
            realidad = repo_prev.resumen_realidad(sesion, terminal["id"])
            ancla = rec.ancla_rodante(
                estado=terminal["estado"],
                fecha_real_maxima=realidad["fecha_real_maxima"],
                fecha_objetivo=terminal["fecha_objetivo"],
                hechos_activos=realidad["hechos_activos"],
            )
            if ancla is None:
                if terminal["estado"] == CANCELADA:
                    return ResultadoGeneracion(
                        regla_id=regla_id,
                        canceladas_encontradas=(terminal["fecha_objetivo"],),
                    )
                raise ErrorMotor(
                    CodigoError.CABEZA_RODANTE_BLOQUEADA,
                    "La ultima ocurrencia REALIZADA no conserva realidad "
                    "ACTIVA: la cadena queda bloqueada para revision.",
                )
            origen = rec.ocurrencia(ancla, cadencia, 1)

        tumbas = repo_prev.identidades_consumidas(sesion, regla_id, (CANCELADA,))
        objetivo = rec.primer_candidato_libre(origen, cadencia, tumbas)

        # Una excepcion omitida consume la ocurrencia y la cadena avanza desde
        # el objetivo canonico, no desde ningun override.
        omitidas: list[dt.date] = []
        for _ in range(0, 120):
            excepcion = repo_reglas.leer_excepcion(sesion, regla_id, objetivo)
            if excepcion is None or not excepcion["omitida"]:
                break
            omitidas.append(objetivo)
            objetivo = rec.primer_candidato_libre(
                rec.ocurrencia(objetivo, cadencia, 1), cadencia, tumbas
            )

        version_id = repo_reglas.version_vigente_en(sesion, regla_id, objetivo)
        if version_id is None:
            version_id = segmento["version_id"]

        resultado = self._materializar_ocurrencia(
            sesion,
            regla_id=regla_id,
            version_id=version_id,
            objetivo=objetivo,
            uuid_reservado=uuid_nuevo,
            tumbas=tumbas,
        )
        if resultado["tipo"] == "CREADA":
            return ResultadoGeneracion(
                regla_id=regla_id,
                creadas=(resultado["id"],),
                omitidas_por_excepcion=tuple(omitidas),
            )
        if resultado["tipo"] == "EXISTENTE":
            return ResultadoGeneracion(
                regla_id=regla_id,
                existentes=(resultado["id"],),
                omitidas_por_excepcion=tuple(omitidas),
            )
        return ResultadoGeneracion(
            regla_id=regla_id, omitidas_por_excepcion=tuple(omitidas)
        )

    # ==================================================================
    # Materializacion de una ocurrencia
    # ==================================================================
    def _materializar_ocurrencia(
        self,
        sesion: SesionMotor,
        *,
        regla_id: uuid.UUID,
        version_id: uuid.UUID,
        objetivo: dt.date,
        uuid_reservado: uuid.UUID | None,
        tumbas: set[dt.date],
    ) -> dict[str, Any]:
        """Crea la ocurrencia si su identidad esta libre.

        Orden deliberado: identidad existente -> tombstone -> excepcion
        omitida -> crear. Si la identidad ya existe se DEVUELVE la existente,
        aunque el llamante traiga otro UUID reservado: el UUID no puede
        eludir una identidad ya consumida.
        """
        existente = repo_prev.prevision_por_identidad(sesion, regla_id, objetivo)
        if existente is not None:
            return {"tipo": "EXISTENTE", "id": existente["id"]}
        if objetivo in tumbas:
            return {"tipo": "TOMBSTONE", "id": None}

        excepcion = repo_reglas.leer_excepcion(sesion, regla_id, objetivo)
        if excepcion is not None and excepcion["omitida"]:
            return {"tipo": "OMITIDA", "id": None}

        if uuid_reservado is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Cada ocurrencia a crear exige su identidad reservada.",
            )

        version = repo_reglas.leer_version(sesion, version_id)
        if version is None:  # pragma: no cover - el lock garantiza su existencia
            raise ErrorMotor(
                CodigoError.REGLA_NO_ENCONTRADA, "La version no es accesible."
            )

        fecha_override = None if excepcion is None else excepcion["fecha_override"]
        ventana = rec.ventana_de(
            objetivo,
            fecha_modo=version["fecha_modo"],
            dia_desde=version["dia_desde"],
            dia_hasta=version["dia_hasta"],
            fecha_override=fecha_override,
        )
        importe = self._importe_esperado(
            sesion, regla_id=regla_id, version=version, objetivo=objetivo,
            excepcion=excepcion,
        )
        if importe is not None and importe == CERO:
            # SALDO_OBJETIVO ya cumplido: no se crea una previsión monetaria de
            # importe 0. La ocurrencia se consume como omision determinista.
            return {"tipo": "OMITIDA", "id": None, "motivo": MOTIVO_SALDO_OBJETIVO_CUMPLIDO}

        snapshot_version = self._snapshot_de_version(version)
        valores = {
            "id": uuid_reservado,
            "regla_version_id": version_id,
            "fecha_objetivo_regla": objetivo,
            "concepto": snapshot_version["concepto"],
            "tipo_hecho_id": snapshot_version["tipo_hecho_id"],
            "categoria_id": snapshot_version["categoria_id"],
            "tercero_id": snapshot_version["tercero_id"],
            "entidad_id": None,
            "fecha_esperada_desde": ventana.desde,
            "fecha_esperada_hasta": ventana.hasta,
            "flujo_tesoreria_esperado": snapshot_version["flujo_tesoreria_esperado"],
            "moneda": snapshot_version["moneda"],
            "importe_esperado": importe,
            "importe_referencia_lado": snapshot_version["importe_referencia_lado"],
            "cuenta_salida_esperada_id": snapshot_version["cuenta_salida_esperada_id"],
            "cuenta_entrada_esperada_id": snapshot_version["cuenta_entrada_esperada_id"],
            "presupuestable": snapshot_version["presupuestable"],
            "estado": ABIERTA,
            "recalculo_automatico": True,
            "motivo_ajuste": None,
        }
        creada = repo_prev.insertar_prevision(sesion, valores)
        if creada is None:
            raise self._conflicto_identidad()
        auditoria.registrar(
            sesion,
            tabla=repo_prev.TABLA_PREVISIONES,
            registro_id=uuid_reservado,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=creada[1],
        )
        return {"tipo": "CREADA", "id": uuid_reservado}

    # ==================================================================
    # Algoritmos de importe
    # ==================================================================
    def _importe_esperado(
        self,
        sesion: SesionMotor,
        *,
        regla_id: uuid.UUID,
        version: dict[str, Any],
        objetivo: dt.date,
        excepcion: dict[str, Any] | None,
    ) -> decimal.Decimal | None:
        """Importe esperado de la ocurrencia. None significa DESCONOCIDO.

        Un override de importe prevalece sobre el algoritmo para esa
        ocurrencia, sin tocar la version ni las demas ocurrencias.
        """
        if excepcion is not None and excepcion["importe_override"] is not None:
            return decimal.Decimal(excepcion["importe_override"])

        modo = version["importe_modo"]
        if modo == IMPORTE_FIJO:
            return decimal.Decimal(version["importe_fijo"])
        if modo == IMPORTE_MANUAL:
            # Desconocido, no cero: el caller puede fijarlo mas tarde.
            return None
        if modo in IMPORTE_MODOS_HISTORICOS:
            return self._importe_historico(
                sesion, regla_id=regla_id, version=version, objetivo=objetivo
            )
        if modo == IMPORTE_SALDO_OBJETIVO:
            saldo = repo_prev.saldo_real_de_cuenta(
                sesion, version["cuenta_calculo_id"]
            )
            return rec.importe_por_saldo_objetivo(
                saldo_real=saldo,
                saldo_objetivo=decimal.Decimal(version["saldo_objetivo"]),
                flujo=version["flujo_tesoreria_esperado"],
            )
        # CALENDARIO_ENTIDAD sin adaptador de dominio autoritativo.
        raise ErrorMotor(
            CodigoError.CALENDARIO_ENTIDAD_NO_SOPORTADO,
            "importe_modo=CALENDARIO_ENTIDAD exige un adaptador de dominio "
            "autoritativo y documentado.",
        )

    def _importe_historico(
        self,
        sesion: SesionMotor,
        *,
        regla_id: uuid.UUID,
        version: dict[str, Any],
        objetivo: dt.date,
    ) -> decimal.Decimal | None:
        """Estimacion a partir de ocurrencias ANTERIORES DE LA MISMA REGLA.

        La fuente no son todos los hechos de la categoria. Y el importe real de
        cada ocurrencia es la suma de `importe_asignado` sobre hechos ACTIVOS,
        nunca `importe_total` del hecho.
        """
        crudos = repo_prev.historicos_de_regla(sesion, regla_id, objetivo)
        muestra = [
            OcurrenciaHistorica(
                fecha_objetivo=h["fecha_objetivo"],
                importe_real=decimal.Decimal(h["importe_real"]),
                moneda=h["moneda"],
            )
            for h in crudos
        ]
        elegibles = rec.historicos_elegibles(
            muestra,
            objetivo=objetivo,
            moneda=version["moneda"],
            meses_historico=version["meses_historico"],
        )
        modo = version["importe_modo"]
        if modo == IMPORTE_MEDIA:
            return rec.media_historica(elegibles)
        if modo == IMPORTE_MEDIANA:
            return rec.mediana_historica(elegibles)
        return rec.ultimo_real(elegibles)

    # ==================================================================
    # Lifecycle
    # ==================================================================
    def omitir(
        self,
        contexto: ContextoOperacion,
        *,
        prevision_id: uuid.UUID,
        row_version_esperada: int,
        motivo: str | None = None,
        uuid_sucesor: uuid.UUID | None = None,
    ) -> ResultadoPrevision:
        """ABIERTA -> OMITIDA. Exige cero hechos ACTIVOS.

        En RODANTE crea el sucesor en la MISMA transaccion, anclado en el
        objetivo canonico. Dejarlo para despues dejaria la cadena sin cabeza.
        """
        return self._terminar(
            contexto,
            prevision_id=prevision_id,
            row_version_esperada=row_version_esperada,
            estado_destino=OMITIDA,
            motivo=motivo,
            uuid_sucesor=uuid_sucesor,
            nombre="omitir_prevision",
        )

    def cancelar(
        self,
        contexto: ContextoOperacion,
        *,
        prevision_id: uuid.UUID,
        row_version_esperada: int,
        motivo: str | None = None,
    ) -> ResultadoPrevision:
        """ABIERTA -> CANCELADA. Tombstone permanente, sin sucesor.

        No equivale a OMITIDA: una omision es "esta vez no toca" y la cadena
        sigue; una cancelacion consume la identidad y no genera sucesor.
        """
        return self._terminar(
            contexto,
            prevision_id=prevision_id,
            row_version_esperada=row_version_esperada,
            estado_destino=CANCELADA,
            motivo=motivo,
            uuid_sucesor=None,
            nombre="cancelar_prevision",
        )

    def _terminar(
        self,
        contexto: ContextoOperacion,
        *,
        prevision_id: uuid.UUID,
        row_version_esperada: int,
        estado_destino: str,
        motivo: str | None,
        uuid_sucesor: uuid.UUID | None,
        nombre: str,
    ) -> ResultadoPrevision:
        def operacion(sesion: SesionMotor) -> ResultadoPrevision:
            repo_hechos.exigir_contexto(sesion)
            prevision = self._exigir_prevision(sesion, prevision_id)
            regla_id = prevision["regla_id"]
            if regla_id is not None:
                repo_reglas.bloquear_regla(sesion, regla_id)

            if prevision["estado"] != ABIERTA:
                raise ErrorMotor(
                    CodigoError.ESTADO_PREVISION_INCOMPATIBLE,
                    "Solo una previsión ABIERTA admite esta transicion.",
                )
            realidad = repo_prev.resumen_realidad(sesion, prevision_id)
            if realidad["hechos_activos"] > 0:
                raise ErrorMotor(
                    CodigoError.ESTADO_PREVISION_INCOMPATIBLE,
                    "La previsión tiene realidad ACTIVA vinculada: omitir o "
                    "cancelar borraria una expectativa ya satisfecha en parte.",
                )

            nueva_version = self._tocar(sesion, prevision_id, row_version_esperada)
            self._cambiar_estado(
                sesion, prevision_id, estado_destino, prevision["snapshot"], motivo
            )

            if estado_destino == OMITIDA and regla_id is not None:
                self._crear_sucesor_si_rodante(sesion, regla_id, uuid_sucesor)

            return ResultadoPrevision(
                prevision_id=prevision_id,
                row_version=nueva_version,
                estado=estado_destino,
                fecha_objetivo_regla=prevision["fecha_objetivo_regla"],
                recalculo_automatico=False,
            )

        return self._ejecutar(contexto, operacion, nombre)

    # ==================================================================
    # OP-17
    # ==================================================================
    def vincular_realidad(
        self,
        contexto: ContextoOperacion,
        *,
        prevision_id: uuid.UUID,
        row_version_esperada: int,
        datos: DatosVinculo,
        uuid_sucesor: uuid.UUID | None = None,
    ) -> ResultadoPrevision:
        """OP-17. Vincula una realidad YA EXISTENTE a una expectativa.

        No crea efecto, ni gasto, ni ingreso, ni deuda, ni derecho, ni
        movimiento, ni aportacion. Y no autoelige el hecho por importe, fecha,
        tercero, categoria, cuenta o descripcion: la decision es del llamante.

        El primer vinculo NO cambia el estado por si solo, pero SI congela la
        expectativa: `recalculo_automatico` pasa a false.
        """
        if datos.importe_asignado is None or decimal.Decimal(
            datos.importe_asignado
        ) <= CERO:
            raise ErrorMotor(
                CodigoError.IMPORTE_NO_POSITIVO,
                "importe_asignado debe ser mayor que cero.",
            )

        def operacion(sesion: SesionMotor) -> ResultadoPrevision:
            repo_hechos.exigir_contexto(sesion)
            # F04-R1 G-R1-D: conjunto sin lock -> hecho -> regla -> previsión.
            # La lectura PREVIA decide la guarda de estado (precedencia de la base).
            previa = self._exigir_prevision(sesion, prevision_id)
            regla_id = previa["regla_id"]
            # Un hecho no visible no se bloquea; lo rechaza la validacion de abajo.
            repo_rel.bloquear_hechos(sesion, [datos.hecho_id])
            if regla_id is not None:
                repo_reglas.bloquear_regla(sesion, regla_id)
            repo_prev.bloquear_prevision(sesion, prevision_id)
            # Relectura de la previsión tras el lock (version, estado y recalculo).
            prevision = self._exigir_prevision(sesion, prevision_id)
            if prevision["regla_id"] != regla_id:  # pragma: no cover - la version es inmutable
                raise ConjuntoCambiado()

            # Reintento exacto antes de la guarda de version, igual que en
            # F04-04: si el COMMIT confirmo y el cliente perdio la respuesta,
            # la version ya avanzo y mirarla primero daria un falso conflicto.
            existente = repo_prev.leer_vinculo(sesion, datos.vinculo_id)
            if existente is not None:
                if (
                    existente["prevision_id"] == prevision_id
                    and existente["hecho_id"] == datos.hecho_id
                    and decimal.Decimal(existente["importe_asignado"])
                    == decimal.Decimal(datos.importe_asignado)
                ):
                    return self._resultado_actual(sesion, prevision_id, idempotente=True)
                raise self._conflicto_identidad()

            if previa["estado"] != ABIERTA:
                raise ErrorMotor(
                    CodigoError.ESTADO_PREVISION_INCOMPATIBLE,
                    "Solo una previsión ABIERTA admite vincular realidad.",
                )

            estado_hecho = repo_hechos.leer_estado(sesion, datos.hecho_id)
            if estado_hecho is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El hecho indicado no existe o no es accesible.",
                )
            if estado_hecho[1] != "ACTIVO":
                raise ErrorMotor(
                    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                    "Un hecho anulado no es realidad: no puede satisfacer una "
                    "previsión.",
                )

            self._exigir_moneda_demostrada(
                sesion, prevision["moneda"], datos
            )

            if repo_prev.vinculo_de_pareja(
                sesion, prevision_id, datos.hecho_id
            ) is not None:
                # Esta previsión ya esta materializada por ESTA realidad. Un
                # segundo vinculo contaria dos veces la misma porcion, que es
                # justo lo que prohibe el contrato de OP-17. La autoridad
                # fisica es `uq_prevision_hechos__prevision_hecho`; aqui solo
                # se traduce a su codigo canonico.
                raise ErrorMotor(
                    CodigoError.PREVISION_YA_MATERIALIZADA_POR_ESTA_REALIDAD,
                    "Esa previsión ya esta materializada por ese hecho: "
                    "vincularlo de nuevo contaria dos veces la misma realidad.",
                )

            # F04-R1 G-R1-C: la misma porcion no se materializa dos veces.
            exigir_porcion(
                sesion,
                datos.hecho_id,
                {datos.vinculo_id: (datos.importe_asignado, prevision["moneda"])},
                solicitado=(datos.importe_asignado, prevision["moneda"]),
            )

            # Guarda de version sobre la previsión RELEIDA, en el punto de la base
            # (justo antes de tocar). Toda transicion de estado incrementa
            # row_version (corr\estado_row_version.md): con la version igual, el
            # estado releido es el previo; la guarda de abajo es solo defensa.
            if prevision["row_version"] != row_version_esperada:
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "La previsión ha cambiado desde la version que conoce el "
                    "llamante.",
                )
            if prevision["estado"] != ABIERTA:
                raise ErrorMotor(
                    CodigoError.ESTADO_PREVISION_INCOMPATIBLE,
                    "Solo una previsión ABIERTA admite vincular realidad.",
                )
            nueva_version = self._tocar(sesion, prevision_id, row_version_esperada)

            snapshot = repo_prev.insertar_vinculo(
                sesion,
                {
                    "id": datos.vinculo_id,
                    "prevision_id": prevision_id,
                    "hecho_id": datos.hecho_id,
                    "importe_asignado": datos.importe_asignado,
                },
            )
            if snapshot is None:
                raise self._conflicto_identidad()
            auditoria.registrar(
                sesion,
                tabla=repo_prev.TABLA_VINCULOS,
                registro_id=datos.vinculo_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=snapshot,
            )

            # El primer hecho ACTIVO congela la expectativa (F04-D019).
            cambios: dict[str, Any] = {}
            if prevision["recalculo_automatico"]:
                cambios["recalculo_automatico"] = False

            if datos.marcar_realizada:
                cambios["estado"] = REALIZADA
                cambios["recalculo_automatico"] = False

            if cambios:
                actualizada = repo_prev.actualizar_prevision(
                    sesion, prevision_id, cambios
                )
                assert actualizada is not None
                auditoria.registrar(
                    sesion,
                    tabla=repo_prev.TABLA_PREVISIONES,
                    registro_id=prevision_id,
                    accion=auditoria.ACCION_ACTUALIZAR,
                    datos_antes_json=actualizada[0],
                    datos_despues_json=actualizada[1],
                    motivo=(
                        "realizacion explicita"
                        if datos.marcar_realizada
                        else "primer vinculo: expectativa congelada"
                    ),
                )

            if datos.marcar_realizada and regla_id is not None:
                self._crear_sucesor_si_rodante(sesion, regla_id, uuid_sucesor)

            return self._resultado_actual(
                sesion, prevision_id, row_version=nueva_version
            )

        return self._ejecutar(contexto, operacion, "OP-17 vincular_realidad")

    # ==================================================================
    # Correccion de vinculos (F04-D021)
    # ==================================================================
    def corregir_vinculo(
        self,
        contexto: ContextoOperacion,
        *,
        vinculo_id: uuid.UUID,
        versiones_esperadas: dict[uuid.UUID, int],
        nuevo_importe: decimal.Decimal | None = None,
        nuevo_hecho_id: uuid.UUID | None = None,
        nueva_prevision_id: uuid.UUID | None = None,
        motivo: str | None = None,
    ) -> ResultadoPrevision:
        """Correccion auditada CONSERVANDO el id y el created_at.

        F04-D021: no se usa DELETE + INSERT para reasignar. La fila es la misma
        realidad corregida y su identidad debe sobrevivir a la correccion.

        Si la reasignacion cruza a otra previsión, se bloquean las DOS en orden
        UUID y se exige la version de cada una, incrementando ambas raices
        exactamente una vez.
        """
        if nuevo_importe is None and nuevo_hecho_id is None and nueva_prevision_id is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una correccion debe cambiar al menos un campo.",
            )
        if nuevo_importe is not None and decimal.Decimal(nuevo_importe) <= CERO:
            raise ErrorMotor(
                CodigoError.IMPORTE_NO_POSITIVO,
                "importe_asignado debe ser mayor que cero.",
            )

        def operacion(sesion: SesionMotor) -> ResultadoPrevision:
            repo_hechos.exigir_contexto(sesion)
            vinculo = repo_prev.leer_vinculo(sesion, vinculo_id)
            if vinculo is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El vinculo indicado no existe o no es accesible.",
                )

            origen_id = vinculo["prevision_id"]
            destino_id = nueva_prevision_id or origen_id
            # F04-R1 G-R1-D: hechos (viejo y nuevo) -> reglas de origen y
            # destino -> previsiones de origen y destino, cada nivel por UUID.
            afectadas = sorted({origen_id, destino_id}, key=str)
            hechos = {vinculo["hecho_id"], nuevo_hecho_id or vinculo["hecho_id"]}
            repo_rel.bloquear_hechos(sesion, sorted(hechos, key=str))
            # MANT DEU-F04-VINCULO-ANULADO: bajo el lock del hecho, el importe de
            # un vinculo que SIGUE en un hecho ANULADO no se corrige. Reasignarlo
            # al hecho correcto (AMB-009, F04-D021; el nuevo se exige ACTIVO mas
            # abajo) o a otra prevision (F04-R1 C1) sigue admitido.
            if nuevo_importe is not None and nuevo_hecho_id is None:
                estado_actual = repo_hechos.leer_estado(sesion, vinculo["hecho_id"])
                if estado_actual is not None and estado_actual[1] != "ACTIVO":
                    raise ErrorMotor(
                        CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                        "El vinculo es de un hecho anulado: su realidad no se corrige.",
                        contexto_extra={"motivo": "HECHO_DEL_VINCULO_ANULADO"},
                    )
            reglas = sorted(
                {r for r in (_regla_de(sesion, p) for p in afectadas) if r is not None},
                key=str,
            )
            _bloquear_reglas(sesion, reglas)
            bloqueadas: dict[uuid.UUID, int] = {}
            for identificador in afectadas:
                version_bloqueada = repo_prev.bloquear_prevision(sesion, identificador)
                if version_bloqueada is None:
                    raise ErrorMotor(
                        CodigoError.AGREGADO_NO_ENCONTRADO,
                        "Alguna previsión implicada no existe o no es "
                        "accesible.",
                    )
                bloqueadas[identificador] = version_bloqueada

            if nueva_prevision_id is not None:
                destino = self._exigir_prevision(sesion, destino_id)
                if destino["estado"] in (OMITIDA, CANCELADA):
                    raise ErrorMotor(
                        CodigoError.ESTADO_PREVISION_INCOMPATIBLE,
                        "Una previsión OMITIDA o CANCELADA no puede recibir "
                        "realidad.",
                    )

            if nuevo_hecho_id is not None:
                estado_hecho = repo_hechos.leer_estado(sesion, nuevo_hecho_id)
                if estado_hecho is None:
                    raise ErrorMotor(
                        CodigoError.AGREGADO_NO_ENCONTRADO,
                        "El hecho indicado no existe o no es accesible.",
                    )
                if estado_hecho[1] != "ACTIVO":
                    raise ErrorMotor(
                        CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                        "Un hecho anulado no es realidad.",
                    )

            # Guarda de version en el punto y el orden de la base (antes del
            # tocar), sobre las previsiones ya bloqueadas: precede a la relectura.
            for identificador in afectadas:
                esperada = versiones_esperadas.get(identificador)
                if esperada is None:
                    raise ErrorMotor(
                        CodigoError.ENTRADA_INVALIDA,
                        "Cada previsión afectada exige su version esperada.",
                    )
                if bloqueadas[identificador] != esperada:
                    raise ErrorMotor(
                        CodigoError.VERSION_DESFASADA,
                        "La previsión ha cambiado desde la version que conoce el "
                        "llamante.",
                    )
            # Relectura: si el vinculo cambio de hecho o de previsión, o cambio
            # el conjunto de reglas, la proteccion adquirida no es la necesaria.
            releido = repo_prev.leer_vinculo(sesion, vinculo_id)
            if (
                releido is None
                or releido["hecho_id"] != vinculo["hecho_id"]
                or releido["prevision_id"] != vinculo["prevision_id"]
                or sorted(
                    {r for r in (_regla_de(sesion, p) for p in afectadas) if r is not None},
                    key=str,
                ) != reglas
            ):
                raise ConjuntoCambiado()
            vinculo = releido

            # F04-R1 G-R1-C: estado posterior de cada hecho afectado; en un
            # traslado, origen y destino por separado y sin compensacion.
            hecho_viejo = vinculo["hecho_id"]
            hecho_nuevo = nuevo_hecho_id or hecho_viejo
            importe_nuevo = (
                nuevo_importe if nuevo_importe is not None else vinculo["importe_asignado"]
            )
            moneda_nueva = repo_prev.leer_prevision(sesion, destino_id)["moneda"]
            solicitado = (importe_nuevo, moneda_nueva)
            if hecho_nuevo == hecho_viejo:
                exigir_porcion(sesion, hecho_viejo, {vinculo_id: solicitado}, solicitado=solicitado)
            else:
                exigir_porcion(sesion, hecho_viejo, {vinculo_id: None}, solicitado=solicitado)
                exigir_porcion(sesion, hecho_nuevo, {vinculo_id: solicitado}, solicitado=solicitado)

            for identificador in afectadas:
                esperada = versiones_esperadas.get(identificador)
                if esperada is None:
                    raise ErrorMotor(
                        CodigoError.ENTRADA_INVALIDA,
                        "Cada previsión afectada exige su version esperada.",
                    )
                self._tocar(sesion, identificador, esperada)

            cambios: dict[str, Any] = {}
            if nuevo_importe is not None:
                cambios["importe_asignado"] = nuevo_importe
            if nuevo_hecho_id is not None:
                cambios["hecho_id"] = nuevo_hecho_id
            if nueva_prevision_id is not None:
                cambios["prevision_id"] = nueva_prevision_id

            actualizado = repo_prev.actualizar_vinculo(sesion, vinculo_id, cambios)
            if actualizado is None:  # pragma: no cover
                raise ErrorMotor(
                    CodigoError.CORRECCION_VINCULO_NO_REPRESENTABLE,
                    "La correccion no pudo aplicarse sobre el vinculo.",
                )
            auditoria.registrar(
                sesion,
                tabla=repo_prev.TABLA_VINCULOS,
                registro_id=vinculo_id,
                accion=auditoria.ACCION_ACTUALIZAR,
                datos_antes_json=actualizado[0],
                datos_despues_json=actualizado[1],
                motivo=motivo,
            )

            # Revalidacion D018/D019 en las dos raices afectadas.
            for identificador in afectadas:
                self._revalidar(sesion, identificador)

            return self._resultado_actual(sesion, destino_id)

        return self._ejecutar(contexto, operacion, "corregir_vinculo")

    def retirar_vinculo(
        self,
        contexto: ContextoOperacion,
        *,
        vinculo_id: uuid.UUID,
        prevision_id_esperada: uuid.UUID,
        prevision_row_version_esperada: int,
        motivo: str | None = None,
    ) -> ResultadoPrevision:
        """Retirada de un vinculo que NUNCA debio existir y sin sustituto.

        Es la unica via con DELETE, y queda auditada con el snapshot completo
        eliminado. Nunca se anula un hecho verdadero para corregir una
        asociacion falsa.

        F04-R2 §7.4: `prevision_row_version_esperada` es la version de
        `prevision_id_esperada`, la previsión a la que el llamante cree que
        pertenece el vinculo; no basta con que coincida la version.
        """

        def operacion(sesion: SesionMotor) -> ResultadoPrevision:
            repo_hechos.exigir_contexto(sesion)
            vinculo = repo_prev.leer_vinculo(sesion, vinculo_id)
            if vinculo is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El vinculo indicado no existe o no es accesible.",
                )
            prevision_id = vinculo["prevision_id"]
            hecho_leido = vinculo["hecho_id"]
            # F04-R1 G-R1-D: vinculo -> regla -> previsión -> relee el vinculo.
            regla_id = self._exigir_prevision(sesion, prevision_id)["regla_id"]
            if regla_id is not None:
                repo_reglas.bloquear_regla(sesion, regla_id)
            version_bloqueada = repo_prev.bloquear_prevision(sesion, prevision_id)
            # Guarda de version (punto de la base) antes de la relectura del vinculo.
            if version_bloqueada != prevision_row_version_esperada:
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "La previsión ha cambiado desde la version que conoce el "
                    "llamante.",
                )
            releido = repo_prev.leer_vinculo(sesion, vinculo_id)
            if releido is None or releido["prevision_id"] != prevision_id:
                raise ConjuntoCambiado()
            # F04-R2 §7.4: identidad sobre el vinculo RELEIDO bajo los locks.
            if (
                releido["prevision_id"] != prevision_id_esperada
                or releido["hecho_id"] != hecho_leido
            ):
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "El vinculo no pertenece a la previsión que conoce el "
                    "llamante.",
                )
            nueva_version = self._tocar(
                sesion, prevision_id, prevision_row_version_esperada
            )
            snapshot = repo_prev.borrar_vinculo(sesion, vinculo_id)
            if snapshot is None:  # pragma: no cover
                raise ErrorMotor(
                    CodigoError.CORRECCION_VINCULO_NO_REPRESENTABLE,
                    "El vinculo no pudo retirarse.",
                )
            auditoria.registrar(
                sesion,
                tabla=repo_prev.TABLA_VINCULOS,
                registro_id=vinculo_id,
                accion=auditoria.ACCION_ANULAR,
                datos_antes_json=snapshot,
                motivo=motivo or "vinculo que nunca debio existir",
            )
            self._revalidar(sesion, prevision_id)
            return self._resultado_actual(
                sesion, prevision_id, row_version=nueva_version
            )

        return self._ejecutar(contexto, operacion, "retirar_vinculo")



    # ==================================================================
    # Recalculo tras nueva version (mandato 43 y 44)
    # ==================================================================
    def recalcular_futuras(
        self,
        contexto: ContextoOperacion,
        *,
        regla_id: uuid.UUID,
        desde_fecha: dt.date,
        motivo: str | None = None,
    ) -> ResultadoRecalculo:
        """Regobierna las ocurrencias FUTURAS con la version que ahora aplica.

        Cuatro desenlaces, y ninguno se mezcla con otro:

        - ABIERTA con `recalculo_automatico=true` y objetivo que SIGUE
          perteneciendo al calendario: se regobierna su snapshot esperado
          —concepto, importe, ventana, cuentas, flujo— con la version vigente.
          `fecha_objetivo_regla` NO se toca: es la identidad canonica.
        - ABIERTA con `recalculo_automatico=false`: se RESPETA. La expectativa
          quedo congelada al llegar realidad o al ajustarse a mano, y
          reescribirla borraria una decision del usuario.
        - ABIERTA sin realidad cuyo objetivo YA NO pertenece a ningun segmento
          —cambio de cadencia, o la fecha cae en una pausa—: se CANCELA
          explicitamente y auditada. No se borra ni se reescribe su identidad.
        - Cualquier ocurrencia con realidad ACTIVA que haya quedado fuera del
          calendario: NO se toca y se devuelve en `requieren_revision`.

        Decision local sobre ese ultimo caso: podria hacerse fallar toda la
        operacion, pero entonces una sola ocurrencia con realidad bloquearia
        el recalculo de todas las demas. Se devuelve senalada en el resultado,
        que es explicito y no silencioso, y ademas la lectura derivada la
        expone como REQUIERE_REVISION. Lo que NO se hace es cancelarla ni
        regobernarla: eso destruiria realidad registrada.

        Las terminales no se tocan nunca: el pasado no se reescribe.
        """

        def operacion(sesion: SesionMotor) -> ResultadoRecalculo:
            repo_hechos.exigir_contexto(sesion)
            if repo_reglas.bloquear_regla(sesion, regla_id) is None:
                raise ErrorMotor(
                    CodigoError.REGLA_NO_ENCONTRADA,
                    "La regla indicada no existe o no es accesible.",
                )

            versiones = repo_reglas.listar_versiones(sesion, regla_id)
            segmentos = self._segmentos(versiones, self._resolver_ancla(sesion))
            futuras = repo_prev.futuras_de_regla(sesion, regla_id, desde_fecha)

            regobernadas: list[uuid.UUID] = []
            congeladas: list[uuid.UUID] = []
            canceladas: list[uuid.UUID] = []
            revision: list[uuid.UUID] = []

            for fila in futuras:
                if fila["estado"] != ABIERTA:
                    continue
                objetivo = fila["fecha_objetivo"]
                pertenece = self._pertenece_al_calendario(
                    sesion, regla_id, segmentos, objetivo
                )
                realidad = repo_prev.resumen_realidad(sesion, fila["id"])

                if not pertenece:
                    if realidad["hechos_activos"] > 0:
                        revision.append(fila["id"])
                        continue
                    detalle = repo_prev.leer_prevision(sesion, fila["id"])
                    assert detalle is not None
                    self._tocar(sesion, fila["id"], detalle["row_version"])
                    self._cambiar_estado(
                        sesion,
                        fila["id"],
                        CANCELADA,
                        detalle["snapshot"],
                        motivo
                        or "la ocurrencia ya no pertenece al calendario vigente",
                    )
                    canceladas.append(fila["id"])
                    continue

                if not fila["recalculo_automatico"]:
                    congeladas.append(fila["id"])
                    continue

                if self._regobernar(sesion, regla_id, fila["id"], objetivo, motivo):
                    regobernadas.append(fila["id"])

            return ResultadoRecalculo(
                regla_id=regla_id,
                regobernadas=tuple(regobernadas),
                congeladas_respetadas=tuple(congeladas),
                canceladas_fuera_de_segmento=tuple(canceladas),
                requieren_revision=tuple(revision),
            )

        return self._ejecutar(contexto, operacion, "recalcular_futuras")

    def _pertenece_al_calendario(
        self,
        sesion: SesionMotor,
        regla_id: uuid.UUID,
        segmentos: Sequence[dict[str, Any]],
        objetivo: dt.date,
    ) -> bool:
        """True si la identidad sigue siendo ocurrencia del calendario vigente.

        Exige las DOS cosas: que haya version vigente en esa fecha —una pausa
        deja la fecha huerfana— y que la fecha sea ocurrencia EXACTA del
        segmento que la contiene. Un cambio de intervalo deja identidades que
        siguen teniendo version pero ya no caen en la serie.
        """
        if repo_reglas.version_vigente_en(sesion, regla_id, objetivo) is None:
            return False
        for segmento in segmentos:
            if segmento["desde"] > objetivo:
                continue
            if segmento["hasta"] is not None and segmento["hasta"] < objetivo:
                continue
            if rec.es_ocurrencia(segmento["origen"], segmento["cadencia"], objetivo):
                return True
        return False

    def _regobernar(
        self,
        sesion: SesionMotor,
        regla_id: uuid.UUID,
        prevision_id: uuid.UUID,
        objetivo: dt.date,
        motivo: str | None,
    ) -> bool:
        """Reescribe el snapshot esperado con la version que ahora gobierna.

        Solo campos de `CAMPOS_REGOBERNABLES`. `fecha_objetivo_regla` no esta
        entre ellos y no se toca: mover la identidad haria que la ocurrencia
        deje de ser reconocible y podria colisionar con otra ya materializada.
        """
        version_id = repo_reglas.version_vigente_en(sesion, regla_id, objetivo)
        if version_id is None:  # pragma: no cover - ya comprobado
            return False
        version = repo_reglas.leer_version(sesion, version_id)
        if version is None:  # pragma: no cover
            return False

        excepcion = repo_reglas.leer_excepcion(sesion, regla_id, objetivo)
        ventana = rec.ventana_de(
            objetivo,
            fecha_modo=version["fecha_modo"],
            dia_desde=version["dia_desde"],
            dia_hasta=version["dia_hasta"],
            fecha_override=None if excepcion is None else excepcion["fecha_override"],
        )
        importe = self._importe_esperado(
            sesion,
            regla_id=regla_id,
            version=version,
            objetivo=objetivo,
            excepcion=excepcion,
        )
        snapshot_version = self._snapshot_de_version(version)

        cambios: dict[str, Any] = {
            "regla_version_id": version_id,
            "concepto": snapshot_version["concepto"],
            "tipo_hecho_id": snapshot_version["tipo_hecho_id"],
            "categoria_id": snapshot_version["categoria_id"],
            "tercero_id": snapshot_version["tercero_id"],
            "fecha_esperada_desde": ventana.desde,
            "fecha_esperada_hasta": ventana.hasta,
            "flujo_tesoreria_esperado": snapshot_version["flujo_tesoreria_esperado"],
            "moneda": snapshot_version["moneda"],
            "importe_esperado": importe,
            "importe_referencia_lado": snapshot_version["importe_referencia_lado"],
            "cuenta_salida_esperada_id": snapshot_version["cuenta_salida_esperada_id"],
            "cuenta_entrada_esperada_id": snapshot_version["cuenta_entrada_esperada_id"],
            "presupuestable": snapshot_version["presupuestable"],
        }
        detalle = repo_prev.leer_prevision(sesion, prevision_id)
        assert detalle is not None
        self._tocar(sesion, prevision_id, detalle["row_version"])
        actualizada = repo_prev.actualizar_prevision(sesion, prevision_id, cambios)
        if actualizada is None:  # pragma: no cover
            return False
        auditoria.registrar(
            sesion,
            tabla=repo_prev.TABLA_PREVISIONES,
            registro_id=prevision_id,
            accion=auditoria.ACCION_ACTUALIZAR,
            datos_antes_json=actualizada[0],
            datos_despues_json=actualizada[1],
            motivo=motivo or "regobernada por nueva version de regla",
        )
        return True

    # ==================================================================
    # F04-D024 — correccion de estado terminal
    # ==================================================================
    def corregir_estado_terminal(
        self,
        contexto: ContextoOperacion,
        *,
        prevision_id: uuid.UUID,
        row_version_esperada: int,
        motivo: str | None,
        sucesor_row_version_esperada: int | None = None,
    ) -> ResultadoPrevision:
        """REALIZADA -> ABIERTA u OMITIDA -> ABIERTA por error de captura.

        NO es una operacion ordinaria: solo corrige un estado que NUNCA fue
        cierto. Exige motivo explicito, version esperada y auditoria.

        Las TRES terminales se reabren por esta via, CANCELADA incluida
        (F04-D024.3). El tombstone es permanente para la generacion y el
        lifecycle ORDINARIOS, pero no convierte un error documentado en
        irreversible: su recuperacion existe solo a traves de este flujo
        auditado, y un read-model no debe confundirla con la reutilizacion
        ordinaria de una identidad cancelada.

        Los vinculos se CONSERVAN. Si el error fue marcar REALIZADA demasiado
        pronto, la realidad vinculada sigue siendo verdadera: la previsión
        vuelve a ABIERTA parcialmente realizada, con `recalculo_automatico`
        en false porque ya hay realidad que congela la expectativa.

        Si existe sucesor RODANTE, solo se admite cuando esta ABIERTA, sin
        realidad y recalculable: entonces se CANCELA en la misma transaccion.
        Si ya es terminal o tiene realidad, la correccion se rechaza
        ATOMICAMENTE con TRAMO_RODANTE_REQUIERE_REVISION (F04-D024.9):
        propagar en silencio sobre una cadena que ya avanzo destruiria realidad
        registrada. Ese codigo es propio de la correccion PREVISIONAL y no se
        confunde con el impacto derivado que OP-02/OP-03 devuelven sin
        rollback: F04-D024.10 separa expresamente las dos vias.
        """
        if not (motivo or "").strip():
            raise ErrorMotor(
                CodigoError.MOTIVO_AUSENTE,
                "La correccion de un estado terminal exige motivo explicito.",
            )

        def operacion(sesion: SesionMotor) -> ResultadoPrevision:
            repo_hechos.exigir_contexto(sesion)
            prevision = self._exigir_prevision(sesion, prevision_id)
            regla_id = prevision["regla_id"]
            if regla_id is not None:
                repo_reglas.bloquear_regla(sesion, regla_id)

            estado = prevision["estado"]
            if estado == ABIERTA:
                raise ErrorMotor(
                    CodigoError.ESTADO_PREVISION_INCOMPATIBLE,
                    "La previsión ya esta ABIERTA: no hay estado terminal que "
                    "corregir.",
                )
            sucesor = self._sucesor_reabrible(
                sesion, regla_id, prevision["fecha_objetivo_regla"]
            )
            if sucesor is not None and sucesor_row_version_esperada is None:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "La cadena tiene sucesor: exige su version esperada para "
                    "poder cancelarlo en la misma transaccion.",
                )

            nueva_version = self._tocar(sesion, prevision_id, row_version_esperada)

            if sucesor is not None:
                self._tocar(
                    sesion, sucesor["id"], sucesor_row_version_esperada
                )
                self._cambiar_estado(
                    sesion,
                    sucesor["id"],
                    CANCELADA,
                    sucesor["snapshot"],
                    "cancelado por correccion del estado terminal anterior",
                )

            actualizada = repo_prev.actualizar_prevision(
                sesion,
                prevision_id,
                {
                    "estado": ABIERTA,
                    # Hay realidad vinculada o la hubo: la expectativa no
                    # vuelve a ser recalculable automaticamente.
                    "recalculo_automatico": False,
                    "motivo_ajuste": motivo,
                },
            )
            assert actualizada is not None
            auditoria.registrar(
                sesion,
                tabla=repo_prev.TABLA_PREVISIONES,
                registro_id=prevision_id,
                accion=auditoria.ACCION_ACTUALIZAR,
                datos_antes_json=actualizada[0],
                datos_despues_json=actualizada[1],
                motivo=f"correccion de estado terminal {estado} -> ABIERTA: {motivo}",
            )

            self._revalidar(sesion, prevision_id)
            return self._resultado_actual(
                sesion, prevision_id, row_version=nueva_version
            )

        return self._ejecutar(contexto, operacion, "corregir_estado_terminal")

    def _sucesor_reabrible(
        self,
        sesion: SesionMotor,
        regla_id: uuid.UUID | None,
        fecha_objetivo: dt.date | None,
    ) -> dict[str, Any] | None:
        """Sucesor RODANTE posterior, si existe y puede cancelarse.

        Devuelve None cuando no hay sucesor. Si existe pero ya es terminal o
        tiene realidad ACTIVA, NO se devuelve: se rechaza la correccion, porque
        cancelar un sucesor con realidad destruiria algo verdadero.
        """
        if regla_id is None or fecha_objetivo is None:
            return None
        cabeza = repo_prev.cabeza_rodante(sesion, regla_id)
        if cabeza is None or cabeza["fecha_objetivo"] <= fecha_objetivo:
            # Sin cabeza abierta posterior: o no hay sucesor, o ya es terminal.
            posterior = repo_prev.terminal_posterior(
                sesion, regla_id, fecha_objetivo
            )
            if posterior is not None:
                raise ErrorMotor(
                    CodigoError.TRAMO_RODANTE_REQUIERE_REVISION,
                    "La cadena ya avanzo a un estado terminal posterior: la "
                    "correccion previsional se rechaza atomicamente.",
                )
            return None
        realidad = repo_prev.resumen_realidad(sesion, cabeza["id"])
        if realidad["hechos_activos"] > 0:
            raise ErrorMotor(
                CodigoError.TRAMO_RODANTE_REQUIERE_REVISION,
                "El sucesor ya tiene realidad ACTIVA vinculada: cancelarlo "
                "destruiria realidad registrada.",
            )
        detalle = repo_prev.leer_prevision(sesion, cabeza["id"])
        assert detalle is not None
        return {"id": cabeza["id"], "snapshot": detalle["snapshot"]}

    # ==================================================================
    # AMB-009 — lectura derivada
    # ==================================================================
    def estado_de(
        self, contexto: ContextoOperacion, prevision_id: uuid.UUID
    ) -> ResultadoPrevision:
        def operacion(sesion: SesionMotor) -> ResultadoPrevision:
            repo_hechos.exigir_contexto(sesion)
            self._exigir_prevision(sesion, prevision_id)
            return self._resultado_actual(sesion, prevision_id)

        return self._ejecutar(contexto, operacion, "estado_de_prevision")

    # ==================================================================
    # Interno
    # ==================================================================
    def _revalidar(self, sesion: SesionMotor, prevision_id: uuid.UUID) -> None:
        """Revalida D018/D019 tras una correccion.

        - REALIZADA sin realidad ACTIVA queda REALIZADA y se expone como
          REALIZADA_SIN_REALIDAD_ACTIVA: no se degrada a ABIERTA ni se inventa
          una omision.
        - OMITIDA o CANCELADA con realidad ACTIVA es incoherente.
        - ABIERTA con realidad ACTIVA queda con recalculo congelado.
        """
        prevision = repo_prev.leer_prevision(sesion, prevision_id)
        if prevision is None:  # pragma: no cover
            return
        realidad = repo_prev.resumen_realidad(sesion, prevision_id)
        if prevision["estado"] in (OMITIDA, CANCELADA) and realidad["hechos_activos"] > 0:
            raise ErrorMotor(
                CodigoError.ESTADO_PREVISION_INCOMPATIBLE,
                "Una previsión OMITIDA o CANCELADA no puede quedar con "
                "realidad ACTIVA.",
            )
        if (
            prevision["estado"] == ABIERTA
            and realidad["hechos_activos"] > 0
            and prevision["recalculo_automatico"]
        ):
            actualizada = repo_prev.actualizar_prevision(
                sesion, prevision_id, {"recalculo_automatico": False}
            )
            if actualizada is not None:
                auditoria.registrar(
                    sesion,
                    tabla=repo_prev.TABLA_PREVISIONES,
                    registro_id=prevision_id,
                    accion=auditoria.ACCION_ACTUALIZAR,
                    datos_antes_json=actualizada[0],
                    datos_despues_json=actualizada[1],
                    motivo="realidad ACTIVA presente: expectativa congelada",
                )

    def _crear_sucesor_si_rodante(
        self, sesion: SesionMotor, regla_id: uuid.UUID, uuid_sucesor: uuid.UUID | None
    ) -> None:
        """Crea la siguiente cabeza si el segmento vigente es RODANTE.

        La regla ya esta bloqueada por el llamante: esta funcion NO vuelve a
        bloquearla ni calcula nada antes del lock.
        """
        versiones = repo_reglas.listar_versiones(sesion, regla_id)
        segmentos = [
            s
            for s in self._segmentos(versiones, self._resolver_ancla(sesion))
            if s["cadencia"].anclaje == RODANTE
        ]
        if not segmentos or uuid_sucesor is None:
            return
        self._generar_rodante(sesion, regla_id, uuid_sucesor)

    def _cambiar_estado(
        self,
        sesion: SesionMotor,
        prevision_id: uuid.UUID,
        estado: str,
        snapshot_previo: str,
        motivo: str | None,
    ) -> None:
        actualizada = repo_prev.actualizar_prevision(
            sesion,
            prevision_id,
            {"estado": estado, "recalculo_automatico": False, "motivo_ajuste": motivo},
        )
        if actualizada is None:  # pragma: no cover
            raise ErrorMotor(
                CodigoError.ESTADO_PREVISION_INCOMPATIBLE,
                "La transicion no pudo aplicarse.",
            )
        auditoria.registrar(
            sesion,
            tabla=repo_prev.TABLA_PREVISIONES,
            registro_id=prevision_id,
            accion=auditoria.ACCION_ACTUALIZAR,
            datos_antes_json=snapshot_previo,
            datos_despues_json=actualizada[1],
            motivo=motivo or f"transicion a {estado}",
        )

    def _tocar(
        self, sesion: SesionMotor, prevision_id: uuid.UUID, esperada: int
    ) -> int:
        nueva = repo_prev.tocar_prevision(sesion, prevision_id, esperada)
        if nueva is None:
            raise ErrorMotor(
                CodigoError.VERSION_DESFASADA,
                "La previsión ha cambiado desde la version que conoce el "
                "llamante.",
            )
        return nueva

    def _resultado_actual(
        self,
        sesion: SesionMotor,
        prevision_id: uuid.UUID,
        *,
        row_version: int | None = None,
        idempotente: bool = False,
    ) -> ResultadoPrevision:
        prevision = repo_prev.leer_prevision(sesion, prevision_id)
        assert prevision is not None
        realidad = repo_prev.resumen_realidad(sesion, prevision_id)
        derivado = None
        if prevision["estado"] == REALIZADA and realidad["hechos_activos"] == 0:
            derivado = REALIZADA_SIN_REALIDAD_ACTIVA
        elif (
            prevision["estado"] in (OMITIDA, CANCELADA)
            and realidad["hechos_activos"] > 0
        ):
            # F04-D022: incoherencia detectada por LECTURA. No se degrada el
            # estado, no se inventa una transicion y no se escribe ninguna
            # marca funcional: se expone y quien corrija decide.
            derivado = REQUIERE_REVISION
        return ResultadoPrevision(
            prevision_id=prevision_id,
            row_version=row_version or prevision["row_version"],
            estado=prevision["estado"],
            estado_derivado=derivado,
            fecha_objetivo_regla=prevision["fecha_objetivo_regla"],
            importe_esperado=prevision["importe_esperado"],
            recalculo_automatico=prevision["recalculo_automatico"],
            idempotente=idempotente,
        )

    @staticmethod
    def _exigir_prevision(
        sesion: SesionMotor, prevision_id: uuid.UUID
    ) -> dict[str, Any]:
        prevision = repo_prev.leer_prevision(sesion, prevision_id)
        if prevision is None:
            raise ErrorMotor(
                CodigoError.AGREGADO_NO_ENCONTRADO,
                "La previsión indicada no existe o no es accesible.",
            )
        return prevision

    @staticmethod
    def _exigir_tipo_hecho(sesion: SesionMotor, codigo: str | None) -> uuid.UUID:
        if codigo is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA, "Se exige el tipo de hecho esperado."
            )
        tipo = repo_reglas.resolver_tipo_hecho(sesion, codigo)
        if tipo is None:
            raise ErrorMotor(
                CodigoError.TIPO_HECHO_DESCONOCIDO,
                "El tipo de hecho indicado no existe en el catalogo.",
            )
        return tipo

    @staticmethod
    def _exigir_moneda_demostrada(
        sesion: SesionMotor, moneda_prevision: str, datos: DatosVinculo
    ) -> None:
        """Multidivisa: sin equivalencia declarada, se rechaza.

        No se consulta FX, no se inventa tipo, no se divide por nominales y no
        se copia el importe de una moneda como si fuese de otra.
        """
        fila = sesion.uno(
            "SELECT moneda FROM gapto.hechos_financieros WHERE id = %s::uuid",
            (datos.hecho_id,),
        )
        if fila is None:  # pragma: no cover - ya se comprobo su existencia
            return
        if fila[0] != moneda_prevision and not datos.equivalencia_declarada:
            raise ErrorMotor(
                CodigoError.ASIGNACION_MULTIDIVISA_NO_DEMOSTRADA,
                "El hecho esta en otra moneda: el importe asignado en moneda "
                "de la previsión debe declararse explicitamente.",
            )

    @staticmethod
    def _segmentos(
        versiones: Sequence[dict[str, Any]],
        resolver_ancla: Any = None,
    ) -> list[dict[str, Any]]:
        """Agrupa versiones contiguas de la misma cadencia en segmentos.

        Rompen segmento la pausa y cualquier cambio de cadencia. El ORIGEN del
        segmento es el `vigente_desde` de su primera version, y es lo que
        alimenta la aritmetica de F04-D020: dentro de un segmento, cambiar
        importe o categoria no reinicia el calendario.
        """
        segmentos: list[dict[str, Any]] = []
        for version in versiones:
            cadencia = Cadencia(
                version["periodicidad"], version["intervalo"], version["anclaje_recurrencia"]
            )
            if not cadencia.recurrente:
                continue
            if segmentos:
                previo = segmentos[-1]
                hay_pausa = (
                    previo["hasta"] is None
                    or version["vigente_desde"] > previo["hasta"] + dt.timedelta(days=1)
                )
                if not rec.rompe_segmento(
                    previo["cadencia"], cadencia, hay_pausa=hay_pausa
                ):
                    previo["hasta"] = version["vigente_hasta"]
                    previo["version_id"] = version["id"]
                    previo["version_ids"].append(version["id"])
                    continue
                ancla_previa = None
                if resolver_ancla is not None and cadencia.anclaje == RODANTE:
                    terminal = resolver_ancla(previo["version_ids"])
                    if terminal is not None:
                        ancla_previa = terminal["fecha_objetivo"]
                origen = rec.origen_de_segmento_nuevo(
                    vigente_desde=version["vigente_desde"],
                    anterior=previo["cadencia"],
                    nueva=cadencia,
                    ancla_terminal_previa=ancla_previa,
                )
            else:
                origen = version["vigente_desde"]
            segmentos.append(
                {
                    "origen": origen,
                    "desde": version["vigente_desde"],
                    "hasta": version["vigente_hasta"],
                    "cadencia": cadencia,
                    "version_id": version["id"],
                    "version_ids": [version["id"]],
                }
            )
        return segmentos

    @staticmethod
    def _resolver_ancla(sesion: SesionMotor) -> Any:
        """Devuelve el resolver de ancla de segmento (F04-D023).

        Se cierra sobre la sesion, que YA tiene la regla bloqueada: la lectura
        del ancla ocurre dentro del lock, igual que el resto del calculo.
        """

        def resolver(version_ids: Sequence[uuid.UUID]) -> dict[str, Any] | None:
            return repo_prev.ultima_terminal_de_versiones(sesion, version_ids)

        return resolver

    @staticmethod
    def _limite_del_segmento(
        segmento: dict[str, Any], hasta_fecha: dt.date | None
    ) -> dt.date | None:
        candidatos = [f for f in (segmento["hasta"], hasta_fecha) if f is not None]
        if not candidatos:
            return None
        return min(candidatos)

    def _replay_manual(
        self,
        sesion: SesionMotor,
        datos: DatosPrevisionManual,
        existente: dict[str, Any],
    ) -> ResultadoPrevision:
        coincide = repo_prev.creacion_previa_coincide(
            sesion,
            repo_prev.TABLA_PREVISIONES,
            datos.prevision_id,
            {
                "id": datos.prevision_id,
                "concepto": (datos.concepto or "").strip(),
                "moneda": datos.moneda,
                "fecha_esperada_desde": datos.fecha_esperada_desde,
                "fecha_esperada_hasta": datos.fecha_esperada_hasta,
            },
            repo_prev.TIPOS_SQL_PREVISION,
        )
        if not coincide:
            raise self._conflicto_identidad()
        return ResultadoPrevision(
            prevision_id=datos.prevision_id,
            row_version=existente["row_version"],
            estado=existente["estado"],
            importe_esperado=existente["importe_esperado"],
            recalculo_automatico=existente["recalculo_automatico"],
            idempotente=True,
        )

    @staticmethod
    def _snapshot_de_version(version: dict[str, Any]) -> dict[str, Any]:
        """Materializa el estado esperado desde la version que gobierna.

        La previsión no vuelve a leer la regla despues para interpretar su
        pasado: lo que se guarda aqui es lo que esa ocurrencia esperaba.
        """
        import json

        crudo = json.loads(version["snapshot"])
        return {
            "concepto": crudo.get("concepto") or "ocurrencia de regla",
            "tipo_hecho_id": crudo["tipo_hecho_id"],
            "categoria_id": crudo["categoria_id"],
            "tercero_id": crudo["tercero_id"],
            "flujo_tesoreria_esperado": crudo["flujo_tesoreria_esperado"],
            "moneda": crudo["moneda"],
            "importe_referencia_lado": crudo["importe_referencia_lado"],
            "cuenta_salida_esperada_id": crudo["cuenta_salida_esperada_id"],
            "cuenta_entrada_esperada_id": crudo["cuenta_entrada_esperada_id"],
            "presupuestable": crudo["presupuestable"],
        }

    @staticmethod
    def _conflicto_identidad() -> ErrorMotor:
        return ErrorMotor(
            CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
            "Alguno de los identificadores reservados ya esta en uso con otra "
            "intencion.",
        )

    @staticmethod
    def _validar_manual(datos: DatosPrevisionManual) -> None:
        if not (datos.concepto or "").strip():
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA, "Una previsión exige concepto."
            )
        if datos.fecha_esperada_desde is None or datos.fecha_esperada_hasta is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una previsión exige ventana esperada desde/hasta.",
            )
        if datos.fecha_esperada_desde > datos.fecha_esperada_hasta:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "La ventana esperada no puede terminar antes de empezar.",
            )
        if datos.moneda is None or not _MONEDA_VALIDA.match(datos.moneda):
            raise ErrorMotor(
                CodigoError.MONEDA_INVALIDA,
                "La moneda debe ser un codigo de tres letras mayusculas.",
            )
        if datos.presupuestable is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "`presupuestable` no tiene default: debe indicarse.",
            )
        if datos.importe_esperado is not None and decimal.Decimal(
            datos.importe_esperado
        ) <= CERO:
            raise ErrorMotor(
                CodigoError.IMPORTE_NO_POSITIVO,
                "El importe esperado, si se conoce, debe ser positivo. Lo "
                "desconocido se expresa con NULL, nunca con cero.",
            )

    def _ejecutar(
        self, contexto: ContextoOperacion, operacion: Any, nombre: str
    ) -> Any:
        resultado = self._unidad.ejecutar_con_traza(contexto, operacion, nombre=nombre)
        self.ultima_traza = resultado.traza
        return resultado.valor


# ==================================================================
# F04-R1 G-R1-C — porcion acumulada de un hecho entre previsiones
# ==================================================================

def exigir_porcion(
    sesion: SesionMotor,
    hecho_id: uuid.UUID,
    cambios: dict[uuid.UUID, tuple[Any, str] | None],
    *,
    solicitado: tuple[Any, str],
) -> None:
    """Evalua el estado POSTERIOR completo de los vinculos de `hecho_id`.

    `cambios`: vinculo_id -> (importe, moneda de su previsión) en el estado
    posterior, o None si el vinculo deja el hecho. Levanta
    PORCION_DE_REALIDAD_EXCEDIDA si la operacion crea o agrava un exceso, o si
    en la rama NO_DETERMINABLE aumenta los vinculos por encima de uno (o, con
    mas de uno preexistente, aumenta su numero o algun importe). El importe
    desconocido nunca cuenta como 0 y la equivalencia declarada no es una
    conversion: en esa rama no hay comparacion numerica.
    """
    porcion = repo_prev.porcion_de_hecho(sesion, hecho_id)
    if porcion is None:  # existencia y visibilidad las deciden las validaciones previas
        return
    tope, moneda_hecho = porcion
    previo = {
        v["id"]: (decimal.Decimal(v["importe"]), v["moneda"])
        for v in repo_prev.vinculos_de_hecho(sesion, hecho_id)
    }
    posterior = dict(previo)
    for vinculo_id, valor in cambios.items():
        if valor is None:
            posterior.pop(vinculo_id, None)
        else:
            posterior[vinculo_id] = (decimal.Decimal(valor[0]), valor[1])

    def comparable(estado: dict) -> bool:
        return tope is not None and all(m == moneda_hecho for _, m in estado.values())

    sigma_previa = (
        sum((i for i, _ in previo.values()), CERO) if comparable(previo) else None
    )

    def rechazo(motivo: str) -> ErrorMotor:
        return ErrorMotor(
            CodigoError.PORCION_DE_REALIDAD_EXCEDIDA,
            "La porcion de realidad del hecho ya esta asignada a otras "
            "previsiones."
            if motivo == "EXCEDE"
            else "El importe del hecho no es comparable con sus vinculos: "
            "solo admite un vinculo.",
            contexto_extra={
                "motivo": motivo,
                "tope": None
                if tope is None
                else {"importe": str(tope), "moneda": moneda_hecho},
                "asignado_previo": {
                    "importe": None if sigma_previa is None else str(sigma_previa),
                    "moneda": moneda_hecho,
                    "vinculos": len(previo),
                },
                "solicitado": {
                    "importe": str(decimal.Decimal(solicitado[0])),
                    "moneda": solicitado[1],
                },
            },
        )

    if not comparable(posterior):
        # Rama NO_DETERMINABLE (restriccion funcional provisional, F04-D058).
        aumenta = len(posterior) > len(previo) and len(posterior) > 1
        sube = len(previo) > 1 and (
            len(posterior) > len(previo)
            or any(posterior[v][0] > previo[v][0] for v in posterior if v in previo)
        )
        if aumenta or sube:
            raise rechazo("NO_DETERMINABLE")
        return

    sigma_posterior = sum((i for i, _ in posterior.values()), CERO)
    if sigma_posterior > tope and (
        sigma_previa is None or sigma_previa <= tope or sigma_posterior > sigma_previa
    ):
        raise rechazo("EXCEDE")


# ==================================================================
# F04-D022 — impacto de una correccion de realidad sobre la cadena
# ==================================================================

def _conjunto_de_impacto(
    sesion: SesionMotor, hecho_id: uuid.UUID
) -> tuple[list[dict[str, Any]], list[uuid.UUID], list[uuid.UUID]]:
    """(REALIZADAS en orden cronologico, reglas por UUID, sucesores por UUID)
    que la propagacion de `hecho_id` puede tocar. Lectura sin lock."""
    filas = repo_prev.rodantes_realizadas_de_hecho(sesion, hecho_id)
    reglas = sorted({f["regla_id"] for f in filas}, key=str)
    sucesores = set()
    for fila in filas:
        sucesor = repo_prev.sucesor_inmediato(sesion, fila["regla_id"], fila["fecha_objetivo"])
        if sucesor is not None:
            sucesores.add(sucesor["id"])
    return filas, reglas, sorted(sucesores, key=str)


def conjunto_impacto_correccion_ancla(
    sesion: SesionMotor, hecho_id: uuid.UUID
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """(reglas, sucesores) por UUID que `impacto_correccion_ancla` bloqueara
    para `hecho_id`. Lectura sin lock: solo prepara la adquisicion del
    llamante (nivel 5 de F04-R2 §6.1); la autorizacion la da la relectura."""
    _, reglas, sucesores = _conjunto_de_impacto(sesion, hecho_id)
    return reglas, sucesores


@dataclass(frozen=True, slots=True)
class PlanImpactoAncla:
    """Conjunto de la propagacion de `hecho_id` YA bloqueado y revalidado
    (reglas FU -> previsiones por UUID). Solo `aplicar_impacto_ancla` lo usa."""

    hecho_id: uuid.UUID
    filas: tuple[dict[str, Any], ...]
    reglas: tuple[uuid.UUID, ...]
    sucesores: tuple[uuid.UUID, ...]


def adquirir_impacto_ancla(sesion: SesionMotor, hecho_id: uuid.UUID) -> PlanImpactoAncla:
    """F04-R1 G-R1-D / F04-R2 §2.3.2 bis nivel 5: calcula el conjunto sin
    lock, adquiere reglas FU y previsiones por UUID y lo relee; si cambio,
    ConjuntoCambiado (reintento completo). No escribe nada."""
    filas, reglas, sucesores = _conjunto_de_impacto(sesion, hecho_id)
    _bloquear_reglas(sesion, reglas)
    for sucesor_id in sucesores:
        repo_prev.bloquear_prevision(sesion, sucesor_id)
    releido = _conjunto_de_impacto(sesion, hecho_id)
    if (
        [f["prevision_id"] for f in releido[0]] != [f["prevision_id"] for f in filas]
        or releido[1:] != (reglas, sucesores)
    ):
        raise ConjuntoCambiado()
    return PlanImpactoAncla(hecho_id=hecho_id, filas=tuple(releido[0]), reglas=tuple(reglas),
                            sucesores=tuple(sucesores))


def impacto_correccion_ancla(
    sesion: SesionMotor, hecho_id: uuid.UUID
) -> dict[str, Any]:
    """Propaga lo que sea seguro y DEVUELVE el impacto derivado: es
    `aplicar_impacto_ancla(adquirir_impacto_ancla(...))`, sin cambio semantico."""
    return aplicar_impacto_ancla(sesion, adquirir_impacto_ancla(sesion, hecho_id))


def aplicar_impacto_ancla(
    sesion: SesionMotor, plan: PlanImpactoAncla
) -> dict[str, Any]:
    """Propaga lo que sea seguro y DEVUELVE el impacto derivado.

    Esta funcion es el colaborador que OP-02 y OP-03 inyectan. Vive aqui
    —dominio de previsiones— y opera sobre la MISMA sesion y la MISMA
    transaccion de la correccion, de modo que `hechos_service` no adquiere
    ninguna dependencia hacia F04-05.

    F04-D022: la realidad manda. Esta funcion NUNCA levanta para impedir la
    correccion de un hecho. Devuelve:

      - `propagadas`: sucesores cuya VENTANA se actualizo con la nueva ancla.
        Su `fecha_objetivo_regla` NO se toca: la identidad es inmutable y solo
        se recalcula lo recalculable (mandato 60).
      - `afectadas` + `requiere_revision`: tramos que no pueden propagarse sin
        reescribir historia. No se persiste marca alguna; el read-model deriva
        la revision de estos mismos datos.

    Se propaga solo cuando el sucesor esta ABIERTA, sin realidad ACTIVA, con
    `recalculo_automatico=true` y sin tramo terminal posterior. Cualquier otra
    situacion se senala en vez de reescribirse.
    """
    propagadas: list[uuid.UUID] = []
    afectadas: list[uuid.UUID] = []

    # F04-R1 G-R1-D: la adquisicion (reglas -> previsiones, por UUID) ya la hizo
    # `adquirir_impacto_ancla`; aqui solo se procesa, en el orden cronologico de
    # siempre, sobre lo bloqueado. No se adquiere ningun lock nuevo.
    for fila in plan.filas:
        prevision_id = fila["prevision_id"]
        regla_id = fila["regla_id"]
        objetivo = fila["fecha_objetivo"]
        cadencia = Cadencia(
            fila["periodicidad"], fila["intervalo"], fila["anclaje_recurrencia"]
        )
        if not cadencia.recurrente:  # pragma: no cover - RODANTE siempre la tiene
            continue

        realidad = repo_prev.resumen_realidad(sesion, prevision_id)
        if realidad["hechos_activos"] == 0 or realidad["fecha_real_maxima"] is None:
            # AMB-009: sin realidad ACTIVA no hay ancla defendible y el
            # objetivo canonico NO sirve de respaldo.
            afectadas.append(prevision_id)
            continue

        sucesor = repo_prev.sucesor_inmediato(sesion, regla_id, objetivo)
        if sucesor is None:
            continue
        if repo_prev.terminal_posterior(sesion, regla_id, sucesor["fecha_objetivo"]):
            afectadas.append(sucesor["id"])
            continue
        if sucesor["estado"] != ABIERTA or not sucesor["recalculo_automatico"]:
            afectadas.append(sucesor["id"])
            continue
        if repo_prev.resumen_realidad(sesion, sucesor["id"])["hechos_activos"] > 0:
            afectadas.append(sucesor["id"])
            continue

        nueva = rec.ocurrencia(realidad["fecha_real_maxima"], cadencia, 1)
        detalle = repo_prev.leer_prevision(sesion, sucesor["id"])
        assert detalle is not None
        if (
            detalle["fecha_esperada_desde"] == nueva
            and detalle["fecha_esperada_hasta"] == nueva
        ):
            continue

        # Un conflicto de version nunca es una actualizacion satisfactoria.
        if repo_prev.tocar_prevision(sesion, sucesor["id"], detalle["row_version"]) is None:
            raise ConjuntoCambiado()
        actualizada = repo_prev.actualizar_prevision(
            sesion,
            sucesor["id"],
            {"fecha_esperada_desde": nueva, "fecha_esperada_hasta": nueva},
        )
        if actualizada is not None:
            auditoria.registrar(
                sesion,
                tabla=repo_prev.TABLA_PREVISIONES,
                registro_id=sucesor["id"],
                accion=auditoria.ACCION_ACTUALIZAR,
                datos_antes_json=actualizada[0],
                datos_despues_json=actualizada[1],
                motivo="ventana recalculada por correccion del ancla real",
            )
            propagadas.append(sucesor["id"])

    return {
        "propagadas": tuple(propagadas),
        "afectadas": tuple(afectadas),
        "requiere_revision": bool(afectadas),
        "motivo": (
            CodigoError.REVISION_DERIVADA_REQUERIDA.value if afectadas else None
        ),
    }
