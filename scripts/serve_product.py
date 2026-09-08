"""Preview the built website locally, without exposing source data or using paid services."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial
from pathlib import Path

root=Path(__file__).resolve().parents[1]/'dist'
if not (root/'index.html').is_file():
    raise SystemExit('No dist/index.html. Run python scripts/build.py first.')
server=None
for port in range(8080,8101):
    try:
        server=ThreadingHTTPServer(('127.0.0.1',port),partial(SimpleHTTPRequestHandler,directory=str(root)))
        break
    except OSError:
        continue
if server is None:
    raise SystemExit('Ports 8080-8100 are occupied.')
print(f'Open http://127.0.0.1:{server.server_port}/ ; Ctrl+C stops the preview.',flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    server.server_close()
