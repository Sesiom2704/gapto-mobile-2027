# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_044_envdev_head_autorizado.py
# Ruta: tests/database/test_044_envdev_head_autorizado.py
# Descripcion: D-197 / revision del P0 de 0340 (hallazgo 1). Verifica sin base
#              de datos que bootstrap_dev_db.py no puede materializar en
#              ENV-DEV una migration posterior al head autorizado solo porque
#              este publicada en main:
#                - el head autorizado vigente es 0340 (D-197); cambiarlo exige
#                  editar este test: es deliberado;
#                - sobre el repositorio real, la cadena termina en 0340 y lo
#                  posterior queda omitido y listado;
#                - cadena incoherente (head ausente, numero duplicado, nombre
#                  fuera de patron) = abortar;
#                - la validacion ocurre ANTES de crear o destruir la base.
#              Discrimina: quitar el techo, poner el techo tras _crear_base o
#              subir la constante sin revision hacen fallar al menos un caso.
# Version: 0.2.0  -- D-197: el head autorizado de ENV-DEV pasa a 0340. Sobre el
#                   repositorio real la cadena debe terminar EXACTAMENTE en 0340;
#                   cualquier migration posterior publicada queda omitida.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_RAIZ = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _RAIZ / "scripts" / "dev" / "bootstrap_dev_db.py"


def _cargar():
    pytest.importorskip("psycopg")
    especificacion = importlib.util.spec_from_file_location("bootstrap_dev_db", _SCRIPT)
    modulo = importlib.util.module_from_spec(especificacion)
    sys.modules["bootstrap_dev_db"] = modulo
    especificacion.loader.exec_module(modulo)
    return modulo


B = _cargar()


def _p(*nombres: str) -> list[pathlib.Path]:
    return [pathlib.Path("migrations") / n for n in nombres]


def test_head_autorizado_vigente_es_0340() -> None:
    assert B.HEAD_AUTORIZADO_ENVDEV == "0340"


def test_repositorio_real_se_corta_en_el_head_autorizado() -> None:
    reales = sorted((_RAIZ / "migrations").glob("0*.sql"))
    a_aplicar, omitidas = B.seleccionar_cadena(reales)
    assert a_aplicar[-1].name.startswith(B.HEAD_AUTORIZADO_ENVDEV + "_")
    assert all(f.name[:4] <= B.HEAD_AUTORIZADO_ENVDEV for f in a_aplicar)
    assert all(f.name[:4] > B.HEAD_AUTORIZADO_ENVDEV for f in omitidas)
    assert len(a_aplicar) + len(omitidas) == len(reales)
    assert a_aplicar[-1].name == "0340_f03_05_categoria_icon_key.sql"


def test_sintetico_omite_lo_posterior() -> None:
    a, o = B.seleccionar_cadena(_p("0001_a.sql", "0330_b.sql", "0340_c.sql", "0350_d.sql"), "0330")
    assert [f.name for f in a] == ["0001_a.sql", "0330_b.sql"]
    assert [f.name for f in o] == ["0340_c.sql", "0350_d.sql"]


@pytest.mark.parametrize("nombres", [
    ("0001_a.sql", "0320_b.sql"),                    # head ausente
    ("0001_a.sql", "0330_b.sql", "0330_c.sql"),      # numero duplicado
    ("0001_a.sql", "0330_b.sql", "0340-c.sql"),      # fuera de patron
], ids=["head_ausente", "duplicado", "fuera_de_patron"])
def test_cadena_incoherente_aborta(nombres) -> None:
    with pytest.raises(SystemExit):
        B.seleccionar_cadena(_p(*nombres), "0330")


def test_valida_antes_de_tocar_la_base(monkeypatch, tmp_path) -> None:
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "0001_a.sql").write_text("SELECT 1;", encoding="utf-8")
    monkeypatch.setattr(B, "RAIZ", tmp_path)

    def _no_debe_llamarse(*_a, **_k):
        raise AssertionError("se intento crear/destruir la base antes de validar la cadena")

    monkeypatch.setattr(B, "_crear_base", _no_debe_llamarse)
    monkeypatch.setattr(sys, "argv", ["bootstrap_dev_db.py", "--admin-dsn", "host=/tmp", "--recrear"])
    with pytest.raises(SystemExit):
        B.main()
