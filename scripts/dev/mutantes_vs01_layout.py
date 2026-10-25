# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_vs01_layout.py
# Ruta: scripts/dev/mutantes_vs01_layout.py
# Descripcion: Arnes de mutacion del detector de layout de e2e_vs01.py
#   (F05-D051 paso 3; F05 §65.3, AJ-F0507G2-05: «un mutante que trunque un
#   importe o un boton: el E2E debe fallar»). Discriminante: el E2E web de
#   VS-01 completo (scripts/dev/e2e_vs01.py), que este arnes levanta de punta a
#   punta: export web del cliente (npx expo export) desde el arbol mutado,
#   base gapto2027_dev RECREADA con bootstrap_dev_db.py en un PostgreSQL LOCAL
#   desechable, API del arbol en loopback y E2E con servidor estatico propio.
#     VSL-01  importe recortado con elipsis (gastos-valor, maxWidth 24)
#             -> guarda: lista blanca de elipsis (truncado no autorizado)
#     VSL-02  boton recortado con elipsis (texto de BotonPrimario, 1 linea, maxWidth 48)
#             -> guarda: lista blanca de elipsis (truncado no autorizado, critico)
#     VSL-03  boton recortado SIN elipsis (BotonPrimario de 72 px, overflow hidden, texto sin encoger)
#             -> guarda: recorte por un ancestro / desbordamiento
#     VSL-04  importe fuera del viewport (gastos-valor fijo en left 300, ancho 200)
#             -> guarda: fuera del viewport / recorte / documento
#     VSL-05  lista blanca vacia en el propio E2E (sin «hola»)
#             -> demuestra que el saludo se mide truncado: la lista blanca no es vacua
#   Veredicto: MUERTO si el E2E sale con rc != 0, su salida contiene
#   «FALLO LAYOUT» y el fallo nombra el elemento objetivo; VIVO si rc = 0;
#   NO_CLASIFICABLE en otro caso (fallo ajeno al layout, export o arranque
#   fallido, identidad no restaurada).
#   Motor (D-181/D-192, WM 12C.2): sustitucion de texto exacto (UNA ocurrencia)
#   desde el repositorio, sin sustituciones en memoria; journal durable ANTES de
#   tocar el primer byte (si al arrancar hay uno pendiente: restaura, verifica
#   SHA-256 y aborta); preflight verde (E2E sin mutante, export limpio en
#   --dist) antes del primer mutante; los mutantes se exportan a --dist-mutante
#   (nunca a --dist); tras cada mutante se restaura y se verifica la identidad
#   byte a byte; veredicto escrito a disco en cuanto se conoce.
#   Uso: python scripts/dev/mutantes_vs01_layout.py --token-fichero <fichero> --dist <dir>
#        --evidencia <dir> [--admin-dsn "host=127.0.0.1 port=<p> user=postgres dbname=postgres"]
#        [--api-puerto 5468] [--web-puerto 5469] [--solo ID,ID] [--salida fichero]
#   El token se lee del fichero y nunca se imprime ni se escribe en la evidencia.
#   El cluster debe ser LOCAL (loopback) y desechable: bootstrap recrea
#   gapto2027_dev. No ejecutar en paralelo con otro arnes ni con otro E2E que
#   use los mismos puertos o la misma base. EVIDENCIA WEB/VIEWPORT, no iOS.
# Version: 0.1.0 (F05-D051 paso 3; F05 §65.3)
# ============================================================

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

from psycopg import conninfo

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_vs01_layout.journal.json"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}

HOME = "mobile/src/screens/HomeScreen.tsx"
BASICOS = "mobile/src/components/Basicos.tsx"
E2E = "scripts/dev/e2e_vs01.py"

_GASTOS = "<Text testID=\"gastos-valor\" style={[importe.secondary, { color: c.textPrimary }]} adjustsFontSizeToFit numberOfLines={1}>"
_BOTON_TEXTO = "<Text style={[tipo.bodyEmphasis, { color: off ? c.textSecondary : c.onAccent }]}>{p.titulo}</Text>"
_BOTON_CAJA = "style={({ pressed }) => [s.primario, { backgroundColor: off ? c.surfaceSecondary : c.accent, opacity: pressed ? 0.85 : 1 }]}"

#: (id, descripcion, [(fichero, texto, sustituto)], elemento objetivo que debe nombrar el fallo)
MUTANTES = [
    ("VSL-01", "importe recortado con elipsis: gastos-valor con maxWidth 24 (lista blanca de elipsis)",
     [(HOME, _GASTOS, _GASTOS.replace("{ color: c.textPrimary }", "{ color: c.textPrimary, maxWidth: 24 }"))],
     "gastos-valor"),
    ("VSL-02", "boton recortado con elipsis: texto de BotonPrimario en 1 linea con maxWidth 48 (lista blanca, critico)",
     [(BASICOS, _BOTON_TEXTO, _BOTON_TEXTO.replace("<Text style", "<Text numberOfLines={1} style")
       .replace("c.onAccent }", "c.onAccent, maxWidth: 48 }"))],
     "registrar"),
    ("VSL-03", "boton recortado sin elipsis: BotonPrimario de 72 px con overflow hidden y texto sin encoger",
     [(BASICOS, _BOTON_CAJA, _BOTON_CAJA.replace("opacity: pressed ? 0.85 : 1 }", "opacity: pressed ? 0.85 : 1, width: 72, overflow: 'hidden' }")),
      (BASICOS, _BOTON_TEXTO, _BOTON_TEXTO.replace("c.onAccent }", "c.onAccent, flexShrink: 0 }"))],
     "registrar"),
    ("VSL-04", "importe fuera del viewport: gastos-valor fijo en left 300 con ancho 200",
     [(HOME, _GASTOS, _GASTOS.replace("{ color: c.textPrimary }",
                                      "{ color: c.textPrimary, position: 'fixed' as never, left: 300, top: 300, width: 200 }"))],
     "gastos-valor"),
    ("VSL-05", "lista blanca vacia en el E2E: el saludo deja de estar autorizado",
     [(E2E, 'ELIPSIS_AUTORIZADA = ("hola",)\n', "ELIPSIS_AUTORIZADA = ()  # MUTANTE VSL-05\n")],
     "hola"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


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


def matar(proc: subprocess.Popen) -> None:
    """Detiene el proceso y sus hijos (en Windows, taskkill /T: terminate no alcanza a los nietos)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def exportar(dist: pathlib.Path, api: str, token: str, log: pathlib.Path) -> bool:
    env = dict(os.environ, EXPO_PUBLIC_GAPTO_API_URL=api, EXPO_PUBLIC_GAPTO_DEV_TOKEN=token)
    if dist.exists():
        shutil.rmtree(dist)
    npx = shutil.which("npx") or "npx"
    with log.open("w", encoding="utf-8") as f:
        r = subprocess.run([npx, "expo", "export", "--platform", "web", "--clear", "--output-dir", str(dist)],
                           cwd=RAIZ / "mobile", env=env, stdout=f, stderr=subprocess.STDOUT)
    return r.returncode == 0 and (dist / "index.html").exists()


def ejecutar_e2e(etiqueta: str, dist: pathlib.Path, a: argparse.Namespace, token: str, ev: pathlib.Path) -> tuple[int | None, str]:
    """Bootstrap + API + E2E VS-01. Devuelve (rc del E2E o None si no llego a lanzarse, salida del E2E)."""
    api = f"http://127.0.0.1:{a.api_puerto}"
    web = f"http://127.0.0.1:{a.web_puerto}"
    dirE = ev / etiqueta
    dirE.mkdir(parents=True, exist_ok=True)
    boot = subprocess.run([sys.executable, str(RAIZ / "scripts/dev/bootstrap_dev_db.py"), "--admin-dsn", a.admin_dsn, "--recrear"],
                          cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (dirE / "bootstrap.log").write_text(boot.stdout + boot.stderr + f"\nrc={boot.returncode}\n", encoding="utf-8")
    if boot.returncode != 0:
        return None, "bootstrap fallido"
    owner = next((l.split("=", 1)[1].strip() for l in boot.stdout.splitlines() if l.startswith("GAPTO_DEV_OWNER_USER_ID=")), None)
    if not owner:
        return None, "bootstrap sin owner"
    params = conninfo.conninfo_to_dict(a.admin_dsn)
    dsn = f"postgresql://{params.get('user', 'postgres')}@{params['host']}:{params.get('port', 5432)}/gapto2027_dev"
    env = dict(os.environ, GAPTO_ENV="development", GAPTO_DATABASE_URL=dsn, GAPTO_DEV_TOKEN=token,
               GAPTO_DEV_OWNER_USER_ID=owner, GAPTO_DEV_CORS_ORIGINS=web, PYTHONIOENCODING="utf-8")
    with (dirE / "api.log").open("w", encoding="utf-8") as fapi:
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.api.app:create_app_desde_entorno", "--factory",
                                 "--host", "127.0.0.1", "--port", str(a.api_puerto)],
                                cwd=RAIZ / "backend", env=env, stdout=fapi, stderr=subprocess.STDOUT)
        try:
            for _ in range(150):
                try:
                    urllib.request.urlopen(f"{api}/v1/salud", timeout=2)
                    break
                except urllib.error.HTTPError:
                    break
                except Exception:
                    time.sleep(0.2)
            else:
                return None, "la API no responde"
            e2e_env = {k: v for k, v in env.items() if k != "GAPTO_DEV_TOKEN"}
            r = subprocess.run([sys.executable, str(RAIZ / E2E), "--web", web, "--dist", str(dist), "--salida", str(dirE)],
                               cwd=RAIZ, env=e2e_env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            texto = r.stdout + r.stderr
            (dirE / "e2e.log").write_text(texto + f"\nrc={r.returncode}\n", encoding="utf-8")
            return r.returncode, texto
        finally:
            matar(proc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin-dsn", default="host=127.0.0.1 port=5463 user=postgres dbname=postgres")
    ap.add_argument("--token-fichero", required=True)
    ap.add_argument("--dist", required=True, help="export web limpio (preflight); se rehace")
    ap.add_argument("--dist-mutante", help="export de los mutantes (por defecto <dist>_mutante)")
    ap.add_argument("--evidencia", required=True)
    ap.add_argument("--api-puerto", type=int, default=5468)
    ap.add_argument("--web-puerto", type=int, default=5469)
    ap.add_argument("--solo")
    ap.add_argument("--salida")
    a = ap.parse_args()
    if conninfo.conninfo_to_dict(a.admin_dsn).get("host") not in LOOPBACK:
        sys.exit("--admin-dsn debe ser loopback (cluster local desechable).")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    token = pathlib.Path(a.token_fichero).read_text(encoding="utf-8").strip()
    api = f"http://127.0.0.1:{a.api_puerto}"
    dist = pathlib.Path(a.dist)
    dist_mut = pathlib.Path(a.dist_mutante or f"{a.dist}_mutante")
    ev = pathlib.Path(a.evidencia)
    ev.mkdir(parents=True, exist_ok=True)
    salida = pathlib.Path(a.salida) if a.salida else None
    solo = set(a.solo.split(",")) if a.solo else None
    elegidos = [mu for mu in MUTANTES if solo is None or mu[0] in solo]

    # Preflight: export limpio y E2E verde, sin ningun fallo de layout.
    if not exportar(dist, api, token, ev / "preflight_export.log"):
        sys.exit("PREFLIGHT ROJO: el export web limpio ha fallado; no se muta nada.")
    rc, texto = ejecutar_e2e("preflight", dist, a, token, ev)
    anotar(salida, f"PREFLIGHT | rc={rc}")
    if rc != 0 or "FALLO" in texto:
        sys.exit("PREFLIGHT ROJO: el E2E sin mutante no esta verde; no se muta nada.")

    veredictos = []
    for mid, desc, cambios, objetivo in elegidos:
        ficheros = sorted({c[0] for c in cambios})
        originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
        textos = {f: b.decode("utf-8") for f, b in originales.items()}
        aplicable = True
        for f, texto_a, sustituto in cambios:
            if textos[f].count(texto_a) != 1:
                aplicable = False
                break
            textos[f] = textos[f].replace(texto_a, sustituto)
        if not aplicable:
            v = (mid, "NO_CLASIFICABLE", "transformacion no aplicable", desc)
            veredictos.append(v)
            anotar(salida, " | ".join(v))
            continue
        JOURNAL.write_text(json.dumps({"mutante": mid, "ficheros": [
            {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros
        ]}), encoding="utf-8")
        rc, texto, nota = None, "", ""
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            if any(f.startswith("mobile/") for f in ficheros):
                destino = dist_mut
                if not exportar(destino, api, token, ev / f"{mid}_export.log"):
                    nota = "export fallido"
            else:
                destino = dist
            if not nota:
                rc, texto = ejecutar_e2e(mid, destino, a, token, ev)
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        lineas = [l for l in texto.splitlines() if "FALLO LAYOUT" in l]
        if not ok:
            resultado, nota = "NO_CLASIFICABLE", "identidad no restaurada"
        elif nota or rc is None:
            resultado, nota = "NO_CLASIFICABLE", nota or texto
        elif rc == 0:
            resultado = "VIVO"
        elif lineas and any(objetivo in l for l in lineas):
            resultado = "MUERTO"
            nota = " | ".join(x.strip() for l in lineas for x in l.split(" | ") if objetivo in x)[:600]
        else:
            resultado = "NO_CLASIFICABLE"
            nota = (texto.strip().splitlines() or ["sin salida"])[-1][:300]
        v = (mid, resultado, f"rc={rc}", f"{desc} :: {nota}")
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    anotar(salida, f"RESUMEN {muertos} muertos, {len(veredictos) - muertos} otros / {len(veredictos)}")
    sys.exit(0 if muertos == len(veredictos) else 1)


if __name__ == "__main__":
    main()
