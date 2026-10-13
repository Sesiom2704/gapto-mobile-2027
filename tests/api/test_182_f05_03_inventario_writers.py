# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_182_f05_03_inventario_writers.py
# Ruta: tests/api/test_182_f05_03_inventario_writers.py
# Descripcion: Inventario FAIL-CLOSED de escritores de las tablas de F05-03 /
#   F05-04 (J2 §1.10; F05 §45.4 R3, §46.3 A7; F05-D032 C2, D-032.2). Test
#   estatico, sin base de datos. Registro CERRADO por tabla y operacion en el
#   codigo productivo (backend/ y scripts/, sin los arneses de mutacion):
#     plantillas_registro, acciones_rapidas -> plantillas/repositorio.py
#       (INSERT, UPDATE); terceros -> terceros/repositorio.py (INSERT,
#       UPDATE); entidades y contextos -> en la capa F05 SOLO
#       contextos/repositorio.py (INSERT, UPDATE; los writers F04 de
#       entidades no son F05 y quedan fuera de este registro);
#       cuenta_capacidades -> CERO writers runtime (solo los SEED_DEV de la
#       semilla, del E2E de preferencias y del script versionado de ENV-DEV);
#       hecho_terceros / hecho_entidades -> la capa F05 nunca los escribe
#       directamente (solo via OP-22).
#   DELETE/TRUNCATE de esas tablas: CERO en todo el codigo productivo F05.
#   Cada comando publico de los servicios de terceros, contextos y
#   plantillas toma su advisory como PRIMERA llamada (C2). Ningun writer F05
#   usa SET ROLE, roles privilegiados ni SECURITY DEFINER (D-032.2).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.10)
# Version: 0.2.0 (F05-03/F05-04 J2+J3 §2.8): el E2E e2e_j2j3.py da de alta las capacidades
#   sinteticas de sus cuentas (base LOCAL desechable), como e2e_preferencias.py.
# Version: 0.3.0 (F05-05 K2 §1.3; F05 §49.4 A5, §49.5 R9): alta aditiva. tercero_afinidades ->
# Version: 0.4.0 (F05-05 K3 §3): EXCLUIDOS incluye el arnes mutantes_f05_05.py (los mutantes son texto).
#   SOLO afinidades/repositorio.py (INSERT, DELETE: quitar una afinidad es borrarla; no hay
#   enabled). terceros sigue con su unico escritor (terceros/repositorio.py): el writer de
#   afinidades sube row_version por `incrementar_version`. Los comandos alta/baja de
#   afinidades/servicio.py toman el advisory primero; afinidades/ y senales/ entran en la
#   capa F05 (sin roles privilegiados).
# Version: 0.5.0 (F05-06 M4; F05-D037, F05 §51.2; adenda LANZAMIENTO_M4_CORR-F4-ENVDEV
#   §1.3/§1.4, aprobada por Moises el 2026-10-13): la garantia «cuenta_capacidades ->
#   CERO writers runtime» era la foto del inventario de J2, cuando la escritura de
#   capacidades era deuda (DEU-F05-CAPACIDADES-UI) asignada a F05-06. F05-D037 aprueba
#   «writer de cuenta_capacidades ... un unico servicio»: la garantia pasa a ser «el
#   UNICO writer runtime de cuenta_capacidades es backend/app/capacidades/servicio.py»
#   (INSERT y DELETE; nunca UPDATE). Falla si cualquier otro fichero de backend/ escribe
#   en la tabla. Registro: alta del servicio y del fixture E2E e2e_f05_06_m4.py (DELETE
#   de las capacidades sinteticas de sus cuentas, base LOCAL desechable); capacidades/
#   entra en la capa F05 (sin roles privilegiados). EXCLUIDOS incluye el arnes
#   mutantes_f05_06_m4.py (los mutantes son texto).
# ============================================================

from __future__ import annotations

import ast
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[2]
EXCLUIDOS = {"scripts/dev/mutantes_f05_01.py", "scripts/dev/mutantes_f05_02.py", "scripts/dev/mutantes_f05_j2j3.py",
             "scripts/dev/mutantes_vs01.py", "scripts/dev/mutantes_cierre_f05_02.py",
             "scripts/dev/mutantes_f05_05.py", "scripts/dev/mutantes_f05_06_m4.py"}
CAPA_F05 = ("backend/app/api/", "backend/app/comun/", "backend/app/terceros/", "backend/app/contextos/",
            "backend/app/plantillas/", "backend/app/preferencias/", "backend/app/categorias/",
            "backend/app/magnitudes/")


def _escritura(tabla: str) -> re.Pattern:
    return re.compile(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE(\s+TABLE)?)\s+(ONLY\s+)?"
                      r"(gapto\s*\.\s*)?\"?" + tabla + r"\b", re.IGNORECASE)


def _rel(p: pathlib.Path) -> str:
    return p.relative_to(RAIZ).as_posix()


def _productivo():
    for raiz in ("backend", "scripts"):
        for p in sorted((RAIZ / raiz).rglob("*.py")):
            if _rel(p) not in EXCLUIDOS:
                yield p


def _escritores(tabla: str, solo_f05: bool = False) -> dict[str, set[str]]:
    patron = _escritura(tabla)
    salida: dict[str, set[str]] = {}
    for p in _productivo():
        ruta = _rel(p)
        if solo_f05 and not ruta.startswith(CAPA_F05):
            continue
        for m in patron.finditer(p.read_bytes().decode("utf-8")):
            salida.setdefault(ruta, set()).add(m.group(1).split()[0].upper())
    return salida


REGISTRO = {
    "plantillas_registro": {"backend/app/plantillas/repositorio.py": {"INSERT", "UPDATE"}},
    "acciones_rapidas": {"backend/app/plantillas/repositorio.py": {"INSERT", "UPDATE"}},
    "terceros": {"backend/app/terceros/repositorio.py": {"INSERT", "UPDATE"}},
    "cuenta_capacidades": {"scripts/dev/bootstrap_dev_db.py": {"INSERT"}, "scripts/dev/e2e_preferencias.py": {"INSERT"},
                           "scripts/dev/e2e_j2j3.py": {"INSERT"},
                           "scripts/envdev/envdev_capacidades_cuenta.py": {"INSERT"},
                           # F05-06 M4 (F05-D037): writer unico runtime y fixture del E2E.
                           "backend/app/capacidades/servicio.py": {"INSERT", "DELETE"},
                           "scripts/dev/e2e_f05_06_m4.py": {"DELETE"}},
}
WRITER_UNICO_CAPACIDADES = "backend/app/capacidades/servicio.py"
#: F05-05 K2 §1.3 (alta aditiva).
REGISTRO["tercero_afinidades"] = {"backend/app/afinidades/repositorio.py": {"INSERT", "DELETE"}}
CAPA_F05 = CAPA_F05 + ("backend/app/afinidades/", "backend/app/senales/")
CAPA_F05 = CAPA_F05 + ("backend/app/capacidades/",)  # F05-06 M4
REGISTRO_F05 = {
    "entidades": {"backend/app/contextos/repositorio.py": {"INSERT", "UPDATE"}},
    "contextos": {"backend/app/contextos/repositorio.py": {"INSERT", "UPDATE"}},
    "hecho_terceros": {},
    "hecho_entidades": {},
}


def test_escritores_registro_cerrado():
    for tabla, esperado in REGISTRO.items():
        assert _escritores(tabla) == esperado, tabla


def test_escritores_en_la_capa_f05_registro_cerrado():
    for tabla, esperado in REGISTRO_F05.items():
        assert _escritores(tabla, solo_f05=True) == esperado, tabla


def test_cuenta_capacidades_unico_writer_runtime():
    """F05-D037: el UNICO writer runtime de cuenta_capacidades es el servicio de
    capacidades. Cualquier otro fichero de backend/ que escriba en la tabla falla."""
    runtime = {r: ops for r, ops in _escritores("cuenta_capacidades").items() if r.startswith("backend/")}
    assert runtime == {WRITER_UNICO_CAPACIDADES: {"INSERT", "DELETE"}}, runtime


def test_comandos_toman_su_advisory_primero():
    for ruta, comandos in {
        "backend/app/terceros/servicio.py": ("alta", "editar", "desactivar", "reactivar"),
        "backend/app/contextos/servicio.py": ("alta", "editar", "desactivar", "reactivar"),
        "backend/app/plantillas/servicio.py": ("alta", "editar", "desactivar", "reactivar", "alta_accion",
                                               "editar_accion", "desactivar_accion", "reordenar_acciones"),
        "backend/app/afinidades/servicio.py": ("alta", "baja"),  # F05-05 K2 §1.3
    }.items():
        arbol = ast.parse((RAIZ / ruta).read_bytes().decode("utf-8"))
        funciones = {n.name: n for n in arbol.body if isinstance(n, ast.FunctionDef)}
        publicas = {n for n in funciones if not n.startswith("_")}
        assert publicas == set(comandos), (ruta, sorted(publicas))
        for nombre in comandos:
            cuerpo = funciones[nombre].body
            if isinstance(cuerpo[0], ast.Expr) and isinstance(cuerpo[0].value, ast.Constant):
                cuerpo = cuerpo[1:]
            primera = cuerpo[0]
            assert isinstance(primera, ast.Expr) and isinstance(primera.value, ast.Call) \
                and ast.unparse(primera.value.func) == "repo.tomar_advisory", (ruta, nombre)


def test_sin_roles_privilegiados_ni_security_definer_en_la_capa_f05():
    prohibido = re.compile(r"SET\s+(LOCAL\s+)?ROLE|SECURITY\s+DEFINER|gapto_owner|gapto_internal|gapto_migrator",
                           re.IGNORECASE)
    for p in _productivo():
        ruta = _rel(p)
        if not ruta.startswith(CAPA_F05):
            continue
        codigo = "\n".join(linea for linea in p.read_bytes().decode("utf-8").splitlines()
                           if not linea.lstrip().startswith("#"))
        assert not prohibido.search(codigo), ruta
