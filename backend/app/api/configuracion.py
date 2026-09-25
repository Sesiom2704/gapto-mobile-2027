# ============================================================
# GAPTO MOBILE 2027
# Fichero: configuracion.py
# Ruta: backend/app/api/configuracion.py
# Descripcion: Configuracion del adaptador HTTP F05-00-B e IDENTIDAD DE
#   DESARROLLO.
#
#   *** NO ES AUTENTICACION DE PRODUCCION ***
#
#   Deuda registrada: F10-01 — sustituir identidad de desarrollo por
#   autenticacion y resolucion autoritativa de tenant/actor.
#
#   Reglas (mandato F05-00-B v0.2 §4):
#     - el cliente NUNCA envia tenant, owner ni actor autoritativos: el owner
#       sale de GAPTO_DEV_OWNER_USER_ID y el actor self se resuelve en BD;
#     - fail-closed fuera de GAPTO_ENV=development;
#     - token estatico solo por entorno (nunca versionado), longitud minima;
#     - la base conectada debe figurar en una lista blanca de bases de
#       desarrollo (por defecto solo `gapto2027_dev`), para impedir apuntar
#       por error a una base de referencia (Neon gapto2027_test) o a Supabase;
#     - datos exclusivamente sinteticos (los crea scripts/dev).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

AVISO_IDENTIDAD = "NO ES AUTENTICACION DE PRODUCCION"
ENTORNO_UNICO_PERMITIDO = "development"
LONGITUD_MINIMA_TOKEN = 24
BASES_DEV_POR_DEFECTO = ("gapto2027_dev",)


class ConfiguracionInvalida(RuntimeError):
    """Arranque rechazado: el adaptador no se levanta en estado dudoso."""


@dataclass(frozen=True, slots=True)
class ConfiguracionApi:
    entorno: str
    dsn: str
    owner_user_id: uuid.UUID
    token_desarrollo: str
    rol_runtime: str | None
    bases_permitidas: tuple[str, ...]

    def __repr__(self) -> str:  # no filtrar DSN ni token en logs
        return (
            f"ConfiguracionApi(entorno={self.entorno!r}, "
            f"bases_permitidas={self.bases_permitidas!r}, dsn=<oculto>, token=<oculto>)"
        )


def cargar_desde_entorno(env: dict[str, str] | None = None) -> ConfiguracionApi:
    e = dict(os.environ if env is None else env)

    entorno = e.get("GAPTO_ENV", "")
    if entorno != ENTORNO_UNICO_PERMITIDO:
        raise ConfiguracionInvalida(
            "El adaptador F05-00-B solo arranca con GAPTO_ENV=development "
            f"({AVISO_IDENTIDAD})."
        )

    dsn = e.get("GAPTO_DATABASE_URL", "")
    if not dsn:
        raise ConfiguracionInvalida("Falta GAPTO_DATABASE_URL.")

    try:
        owner = uuid.UUID(e.get("GAPTO_DEV_OWNER_USER_ID", ""))
    except ValueError as exc:
        raise ConfiguracionInvalida("GAPTO_DEV_OWNER_USER_ID ausente o no es UUID.") from exc

    token = e.get("GAPTO_DEV_TOKEN", "")
    if len(token) < LONGITUD_MINIMA_TOKEN:
        raise ConfiguracionInvalida(
            f"GAPTO_DEV_TOKEN ausente o menor de {LONGITUD_MINIMA_TOKEN} caracteres."
        )

    rol = e.get("GAPTO_DB_RUNTIME_ROLE", "gapto_runtime") or None
    bases = tuple(
        b.strip()
        for b in e.get("GAPTO_DEV_DB_ALLOWLIST", ",".join(BASES_DEV_POR_DEFECTO)).split(",")
        if b.strip()
    )
    if not bases:
        raise ConfiguracionInvalida("GAPTO_DEV_DB_ALLOWLIST vacia.")

    return ConfiguracionApi(
        entorno=entorno,
        dsn=dsn,
        owner_user_id=owner,
        token_desarrollo=token,
        rol_runtime=rol,
        bases_permitidas=bases,
    )


def verificar_base_permitida(nombre_base: str, cfg: ConfiguracionApi) -> None:
    if nombre_base not in cfg.bases_permitidas:
        raise ConfiguracionInvalida(
            f"La base conectada '{nombre_base}' no esta en la lista blanca de "
            "desarrollo; el adaptador no arranca."
        )
