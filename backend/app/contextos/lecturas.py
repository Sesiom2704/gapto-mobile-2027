# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/contextos/lecturas.py
# Descripcion: Lecturas de contextos para el registro y Ajustes › Contextos
#   (F05-04 J2 §1.4/§1.9; lamina SET-CTX v0.1 S03). Solo lectura, sin locks,
#   RLS del tenant. `listar`: todos los contextos del owner (activos e
#   inactivos) en orden estable (nombre normalizado, id).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.4)
# ============================================================

from __future__ import annotations

from typing import Any

from app.categorias.normalizacion import normalizar
from app.contextos import repositorio as repo
from app.core.unidad_trabajo import SesionMotor


def listar(sesion: SesionMotor) -> list[dict[str, Any]]:
    return sorted(repo.todos(sesion), key=lambda x: (normalizar(x["nombre"]), str(x["id"])))
