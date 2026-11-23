# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f06_t4_token.py
# Ruta: scripts/dev/mutantes_f06_t4_token.py
# Descripcion: Arnes de mutacion del token BETA_LOCAL (F06 T4; mandato 4f0e40af... par. 5; dictamen AJ-TOK-07).
#   Mutantes del diseno v0.1 par. 5 (M-TOK-01..04: lectura de la variable publica del token, credencial en
#   AsyncStorage, aceptar el codigo sin comprobarlo con el PC, peticion sin credencial) y los del dictamen
#   (M-TOK-05..10: peticion antes de terminar la inicializacion; timeout de /v1/salud como credencial invalida;
#   token en un log del cliente (07a) y del backend (07b); «Desconectar» que conserva el token en memoria (08a) o
#   la conexion activa (08b); 401 que da por rechazada la escritura y abre una intencion distinta; perfil remoto
#   con HTTP sin TLS). Mismo motor que mutantes_f06_t4_aj05.py: journal durable, preflight verde, restauracion
#   verificada por SHA-256 y veredicto a disco. Discriminantes: Jest (token_credencial, token_bundle) y
#   tests/api/test_316 (07b, necesita GAPTO_TEST_DATABASE_URL de una base desechable con la cadena aplicada).
#   Los textos de los mutantes son exactos (ficheros LF).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> python -u scripts/dev/mutantes_f06_t4_token.py [--solo ID,ID] [--salida f]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F06 T4 token BETA_LOCAL)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f06_t4_token.journal.json"

CFG = "mobile/src/api/config.ts"
ALM = "mobile/src/api/almacenCredencial.ts"
CRE = "mobile/src/api/credencial.ts"
CLI = "mobile/src/api/cliente.ts"
TRA = "mobile/src/api/transporte.ts"
APP = "backend/app/api/app.py"
TC = "jest:__tests__/token_credencial.test.tsx::"
TB = "jest:__tests__/token_bundle.test.ts::"
T316 = "tests/api/test_316_f06_t4_token_rotacion_aislamiento.py::test_el_token_no_aparece_en_jsonl_logs_ni_salida"
N = "\n"

# (id, descripcion, [(fichero, texto_exacto, sustituto)], [tests discriminantes])
MUTANTES = [
    ("M-TOK-01", "config.ts vuelve a leer la variable publica del token (se incrusta en el bundle)",
     [(CFG, "  token: '',", "  token: process.env.EXPO_PUBLIC_GAPTO_DEV_TOKEN ?? '',")],
     [TB + "nombra una variable EXPO_PUBLIC"]),
    ("M-TOK-02", "credencial guardada en AsyncStorage en lugar del llavero",
     [(ALM, "import * as SecureStore from 'expo-secure-store';",
       "import * as SecureStore from 'expo-secure-store';" + N + "import AsyncStorage from '@react-native-async-storage/async-storage';"),
      (ALM, "  guardar: (valor: string) => SecureStore.setItemAsync(CLAVE_CREDENCIAL, valor, OPCIONES),",
       "  guardar: (valor: string) => AsyncStorage.setItem(CLAVE_CREDENCIAL, valor),")],
     [TB + "la credencial solo se persiste con expo-secure-store"]),
    ("M-TOK-03", "el codigo se acepta y guarda sin comprobarlo contra /v1/salud",
     [(CRE, "    const r = await comprobarCredencial(this.o.baseUrl, valor, this.o.fetchImpl, this.o.timeoutMs);",
       "    const r = 'VALIDA' as ResultadoComprobacion;")],
     [TC + "digo incorrecto"]),
    ("M-TOK-04", "sin credencial la peticion sale igualmente",
     [(CLI, "    if (cfg.credencial && !token) {", "    if (false && cfg.credencial && !token) {")],
     [TC + "borra memoria y llavero", TC + "con el llavero lento"]),
    ("M-TOK-05", "peticion antes de terminar la inicializacion (token en memoria fuera de CONECTADA)",
     [(CRE, "    return this.actual.tipo === 'CONECTADA' ? this.memoria : null;", "    return this.memoria;")],
     [TC + "con el llavero lento"]),
    ("M-TOK-06", "timeout de /v1/salud tratado como credencial invalida y borrada",
     [(CRE, "    this.poner({ tipo: 'ERROR_DE_CONEXION', motivo: 'SIN_RESPUESTA' });" + N + "  }",
       "    return this.olvidar('CREDENCIAL_RECHAZADA');" + N + "  }")],
     [TC + "timeout de /v1/salud con credencial guardada"]),
    ("M-TOK-07a", "el token se imprime en un log de diagnostico del cliente",
     [(CRE, "    const valor = codigo.trim();", "    const valor = codigo.trim(); console.log('diagnostico conectar', valor);")],
     [TC + "digo correcto: se comprueba", TB + "no escriben en consola"]),
    ("M-TOK-07b", "el backend registra la cabecera Authorization",
     [(APP, '        cabecera = request.headers.get("authorization", "")',
       '        cabecera = request.headers.get("authorization", ""); _LOG.info("autorizacion %s", cabecera)')],
     [T316]),
    ("M-TOK-08a", "«Desconectar» borra el llavero pero conserva el token en memoria",
     [(CRE, "    this.memoria = null;" + N + "    this.poner({ tipo: 'SIN_CREDENCIAL', motivo: 'DESCONECTADO' });",
       "    this.poner({ tipo: 'SIN_CREDENCIAL', motivo: 'DESCONECTADO' });")],
     [TC + "borra memoria y llavero"]),
    ("M-TOK-08b", "«Desconectar» borra el llavero pero la conexion sigue activa",
     [(CRE, "    this.memoria = null;" + N + "    this.poner({ tipo: 'SIN_CREDENCIAL', motivo: 'DESCONECTADO' });",
       "    void 0;")],
     [TC + "borra memoria y llavero"]),
    ("M-TOK-09", "un 401 da la escritura por rechazada (la cola la descarta y se rehace con otra intencion)",
     [(CLI, "        return { tipo: 'INDETERMINADO', mensaje: MSG_CREDENCIAL_RECHAZADA };",
       "        return { tipo: 'RECHAZADO', codigo: 'NO_AUTORIZADO', mensaje: MSG_CREDENCIAL_RECHAZADA } as Respuesta<T>;")],
     [TC + "401 en el propio pago"]),
    ("M-TOK-10", "el perfil remoto admite HTTP sin TLS",
     [(TRA, "  return hostPrivado(p.host);", "  return true;")],
     [TC + "transporte: http solo", TC + "transporte: con un perfil remoto"]),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    """pytest de tests/api con su rootdir y Jest en mobile/ (cada patron por separado). rc != 0 si alguno falla."""
    api = [t for t in tests if t.startswith("tests/api/")]
    jest = [t[len("jest:"):] for t in tests if t.startswith("jest:")]
    rc = 0
    if api:
        cmd = [sys.executable, "-m", "pytest", *api, "-q", "-x", "-p", "no:cacheprovider", "--rootdir=tests/api"]
        rc = rc or subprocess.run(cmd, cwd=RAIZ, capture_output=True).returncode
    npx = "npx.cmd" if os.name == "nt" else "npx"
    for t in jest:
        fichero, patron = t.split("::", 1)
        cmd = [npx, "jest", fichero, "-t", patron, "--silent"]
        r = subprocess.run(cmd, cwd=RAIZ / "mobile", capture_output=True, text=True, encoding="utf-8", errors="replace")
        salida = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0 and " passed" not in salida.split("Tests:")[-1]:
            return 3  # el patron no selecciono ningun test: el preflight lo detecta
        rc = rc or r.returncode
    return rc


def recuperar_si_pendiente() -> bool:
    if not JOURNAL.exists():
        return False
    j = json.loads(JOURNAL.read_text(encoding="utf-8"))
    for f in j["ficheros"]:
        ruta = RAIZ / f["fichero"]
        ruta.write_bytes(bytes.fromhex(f["original_hex"]))
        if sha(ruta.read_bytes()) != f["sha256"]:
            sys.exit(f"RECUPERACION FALLIDA: identidad no verificada en {f['fichero']}")
    JOURNAL.unlink()
    return True


def anotar(salida: pathlib.Path | None, linea: str) -> None:
    print(linea, flush=True)
    if salida is not None:
        with salida.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())


def main() -> None:
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    salida = pathlib.Path(sys.argv[sys.argv.index("--salida") + 1]) if "--salida" in sys.argv else None
    elegidos = [mu for mu in MUTANTES if solo is None or mu[0] in solo]
    if any(t.startswith("tests/api/") for mu in elegidos for t in mu[3]) and not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable) para M-TOK-07b.")
    preflight = sorted({t for mu in elegidos for t in mu[3]})
    for t in preflight:
        if correr([t]) != 0:
            sys.exit(f"PREFLIGHT ROJO ({t}): no se muta nada.")
    veredictos = []
    for mid, desc, cambios, tests in elegidos:
        ficheros = sorted({c[0] for c in cambios})
        originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
        textos = {f: b.decode("utf-8") for f, b in originales.items()}
        aplicable = True
        for f, texto, sustituto in cambios:
            if textos[f].count(texto) != 1:
                aplicable = False
                break
            textos[f] = textos[f].replace(texto, sustituto)
        if not aplicable:
            v = (mid, "NO_APLICADO", "transformacion no aplicable", desc)
            veredictos.append(v)
            anotar(salida, " | ".join(v))
            continue
        JOURNAL.write_text(json.dumps({"mutante": mid, "ficheros": [
            {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros
        ]}), encoding="utf-8")
        resultado = "NO_CLASIFICABLE"
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            resultado = "MUERTO" if correr(tests) != 0 else "VIVO"
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        v = (mid, resultado if ok else "NO_CLASIFICABLE", ",".join(t.split("::", 1)[-1] for t in tests), desc)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    anotar(salida, f"RESUMEN {muertos} muertos, {len(veredictos) - muertos} otros / {len(veredictos)} (los NO_APLICADO no cuentan como muertos)")
    sys.exit(0 if muertos == len(veredictos) else 1)


if __name__ == "__main__":
    main()
