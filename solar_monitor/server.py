#!/usr/bin/env python3
"""
ARSolar - Servidor Web Local
Serve o dashboard.html e expõe o endpoint /refresh para acionar o monitor sob demanda.
Não requer dependências externas além do Python padrão.
"""
import os
import sys
import subprocess
import json
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

DIR_PATH    = os.path.dirname(os.path.abspath(__file__))
DASHBOARD   = os.path.join(DIR_PATH, "dashboard.html")
MONITOR     = os.path.join(DIR_PATH, "monitor.py")
PORT        = 8765

_refresh_lock = threading.Lock()
_refresh_status = {"running": False, "last_msg": ""}

# ─────────────────────────────────────────────────────────────────────────────
class ARSolarHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for the ARSolar dashboard."""

    def log_message(self, fmt, *args):
        # Suppress default Apache-style access log
        pass

    # ── GET  ──────────────────────────────────────────────────────────────────
    def do_GET(self):
        if self.path in ('/', '/dashboard.html', '/index.html'):
            self._serve_dashboard()
        elif self.path == '/status':
            self._json_response({"running": _refresh_status["running"],
                                  "last_msg": _refresh_status["last_msg"]})
        else:
            self.send_error(404, "Not found")

    # ── POST ──────────────────────────────────────────────────────────────────
    def do_POST(self):
        if self.path == '/refresh':
            self._do_refresh()
        else:
            self.send_error(404, "Not found")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _serve_dashboard(self):
        try:
            with open(DASHBOARD, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(503, "dashboard.html not found - run monitor.py first")

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _do_refresh(self):
        global _refresh_status

        # If already running, return immediately
        if not _refresh_lock.acquire(blocking=False):
            self._json_response({"status": "running",
                                  "message": "Atualização já em andamento, aguarde..."})
            return

        _refresh_status["running"] = True
        _refresh_status["last_msg"] = ""

        try:
            result = subprocess.run(
                [sys.executable, MONITOR, "--force"],
                capture_output=True, text=True,
                timeout=180, cwd=DIR_PATH,
                encoding='utf-8', errors='replace'
            )
            success = result.returncode == 0
            msg = (result.stdout + result.stderr).strip()
            _refresh_status["last_msg"] = msg

            self._json_response({
                "status":  "ok" if success else "error",
                "message": msg
            })
        except subprocess.TimeoutExpired:
            self._json_response({"status": "error",
                                  "message": "Tempo esgotado (>3 min). Verifique a conexão."})
        except Exception as e:
            self._json_response({"status": "error", "message": str(e)})
        finally:
            _refresh_status["running"] = False
            _refresh_lock.release()

# ─────────────────────────────────────────────────────────────────────────────
def main():
    # Run an initial monitor sweep on startup if dashboard doesn't exist yet
    if not os.path.exists(DASHBOARD):
        print("Dashboard não encontrado. Rodando varredura inicial...")
        subprocess.run([sys.executable, MONITOR, "--force"], cwd=DIR_PATH)

    server = HTTPServer(('localhost', PORT), ARSolarHandler)
    url    = f"http://localhost:{PORT}"

    print("=" * 55)
    print("  ☀️  ARSolar Monitor — Servidor Local")
    print("=" * 55)
    print(f"  Dashboard: {url}")
    print(f"  Pressione Ctrl+C para encerrar.")
    print("=" * 55)

    # Open browser automatically
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")

if __name__ == '__main__':
    main()
