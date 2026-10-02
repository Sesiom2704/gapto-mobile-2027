# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/magnitudes/lecturas.py
# Descripcion: Lectura del catalogo de magnitudes del owner (F05-D020,
#   AJ-S7MAG-08; GET /v1/magnitudes). Solo lectura, bajo gapto_runtime y RLS.
#   - TODAS las magnitudes del owner: activas, deshabilitadas y sin
#     asociaciones, ordenadas por nombre e id.
#   - `categorias`: asociaciones de la magnitud con su categoria (id, nombre,
#     obligatoria, categoria_enabled), por nombre de categoria e id.
#   - `n_hechos`: count(hecho_magnitudes) por magnitud bajo RLS: registros
#     historicos, contador DIFERENCIADO del de categorias asociadas.
#     hecho_magnitudes no referencia la asociacion (CE-S7MAG-06): el recuento
#     es de la magnitud, nunca se atribuye a una asociacion.
#   Sin N+1: una consulta por coleccion (magnitudes, asociaciones, recuentos).
#   Nunca es autoridad de persistencia; sin locks.
# Version: 0.1.0 (F05-01 S7-MAG)
# ============================================================

from __future__ import annotations

from typing import Any

from app.core.unidad_trabajo import SesionMotor


def catalogo(sesion: SesionMotor) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, nombre, unidad_default, precision_decimales, enabled, row_version FROM gapto.magnitudes "
            "WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid ORDER BY nombre, id"
        )
        magnitudes = cur.fetchall()
        cur.execute(
            "SELECT cm.magnitud_id, c.id, c.nombre, cm.obligatoria, c.enabled FROM gapto.categoria_magnitudes cm "
            "JOIN gapto.categorias_financieras c ON c.id = cm.categoria_id "
            "WHERE c.owner_user_id = current_setting('gapto.owner_user_id')::uuid ORDER BY c.nombre, c.id"
        )
        asociadas = cur.fetchall()
        cur.execute(
            "SELECT hm.magnitud_id, count(*) FROM gapto.hecho_magnitudes hm "
            "JOIN gapto.magnitudes m ON m.id = hm.magnitud_id "
            "WHERE m.owner_user_id = current_setting('gapto.owner_user_id')::uuid GROUP BY hm.magnitud_id"
        )
        hechos = {mid: int(n) for mid, n in cur.fetchall()}
    por_magnitud: dict[Any, list[dict[str, Any]]] = {}
    for mid, cid, nombre, obligatoria, enabled in asociadas:
        por_magnitud.setdefault(mid, []).append(
            {"categoria_id": cid, "nombre": nombre, "obligatoria": obligatoria, "categoria_enabled": enabled})
    return [
        {"id": mid, "nombre": nombre, "unidad_default": unidad, "precision_decimales": precision,
         "enabled": enabled, "row_version": version, "categorias": por_magnitud.get(mid, []),
         "n_hechos": hechos.get(mid, 0)}
        for mid, nombre, unidad, precision, enabled, version in magnitudes
    ]
