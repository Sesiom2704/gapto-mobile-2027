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
#     - llamante de escritura: se invoca para una intencion nueva, DESPUES del
#       reconocimiento de identidad y ANTES de componer/ejecutar OP-22: un
#       reintento de una intencion ya materializada no revalida la categoria;
#     - llamante de lectura (F05-D028 §43.4, AJ-B2-01):
#       preferencias/lecturas.py::propuesta, para que la propuesta del registro
#       nunca acepte una categoria que la intencion rechazaria (§42.7). Abre su
#       propia transaccion corta de lectura: FOR SHARE de la categoria (unico
#       lock de fila, sin advisory) -> lecturas sin lock del resolver -> COMMIT.
#       Orden de locks: categoria -> nada; no puede formar ciclo con los
#       writers de CATEGORIAS ni de PREFERENCIAS;
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
#   Los codigos son de la capa F05 y NO forman parte de la taxonomia F04
#   (core/errores.py no se modifica).
#
#   v0.2.0 (F05-01, S6-C07; F05-D014 §28.2): se RETIRA el bloqueo transitorio
#   CATEGORIA_REQUIERE_MAGNITUDES. La guarda vuelve a decidir solo la
#   elegibilidad C02 (owner, `enabled`, `ambito`); las magnitudes las decide
#   C07 (captura_magnitudes.py), que se ejecuta despues de esta guarda y bajo
#   el mismo FOR SHARE de la categoria.
#
#   v0.2.1 (F05-02 B3, AJ-B2-01; F05-D028 §43.4): SOLO cabecera. Registra el
#   segundo llamante, de lectura (propuesta de preferencias), y su orden de
#   locks. El cuerpo de la guarda no cambia.
#
#   v0.3.0 (F06 T2-F06 CAT-VIV N1; L-04, OBL-VIV-01 de AJ-T2 §2.1; Q-CV-06, Q-CV-07, Q-CV-11): funcion UNICA
#   `exigir_propiedad(sesion, categoria_id, tipo_efecto, propiedad_id)`. Todo writer que cree un hecho REAL con
#   efecto GASTO y categoria la llama DESPUES de la identidad y ANTES de componer, en su transaccion; lee
#   `asociada_vivienda` (0353) bajo el MISMO `FOR SHARE` de la fila que toma C-a: decide la marca del momento
#   del registro, nunca la que mostro la UI. Categoria marcada y sin propiedad -> CATEGORIA_EXIGE_PROPIEDAD
#   (422, sin escritura). Solo GASTO (Q-CV-11): un INGRESO, aunque su categoria sea AMBOS, no queda sujeto. Sin
#   exenciones: no hay parametro, bandera ni ruta que la apague (OBL-VIV-01.5). La comprobacion de que la
#   propiedad existe, es del owner y no es DE_OTROS es del writer (bloque `propiedad`), bajo su propio lock.
#   Inventario discriminante: tests/api/test_280_f06_t2_cat_viv_inventario.py. `validar_seleccion_categoria`
#   no cambia.
# Version: 0.3.0
# ============================================================

from __future__ import annotations

import uuid

from app.core.unidad_trabajo import SesionMotor

CODIGO_CATEGORIA_NO_ELEGIBLE = "CATEGORIA_NO_ELEGIBLE"
#: T2-F06 CAT-VIV (OBL-VIV-01.2): gasto real de categoria «Asociada a vivienda» sin propiedad.
CODIGO_EXIGE_PROPIEDAD = "CATEGORIA_EXIGE_PROPIEDAD"

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


def exigir_propiedad(sesion: SesionMotor, categoria_id: uuid.UUID | None, tipo_efecto: str,
                     propiedad_id: uuid.UUID | None) -> str | None:
    """OBL-VIV-01. None si se admite; CATEGORIA_EXIGE_PROPIEDAD si la categoria del GASTO esta marcada y no
    hay propiedad. No escribe. Bajo el FOR SHARE de la fila de la categoria (el mismo de C-a)."""
    if tipo_efecto != "GASTO" or categoria_id is None:
        return None
    fila = sesion.uno(
        "SELECT asociada_vivienda FROM gapto.categorias_financieras WHERE id = %s "
        "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR SHARE",
        (categoria_id,),
    )
    if fila is not None and fila[0] and propiedad_id is None:
        return CODIGO_EXIGE_PROPIEDAD
    return None


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
    return None
