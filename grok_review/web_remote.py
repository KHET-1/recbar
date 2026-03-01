"""Mobile web remote — control OBS from your phone.

Serves a responsive HTML page on http://IP:PORT?token=XXX with buttons for
recording, pause, mic, scene switching, reactions, chapters, and bar sizing.

Token auth: a random token is generated on launch and printed to console.
All requests require ?token=XXX or are rejected with 403.

Auto-refreshes status every 2 seconds via /status JSON endpoint.
"""

import json
import os
import secrets
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from .config import WEB_PORT
from .ipc import send_command

# Generate auth token on import (once per launch)
AUTH_TOKEN = secrets.token_urlsafe(16)

# ── Embedded mobile HTML ───────────────────────────────────

MOBILE_HTML = r"""<!DOCTYPE html>
<html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RecBar Remote</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#1a1a2e;color:#eee;padding:16px;
     max-width:480px;margin:0 auto}
h1{text-align:center;color:#00bcd4;font-size:22px;margin:12px 0}
h2{color:#607d8b;font-size:14px;margin:16px 0 6px;text-transform:uppercase;letter-spacing:1px}
.status{text-align:center;padding:10px;background:#0d0d1a;border-radius:8px;
        margin:8px 0;font-size:13px;color:#aaa}
.row{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0}
.btn{flex:1;min-width:60px;padding:12px 8px;border:1px solid #2a2a4e;border-radius:8px;
     background:#222240;color:#eee;font-size:14px;cursor:pointer;text-align:center;
     transition:background 0.15s,transform 0.1s}
.btn:active{background:#3a3a6e;transform:scale(0.96)}
.btn-rec{background:#b71c1c;border-color:#d32f2f;font-weight:bold}
.btn-rec.recording{background:#d32f2f;box-shadow:0 0 12px rgba(211,47,47,0.5)}
.btn-scene{border-color:#2196F3}
.btn-scene.active{background:#1a3a5e;border-color:#64b5f6}
.btn-react{font-size:22px;padding:10px}
input{width:100%;padding:10px;background:#222240;color:#eee;border:1px solid #2a2a4e;
      border-radius:6px;font-size:14px;margin:4px 0}
.chapters{font-size:12px;color:#888;margin:6px 0}
.chapters div{padding:2px 0;border-left:2px solid #2a2a4e;padding-left:8px;margin:2px 0}
.footer{text-align:center;color:#333;font-size:11px;margin-top:24px}
</style>
</head><body>
<h1>&#9889; RecBar Remote</h1>
<div id="status" class="status">Connecting...</div>
<h2>Recording</h2>
<div class="row">
<button class="btn btn-rec" id="recBtn" onclick="send('rec')">&#9210; REC</button>
<button class="btn" onclick="send('pause')">&#9208; PAUSE</button>
<button class="btn" onclick="send('mic')">&#127908; MIC</button>
</div>
<h2>Scenes</h2>
<div id="scenes" class="row"></div>
<h2>Reactions</h2>
<div class="row">
<button class="btn btn-react" onclick="send('react:&#128293;')">&#128293;</button>
<button class="btn btn-react" onclick="send('react:&#128077;')">&#128077;</button>
<button class="btn btn-react" onclick="send('react:&#10084;')">&#10084;</button>
<button class="btn btn-react" onclick="send('react:&#128640;')">&#128640;</button>
<button class="btn btn-react" onclick="send('react:&#128175;')">&#128175;</button>
<button class="btn btn-react" onclick="send('react:&#127881;')">&#127881;</button>
</div>
<h2>Chapter Mark</h2>
<input id="ch" placeholder="Chapter title..." onkeydown="if(event.key==='Enter')addCh()">
<div class="row">
<button class="btn" onclick="addCh()">+ Add Chapter</button>
</div>
<div id="chapters" class="chapters"></div>
<h2>Bar Size</h2>
<div class="row">
<button class="btn" onclick="send('size1')">Slim</button>
<button class="btn" onclick="send('size2')">Medium</button>
<button class="btn" onclick="send('size3')">Large</button>
</div>
<h2>Auto-Scene</h2>
<div class="row">
<button class="btn" id="autoBtn" onclick="toggleAuto()">OFF</button>
</div>
<div class="footer">RecBar &mdash; OBS Recording Companion</div>
<script>
var T=new URLSearchParams(location.search).get('token')||'';
function send(c){fetch('/cmd?token='+T,{method:'POST',body:c}).then(()=>{
var s=document.getElementById('status');s.textContent='Sent: '+c;
setTimeout(poll,500)}).catch(()=>{})}
function addCh(){var t=document.getElementById('ch').value;
if(t){send('chapter:'+t);document.getElementById('ch').value=''}}
function toggleAuto(){var b=document.getElementById('autoBtn');
var on=b.textContent==='OFF';send('auto_scene:'+(on?'on':'off'));
b.textContent=on?'ON':'OFF';b.style.background=on?'#1b5e20':'#222240'}
function poll(){fetch('/status?token='+T).then(r=>r.json()).then(s=>{
var st=(s.recording?(s.paused?'&#9208; PAUSED':'&#128308; REC ')+s.rec_time:'&#9899; IDLE');
st+=' | '+s.scene+(s.mic?' | &#127908; ON':' | &#128263; OFF');
if(s.disk>=0)st+=' | '+s.disk.toFixed(1)+'GB';
document.getElementById('status').innerHTML=st;
var rb=document.getElementById('recBtn');
if(s.recording){rb.classList.add('recording')}else{rb.classList.remove('recording')}
var sd=document.getElementById('scenes');
sd.innerHTML=s.scenes.map(n=>'<button class="btn btn-scene'+(n===s.scene?' active':'')+
'" onclick="send(\'scene:'+n+'\')">'+n+'</button>').join('');
var cd=document.getElementById('chapters');
if(s.chapters&&s.chapters.length)cd.innerHTML=s.chapters.map(c=>'<div>'+c+'</div>').join('');
else cd.innerHTML='';
}).catch(()=>{})}
setInterval(poll,2000);poll()
</script>
</body></html>"""


class RemoteHandler(BaseHTTPRequestHandler):
    """HTTP handler for the mobile web remote."""

    state = None
    chapters = None

    def _check_auth(self):
        """Verify token parameter. Returns True if authorized."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token = params.get('token', [None])[0]
        if token != AUTH_TOKEN:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'Forbidden - invalid or missing token')
            return False
        return True

    @property
    def _clean_path(self):
        """Return path without query string."""
        return urlparse(self.path).path

    def do_GET(self):
        if not self._check_auth():
            return
        path = self._clean_path
        if path == '/':
            self._respond(200, 'text/html', MOBILE_HTML.encode())
        elif path == '/status':
            s = self.state
            payload = json.dumps({
                'recording': s.recording,
                'paused': s.paused,
                'rec_time': s.rec_time,
                'scene': s.scene,
                'scenes': s.scenes,
                'mic': s.mic_active,
                'disk': round(s.disk_free_gb, 1),
                'chapters': self.chapters.format_chapters() if self.chapters else [],
            })
            self._respond(200, 'application/json', payload.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if not self._check_auth():
            return
        path = self._clean_path
        if path == '/cmd':
            length = int(self.headers.get('Content-Length', 0))
            cmd = self.rfile.read(length).decode()
            send_command(cmd)
            self._respond(200, 'text/plain', b'ok')
        else:
            self.send_response(404)
            self.end_headers()

    def _respond(self, code, content_type, body):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # Suppress HTTP access logs


class MobileServer(threading.Thread):
    """Background thread running the mobile web remote HTTP server."""

    def __init__(self, state, chapters, port=WEB_PORT):
        super().__init__(daemon=True)
        self.port = port
        RemoteHandler.state = state
        RemoteHandler.chapters = chapters

    def run(self):
        try:
            server = HTTPServer(('0.0.0.0', self.port), RemoteHandler)
            server.serve_forever()
        except OSError as e:
            import sys
            print(f"  WARNING: Web remote failed to start on port {self.port}: {e}",
                  file=sys.stderr)


def get_local_ip():
    """Get the LAN IP address for displaying the remote URL."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def get_remote_url():
    """Get the full authenticated remote URL."""
    ip = get_local_ip()
    return f"http://{ip}:{WEB_PORT}?token={AUTH_TOKEN}"
