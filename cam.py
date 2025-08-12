import cv2
import time
import threading
import socket
import psutil
import logging
from flask import Flask, Response, render_template_string
from flask_socketio import SocketIO
import numpy as np
import signal
import sys

# Konfigurasi Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Konfigurasi Kamera
FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
FRAME_RATE = 30
JPEG_QUALITY = 80

# Inisialisasi Flask + SocketIO
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global
camera = None
is_running = True
frame_count = 0
fps_deque = []
last_bandwidth_check = time.time()
last_bytes_sent = 0
latency_samples = []
frame_lock = threading.Lock()

# HTML minimal
HTML_PAGE = """
<!doctype html>
<html>
<head><title>Stream</title></head>
<body>
    <h1>Live Stream</h1>
    <img src="/video_feed" width="800">
    <script src="//cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.min.js"></script>
    <script>
        var socket = io();
        socket.on('stats_update', console.log);
        socket.on('network_stats', console.log);
        socket.on('latency_stats', console.log);
        socket.on('system_stats', console.log);
        socket.on('frame_timestamp', console.log);
    </script>
</body>
</html>
"""

# Halaman utama
@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

# Feed video
@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# Fungsi utama pengambil frame
def generate_frames():
    global frame_count, last_bandwidth_check, last_bytes_sent
    while is_running:
        with frame_lock:
            success, frame = camera.read()
        if not success:
            logger.warning("Frame gagal dibaca")
            continue

        frame_count += 1
        start_time = time.time()

        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not ret:
            continue
        frame_bytes = buffer.tobytes()

        frame_time = time.time() - start_time
        if frame_time > 0.001:
            fps_deque.append(1.0 / frame_time)
        if len(fps_deque) > 30:
            fps_deque.pop(0)

        # Hitung bandwidth
        now = time.time()
        if now - last_bandwidth_check >= 1.0:
            bytes_sent = frame_count * len(frame_bytes)
            bandwidth_kbps = 8 * (bytes_sent - last_bytes_sent) / 1000
            last_bytes_sent = bytes_sent
            last_bandwidth_check = now
            socketio.emit('network_stats', {'bandwidth_kbps': round(bandwidth_kbps, 2)})

        # Emit statistik
        socketio.emit('stats_update', {
            'fps': round(np.mean(fps_deque), 2) if fps_deque else 0,
            'frame_count': frame_count,
            'resolution': f"{FRAME_WIDTH}x{FRAME_HEIGHT}"
        })

        # Timestamp server
        socketio.emit('frame_timestamp', {'server_ts': time.time()})

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# Latency Monitoring
def latency_monitor_thread():
    host = "8.8.8.8"
    port = 53
    timeout = 1

    while is_running:
        start = time.time()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            sock.sendto(b'', (host, port))
            sock.recvfrom(512)
            latency = time.time() - start
            latency_samples.append(latency)
            if len(latency_samples) > 30:
                latency_samples.pop(0)
        except socket.timeout:
            pass
        except Exception as e:
            logger.warning(f"Latency monitor error: {e}")
        finally:
            sock.close()

        if len(latency_samples) >= 5:
            try:
                diffs = [abs(latency_samples[i] - latency_samples[i - 1]) for i in range(1, len(latency_samples))]
                jitter = sum(diffs) / len(diffs)
                avg_latency = sum(latency_samples) / len(latency_samples)
                socketio.emit('latency_stats', {
                    'avg_latency_ms': round(avg_latency * 1000, 2),
                    'jitter_ms': round(jitter * 1000, 2)
                })
            except Exception as e:
                logger.warning(f"Gagal hitung latency/jitter: {e}")

        time.sleep(1)

# System stats
def system_stats_thread():
    while is_running:
        try:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            socketio.emit('system_stats', {
                'cpu_percent': cpu,
                'mem_percent': mem
            })
        except Exception as e:
            logger.warning(f"Gagal ambil system stats: {e}")
        time.sleep(1)

# Inisialisasi kamera
def init_camera():
    global camera
    for source in [0, 1, '/dev/video0', '/dev/video1']:
        try:
            cam = cv2.VideoCapture(source)
            if cam.isOpened():
                cam.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
                cam.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
                cam.set(cv2.CAP_PROP_FPS, FRAME_RATE)
                logger.info(f"Camera opened successfully from source: {source}")
                return cam
        except Exception as e:
            logger.warning(f"Camera source {source} failed: {e}")
    raise RuntimeError("Gagal membuka kamera dari semua source")

# Shutdown
def signal_handler(sig, frame):
    global is_running
    logger.info("Shutdown signal received. Cleaning up...")
    is_running = False
    if camera and camera.isOpened():
        camera.release()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# MAIN
if __name__ == '__main__':
    try:
        camera = init_camera()
        threading.Thread(target=latency_monitor_thread, daemon=True).start()
        threading.Thread(target=system_stats_thread, daemon=True).start()
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except Exception as e:
        logger.error(f"Main error: {e}")
        signal_handler(None, None)
