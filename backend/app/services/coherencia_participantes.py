# ============================================================
# GAPTO MOBILE 2027
# Fichero: coherencia_participantes.py
# Ruta: backend/app/services/coherencia_participantes.py
# Descripcion: Guarda compartida del recuento de participantes (F04-D038 §10).
#
#   CONTRATO. Si `hechos_financieros.numero_participantes_total` esta
#   informado, debe ser mayor o igual que el numero de PERSONAS distintas
#   identificadas en `hecho_participantes`. Roles multiples del mismo actor
#   cuentan una sola persona.
#
#   `numero_participantes_total = NULL` es valido aunque existan identificados:
#   NULL significa que el total global no se conoce, no que sea cero. Un hecho
#   con ocho comensales de los que solo dos son actores del sistema es correcto
#   con total 8 y dos filas, y tambien con total NULL y dos filas.
#
#   DOS CAMINOS, UNA GUARDA. La incoherencia se puede alcanzar por los dos
#   extremos: subiendo identificados o bajando el total. Por eso la evaluan
#   tanto el writer de participantes como OP-02 cuando corrige el total, y por
#   eso ambos llaman aqui en vez de escribir dos comprobaciones que podrian
#   divergir.
#
#   SIEMPRE SOBRE EL ESTADO FINAL. Se evalua despues de aplicar los cambios y
#   con la raiz ya bloqueada: comprobar antes dejaria la ventana entre lectura
#   y escritura, y esa ventana es justo donde vive la carrera I1 (dos actores
#   distintos anadidos a la vez contra un total limitado).
#
#   NO SE FABRICA NADA. Si el total declarado es mayor que los identificados,
#   la diferencia son personas reales que el sistema no conoce. No se crean
#   participantes anonimos para cuadrar, ni se ajusta el total al recuento.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid

from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_trabajo import SesionMotor
from app.repositories import participantes_repository as repo_part


def exigir_recuento_coherente(sesion: SesionMotor, *, hecho_id: uuid.UUID) -> None:
    """Verifica `numero_participantes_total >= personas identificadas`."""
    visible, total = repo_part.total_declarado(sesion, hecho_id)
    if not visible:
        raise ErrorMotor(
            CodigoError.AGREGADO_NO_ENCONTRADO,
            "El hecho indicado no existe o no es accesible.",
        )
    if total is None:
        return
    identificados = repo_part.recuento_identificados(sesion, hecho_id)
    if total < identificados:
        raise ErrorMotor(
            CodigoError.PARTICIPANTES_INCONSISTENTES,
            f"El hecho declara {total} participante(s) en total y ya tiene "
            f"{identificados} persona(s) identificada(s). El total no puede "
            "ser menor que lo ya conocido: o el total es falso, o sobra algun "
            "participante.",
        )
