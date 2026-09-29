# ============================================================
# GAPTO MOBILE 2027
# Fichero: iconos.py
# Ruta: backend/app/categorias/iconos.py
# Descripcion: Biblioteca de iconos de categoria v1 (F05-D013 §27.2; F09
#   §12.97.9, PUBLICADA, version 1). El backend es la autoridad de la
#   biblioteca (Q4); la app mantiene una copia con test cruzado.
#
#   - Solo CLAVES semanticas: ni etiquetas ni glifos (AJ-ICON-08; la
#     presentacion es de la app). El icono de reserva
#     (`categoriaIconoFallback` / `pricetag-outline`) NO es clave: no esta
#     aqui y nunca se persiste.
#   - PUBLICADAS = todas las que alguna version ha publicado; ACTIVAS = las que
#     ofrece el selector vigente (AJ-ICON-01). En escritura se acepta cualquier
#     clave publicada. En v1 ambos conjuntos coinciden.
#   - Validacion exacta (AJ-ICON-03): pertenencia literal al conjunto
#     publicado, sin recorte, sin cambio de mayusculas y sin alias.
#   Sin SQL: modulo puro (inventario C-b, test_154).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

ICONOS_CATEGORIA_VERSION = 1

#: Formato y longitud de una clave (coherencia interna; la autoridad es la
#: pertenencia a CLAVES_PUBLICADAS). La longitud es la de varchar(80) de 0340.
PATRON = r"^[a-z]+\.[a-z_]+$"
LONGITUD_MAXIMA = 80

CLAVES_PUBLICADAS: frozenset[str] = frozenset({
    "compras.carrito", "compras.cesta", "compras.ropa",
    "comida.restaurante", "comida.cafe",
    "hogar.casa", "hogar.luz", "hogar.agua", "hogar.gas", "hogar.internet", "hogar.reparaciones",
    "transporte.coche", "transporte.bus", "transporte.avion", "transporte.viaje",
    "salud.corazon", "salud.farmacia", "salud.deporte",
    "personal.peluqueria", "personal.mascota", "personal.educacion", "personal.movil",
    "ocio.regalo", "ocio.libro", "ocio.musica", "ocio.cine",
    "finanzas.dinero", "finanzas.impuestos", "finanzas.seguro", "finanzas.suscripcion",
})

#: v1: todas las publicadas estan activas.
CLAVES_ACTIVAS: frozenset[str] = CLAVES_PUBLICADAS


def icono_valido(icon_key: str | None) -> bool:
    """None (sin icono) es valido; una clave lo es solo si pertenece, tal
    cual, al conjunto publicado (AJ-ICON-03/05)."""
    if icon_key is None:
        return True
    return icon_key in CLAVES_PUBLICADAS
