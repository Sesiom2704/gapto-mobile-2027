# ============================================================
# GAPTO MOBILE 2027
# Fichero: __init__.py
# Ruta: backend/app/magnitudes/__init__.py
# Descripcion: Paquete propietario de F05-01 S7-MAG (F05-D020, expediente F05
#   §34) para la parametrizacion de magnitudes por categoria: catalogo de
#   magnitudes del owner y sus asociaciones con categorias. Vive FUERA de
#   backend/app/services (motor F04 certificado), igual que
#   backend/app/categorias. Reutiliza UnidadDeTrabajo, el advisory y la
#   lectura bloqueante de categorias (categorias/repositorio.py), la
#   normalizacion de C06 (categorias/normalizacion.py) y el repositorio de
#   auditoria, sin modificarlos. Sus codigos de error son de la capa F05.
#   API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10 (F10-03/04).
# Version: 0.1.0 (F05-01 S7-MAG)
# ============================================================
