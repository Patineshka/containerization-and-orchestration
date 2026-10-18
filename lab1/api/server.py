#!/usr/bin/env python3
"""Подопытный HTTP-сервис для лабораторной по контейнеризации."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

allocations = []
allocation_lock = threading.Lock()
burn_lock = threading.Lock()
burn_started = False


def burn():
    value = 0
    while True:
        value = (value + 1) % 1000003


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        payload = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        global burn_started
        request = urlparse(self.path)
        if request.path == '/health':
            self.reply(200, 'ok')
        elif request.path == '/eat':
            try:
                mb = int(parse_qs(request.query).get('mb', [''])[0])
                if mb <= 0:
                    raise ValueError()
            except ValueError:
                self.reply(400, 'mb must be a positive integer')
                return
            try:
                block = bytearray(mb * 1024 * 1024)
                # Touch pages so RSS reflects the allocation even with lazy allocation.
                for offset in range(0, len(block), 4096):
                    block[offset] = 1
                with allocation_lock:
                    allocations.append(block)
                    total = sum(len(item) for item in allocations)
                self.reply(200, json.dumps({'held_bytes': total}))
            except MemoryError:
                self.reply(503, 'allocation failed')
        elif request.path == '/burn':
            with burn_lock:
                if not burn_started:
                    threading.Thread(target=burn, daemon=True).start()
                    burn_started = True
            self.reply(200, 'CPU load started')
        else:
            self.reply(404, 'not found')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8080'))
    print(f'api pid={os.getpid()} listening on 0.0.0.0:{port}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
