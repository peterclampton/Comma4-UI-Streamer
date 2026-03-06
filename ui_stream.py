"""MJPEG stream server for sunnypilot UI with telemetry overlay.
Imported lazily when STREAM=1."""
import threading
import io
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

from PIL import Image
import pyray as rl


class StreamState:
    def __init__(self):
        self.frame = b""
        self.lock = threading.Lock()
        self.event = threading.Event()

    def update(self, jpeg):
        with self.lock:
            self.frame = jpeg
        self.event.set()

    def get(self):
        with self.lock:
            return self.frame

    def wait(self, t=2.0):
        self.event.wait(t)
        self.event.clear()


_OVERLAY_HTML = """<!DOCTYPE html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>openpilot live</title>
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#000;overflow:hidden;height:100vh;width:100vw;margin:0;font-family:-apple-system,sans-serif}
#wrap{position:relative;width:100vw;height:100vh;display:flex;justify-content:center;align-items:center}
#cam{width:82%;height:95%;object-fit:contain;margin-left:auto;margin-right:5%}

/* Overlay container - matches image bounds */
#hud{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none}

/* Speed cluster - center bottom */


/* Set speed - top right */
#set-speed{position:absolute;top:18%;left:1%;background:rgba(0,0,0,0.5);border-radius:12px;padding:6px 14px;text-align:center;border:1px solid rgba(255,255,255,0.15)}
#set-label{font-size:min(2.5vw,11px);color:#888;text-transform:uppercase;letter-spacing:1px}
#set-val{font-size:min(7vw,36px);font-weight:600;color:#fff}

/* Lead car info - center top */
#lead-info{position:absolute;top:38%;left:50%;transform:translateX(-50%);text-align:center;opacity:0;transition:opacity 0.3s;background:rgba(0,0,0,0.55);padding:6px 14px;border-radius:8px}
#lead-info.show{opacity:1}
#lead-dist{font-size:min(4.5vw,22px);font-weight:600;color:#fff;text-shadow:0 1px 4px rgba(0,0,0,0.8)}
#lead-gap{font-size:min(3.5vw,16px);font-weight:500;color:#4fc3f7}

/* Status bar - top left */
#status{position:absolute;top:5%;left:1%}
#engage-badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:min(3vw,13px);font-weight:600;letter-spacing:1px;text-transform:uppercase}
#engage-badge.off{background:rgba(100,100,100,0.5);color:#888}
#engage-badge.on{background:rgba(76,175,80,0.3);color:#4caf50;border:1px solid rgba(76,175,80,0.4)}

/* Metrics strip - bottom left/right */
.metric{position:absolute;bottom:4%;font-size:min(3vw,13px);color:#aaa;text-shadow:0 1px 3px rgba(0,0,0,0.8)}
.metric .val{font-size:min(4.5vw,20px);font-weight:600;color:#e0e0e0}
#m-steer{left:4%}
#m-grade{left:1%}
#m-accel{position:absolute;left:50%;top:10%;transform:translateX(-50%);text-align:center;width:min(50vw,220px)}
#accel-label{font-size:min(2.5vw,10px);color:#888;letter-spacing:1px;margin-bottom:2px}
#accel-bar-wrap{display:flex;align-items:center;height:min(2.5vw,12px);background:rgba(255,255,255,0.1);border-radius:6px;overflow:hidden;position:relative}
#accel-bar-neg{height:100%;width:0;background:#f44336;position:absolute;right:50%;border-radius:6px 0 0 6px;transition:width 0.1s}
#accel-bar-pos{height:100%;width:0;background:#4caf50;position:absolute;left:50%;border-radius:0 6px 6px 0;transition:width 0.1s}
#accel-center{position:absolute;left:50%;top:0;bottom:0;width:2px;background:rgba(255,255,255,0.4);transform:translateX(-50%);z-index:1}
#accel-num{font-size:min(4vw,18px);color:#aaa;margin-top:1px}
#m-cpu{right:6%;top:10%;font-size:min(2vw,10px)}

/* Brake/Gas indicators */
#pedals{position:absolute;bottom:15%;left:1%;display:flex;gap:10px;align-items:flex-end}
.pedal-wrap{display:flex;flex-direction:column;align-items:center;gap:2px}
.pedal-label{font-size:min(2.5vw,10px);color:#888;letter-spacing:1px}
.pedal-bar{width:min(4vw,18px);min-height:2px;border-radius:3px;transition:height 0.15s}
.pedal-val{font-size:min(2.5vw,11px);color:#aaa}
#gas-bar{background:#4caf50}
#brake-bar{background:#f44336}
#perf-strip{position:absolute;bottom:1%;left:50%;transform:translateX(-50%);display:flex;gap:min(3vw,14px);background:rgba(0,0,0,0.5);padding:3px 10px;border-radius:6px}
.pf{text-align:center}
.pf-label{font-size:min(1.8vw,8px);color:#666;letter-spacing:0.5px}
.pf-val{font-size:min(2.5vw,12px);color:#888;font-weight:500}
.pf-val.warn{color:#ff9800}
.pf-val.bad{color:#f44336}
</style></head><body>
<div id="wrap">
  <img id="cam" src="/stream">
  <div id="hud"><div ontouchend="event.preventDefault();event.stopPropagation();toggleFS();" onclick="toggleFS()" style="position:absolute;right:1%;top:5%;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.6);font-size:16px;padding:8px 12px;border-radius:8px;pointer-events:auto;z-index:9999;cursor:pointer">&#x26F6;</div>
    <div id="status"><span id="engage-badge" class="off">OFF</span></div>

    <div id="set-speed">
      <div id="set-label">SET</div>
      <div id="set-val">--</div>
    </div>

    <div id="lead-info">
      <div id="lead-dist">--</div>
      <div id="lead-gap">--</div>
    </div>



    
    
    <div id="m-accel">
      <div id="accel-label">ACCEL</div>
      <div id="accel-bar-wrap">
        <div id="accel-bar-neg" class="accel-fill"></div>
        <div id="accel-center"></div>
        <div id="accel-bar-pos" class="accel-fill"></div>
      </div>
      <div id="accel-num">0.0</div>
    </div>
    <div class="metric" id="m-cpu"><div class="val" id="cpu-val">--&deg;</div>cpu</div>

    <div class="metric" id="m-grade"><div class="val" id="grade-val">--%</div>grade</div>
    <div id="pedals">
      <div class="pedal-wrap"><div class="pedal-label">GAS</div><div id="gas-bar" class="pedal-bar"></div><div class="pedal-val" id="gas-val">0</div></div>
      <div class="pedal-wrap"><div class="pedal-label">BRK</div><div id="brake-bar" class="pedal-bar"></div><div class="pedal-val" id="brake-val">0</div></div>
    </div>
    <div id="perf-strip">
      <div class="pf"><div class="pf-label">MODEL</div><div class="pf-val" id="pf-model">--</div></div>
      <div class="pf"><div class="pf-label">DROPS</div><div class="pf-val" id="pf-drops">--</div></div>
      <div class="pf"><div class="pf-label">CPU</div><div class="pf-val" id="pf-cpu">--</div></div>
      <div class="pf"><div class="pf-label">MEM</div><div class="pf-val" id="pf-mem">--</div></div>
    </div>
  </div>
</div>
<script>
let lastData = null;
function poll() {
  fetch('/telemetry').then(r => r.json()).then(d => {
    lastData = d;
    // Speed


    // Set speed
    const sv = document.getElementById('set-val');
    sv.textContent = d.setSpeed > 0 ? d.setSpeed : '--';

    // Engage status
    const badge = document.getElementById('engage-badge');
    const engaged = d.cruiseEnabled === true || d.driveState === 'active';
    const standby = !engaged && (d.driveState === 'standby' || d.cruiseEnabled === false);
    badge.className = engaged ? 'on' : 'off';
    badge.textContent = engaged ? 'ENGAGED' : standby ? 'STANDBY' : 'OFF';

    // Lead car
    const li = document.getElementById('lead-info');
    const isEngaged = d.cruiseEnabled === true || d.driveState === 'active';
    if (isEngaged && d.leadDist !== undefined && d.leadDist !== null) {
      li.className = 'show';
      const ft = Math.round(d.leadDist * 3.28084);
      const egoMph = d.vEgo * 2.23694;
      const gap = d.vEgo > 0.5 ? (d.leadDist / d.vEgo).toFixed(1) : '--';
      document.getElementById('lead-dist').textContent = ft + ' ft';
      document.getElementById('lead-gap').textContent = gap + ' s';
    } else {
      li.className = '';
    }

    // Steer
    

    // Grade
    
    

    // Accel
    const a = d.aEgo || 0;
    const pct = Math.min(Math.abs(a) / 3.0 * 50, 50);
    document.getElementById('accel-bar-pos').style.width = (a > 0 ? pct : 0) + '%';
    document.getElementById('accel-bar-neg').style.width = (a < 0 ? pct : 0) + '%';
    document.getElementById('accel-num').textContent = a.toFixed(1) + ' m/s2';

    // CPU
    if (d.cpuTemp > 0) document.getElementById('cpu-val').textContent = d.cpuTemp + String.fromCharCode(176);

    // Gas/Brake bars
    if (d.grade !== undefined) document.getElementById('grade-val').textContent = d.grade + '%';
    document.getElementById('gas-bar').style.height = Math.max(2, d.gas * 0.6) + 'px';
    document.getElementById('gas-val').textContent = d.gas;
    document.getElementById('brake-bar').style.height = Math.max(2, d.brake * 0.6) + 'px';
    document.getElementById('brake-val').textContent = d.brake;
    if (d.modelExec !== undefined) { var e=document.getElementById("pf-model"); e.textContent=d.modelExec+"ms"; e.className="pf-val"+(d.modelExec>35?" bad":d.modelExec>25?" warn":""); }
    if (d.frameDropPerc !== undefined) { var e=document.getElementById("pf-drops"); e.textContent=d.frameDropPerc+"%"; e.className="pf-val"+(d.frameDropPerc>5?" bad":d.frameDropPerc>1?" warn":""); }
    if (d.cpuUsage !== undefined) { var e=document.getElementById("pf-cpu"); e.textContent=d.cpuUsage+"%"; e.className="pf-val"+(d.cpuUsage>80?" bad":d.cpuUsage>60?" warn":""); }
    if (d.memUsed !== undefined) { var e=document.getElementById("pf-mem"); e.textContent=d.memUsed+"%"; e.className="pf-val"+(d.memUsed>80?" bad":d.memUsed>60?" warn":""); }

  }).catch(() => {});
  setTimeout(poll, 250);
}
document.addEventListener("DOMContentLoaded",function(){
  setTimeout(function(){window.scrollTo(0,1);},100);
  setTimeout(function(){window.scrollTo(0,0);},200);
});
function toggleFS(){var d=document.documentElement;try{if(!document.fullscreenElement&&!document.webkitFullscreenElement){if(d.requestFullscreen)d.requestFullscreen();else if(d.webkitRequestFullscreen)d.webkitRequestFullscreen(Element.ALLOW_KEYBOARD_INPUT);else if(d.webkitEnterFullscreen)d.webkitEnterFullscreen();else alert('Fullscreen not supported');}else{if(document.exitFullscreen)document.exitFullscreen();else if(document.webkitExitFullscreen)document.webkitExitFullscreen();}}catch(e){alert('FS error: '+e);}}
poll();
</script></body></html>"""


class StreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=--frame")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                while True:
                    self.server._state.wait(2.0)
                    f = self.server._state.get()
                    if f:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(f)).encode() + b"\r\n\r\n")
                        self.wfile.write(f)
                        self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path == "/snapshot":
            f = self.server._state.get()
            if f:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(f)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(f)
            else:
                self.send_response(503)
                self.end_headers()
        elif self.path == "/telemetry":
            try:
                with open("/tmp/telemetry.json", "r") as f:
                    data = f.read().encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            except:
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(_OVERLAY_HTML)))
            self.end_headers()
            self.wfile.write(_OVERLAY_HTML.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


_state = None
_counter = 0


def start(port=8082):
    """Start the MJPEG HTTP server in a background thread."""
    global _state
    _state = StreamState()
    srv = ThreadingHTTPServer(("0.0.0.0", port), StreamHandler)
    srv._state = _state
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return _state


def capture_frame(app, quality=50, target_fps=10):
    """Call this from the render loop to capture a frame."""
    global _counter
    if _state is None or app._render_texture is None:
        return
    _counter += 1
    skip = max(1, app._target_fps // target_fps)
    if _counter % skip != 0:
        return
    si = rl.load_image_from_texture(app._render_texture.texture)
    raw = bytes(rl.ffi.buffer(si.data, si.width * si.height * 4))
    rl.unload_image(si)
    img = Image.frombytes("RGBA", (si.width, si.height), raw).transpose(Image.FLIP_TOP_BOTTOM).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    _state.update(buf.getvalue())
