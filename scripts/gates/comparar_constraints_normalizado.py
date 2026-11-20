#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: comparar_constraints_normalizado.py
# Ruta: scripts/gates/comparar_constraints_normalizado.py
# Descripcion: Comparador normalizado de constraints para certificar la vuelta atras de C7 (AJ-T3C-06, R-T3C-06).
#   Compara dos extracciones de constraints (A = referencia, B = observada) POR NOMBRE y, para cada una, informa:
#   presencia (AMBAS / FALTA / SOBRA), igualdad literal de pg_get_constraintdef, igualdad normalizada y clase de
#   diferencia. No se conecta a ninguna base: trabaja sobre ficheros.
#   Normalizacion CERRADA (borrador v0.1 §1.2; mandato MANT v1.0 §2.2). Cualquier otra diferencia es semantica:
#     N1  casts redundantes de los literales de un ARRAY dentro de «<op> ANY (...)» o «<op> ALL (...)», con el
#         MISMO operador y el MISMO cuantificador en los dos lados (ampliacion de la decision 16 de Moises,
#         2026-11-20; antes solo «= ANY»): «(ARRAY['A'::B, ...])::T[]» equivale a «ARRAY[('A'::B)::T, ...]» solo
#         si TODOS los elementos son literales de cadena con el MISMO tipo base B y el cast final es T[] (T
#         aparece en cada elemento de la forma canonica, asi que un T distinto sigue siendo distinto). Solo
#         cambia la colocacion del cast: no reordena, no toca valores, ni el operador ni el cuantificador, que
#         quedan fuera del tramo reescrito.
#     N2  parentesis redundantes alrededor de UN unico operando atomico (identificador, numero o literal),
#         solo si no son los de una llamada ni van seguidos de «.», «(» o «[».
#     N3  espacios en blanco fuera de literales y de identificadores entre comillas.
#   No normaliza nombres de columnas, operadores, orden de elementos, mayusculas ni valores literales. Los
#   atributos (tipo, DEFERRABLE, INITIALLY DEFERRED) se comparan tal cual cuando la extraccion los trae, y
#   ademas forman parte del texto de pg_get_constraintdef («DEFERRABLE INITIALLY DEFERRED», «NOT VALID»).
#   Nunca sustituye una huella D-111: la h2 literal se informa aparte (--huellas, copia literal).
#   Veredicto global: IGUAL_LITERAL / IGUAL_NORMALIZADO (con la regla Nk por constraint) / DIFERENCIA_SEMANTICA.
#   Formatos de entrada admitidos (se detectan solos):
#     - JSON objeto {"gapto.tabla.constraint": "<pg_get_constraintdef>"} (C7 de T2, R-L18-02);
#     - JSON lista de objetos {conname|nombre, tabla?, tipo?, deferrable?, deferred?, definicion|def};
#     - texto «nombre|contype|condeferrable|condeferred|definicion» por linea (8b_referencia_virgen_0354).
# Uso: python scripts/gates/comparar_constraints_normalizado.py --a <referencia> --b <observada>
#        [--huellas <huellas.json>] [--salida <f.json>]
#      rc 0 = IGUAL_LITERAL o IGUAL_NORMALIZADO; rc 1 = DIFERENCIA_SEMANTICA (STOP en C7); rc 2 = error de entrada.
# Version: 1.0.0 (F06 — T3 · MANT N1 del comparador normalizado de constraints h2, AJ-T3C-06; decision 15;
#   N1 con «<op> ANY/ALL» por la decision 16)
# ============================================================
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from itertools import combinations

REGLAS = ("N1", "N2", "N3")

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<lit>'(?:[^']|'')*')
  | (?P<qid>"(?:[^"]|"")*")
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<id>[A-Za-z_][A-Za-z0-9_$]*)
  | (?P<cast>::)
  | (?P<op>[<>=!~+\-*/%^|&#@?]+)
  | (?P<punt>[()\[\],.;])
  | (?P<otro>.)
""", re.X | re.S)

_CABECERA_TXT = re.compile(r"^([A-Za-z_][\w$]*\.[\w$]+\.[\w$]+)\|([a-z])\|([tf])\|([tf])\|(.*)$")

_CUANTIFICADORES = ("ANY", "ALL")

# Palabras tras las que un «(» no es el de una llamada (N2).
_PALABRAS_OPERADOR = {"AND", "OR", "NOT"}


def tokenizar(texto: str) -> list[tuple[str, str]]:
    return [(m.lastgroup, m.group()) for m in _TOKEN.finditer(texto)]


def _sig(toks: list[tuple[str, str]], i: int, paso: int = 1) -> int:
    """Indice del siguiente token significativo (no espacio) desde i (incluido) en la direccion paso; -1 o len si no hay."""
    while 0 <= i < len(toks) and toks[i][0] == "ws":
        i += paso
    return i


def _val(toks, i):
    return toks[i][1] if 0 <= i < len(toks) else None


def _n1(toks: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], bool]:
    """Reescribe «= ANY ((ARRAY[l1::B, ...])::T[])» a «= ANY (ARRAY[(l1::B)::T, ...])». Devuelve (tokens, cambio)."""
    cambio = False
    i = 0
    while i < len(toks):
        # buscamos «(» «ARRAY» «[» con «<cuantificador> (» delante (ANY o ALL) y un operador delante del
        # cuantificador (decision 16). Operador y cuantificador quedan FUERA del tramo reescrito: se conservan tal
        # cual en los dos lados, asi que un operador o un cuantificador distinto sigue dando diferencia.
        if toks[i][1] != "(":
            i += 1
            continue
        p_par = _sig(toks, i - 1, -1)
        p_cuant = _sig(toks, p_par - 1, -1)
        p_op = _sig(toks, p_cuant - 1, -1)
        if not (_val(toks, p_par) == "(" and _val(toks, p_cuant) in _CUANTIFICADORES
                and 0 <= p_op < len(toks) and toks[p_op][0] == "op"):
            i += 1
            continue
        j = _sig(toks, i + 1)
        if _val(toks, j) != "ARRAY":
            i += 1
            continue
        j = _sig(toks, j + 1)
        if _val(toks, j) != "[":
            i += 1
            continue
        elementos = []          # (lit_token, slice_B)
        ok = True
        j = _sig(toks, j + 1)
        while True:
            if not (0 <= j < len(toks)) or toks[j][0] != "lit":
                ok = False
                break
            lit = toks[j]
            k = _sig(toks, j + 1)
            if _val(toks, k) != "::":
                ok = False
                break
            b_ini = _sig(toks, k + 1)
            b_fin = b_ini
            while 0 <= b_fin < len(toks) and toks[b_fin][0] in ("id", "ws") and toks[b_fin][1] not in (",", "]"):
                b_fin += 1
            # quitamos los espacios finales del tipo base
            while b_fin > b_ini and toks[b_fin - 1][0] == "ws":
                b_fin -= 1
            if b_fin == b_ini:
                ok = False
                break
            elementos.append((lit, toks[b_ini:b_fin]))
            k = _sig(toks, b_fin)
            if _val(toks, k) == ",":
                j = _sig(toks, k + 1)
                continue
            if _val(toks, k) == "]":
                j = k
                break
            ok = False
            break
        if not ok or not elementos:
            i += 1
            continue
        bases = {tuple(v for t, v in b if t != "ws") for _, b in elementos}
        if len(bases) != 1:                      # todos del MISMO tipo base
            i += 1
            continue
        k = _sig(toks, j + 1)
        if _val(toks, k) != ")":
            i += 1
            continue
        k = _sig(toks, k + 1)
        if _val(toks, k) != "::":
            i += 1
            continue
        t_ini = _sig(toks, k + 1)
        t_fin = t_ini
        while 0 <= t_fin < len(toks) and toks[t_fin][0] in ("id", "ws"):
            t_fin += 1
        while t_fin > t_ini and toks[t_fin - 1][0] == "ws":
            t_fin -= 1
        if t_fin == t_ini:
            i += 1
            continue
        k = _sig(toks, t_fin)
        if _val(toks, k) != "[":
            i += 1
            continue
        k2 = _sig(toks, k + 1)
        if _val(toks, k2) != "]":
            i += 1
            continue
        cierre = _sig(toks, k2 + 1)
        if _val(toks, cierre) != ")" or cierre != _sig(toks, k2 + 1):
            i += 1
            continue
        tipo_t = toks[t_ini:t_fin]
        nuevo: list[tuple[str, str]] = [("id", "ARRAY"), ("punt", "[")]
        for n, (lit, base) in enumerate(elementos):
            if n:
                nuevo += [("punt", ","), ("ws", " ")]
            nuevo += [("punt", "("), lit, ("cast", "::"), *base, ("punt", ")"), ("cast", "::"), *tipo_t]
        nuevo.append(("punt", "]"))
        toks = toks[:i] + nuevo + toks[k2 + 1:]
        cambio = True
        i += len(nuevo)
    return toks, cambio


def _n2(toks: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], bool]:
    """Quita «(» «)» alrededor de un unico operando atomico. Devuelve (tokens, cambio)."""
    cambio = False
    seguir = True
    while seguir:
        seguir = False
        for i, (tipo, v) in enumerate(toks):
            if v != "(":
                continue
            x = _sig(toks, i + 1)
            if not (0 <= x < len(toks)) or toks[x][0] not in ("id", "num", "lit", "qid"):
                continue
            c = _sig(toks, x + 1)
            if _val(toks, c) != ")":
                continue
            prev = _sig(toks, i - 1, -1)
            if prev >= 0:
                pt, pv = toks[prev]
                if not (pv in ("(", "[", ",") or pt == "op" or (pt == "id" and pv.upper() in _PALABRAS_OPERADOR
                                                               and pv == pv.upper())):
                    continue                     # llamada, palabra clave (ANY, CHECK...) o cast: no se toca
            nxt = _sig(toks, c + 1)
            if _val(toks, nxt) in (".", "(", "["):
                continue
            toks = toks[:i] + toks[i + 1:c] + toks[c + 1:]
            cambio = seguir = True
            break
    return toks, cambio


def normalizar(texto: str, reglas: tuple[str, ...] = REGLAS) -> tuple[tuple[str, ...], set[str]]:
    """Forma normalizada (tupla de valores de token) y reglas que han reescrito algo en este texto."""
    toks = tokenizar(texto)
    aplicadas: set[str] = set()
    if "N1" in reglas:
        toks, c = _n1(toks)
        if c:
            aplicadas.add("N1")
    if "N2" in reglas:
        toks, c = _n2(toks)
        if c:
            aplicadas.add("N2")
    if "N3" in reglas:
        sin_ws = [t for t in toks if t[0] != "ws"]
        if len(sin_ws) != len(toks):
            aplicadas.add("N3")
        toks = sin_ws
    return tuple(v for _, v in toks), aplicadas


def iguales_con(a: str, b: str, reglas: tuple[str, ...]) -> bool:
    return normalizar(a, reglas)[0] == normalizar(b, reglas)[0]


def reglas_necesarias(a: str, b: str) -> list[str] | None:
    """Conjunto MINIMO de reglas que iguala a y b (None si ninguno lo hace). Primero los conjuntos mas pequenos."""
    for n in range(1, len(REGLAS) + 1):
        for sub in combinations(REGLAS, n):
            if iguales_con(a, b, sub):
                return list(sub)
    return None


# ---------------------------------------------------------------- entrada

def cargar(ruta: pathlib.Path) -> dict[str, dict]:
    """Devuelve {nombre: {definicion, tipo?, deferrable?, deferred?}}."""
    datos = ruta.read_bytes().decode("utf-8-sig")
    out: dict[str, dict] = {}
    s = datos.lstrip()
    if s.startswith("{") or s.startswith("["):
        obj = json.loads(s)
        if isinstance(obj, dict):
            for k, v in obj.items():
                if not isinstance(v, str):
                    raise ValueError(f"{ruta}: valor no textual para {k}")
                out[k] = {"definicion": v}
        else:
            for e in obj:
                nombre = e.get("conname") or e.get("nombre")
                if e.get("tabla") and "." not in nombre:
                    nombre = f"{e['tabla']}.{nombre}"
                fila = {"definicion": e.get("definicion", e.get("def"))}
                for k in ("tipo", "deferrable", "deferred"):
                    if k in e:
                        fila[k] = e[k]
                if nombre in out:
                    raise ValueError(f"{ruta}: nombre duplicado {nombre}")
                out[nombre] = fila
    else:
        # Una constraint empieza en una linea «schema.tabla.nombre|contype|t/f|t/f|»; las definiciones de varias
        # lineas (p. ej. CASE) siguen en las lineas siguientes y se unen con «\n», tal cual las imprime psql.
        actual = None
        for n, linea in enumerate(datos.splitlines(), 1):
            m = _CABECERA_TXT.match(linea)
            if m:
                nombre, tipo, dfr, dfd, defin = m.groups()
                if nombre in out:
                    raise ValueError(f"{ruta}:{n}: nombre duplicado {nombre}")
                actual = out[nombre] = {"definicion": defin, "tipo": tipo, "deferrable": dfr, "deferred": dfd}
            elif actual is not None:
                actual["definicion"] += "\n" + linea
            elif linea.strip():
                raise ValueError(f"{ruta}:{n}: se esperaba «nombre|contype|condeferrable|condeferred|definicion»")
    for k, v in out.items():
        if not isinstance(v.get("definicion"), str):
            raise ValueError(f"{ruta}: {k} sin definicion")
    return out


# ---------------------------------------------------------------- comparacion

def comparar(a: dict[str, dict], b: dict[str, dict]) -> dict:
    filas = []
    for nombre in sorted(set(a) | set(b)):
        if nombre not in b:
            filas.append({"constraint": nombre, "presencia": "FALTA", "igual_literal": False, "igual_normalizado": False,
                          "clase": "DIFERENCIA_SEMANTICA", "motivo": "falta en la observada", "reglas": [],
                          "a": a[nombre]["definicion"], "b": None})
            continue
        if nombre not in a:
            filas.append({"constraint": nombre, "presencia": "SOBRA", "igual_literal": False, "igual_normalizado": False,
                          "clase": "DIFERENCIA_SEMANTICA", "motivo": "sobra en la observada", "reglas": [],
                          "a": None, "b": b[nombre]["definicion"]})
            continue
        da, db = a[nombre]["definicion"], b[nombre]["definicion"]
        atributos = [k for k in ("tipo", "deferrable", "deferred")
                     if k in a[nombre] and k in b[nombre] and a[nombre][k] != b[nombre][k]]
        fila = {"constraint": nombre, "presencia": "AMBAS", "a": da, "b": db}
        if da == db and not atributos:
            fila.update(igual_literal=True, igual_normalizado=True, clase="IGUAL_LITERAL", reglas=[], motivo="")
        else:
            reglas = None if atributos else reglas_necesarias(da, db)
            fila["igual_literal"] = False
            if reglas is not None:
                fila.update(igual_normalizado=True, clase="IGUAL_NORMALIZADO", reglas=reglas,
                            motivo="igual con " + "+".join(reglas))
            else:
                fila.update(igual_normalizado=False, clase="DIFERENCIA_SEMANTICA", reglas=[],
                            motivo=("atributos distintos: " + ", ".join(atributos)) if atributos
                            else "definicion distinta tras N1-N3")
        filas.append(fila)
    sem = [f for f in filas if f["clase"] == "DIFERENCIA_SEMANTICA"]
    norm = [f for f in filas if f["clase"] == "IGUAL_NORMALIZADO"]
    veredicto = "DIFERENCIA_SEMANTICA" if sem else ("IGUAL_NORMALIZADO" if norm else "IGUAL_LITERAL")
    por_regla: dict[str, int] = {}
    for f in norm:
        clave = "+".join(f["reglas"])
        por_regla[clave] = por_regla.get(clave, 0) + 1
    return {
        "n_a": len(a), "n_b": len(b),
        "n_igual_literal": sum(f["clase"] == "IGUAL_LITERAL" for f in filas),
        "n_igual_normalizado": len(norm),
        "n_diferencia_semantica": len(sem),
        "igual_normalizado_por_regla": por_regla,
        "igual_normalizado": [{"constraint": f["constraint"], "reglas": f["reglas"]} for f in norm],
        "diferencia_semantica": [{"constraint": f["constraint"], "motivo": f["motivo"]} for f in sem],
        "veredicto": veredicto,
        "filas": filas,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Comparador normalizado de constraints (N1-N3, lista cerrada).")
    ap.add_argument("--a", required=True, help="extraccion de referencia")
    ap.add_argument("--b", required=True, help="extraccion observada")
    ap.add_argument("--huellas", action="append", default=[], help="JSON de huellas D-111 que se copia literal")
    ap.add_argument("--salida")
    x = ap.parse_args(argv)
    try:
        pa, pb = pathlib.Path(x.a), pathlib.Path(x.b)
        a, b = cargar(pa), cargar(pb)
        huellas = {h: json.loads(pathlib.Path(h).read_text(encoding="utf-8-sig")) for h in x.huellas}
    except (OSError, ValueError) as exc:
        print(f"entrada no valida: {exc}", file=sys.stderr)
        return 2
    res = comparar(a, b)
    res = {
        "comparador": "scripts/gates/comparar_constraints_normalizado.py 1.0.0",
        "normalizacion": "cerrada N1-N3 (AJ-T3C-06)",
        "a": str(pa), "a_sha256": hashlib.sha256(pa.read_bytes()).hexdigest(),
        "b": str(pb), "b_sha256": hashlib.sha256(pb.read_bytes()).hexdigest(),
        "huellas_d111_literales": huellas,
        "nota": "La h2 literal se informa sin cambios; este resultado no sustituye ninguna huella D-111.",
        **res,
    }
    texto = json.dumps(res, ensure_ascii=False, indent=1)
    if x.salida:
        pathlib.Path(x.salida).write_text(texto, encoding="utf-8", newline="\n")
    resumen = {k: res[k] for k in ("n_a", "n_b", "n_igual_literal", "n_igual_normalizado", "n_diferencia_semantica",
                                   "igual_normalizado_por_regla", "veredicto")}
    print(json.dumps(resumen, ensure_ascii=False))
    return 1 if res["veredicto"] == "DIFERENCIA_SEMANTICA" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
