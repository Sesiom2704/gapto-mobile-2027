# ============================================================
# GAPTO MOBILE 2027
# Fichero: servir_web_e2e.py
# Ruta: scripts/dev/servir_web_e2e.py
# Descripcion: Servidor estatico MINIMO, solo loopback, del bundle web del
#   cliente exportado con `npx expo export --platform web`, para los E2E
#   web/viewport (e2e_regcat.py, e2e_vs01.py). Solo desarrollo; no produce
#   veredictos (los E2E son corroboracion, no certificacion de proveedor).
#   - Solo biblioteca estandar de Python (http.server, gzip, mimetypes).
#   - HTTP/1.1 con keep-alive: con el http.server por defecto (HTTP/1.0, cierre
#     de la conexion tras cada respuesta) las descargas grandes (bundle JS,
#     fuente de Ionicons) se cortaban de forma intermitente en Windows
#     (ERR_CONNECTION_RESET); con keep-alive se descargan completas.
#   - Respuestas completas con Content-Length exacto y gzip si el cliente lo
#     acepta. Rutas desconocidas -> index.html (aplicacion de una pagina).
#   - Escucha solo en 127.0.0.1; nunca expone la maquina a la red.
#   Uso:
#     python scripts/dev/servir_web_e2e.py <carpeta_del_export_web> <puerto>
# Version: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
# ============================================================

from __future__ import annotations

import gzip
import mimetypes
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def crear_manejador(raiz: pathlib.Path) -> type[BaseHTTPRequestHandler]:
    class Manejador(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # keep-alive: sin cierre abrupto tras cada respuesta

        def do_GET(self) -> None:  # noqa: N802 (nombre impuesto por http.server)
            ruta = self.path.split("?")[0].lstrip("/") or "index.html"
            f = (raiz / ruta).resolve()
            if (raiz not in f.parents and f != raiz) or not f.is_file():
                f = raiz / "index.html"
            datos = f.read_bytes()
            comprimir = "gzip" in (self.headers.get("Accept-Encoding") or "")
            if comprimir:
                datos = gzip.compress(datos)
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            if comprimir:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)
            self.wfile.flush()

        def log_message(self, *args) -> None:
            pass

    return Manejador


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("Uso: servir_web_e2e.py <carpeta_del_export_web> <puerto>")
    raiz = pathlib.Path(sys.argv[1]).resolve()
    if not (raiz / "index.html").is_file():
        sys.exit(f"{raiz} no contiene index.html (¿se exporto el cliente web?)")
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[2])), crear_manejador(raiz)).serve_forever()


if __name__ == "__main__":
    main()
