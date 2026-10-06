# ============================================================
# GAPTO MOBILE 2027
# Fichero: integridad_posicion.py
# Ruta: backend/app/services/integridad_posicion.py
# Descripcion: F04-D053. Integridad de la posicion generica (DERECHO_COBRO /
#   OBLIGACION_PAGO de `derechos_obligaciones_financieras`).
#
#   B8 · RAIZ DE BLOQUEO. Toda via que crea, corrige, cambia de fecha o anula
#   un delta de posicion serializa lectura, validacion y escritura sobre la
#   fila `entidades` de cada posicion afectada, y adquiere los recursos en un
#   ORDEN GLOBAL UNICO:
#
#     1. advisory (INVERSIONES, owner)  si la operacion escribira algo que
#        D-080 / 0270 validan en el COMMIT (vinculo hecho_entidades,
#        importe_delta o tipo_efecto). D-158: el patron fila -> advisory
#        diferido frente a advisory -> fila es interbloqueo determinista.
#     2. hechos existentes FOR NO KEY UPDATE ORDER BY id (D-171, sin cambios).
#     3. posiciones FOR NO KEY UPDATE ORDER BY id (raiz F04-D053).
#     4. movimientos existentes (lo hace el llamante, despues).
#
#   Las posiciones de un hecho se leen DESPUES de bloquear el hecho: con el
#   hecho bloqueado su conjunto de vinculos no puede cambiar.
# Version: 0.1.0
#   0.1.0 (F04-D053 B1 · P0-1): raiz de bloqueo y orden global.
# ============================================================

from __future__ import annotations

import uuid
from collections.abc import Iterable

from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_trabajo import SesionMotor
from app.repositories import correcciones_repository as repo_corr
from app.repositories import posiciones_repository as repo_pos
from app.repositories import relaciones_repository as repo_rel


def adquirir_raiz(
    sesion: SesionMotor,
    owner: uuid.UUID,
    *,
    hechos: Iterable[uuid.UUID] = (),
    posiciones: Iterable[uuid.UUID] = (),
    advisory: bool = False,
) -> list[uuid.UUID]:
    """Adquiere advisory -> hechos -> posiciones, en ese orden y una sola vez.

    Devuelve las posiciones bloqueadas: las indicadas mas las alimentadas por
    los hechos. Un hecho no visible falla cerrado (AGREGADO_NO_ENCONTRADO),
    igual que en OP-21.
    """
    if advisory:
        repo_corr.tomar_advisory_inversiones(sesion, owner)
    hechos = sorted(set(hechos), key=str)
    if hechos and not repo_rel.bloquear_hechos(sesion, hechos):
        raise ErrorMotor(
            CodigoError.AGREGADO_NO_ENCONTRADO,
            "El hecho indicado no existe o no es accesible.",
        )
    objetivo = set(posiciones)
    for hecho_id in hechos:
        objetivo.update(repo_pos.posiciones_de_hecho(sesion, hecho_id))
    return repo_pos.bloquear_posiciones(sesion, list(objetivo))
