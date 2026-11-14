#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: t2_f06_pag.py
# Ruta: scripts/mutantes/t2_f06_pag.py
# Descripcion: Arnes de mutacion de T2-F06 · PAG «quien pago y quien debe» (N1; mandato PAG §9.3: un mutante por guarda).
#   Mismo motor que scripts/mutantes/f06_01_b3.py (copiado sin cambios de logica):
#   - sustitucion de texto EXACTO que aparece una sola vez (0 o mas de 1 -> NO_CLASIFICABLE y el arnes PARA);
#   - journal (marcador con el contenido original) ANTES del primer byte mutado; si una ejecucion anterior se
#     corto, restaura y aborta;
#   - restauracion verificada por SHA-256 tras cada mutante (tambien si pytest aborta);
#   - preflight: todos los discriminantes verdes antes de mutar;
#   - veredicto escrito a disco en cuanto se conoce (GAPTO_PAG_MUTANTES_VEREDICTOS, una linea JSON por mutante)
#     y salida de pytest de cada mutante (GAPTO_PAG_MUTANTES_SALIDA).
#   Un mutante solo se da por MUERTO si cae al menos uno de SUS discriminantes.
#   Mutantes: M-PAG-01..08 (anexo B §8), M-PAG-09..14 (laboratorio lab-t2 6cb1c6f, como catalogo; textos nuevos sobre
#   el codigo de la rama), M-PAG-09b, M-PAG-15..24 (mandato §9.3) y M-PAG-25 (terceros FOR SHARE, bateria serie).
#   Requiere GAPTO_TEST_DATABASE_URL (base desechable, formato postgresql://) y GAPTO_PAG_CONCURRENCIA=1
#   (discriminante de la bateria serie de M-PAG-25).
# Uso:
#   python scripts/mutantes/t2_f06_pag.py              # todos
#   python scripts/mutantes/t2_f06_pag.py M-PAG-09     # subconjunto
# Version: 0.1.0 (F06 T2-F06 PAG N1)
# ============================================================
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass

RAIZ = pathlib.Path(__file__).resolve().parents[2]
GP = "backend/app/patrimonio/gasto_propiedad.py"
PAG = "backend/app/patrimonio/pagos.py"
LEC = "backend/app/patrimonio/lecturas_pag.py"
RUT = "backend/app/patrimonio/rutas_pag.py"
ACT = "backend/app/actividad/lecturas.py"
T262 = "tests/api/test_262_f06_t2_pag_quien_pago.py"
T263 = "tests/api/test_263_f06_t2_pag_concurrencia_serial.py"
T264 = "tests/api/test_264_f06_t2_pag_actividad_f05.py"
MARCADOR = RAIZ / ".mutante_t2_f06_pag_en_curso"


def n(fichero: str, nombre: str) -> str:
    return f"{fichero}::{nombre}"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    fichero: str
    viejo: str
    nuevo: str
    discriminantes: tuple[str, ...]


MUTANTES = (
    # ------------------------------------------------------------------ anexo B §8
    Mutante("M-PAG-01", "P2 (y NADA) no crea posiciones por defecto", PAG,
            '            continue\n        actor = _uuid(s["actor_id"])\n        posiciones.append(DatosAltaPosicion(\n',
            '            s = {**s, "sentido": ME_DEBE, "importe": "1.00"}\n        actor = _uuid(s["actor_id"])\n'
            '        posiciones.append(DatosAltaPosicion(\n',
            (n(T262, "test_o_pag_02_qp_p2_cada_uno_su_parte_h_pag_01_conciliado_por_menos"),
             n(T262, "test_o_pag_20_nada_con_desequilibrio_es_invitacion"))),
    Mutante("M-PAG-02", "El cotitular no paga desde mis cuentas (P3 sin movimiento en mis cuentas)", PAG,
            '    if any(p.get("cuenta_id") for p in pagos if not es_mio(p)):\n',
            "    if False:\n",
            (n(T262, "test_qp_x_o_pag_22_mezclas_rechazadas"),)),
    Mutante("M-PAG-03", "La obligacion (LE_DEBO) no se crea sin confirmacion", PAG,
            '                       for s in saldos if s["sentido"] != NADA)\n',
            '                       for s in saldos if s["sentido"] == ME_DEBE)\n',
            (n(T262, "test_o_pag_06_posicion_sin_confirmar_422_estado_identico"),
             n(T262, "test_o_pag_03_qp_p3_paga_el_cotitular_le_debo_y_despues_le_pago_op12b"))),
    Mutante("M-PAG-04", "P2: la aportacion del cotitular va SIN movimiento", PAG,
            '                                                criterio_aportacion="MANUAL", actor_id=actor))',
            '                                                criterio_aportacion="MANUAL", actor_id=actor,\n'
            '                                                hecho_movimiento_tesoreria_id=ident("conciliacion")))',
            (n(T262, "test_o_pag_02_qp_p2_cada_uno_su_parte_h_pag_01_conciliado_por_menos"),)),
    Mutante("M-PAG-05", "La posicion se crea por el saldo declarado (mi parte), no por el total", PAG,
            'importe_inicial=_d(s["importe"])))',
            'importe_inicial=_d(s["importe"]) * 2))',
            (n(T262, "test_o_pag_03_qp_p3_paga_el_cotitular_le_debo_y_despues_le_pago_op12b"),
             n(T262, "test_o_pag_01_qp_p1_pago_yo_todo_y_me_debe_su_parte"))),
    Mutante("M-PAG-06", "Nunca hay posicion frente a una EMPRESA", GP,
            '    if any(nat.get(a) != "PERSONA" for a in con_posicion):                       # sin posicion frente a EMPRESA\n',
            "    if False:\n",
            (n(T262, "test_o_pag_08_qp_e_empresa_aporta_sin_posicion_y_nunca_le_debo"),
             n(T262, "test_o_pag_18_empresa_como_pagador_frente_a_cotitular_persona"))),
    Mutante("M-PAG-07", "El servidor nunca infiere LE_DEBO (compone solo lo declarado)", GP,
            'nota=p.get("nota"), pagos=p["pagos"], saldos=p.get("saldos") or [], yo=yo)',
            'nota=p.get("nota"), pagos=p["pagos"], yo=yo, saldos=[dict(s, sentido="LE_DEBO", importe="1.00") '
            'if s["sentido"] == "NADA" and pag.mi_pago(p["pagos"]) is None else s for s in (p.get("saldos") or [])])',
            (n(T262, "test_o_pag_04_p3_con_nada_sin_posicion"),)),
    Mutante("M-PAG-08", "La lectura no reinterpreta un hecho del tren 1 como P1", PAG,
            '"con_movimiento": m, "cuenta_id": c} for a, i, m, c in filas],',
            '"con_movimiento": m, "cuenta_id": c} for a, i, m, c in filas] or [{"actor_id": None, '
            '"importe": str(_d(-Decimal(salido))), "con_movimiento": True, "cuenta_id": None}],',
            (n(T262, "test_o_pag_12_hecho_de_b3_del_tren_1_pago_sin_declarar_sin_escrituras"),)),
    # ------------------------------------------------------------------ catalogo del laboratorio
    Mutante("M-PAG-09", "Cada ME_DEBE frente a SU desequilibrio (saldo = pagado - parte)", PAG,
            "            if not (saldo < 0 and valor <= -saldo):\n",
            "            if False:\n",
            (n(T262, "test_o_pag_16b_tope_por_la_suma_bilateral_y_compuesto"),)),
    Mutante("M-PAG-09b", "LE_DEBO solo a quien pago de mas", PAG,
            "            if not (saldo > 0 and valor <= saldo):\n",
            "            if False:\n",
            (n(T262, "test_o_pag_16b_tope_por_la_suma_bilateral_y_compuesto"),)),
    Mutante("M-PAG-10", "Con NO_LO_SE no se admite deuda (Q-PAG-09)", PAG,
            '        return ENTRADA_INVALIDA if any(s["sentido"] != NADA for s in saldos) else None\n',
            "        return None\n",
            (n(T262, "test_o_pag_05_qp_p7_no_lo_se_admite_pagadores_sin_deuda"),)),
    Mutante("M-PAG-11", "Los pagos suman el importe (PAGOS_NO_CUADRAN)", PAG,
            "        return PAGOS_NO_CUADRAN\n",
            "        pass\n",
            (n(T262, "test_o_pag_09_pagos_no_cuadran"),)),
    Mutante("M-PAG-12", "Un pagador ajeno al reparto se rechaza", PAG,
            "    if not set(otros) <= cotitulares:\n",
            "    if False:\n",
            (n(T262, "test_qp_r_rechazos_sin_escritura"),)),
    Mutante("M-PAG-13", "C-MEJ-01 v1 y v2 no se mezclan", GP,
            '        return (p.get("cuenta_id") is not None or bool(p.get("deuda")) or bool(p.get("derechos_confirmados"))\n'
            '                or p.get("aportacion_indicada") is not None)\n',
            "        return False\n",
            (n(T262, "test_qp_x_o_pag_22_mezclas_rechazadas"),)),
    Mutante("M-PAG-14", "La lectura no reinterpreta un hecho sin aportaciones (pago sin declarar)", PAG,
            '        "declarado": bool(filas),',
            '        "declarado": True,',
            (n(T262, "test_o_pag_12_hecho_de_b3_del_tren_1_pago_sin_declarar_sin_escrituras"),)),
    # ------------------------------------------------------------------ mandato §9.3
    Mutante("M-PAG-15", "posiciones_confirmadas se verifican (actor, tipo e importe)", PAG,
            "    if esperadas != recibidas:\n",
            "    if False:\n",
            (n(T262, "test_o_pag_21_posiciones_confirmadas_distintas_422"),
             n(T262, "test_o_pag_06_posicion_sin_confirmar_422_estado_identico"))),
    Mutante("M-PAG-16", "El mixto con tres o mas titulares se rechaza", PAG,
            "    if len(partes) >= 3 and modo(",
            "    if False and modo(",
            (n(T262, "test_o_pag_16_mixto_con_tres_titulares_rechazado"),)),
    Mutante("M-PAG-17", "Tope por la SUMA de mis ME_DEBE/LE_DEBO (nunca posiciones entre terceros)", PAG,
            "    if suma_me_debe > max(mi_saldo, CERO) or suma_le_debo > max(-mi_saldo, CERO):\n",
            "    if False:\n",
            (n(T262, "test_o_pag_15_tres_titulares_p1_p2_p3_sin_posiciones_entre_terceros"),)),
    Mutante("M-PAG-18", "Un pago mio desde una cuenta compartida en pagos[] se rechaza", GP,
            "        return pag.PAGO_DESDE_CUENTA_COMPARTIDA\n",
            "        return None\n",
            (n(T262, "test_o_pag_17_cuenta_compartida_en_pagos_rechazada_y_via_b3_sigue"),)),
    Mutante("M-PAG-19", "«Invertido» no incluye compras", LEC,
            "AND th.codigo = 'MEJORA_PATRIMONIAL' \"\n"
            "    \"AND h.fecha_hecho >= %(inicio)s AND h.fecha_hecho < %(fin)s \"\n"
            "    \"AND e.tipo_efecto = 'VALOR_ACTIVO' AND e.causa_valor_activo = 'TRANSFORMACION_CAPITALIZABLE'\"\n",
            "\"\n"
            "    \"AND h.fecha_hecho >= %(inicio)s AND h.fecha_hecho < %(fin)s \"\n"
            "    \"AND e.tipo_efecto = 'VALOR_ACTIVO'\"\n",
            (n(T262, "test_o_pag_23b_invertido_no_cuenta_compras"),)),
    Mutante("M-PAG-20", "«Invertido» suma mi parte, no el total", LEC,
            "    \" WHERE a.efecto_id = e.id AND a.actor_id = %(actor)s) \"\n",
            "    \" WHERE a.efecto_id = e.id) \"\n",
            (n(T262, "test_o_pag_23_invertido_en_viviendas_este_mes"),)),
    Mutante("M-PAG-21", "Actividad: tu parte de la reforma sale de su VALOR_ACTIVO (no el total)", ACT,
            "\"     OR (e.tipo_efecto = 'VALOR_ACTIVO' AND th.codigo = 'MEJORA_PATRIMONIAL')) \"",
            "\"     OR false) \"",
            (n(T264, "test_o_pag_24_actividad_mi_parte_salida_real_y_posicion"),)),
    Mutante("M-PAG-22", "L-MOV-CUENTA filtra por la cuenta", LEC,
            "WHERE m.cuenta_id = %(c)s AND m.estado = 'ACTIVO' ",
            "WHERE %(c)s::uuid IS NOT NULL AND m.estado = 'ACTIVO' ",
            (n(T262, "test_o_pag_25_l_mov_cuenta"),)),
    Mutante("M-PAG-23", "Un unico punto de llamada a OP-22 en C-MEJ-01 (v1 y v2)", GP,
            '    if repo_comp.leer(sesion, "hechos_financieros", iid) is not None:            # identidad: OP-22 decide\n'
            "        partes = partes_peticion\n",
            '    if repo_comp.leer(sesion, "hechos_financieros", iid) is not None:            # identidad: OP-22 decide\n'
            "        d = datos(partes_peticion)\n"
            "        r = _op22(sesion).registrar_hecho_compuesto(sesion.contexto, d)\n"
            "        return _respuesta(sesion, propiedad_id, d, clase, r.idempotente)\n",
            (n(T262, "test_m_pag_23_un_unico_punto_de_llamada_a_op22_en_c_mej_01"),)),
    Mutante("M-PAG-24", "La reserva de OP-21 no se salta: PAG no importa OP-21/OP-03", RUT,
            "from app.patrimonio import lecturas_pag\n",
            "from app.patrimonio import lecturas_pag\nfrom app.services import correcciones_service  # noqa: F401\n",
            (n(T262, "test_o_pag_14_h_pag_02_obligacion_frente_a_la_reserva_de_op21"),)),
    Mutante("M-PAG-25", "Terceros de pagadores y saldos FOR SHARE (cambio de naturaleza concurrente)", GP,
            '"ORDER BY t.id FOR SHARE OF t", (actores,))',
            '"ORDER BY t.id", (actores,))',
            (n(T263, "test_c3_cmej01_v2_p3_frente_al_cambio_del_tercero_pagador"),)),
)


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _recuperar_si_aborto_previo() -> None:
    if MARCADOR.exists():
        ruta_rel, original_hex = MARCADOR.read_text("ascii").split("\n", 1)
        (RAIZ / ruta_rel).write_bytes(bytes.fromhex(original_hex.strip()))
        MARCADOR.unlink()
        raise SystemExit(f"ABORTADO: habia una mutacion a medias en {ruta_rel}; restaurada. "
                         "Revisa el arbol y vuelve a ejecutar.")


def _estado_arbol() -> str:
    return subprocess.run(["git", "status", "--porcelain"], cwd=RAIZ, capture_output=True, text=True).stdout


def _pytest(nodos: tuple[str, ...]) -> tuple[int, str]:
    proceso = subprocess.run(
        [sys.executable, "-m", "pytest", *nodos, "-q", "-p", "no:cacheprovider", "--rootdir=tests/api", "-rfE"],
        cwd=RAIZ, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return proceso.returncode, proceso.stdout + proceso.stderr


def _a_disco(registro: dict) -> None:
    destino = os.environ.get("GAPTO_PAG_MUTANTES_VEREDICTOS")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _guardar_salida(m: Mutante, salida: str) -> None:
    carpeta = os.environ.get("GAPTO_PAG_MUTANTES_SALIDA")
    if carpeta:
        pathlib.Path(carpeta).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(carpeta) / f"{m.ident}.log").write_text(salida, encoding="utf-8")


def comprobar_patrones(seleccion) -> list[str]:
    malos = []
    for m in seleccion:
        apariciones = (RAIZ / m.fichero).read_bytes().decode("utf-8").count(m.viejo)
        if apariciones != 1:
            malos.append(f"{m.ident}: patron encontrado {apariciones} veces en {m.fichero}")
    return malos


def ejecutar(m: Mutante) -> str:
    ruta = RAIZ / m.fichero
    original = ruta.read_bytes()
    sha_original = _sha(original)
    texto = original.decode("utf-8")
    MARCADOR.write_text(f"{m.fichero}\n{original.hex()}", "ascii")          # journal antes del primer byte
    try:
        ruta.write_bytes(texto.replace(m.viejo, m.nuevo, 1).encode("utf-8"))
        codigo, salida = _pytest(m.discriminantes)
        _guardar_salida(m, salida)
    finally:
        ruta.write_bytes(original)
        if _sha(ruta.read_bytes()) != sha_original:
            raise SystemExit(f"ABORTADO: restauracion fallida en {m.fichero}")
        MARCADOR.unlink()
    if "passed" not in salida and "failed" not in salida and "error" not in salida:
        return "NO_CLASIFICABLE pytest no llego a ejecutarse"
    fallos = [linea for linea in salida.splitlines() if linea.startswith(("FAILED", "ERROR"))]
    if codigo == 0:
        return "VIVO      ningun discriminante cae"
    nombres = [d.split("::", 1)[1] for d in m.discriminantes]
    if not any(nm in linea for nm in nombres for linea in fallos):
        return f"NO_CLASIFICABLE caen {len(fallos)} tests pero no un discriminante"
    return f"MUERTO    fallos={len(fallos)}"


def main(argv: list[str]) -> int:
    _recuperar_si_aborto_previo()
    seleccion = [m for m in MUTANTES if not argv or m.ident in argv]
    malos = comprobar_patrones(seleccion)
    if malos:
        print("\n".join(malos))
        raise SystemExit("ABORTADO (NO_CLASIFICABLE): patron con 0 o mas de 1 apariciones; no se muta nada.")
    arbol = _estado_arbol()
    nodos = tuple(dict.fromkeys(d for m in seleccion for d in m.discriminantes))
    codigo, salida = _pytest(nodos)
    if codigo != 0:
        print(salida[-4000:])
        raise SystemExit("ABORTADO: los discriminantes no estan verdes antes de mutar.")
    print(f"PREFLIGHT VERDE: {len(nodos)} discriminantes", flush=True)
    print("=== T2-F06 PAG · MUTANTES ===", flush=True)
    muertos = 0
    for m in seleccion:
        veredicto = ejecutar(m)
        muertos += veredicto.startswith("MUERTO")
        _a_disco({"id": m.ident, "invariante": m.invariante, "fichero": m.fichero, "veredicto": veredicto.split()[0],
                  "detalle": veredicto, "discriminantes": list(m.discriminantes)})
        print(f"  {m.ident:9}  {veredicto}   [{m.invariante}]", flush=True)
        if veredicto.startswith("NO_CLASIFICABLE"):
            raise SystemExit(f"ABORTADO: {m.ident} NO_CLASIFICABLE")
    if _estado_arbol() != arbol:
        raise SystemExit("ABORTADO: el estado del arbol cambio durante la tirada.")
    print(f"RESULTADO: {muertos}/{len(seleccion)} muertos")
    return 0 if muertos == len(seleccion) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
