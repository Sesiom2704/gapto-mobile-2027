# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_000_repo_sin_datos_v3.py
# Ruta: tests/migration/test_rv3_000_repo_sin_datos_v3.py
# Descripcion: RV3-E001 §2. Guarda del repositorio: ningun fichero que vaya a
#              versionarse puede contener datos V3 reales, datasets, dumps,
#              secretos, cadenas de conexion con credenciales ni rutas locales
#              absolutas.
#
#   Funciona en dos modos:
#     - con .git: revisa exactamente lo que se versionaria
#       (git ls-files --cached --others --exclude-standard);
#     - sin .git (copia ZIP de main, subida por la web de GitHub): recorre el
#       arbol completo. La web de GitHub NO respeta .gitignore, por eso en este
#       modo cualquier fichero dentro de data/migration_v3/ distinto de
#       .gitkeep es fallo: los datos V3 reales deben vivir fuera del
#       repositorio (GAPTO_RV3_DATA_DIR).
#
#   No necesita base de datos. Se ejecuta con:
#       python -m pytest tests/migration/test_rv3_000_repo_sin_datos_v3.py -q
#
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]

EXTENSIONES_PROHIBIDAS = {
    ".xlsx", ".xlsm", ".xls", ".ods", ".jsonl", ".parquet", ".dump", ".backup",
    ".bak", ".sqlite", ".sqlite3", ".db", ".pem", ".key", ".p12", ".pfx",
}
NOMBRES_PROHIBIDOS = re.compile(r"(Base_Datos_Personal_py|GaptoMobile_2027_DB|RUN0[0-9]|\.env$)", re.I)
PERMITIDOS_NOMBRE = {".env.example"}

IGNORAR_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                ".venv", "venv", "node_modules", ".expo"}

PATRONES_TEXTO = {
    "cadena_conexion_con_credenciales": re.compile(r"postgres(?:ql)?://[^\s:/@'\"]+:[^\s@'\"]+@", re.I),
    "ruta_absoluta_windows": re.compile(r"\b[A-Za-z]:\\(?:Users|DEV|Documents)\\", re.I),
    "ruta_absoluta_posix": re.compile(r"(?<![\w.])/(?:home|Users|mnt/user-data)/[A-Za-z0-9_]"),
    "url_firmada": re.compile(r"[?&](?:X-Amz-Signature|X-Goog-Signature|sig)=[A-Za-z0-9%]{16,}"),
}
EXTENSIONES_TEXTO = {".py", ".sql", ".ps1", ".md", ".txt", ".json", ".toml", ".cfg", ".ini",
                     ".yml", ".yaml", ".ts", ".tsx", ".js", ".csv", ""}

ESTE_FICHERO = Path(__file__).resolve()


def _ficheros_versionables() -> tuple[str, list[Path]]:
    if (RAIZ / ".git").exists():
        try:
            out = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                cwd=RAIZ, capture_output=True, check=True,
            ).stdout.decode("utf-8")
            return "git", [RAIZ / p for p in out.split("\0") if p]
        except (OSError, subprocess.CalledProcessError):
            pass
    ficheros = []
    for p in RAIZ.rglob("*"):
        if p.is_file() and not (set(p.relative_to(RAIZ).parts) & IGNORAR_DIRS):
            ficheros.append(p)
    return "arbol", ficheros


MODO, FICHEROS = _ficheros_versionables()


def _rel(p: Path) -> str:
    return p.relative_to(RAIZ).as_posix()


def test_hay_ficheros_que_revisar():
    assert len(FICHEROS) > 50, f"modo={MODO}: la guarda no ha encontrado el arbol del repositorio"


def test_data_migration_v3_solo_contiene_placeholders():
    malos = [_rel(p) for p in FICHEROS
             if _rel(p).startswith("data/migration_v3/") and p.name != ".gitkeep"]
    assert not malos, (
        "Datos dentro de data/migration_v3/ (la web de GitHub no respeta .gitignore; "
        f"muevelos a GAPTO_RV3_DATA_DIR fuera del repo): {malos}")


def test_sin_extensiones_de_datos_ni_claves():
    malos = [_rel(p) for p in FICHEROS if p.suffix.lower() in EXTENSIONES_PROHIBIDAS]
    assert not malos, f"Ficheros de datos/dumps/claves en el repositorio: {malos}"


def test_sin_artefactos_v3_por_nombre():
    malos = [_rel(p) for p in FICHEROS
             if p.name not in PERMITIDOS_NOMBRE and NOMBRES_PROHIBIDOS.search(p.name)]
    assert not malos, f"Artefactos V3/RUN o .env en el repositorio: {malos}"


@pytest.mark.parametrize("nombre", sorted(PATRONES_TEXTO))
def test_sin_secretos_ni_rutas_locales_en_texto(nombre):
    patron = PATRONES_TEXTO[nombre]
    malos = []
    for p in FICHEROS:
        if p.resolve() == ESTE_FICHERO or p.suffix.lower() not in EXTENSIONES_TEXTO:
            continue
        try:
            if p.stat().st_size > 2_000_000:
                continue
            texto = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if patron.search(texto):
            malos.append(_rel(p))
    assert not malos, f"{nombre} encontrado en: {malos}"


def test_la_guarda_detecta_lo_que_dice_detectar():
    # Discriminante (WM §12C.2): cada patron debe disparar con un ejemplo sintetico.
    ejemplos = {
        "cadena_conexion_con_credenciales": "postgresql://usuario:clave@host/db",
        "ruta_absoluta_windows": r"C:\DEV\gapto-mobile-2027-main\x",
        "ruta_absoluta_posix": "leer /home/alguien/fichero",
        "url_firmada": "https://x/y?X-Goog-Signature=0123456789abcdef0123",
    }
    for nombre, texto in ejemplos.items():
        assert PATRONES_TEXTO[nombre].search(texto), nombre
    assert NOMBRES_PROHIBIDOS.search("GaptoMobile_2027_DB_RUN06_v08.xlsx")
    assert NOMBRES_PROHIBIDOS.search("Base_Datos_Personal_py.xlsx")
    assert ".xlsx" in EXTENSIONES_PROHIBIDAS
