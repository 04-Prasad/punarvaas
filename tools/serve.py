"""
A minimal ASGI server, so the whole system runs with nothing installed.

This exists for one reason: uvicorn is not in the standard library, and a district
officer or a reviewer on an air-gapped machine should still be able to start the
console. It speaks enough HTTP/1.1 to serve the API and the static console —
request line, headers, Content-Length bodies, keep-alive, and the ASGI 3.0
`http` scope. It is not a production server and does not pretend to be: no TLS,
no HTTP/2, no websockets, no worker pool.

    python -m tools.serve --port 8000

Production runs uvicorn. Both drive the identical FastAPI app, so there is no
second code path to keep correct.

NOTE ON ACCESS CONTROL: this server binds 127.0.0.1 by default and has **no
authentication**. Every endpoint is read-only and the data is advisory, but the
provenance card does expose per-cell population counts. Do not bind it to a
public interface without putting an authenticating reverse proxy in front.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import traceback
from urllib.parse import unquote, urlsplit

MAX_HEADER_BYTES = 64 * 1024
MAX_BODY_BYTES = 8 * 1024 * 1024
STATUS_TEXT = {200: "OK", 204: "No Content", 304: "Not Modified",
               400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed",
               413: "Payload Too Large", 422: "Unprocessable Entity",
               500: "Internal Server Error"}


class Protocol(asyncio.Protocol):
    def __init__(self, app, server: str):
        self.app, self.server_hdr = app, server
        self.buf = bytearray()
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data: bytes):
        self.buf += data
        if len(self.buf) > MAX_HEADER_BYTES + MAX_BODY_BYTES:
            self._fail(413)
            return
        while True:
            head_end = self.buf.find(b"\r\n\r\n")
            if head_end < 0:
                if len(self.buf) > MAX_HEADER_BYTES:
                    self._fail(400)
                return
            head = bytes(self.buf[:head_end])
            try:
                req = self._parse(head)
            except ValueError:
                self._fail(400)
                return
            need = head_end + 4 + req["length"]
            if len(self.buf) < need:
                return                       # body still arriving
            req["body"] = bytes(self.buf[head_end + 4:need])
            del self.buf[:need]
            asyncio.get_running_loop().create_task(self._handle(req))

    # ── HTTP/1.1 (the subset we need) ───────────────────────────────────────
    @staticmethod
    def _parse(head: bytes) -> dict:
        lines = head.split(b"\r\n")
        method, target, version = lines[0].decode("latin-1").split(" ")
        if not version.startswith("HTTP/1."):
            raise ValueError(version)
        headers, length, keep = [], 0, version == "HTTP/1.1"
        for line in lines[1:]:
            if not line or b":" not in line:
                continue
            k, v = line.split(b":", 1)
            k = k.strip().lower()
            v = v.strip()
            headers.append((k, v))
            if k == b"content-length":
                length = int(v)
                if length > MAX_BODY_BYTES:
                    raise ValueError("body too large")
            elif k == b"connection":
                keep = v.lower() != b"close"
        u = urlsplit(target)
        return {"method": method, "path": unquote(u.path) or "/",
                "query": u.query.encode("latin-1"), "headers": headers,
                "length": length, "keep": keep}

    def _write_head(self, status: int, headers: list[tuple[bytes, bytes]], keep: bool):
        text = STATUS_TEXT.get(status, "OK")
        out = [f"HTTP/1.1 {status} {text}\r\n".encode("latin-1")]
        seen = {k.lower() for k, _ in headers}
        for k, v in headers:
            out.append(k + b": " + v + b"\r\n")
        if b"server" not in seen:
            out.append(b"server: " + self.server_hdr.encode() + b"\r\n")
        out.append(b"connection: " + (b"keep-alive" if keep else b"close") + b"\r\n\r\n")
        self.transport.write(b"".join(out))

    def _fail(self, status: int):
        body = STATUS_TEXT.get(status, "Error").encode()
        self._write_head(status, [(b"content-type", b"text/plain"),
                                  (b"content-length", str(len(body)).encode())], False)
        self.transport.write(body)
        self.transport.close()

    # ── ASGI 3.0 bridge ─────────────────────────────────────────────────────
    async def _handle(self, req: dict):
        peer = self.transport.get_extra_info("peername") or ("", 0)
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
                 "http_version": "1.1", "method": req["method"],
                 "scheme": "http", "path": req["path"], "raw_path": req["path"].encode(),
                 "query_string": req["query"], "root_path": "",
                 "headers": req["headers"], "client": (peer[0], peer[1]),
                 "server": ("127.0.0.1", 0)}
        sent_body = bytearray()
        state = {"status": 200, "headers": [], "started": False}
        body_sent = False

        async def receive():
            return {"type": "http.request", "body": req["body"], "more_body": False}

        async def send(msg):
            nonlocal body_sent
            if msg["type"] == "http.response.start":
                state["status"] = msg["status"]
                state["headers"] = [(k, v) for k, v in msg.get("headers", [])]
                state["started"] = True
            elif msg["type"] == "http.response.body":
                sent_body.extend(msg.get("body", b""))
                if not msg.get("more_body", False):
                    body_sent = True

        try:
            await self.app(scope, receive, send)
        except Exception:                                    # noqa: BLE001
            traceback.print_exc()
            if not state["started"]:
                self._fail(500)
                return
        hdrs = [(k, v) for k, v in state["headers"]
                if k.lower() not in (b"content-length", b"connection")]
        hdrs.append((b"content-length", str(len(sent_body)).encode()))
        self._write_head(state["status"], hdrs, req["keep"])
        if req["method"] != "HEAD":
            self.transport.write(bytes(sent_body))
        if not req["keep"]:
            self.transport.close()


async def serve(app, host: str, port: int, name: str = "punarvaas/0.9"):
    loop = asyncio.get_running_loop()
    server = await loop.create_server(lambda: Protocol(app, name), host, port)
    for s in server.sockets or []:
        h, p = s.getsockname()[:2]
        print(f"  PUNARVAAS console  http://{h}:{p}/")
        print(f"  API docs           http://{h}:{p}/api/docs")
    print("  (stdlib ASGI server — no authentication; do not expose publicly)")
    async with server:
        await server.serve_forever()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the PUNARVAAS API with no deps")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)
    from api.main import app
    try:
        asyncio.run(serve(app, a.host, a.port))
    except KeyboardInterrupt:
        print("\n  stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
