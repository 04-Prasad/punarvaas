"""Smoke-test a public PUNARVAAS deployment without browser credentials."""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen


def main():
    base = sys.argv[1].rstrip("/")

    def fetch(path):
        with urlopen(base + path, timeout=60) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            if path.startswith("/api/") and not path.endswith("/report"):
                assert "application/json" in content_type, (path, content_type)
                value = json.loads(body)
                if path.endswith("/grid"):
                    assert value["n"] > 0
                if path == "/api/health":
                    assert value["status"] == "ok" and len(value["districts"]) == 2
            elif path.endswith("/report") or path == "/":
                assert b"PUNARVAAS" in body
            else:
                assert "text/html" not in content_type, (path, content_type)
            print(f"OK {path}: {len(body)} bytes", flush=True)
            return body

    page = fetch("/").decode("utf-8")
    paths = ["/api/health", "/api/districts"]
    paths += re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page)
    for district in ("chamoli", "kendrapara"):
        paths += [f"/api/districts/{district}/{endpoint}" for endpoint in
                  ("grid", "habitations", "sites", "plan", "report")]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, paths))
    print(f"Passed {len(paths) + 1} public deployment checks")


if __name__ == "__main__":
    main()
