# ============================================================
# GAPTO MOBILE 2027
# Fichero: contexto_service.py
# Ruta: backend/app/services/contexto_service.py
# Descripcion: F04-D048 R3 (A18). Writers internos del agregado para las
#   cuatro dimensiones contextuales del hecho y operacion ordinaria de
#   ENRIQUECIMIENTO posterior.
#
#   ENRIQUECER no es CORREGIR. Enriquecer significa que el dato no estaba
#   registrado y ahora se conoce: solo AÑADE filas, no exige motivo y no finge
#   que el hecho economico ocurriera de nuevo. Retirar o cambiar un dato que
#   nunca fue cierto es OP-21 (correcciones_service), con motivo.
#
#   Un solo codigo de validacion y alta (`escribir_contexto`) sirve al alta
#   dentro de OP-22, al enriquecimiento y a las altas de reemplazo de OP-21:
#   no hay dos implementaciones de ninguna dimension.
#
#   MATRIZ `hecho_entidades` (pronunciamiento R3-01, vinculante): se valida
#   conjuntamente tipo_entidad x nivel hecho/efecto x tipo_relacion x principal.
#     - Solo AFECTA_A y RELACIONADO_CON. GENERADO_POR y REPERCUTIBLE_A son
#       reservadas -> ENTRADA_INVALIDA (relacion no permitida; no es F07).
#     - DERECHO_OBLIGACION: sin vinculo contextual (su vinculo es el
#       GENERADO_POR de OP-12; una fila contextual entraria en su saldo)
#       -> ENTRADA_INVALIDA.
#     - INVERSION: solo nivel hecho, efecto_id NULL y principal=false; efecto o
#       principal=true -> OWNERSHIP_F07 (podria contar para D-080).
#     - FINANCIACION: solo nivel hecho; a nivel de efecto -> OWNERSHIP_F07.
#     - PROPIEDAD/CONTRATO/SERVICIO/CONTEXTO: hecho o efecto del MISMO hecho.
#   Objeto referenciado no visible (otro tenant o inexistente) ->
#   AGREGADO_NO_ENCONTRADO; deshabilitado -> OPERACION_NO_PERMITIDA_EN_ESTADO
#   (solo en altas NUEVAS: el replay compara identidad antes de validar).
#
#   `principal` (R3-04): obligatorio y booleano; None o ausencia se rechazan
#   ANTES del INSERT y nunca se convierten en false.
#
#   Magnitudes (F04-D048 Q03): `categoria_magnitudes.obligatoria` NO se
#   consulta; ausencia de una magnitud marcada obligatoria no es invariante
#   F04. Valor desconocido = ausencia de fila; nunca cero.
#
#   D-080 (pronunciamiento R3-02): `trg_hecho_entidades__d080` toma el advisory
#   INVERSIONES en el COMMIT en TODA escritura de hecho_entidades. Por eso
#   cualquier operacion que vaya a escribir hecho_entidades toma el advisory
#   ANTES de cualquier row lock (`tomar_advisory_si_entidades`).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import uuid
from typing import Any

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import ESTADO_ACTIVO
from app.core.modelos_compuesto import (
    RELACIONES_CONTEXTUALES,
    RELACIONES_RESERVADAS,
    ROLES_TERCERO,
    TIPO_ENTIDAD_FINANCIACION,
    TIPO_ENTIDAD_INVERSION,
    TIPO_ENTIDAD_POSICION,
    TIPOS_ENTIDAD_CONTEXTO_LIBRE,
    DatosContextoHecho,
    DatosEntidadHecho,
    DatosEtiquetaHecho,
    DatosMagnitudHecho,
    DatosTerceroHecho,
    ResultadoContexto,
)
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import contexto_repository as repo_ctx
from app.repositories import correcciones_repository as repo_corr
from app.repositories import hechos_repository as repo_hechos

UNIDAD_MAX = 20


def _mismo(a: Any, b: Any) -> bool:
    """Igualdad tolerante a representacion (uuid/Decimal/str)."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b
    try:
        return decimal.Decimal(str(a)) == decimal.Decimal(str(b))
    except (decimal.InvalidOperation, ValueError):
        return str(a) == str(b)


# ----------------------------------------------------------------------
# Validacion estructural (pura, sin estado)
# ----------------------------------------------------------------------
def _exigir_principal(valor: Any, que: str) -> None:
    if not isinstance(valor, bool):
        raise ErrorMotor(
            CodigoError.ENTRADA_INVALIDA,
            f"`principal` es obligatorio y explicito en {que} (R3-04): no se "
            "convierte la ausencia de decision en false.",
        )


def validar_estructura(datos: DatosContextoHecho) -> None:
    ids = datos.identidades()
    if len(ids) != len(set(ids)):
        raise ErrorMotor(
            CodigoError.ENTRADA_INVALIDA,
            "Cada fila contextual necesita una identidad reservada propia.",
        )
    for t in datos.terceros:
        _exigir_principal(t.principal, "hecho_terceros")
        if t.rol_en_hecho not in ROLES_TERCERO:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                f"rol_en_hecho debe ser uno de {sorted(ROLES_TERCERO)}.",
            )
    for e in datos.entidades:
        _exigir_principal(e.principal, "hecho_entidades")
        if e.tipo_relacion in RELACIONES_RESERVADAS:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                f"Relacion no permitida como contexto: {e.tipo_relacion} esta "
                "reservada a su operacion propietaria.",
            )
        if e.tipo_relacion not in RELACIONES_CONTEXTUALES:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Relacion no permitida como contexto: solo AFECTA_A o "
                "RELACIONADO_CON.",
            )
    for m in datos.magnitudes:
        if m.valor is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una magnitud desconocida no se registra: no se envia la fila "
                "(nunca se convierte en cero).",
            )
        try:
            valor = decimal.Decimal(m.valor)
        except (decimal.InvalidOperation, TypeError, ValueError) as exc:
            raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "valor no numerico.") from exc
        if not valor.is_finite():
            raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "valor no finito.")
        if m.unidad is not None and (
            not m.unidad.strip() or len(m.unidad) > UNIDAD_MAX
        ):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "unidad debe ser texto no vacio de hasta 20 caracteres.",
            )


# ----------------------------------------------------------------------
# D-080
# ----------------------------------------------------------------------
def tomar_advisory_si_entidades(
    sesion: SesionMotor, owner: uuid.UUID, escribe_entidades: bool
) -> None:
    """R3-02: advisory INVERSIONES antes de cualquier row lock."""
    if escribe_entidades:
        repo_corr.tomar_advisory_inversiones(sesion, owner)


# ----------------------------------------------------------------------
# Validacion contra estado + alta (compartido por OP-22, enriquecimiento y
# altas de reemplazo de OP-21)
# ----------------------------------------------------------------------
def _objeto_visible_y_habilitado(ficha: dict[str, Any] | None, que: str) -> None:
    if ficha is None:
        raise ErrorMotor(
            CodigoError.AGREGADO_NO_ENCONTRADO,
            f"{que} no existe o no es accesible.",
        )
    if not ficha["enabled"]:
        raise ErrorMotor(
            CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
            f"{que} esta deshabilitado: no admite vinculos nuevos.",
        )


def validar_entidad_contextual(
    sesion: SesionMotor, hecho_id: uuid.UUID, e: DatosEntidadHecho
) -> None:
    """Matriz R3-01: tipo_entidad x nivel x relacion x principal."""
    ficha = repo_ctx.leer_entidad(sesion, e.entidad_id)
    _objeto_visible_y_habilitado(ficha, "La entidad")
    tipo = ficha["tipo_entidad"]
    if tipo == TIPO_ENTIDAD_POSICION:
        raise ErrorMotor(
            CodigoError.ENTRADA_INVALIDA,
            "Una posicion no admite vinculo contextual: su vinculo con efectos "
            "es el GENERADO_POR de su operacion propietaria.",
        )
    if tipo == TIPO_ENTIDAD_INVERSION:
        if e.efecto_id is not None or e.principal:
            raise ErrorMotor(
                CodigoError.OWNERSHIP_F07,
                "Un vinculo de inversion a nivel de efecto o principal puede "
                "participar en D-080: pertenece a F07.",
            )
    elif tipo == TIPO_ENTIDAD_FINANCIACION:
        if e.efecto_id is not None:
            raise ErrorMotor(
                CodigoError.OWNERSHIP_F07,
                "Un vinculo de financiacion a nivel de efecto pertenece a F07.",
            )
    elif tipo not in TIPOS_ENTIDAD_CONTEXTO_LIBRE:
        raise ErrorMotor(
            CodigoError.ENTRADA_INVALIDA,
            f"Tipo de entidad sin contrato de contexto R3: {tipo}.",
        )
    if e.efecto_id is not None and not repo_ctx.efecto_del_hecho(
        sesion, hecho_id, e.efecto_id
    ):
        raise ErrorMotor(
            CodigoError.ENTRADA_INVALIDA,
            "El efecto indicado no pertenece a este hecho.",
        )


def escribir_contexto(
    sesion: SesionMotor,
    owner: uuid.UUID,
    hecho_id: uuid.UUID,
    datos: DatosContextoHecho,
    motivo: str | None = None,
) -> dict[str, int]:
    """Valida contra el estado actual e inserta. Exige raiz ya bloqueada y,
    si hay entidades, advisory ya tomado. Cualquier fallo aborta la
    transaccion anfitriona entera."""
    creados = {"terceros": 0, "entidades": 0, "magnitudes": 0, "etiquetas": 0}

    def _crear(tabla: str, registro_id: uuid.UUID, snapshot: str | None) -> None:
        if snapshot is None:
            raise ErrorMotor(
                CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                "El identificador de la fila contextual ya esta en uso.",
            )
        auditoria.registrar(
            sesion,
            tabla=tabla,
            registro_id=registro_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=snapshot,
            motivo=motivo,
        )

    for t in datos.terceros:
        _objeto_visible_y_habilitado(repo_ctx.leer_tercero(sesion, t.tercero_id), "El tercero")
        _crear(
            repo_ctx.TABLA_TERCEROS,
            t.registro_id,
            repo_ctx.insertar_tercero(
                sesion,
                registro_id=t.registro_id,
                hecho_id=hecho_id,
                tercero_id=t.tercero_id,
                rol_en_hecho=t.rol_en_hecho,
                principal=t.principal,
            ),
        )
        creados["terceros"] += 1
    for e in datos.entidades:
        validar_entidad_contextual(sesion, hecho_id, e)
        _crear(
            repo_ctx.TABLA_ENTIDADES,
            e.registro_id,
            repo_ctx.insertar_entidad(
                sesion,
                registro_id=e.registro_id,
                owner_user_id=owner,
                hecho_id=hecho_id,
                efecto_id=e.efecto_id,
                entidad_id=e.entidad_id,
                tipo_relacion=e.tipo_relacion,
                principal=e.principal,
            ),
        )
        creados["entidades"] += 1
    for m in datos.magnitudes:
        ficha = repo_ctx.leer_magnitud(sesion, m.magnitud_id)
        _objeto_visible_y_habilitado(ficha, "La magnitud")
        _crear(
            repo_ctx.TABLA_MAGNITUDES,
            m.registro_id,
            repo_ctx.insertar_magnitud(
                sesion,
                registro_id=m.registro_id,
                hecho_id=hecho_id,
                magnitud_id=m.magnitud_id,
                valor=decimal.Decimal(m.valor),
                unidad=m.unidad if m.unidad is not None else ficha["unidad_default"],
            ),
        )
        creados["magnitudes"] += 1
    for g in datos.etiquetas:
        _objeto_visible_y_habilitado(repo_ctx.leer_etiqueta(sesion, g.etiqueta_id), "La etiqueta")
        _crear(
            repo_ctx.TABLA_ETIQUETAS,
            g.registro_id,
            repo_ctx.insertar_etiqueta(
                sesion, registro_id=g.registro_id, hecho_id=hecho_id, etiqueta_id=g.etiqueta_id
            ),
        )
        creados["etiquetas"] += 1
    return creados


# ----------------------------------------------------------------------
# Replay: identidad ANTES de validacion
# ----------------------------------------------------------------------
def _coincide(tabla: str, fila: dict[str, Any], hecho_id: uuid.UUID, d: Any) -> bool:
    if not _mismo(fila["hecho_id"], hecho_id):
        return False
    if tabla == repo_ctx.TABLA_TERCEROS:
        return (
            _mismo(fila["tercero_id"], d.tercero_id)
            and fila["rol_en_hecho"] == d.rol_en_hecho
            and fila["principal"] is d.principal
        )
    if tabla == repo_ctx.TABLA_ENTIDADES:
        return (
            _mismo(fila["entidad_id"], d.entidad_id)
            and _mismo(fila["efecto_id"], d.efecto_id)
            and fila["tipo_relacion"] == d.tipo_relacion
            and fila["principal"] is d.principal
        )
    if tabla == repo_ctx.TABLA_MAGNITUDES:
        return (
            _mismo(fila["magnitud_id"], d.magnitud_id)
            and _mismo(fila["valor"], d.valor)
            and (d.unidad is None or fila["unidad"] == d.unidad)
        )
    return _mismo(fila["etiqueta_id"], d.etiqueta_id)


def filas_solicitadas(datos: DatosContextoHecho) -> list[tuple[str, Any]]:
    return (
        [(repo_ctx.TABLA_TERCEROS, t) for t in datos.terceros]
        + [(repo_ctx.TABLA_ENTIDADES, e) for e in datos.entidades]
        + [(repo_ctx.TABLA_MAGNITUDES, m) for m in datos.magnitudes]
        + [(repo_ctx.TABLA_ETIQUETAS, g) for g in datos.etiquetas]
    )


def clasificar_replay(
    sesion: SesionMotor, hecho_id: uuid.UUID, datos: DatosContextoHecho
) -> str:
    """NUEVO (ninguna existe) / REPLICA (todas existen e iguales) / CONFLICTO.

    Solo compara identidad e intencion: no consulta enabled ni ningun otro
    estado mutable, para que un reintento tras COMMIT desconocido no quede
    oculto por cambios posteriores de configuracion (§14).
    """
    existentes = 0
    iguales = 0
    solicitadas = filas_solicitadas(datos)
    for tabla, d in solicitadas:
        leida = repo_ctx.leer_registro(sesion, tabla, d.registro_id)
        if leida is None:
            continue
        existentes += 1
        iguales += _coincide(tabla, leida[0], hecho_id, d)
    if existentes == 0:
        return "NUEVO"
    if existentes == len(solicitadas) and iguales == existentes:
        return "REPLICA"
    return "CONFLICTO"


# ----------------------------------------------------------------------
# Servicio: enriquecimiento posterior
# ----------------------------------------------------------------------
class ContextoService:
    """Enriquecimiento ordinario de las dimensiones contextuales."""

    __slots__ = ("_unidad", "ultima_traza")

    def __init__(self, unidad: UnidadDeTrabajo) -> None:
        self._unidad = unidad
        self.ultima_traza: Traza | None = None

    def enriquecer(
        self,
        contexto: ContextoOperacion,
        *,
        hecho_id: uuid.UUID,
        row_version_esperada: int,
        datos: DatosContextoHecho,
    ) -> ResultadoContexto:
        """Añade conocimiento contextual que faltaba. Solo altas.

        Replay exacto -> idempotente sin incrementar version; subconjunto o
        diferencia -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION; nuevo ->
        advisory D-080 si hay entidades, root lock con version, validacion,
        alta y auditoria. La version sube UNA vez.
        """
        if datos is None or datos.vacio:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "El enriquecimiento exige al menos una fila contextual.",
            )
        validar_estructura(datos)

        def operacion(sesion: SesionMotor) -> ResultadoContexto:
            owner = repo_hechos.exigir_contexto(sesion)
            estado = repo_hechos.leer_estado(sesion, hecho_id)
            if estado is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El hecho indicado no existe o no es accesible.",
                )
            replay = clasificar_replay(sesion, hecho_id, datos)
            if replay == "REPLICA":
                return ResultadoContexto(
                    hecho_id=hecho_id, hecho_row_version=estado[0], idempotente=True
                )
            if replay == "CONFLICTO":
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "Alguna fila contextual reservada ya existe con otra "
                    "intencion o solo existe una parte del lote.",
                )
            if estado[1] != ESTADO_ACTIVO:
                raise ErrorMotor(
                    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                    "Un hecho anulado no admite enriquecimiento.",
                )
            tomar_advisory_si_entidades(sesion, owner, bool(datos.entidades))
            nueva = repo_hechos.tocar_raiz(sesion, hecho_id, row_version_esperada)
            if nueva is None:
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "El hecho ha cambiado desde la version que conoce el llamante.",
                )
            creados = escribir_contexto(sesion, owner, hecho_id, datos)
            return ResultadoContexto(
                hecho_id=hecho_id,
                hecho_row_version=nueva,
                terceros_creados=creados["terceros"],
                entidades_creadas=creados["entidades"],
                magnitudes_creadas=creados["magnitudes"],
                etiquetas_creadas=creados["etiquetas"],
            )

        resultado = self._unidad.ejecutar_con_traza(
            contexto, operacion, nombre="R3 enriquecer_contexto"
        )
        self.ultima_traza = resultado.traza
        return resultado.valor
