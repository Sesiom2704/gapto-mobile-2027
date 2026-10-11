# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/afinidades/lecturas.py
# Descripcion: Lectura del detalle de afinidades de un tercero (F05 §49.4 A5,
#   A8; lamina C1). Solo lectura, sin locks, gapto_runtime con RLS.
#   - `guardadas`: afinidades explicitas del tercero con su ruta y
#     `disponible` = categoria habilitada (si no, «No disponible» y no se
#     sugiere, caso 4).
#   - `segun_historial`: uso del tercero por categoria en la ventana de las
#     senales (backend/app/senales), EXCLUYENDO las guardadas, con «N de tus
#     M gastos». Se calcula, no se guarda (R5).
#   Un tercero no visible (otro owner o inexistente) -> None (404 en la ruta).
# Version: 0.1.0 (F05-05 K2 §1.3)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.comun.rutas_categoria import catalogo, clave_orden, ruta_texto
from app.core.unidad_trabajo import SesionMotor
from app.senales import lecturas as senales


def detalle(sesion: SesionMotor, tercero_id: uuid.UUID, tipo: str, fecha: dt.date) -> dict[str, Any] | None:
    if not senales.tercero_visible(sesion, tercero_id):
        return None
    nodos = catalogo(sesion)
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT id, categoria_id FROM gapto.tercero_afinidades WHERE tercero_id = %s", (tercero_id,))
        filas = cur.fetchall()
    guardadas = sorted(
        ({"id": aid, "categoria_id": cid, "nombre": nodos[cid]["nombre"], "ruta": ruta_texto(nodos[cid]),
          "disponible": bool(nodos[cid]["enabled"])} for aid, cid in filas),
        key=lambda g: clave_orden(nodos[g["categoria_id"]]))
    ya = {g["categoria_id"] for g in guardadas}
    historial, total = senales.historial_tercero(sesion, tipo, tercero_id, fecha)
    segun = [{"categoria_id": h["categoria_id"], "nombre": h["nombre"], "ruta": h["ruta"], "usos": h["usos"]}
             for h in historial if h["categoria_id"] not in ya]
    return {"tercero_id": tercero_id, "tipo": tipo, "guardadas": guardadas, "segun_historial": segun,
            "total_registros": total}
