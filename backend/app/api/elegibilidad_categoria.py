# ============================================================
# GAPTO MOBILE 2027
# Fichero: elegibilidad_categoria.py
# Ruta: backend/app/api/elegibilidad_categoria.py
# Descripcion: Guarda UNICA de elegibilidad categorial de la frontera F05
#   (F05-D009 §23.3 C-a; F05-D008 C02/C04). API DE INTEGRACION F05,
#   PENDIENTE DE CONSOLIDACION F10.
#
#   Es el unico componente autorizado a decidir si una SELECCION NUEVA de
#   categoria puede persistirse. El motor F04 no valida `enabled` ni `ambito`
#   (precheck H2) y no debe hacerlo: `enabled` es selectabilidad futura
#   (D-198) y una referencia historica a una categoria hoy deshabilitada sigue
#   siendo valida (OP-13 por D-194, OP-21 por C04).
#
#   Contrato de uso (lo verifica el inventario C-b):
#     - se invoca SOLO para una intencion nueva, DESPUES del reconocimiento de
#       identidad y ANTES de componer/ejecutar OP-22: un reintento de una
#       intencion ya materializada no revalida la categoria;
#     - toma `FOR SHARE` sobre la fila de la categoria y relee dentro de la
#       transaccion owner, `enabled` y `ambito` (C04). Nunca valida el estado
#       que mostro la UI;
#     - NO toma el advisory (CATEGORIAS, owner): el registro no serializa el
#       catalogo (C04);
#     - no escribe nada: un rechazo se devuelve antes de cualquier escritura.
#
#   Matriz C02 precisada por F05-D009 §23.2 (literal):
#     GASTO   -> ambito GASTO o AMBOS
#     INGRESO -> ambito INGRESO o AMBOS
#     DEUDA, DERECHO_COBRO, INVERSION, VALOR_ACTIVO -> solo categoria NULL
#   AMBOS significa GASTO e INGRESO, nunca "cualquier naturaleza".
#
#   Bloqueo TRANSITORIO de magnitudes (mandato F05-01 backend v0.2, AJ-02):
#   si la categoria tiene alguna `categoria_magnitudes.obligatoria = true`, el
#   wire actual no puede materializarlas y la seleccion falla cerrado con
#   CATEGORIA_REQUIERE_MAGNITUDES. NO es la implementacion de C07; F05-01 no
#   es cerrable mientras este bloqueo sustituya a la captura de C07.
#
#   Los codigos son de la capa F05 y NO forman parte de la taxonomia F04
#   (core/errores.py no se modifica).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid

from app.core.unidad_trabajo import SesionMotor

CODIGO_CATEGORIA_NO_ELEGIBLE = "CATEGORIA_NO_ELEGIBLE"
CODIGO_CATEGORIA_REQUIERE_MAGNITUDES = "CATEGORIA_REQUIERE_MAGNITUDES"

#: Matriz C02 (F05-D009 §23.2). Naturaleza -> ambitos admitidos. Una
#: naturaleza con conjunto vacio solo admite categoria NULL.
AMBITOS_ADMITIDOS: dict[str, frozenset[str]] = {
    "GASTO": frozenset({"GASTO", "AMBOS"}),
    "INGRESO": frozenset({"INGRESO", "AMBOS"}),
    "DEUDA": frozenset(),
    "DERECHO_COBRO": frozenset(),
    "INVERSION": frozenset(),
    "VALOR_ACTIVO": frozenset(),
}


def ambito_compatible(tipo_efecto: str, ambito: str) -> bool:
    """Matriz C02 pura. Una naturaleza desconocida no es compatible."""
    return ambito in AMBITOS_ADMITIDOS.get(tipo_efecto, frozenset())


def validar_seleccion_categoria(
    sesion: SesionMotor, categoria_id: uuid.UUID, tipo_efecto: str
) -> str | None:
    """Guarda C-a. Devuelve None si la seleccion es elegible o el codigo F05
    de rechazo. No escribe. Debe llamarse dentro de la transaccion que va a
    persistir la seleccion, tras reconocer la identidad de la intencion."""
    if not AMBITOS_ADMITIDOS.get(tipo_efecto):
        # Naturaleza sin semantica categorial: ni siquiera se lee la fila.
        return CODIGO_CATEGORIA_NO_ELEGIBLE

    fila = sesion.uno(
        "SELECT owner_user_id, enabled, ambito FROM gapto.categorias_financieras "
        "WHERE id = %s FOR SHARE",
        (categoria_id,),
    )
    # Inexistente u oculta por RLS (otro tenant): mismo codigo, sin revelar
    # si la categoria existe en otro tenant.
    if fila is None:
        return CODIGO_CATEGORIA_NO_ELEGIBLE
    owner = sesion.uno("SELECT current_setting('gapto.owner_user_id')::uuid")
    if owner is None or fila[0] != owner[0]:
        return CODIGO_CATEGORIA_NO_ELEGIBLE
    if not fila[1]:
        return CODIGO_CATEGORIA_NO_ELEGIBLE
    if not ambito_compatible(tipo_efecto, fila[2]):
        return CODIGO_CATEGORIA_NO_ELEGIBLE

    requiere = sesion.uno(
        "SELECT EXISTS (SELECT 1 FROM gapto.categoria_magnitudes "
        "WHERE categoria_id = %s AND obligatoria)",
        (categoria_id,),
    )
    if requiere is not None and requiere[0]:
        return CODIGO_CATEGORIA_REQUIERE_MAGNITUDES
    return None
