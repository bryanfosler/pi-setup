#!/usr/bin/env python3
"""
petcam-control.py — Tiny HTTP control server for the petcam service.

Endpoints:
  GET  /status  →  {"running": true/false, "active_state": "active|inactive|failed"}
  POST /start   →  starts petcam, returns updated status
  POST /stop    →  stops petcam, returns updated status

Runs on port 8082. Used by Homebridge (HomeKit) and Piper (Telegram) to
start/stop the petcam without needing SSH access.
"""

import json
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8082


def get_service_status():
    result = subprocess.run(
        ["systemctl", "is-active", "petcam"],
        capture_output=True, text=True
    )
    active_state = result.stdout.strip()
    return {
        "running": active_state == "active",
        "active_state": active_state,
    }


def run_systemctl(action):
    subprocess.run(["sudo", "systemctl", action, "petcam"], capture_output=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress per-request logs

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            self._send_json(get_service_status())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/start":
            run_systemctl("start")
            self._send_json(get_service_status())
        elif self.path == "/stop":
            run_systemctl("stop")
            self._send_json(get_service_status())
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"petcam-control listening on port {PORT}")
    server.serve_forever()
