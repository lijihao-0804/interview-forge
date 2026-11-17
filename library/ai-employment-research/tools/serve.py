"""Local-only static preview. Standard library, no package installation."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

class Handler(SimpleHTTPRequestHandler):
    extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.mjs':'text/javascript','.json':'application/json','.gz':'application/gzip','.md':'text/plain; charset=utf-8'}
    def end_headers(self):
        self.send_header('Cache-Control','no-cache')
        super().end_headers()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(root)))
    print(f'本地预览: http://127.0.0.1:{server.server_port}/  (Ctrl+C 停止)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
