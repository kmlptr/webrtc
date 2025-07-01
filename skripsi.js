document.addEventListener('DOMContentLoaded', function() {
    const ipInput = document.getElementById('ipInput');
    const connectButton = document.getElementById('connectButton');
    const disconnectButton = document.getElementById('disconnectButton');
    const connectionStatus = document.getElementById('connectionStatus');
    const videoFeed = document.getElementById('videoFeed');
    const errorDisplay = document.getElementById('error');
    const ipAddressStat = document.getElementById('ipAddressStat');
    const portStat = { textContent: '5000' };

    let currentIP = '';
    const currentPort = '5000';
    let socket = null;
    let connectionTimeout = null;
    let frameCount = 0;
    let fpsInterval = null;

    function validateIP(ip) {
        const parts = ip.split('.');
        if (parts.length !== 4) return false;
        for (const part of parts) {
            const num = parseInt(part, 10);
            if (isNaN(num) || num < 0 || num > 255 || part !== num.toString()) return false;
        }
        return true;
    }

    connectButton.addEventListener('click', connectToCamera);
    disconnectButton.addEventListener('click', disconnectFromCamera);
    ipInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') connectToCamera();
    });

    function connectToCamera() {
        const ipAddress = ipInput.value.trim();
        if (!validateIP(ipAddress)) {
            connectionStatus.innerHTML = '<span style="color: red">Format IP tidak valid. Gunakan format X.X.X.X (0-255)</span>';
            return;
        }
        if (socket) socket.disconnect();
        connectButton.disabled = true;
        connectionStatus.innerHTML = '<span style="color: blue">Menghubungkan...</span> <div class="loading"></div>';
        errorDisplay.textContent = '';
        currentIP = ipAddress;
        videoFeed.src = `http://${ipAddress}:${currentPort}/video_feed?ts=${Date.now()}`;
        connectionTimeout = setTimeout(() => onConnectionFailed("Timeout: Perangkat tidak merespon"), 15000);
        videoFeed.onload = function() {
            frameCount++;
            onConnectionSuccess();
        };
        videoFeed.onerror = function() {
            onConnectionFailed("Gagal terhubung ke feed video");
        };
    }

    function onConnectionSuccess() {
        clearTimeout(connectionTimeout);
        connectionStatus.innerHTML = '<span style="color: green">Terhubung!</span>';
        connectButton.style.display = 'none';
        disconnectButton.style.display = 'block';
        ipAddressStat.textContent = currentIP;
        portStat.textContent = currentPort;
        initializeSocketConnection(currentIP, currentPort);
        saveConnectionInfo(currentIP);
        fpsInterval = setInterval(() => {
            document.getElementById('fps').textContent = frameCount;
            frameCount = 0;
        }, 1000);
    }

    function onConnectionFailed(message) {
        clearTimeout(connectionTimeout);
        connectionStatus.innerHTML = `<span style="color: red">${message}</span>`;
        connectButton.disabled = false;
        connectButton.style.display = 'block';
        disconnectButton.style.display = 'none';
        errorDisplay.textContent = 'Pastikan: 1) Server berjalan , 2) Port 5000 terbuka, 3) Tidak ada blok firewall';
    }

    function disconnectFromCamera() {
        if (socket) {
            socket.disconnect();
            socket = null;
        }
        videoFeed.src = '';
        videoFeed.onload = null;
        videoFeed.onerror = null;
        connectionStatus.innerHTML = '<span style="color: orange">Koneksi diputuskan</span>';
        connectButton.style.display = 'block';
        disconnectButton.style.display = 'none';
        connectButton.disabled = false;
        ipAddressStat.textContent = '-';
        document.getElementById('latency').textContent = '-';
        document.getElementById('packetLoss').textContent = '-';
        document.getElementById('jitter').textContent = '-';
        document.getElementById('throughput').textContent = '-';
        document.getElementById('fps').textContent = '-';
        if (fpsInterval) clearInterval(fpsInterval);
    }

    function initializeSocketConnection(ip, port) {
        socket = io(`http://${ip}:${port}`);
        socket.on('network_stats', function(data) {
            document.getElementById('latency').textContent = data.latency + ' ms';
            document.getElementById('packetLoss').textContent = data.packetLoss + '%';
            document.getElementById('jitter').textContent = data.jitter + ' ms';
            document.getElementById('throughput').textContent = data.bandwidth + ' Mbps';
            if (data.fps !== undefined) {
                document.getElementById('fps').textContent = data.fps;
            }
        });
        socket.on('connect', () => errorDisplay.textContent = '');
        socket.on('disconnect', () => {
            errorDisplay.textContent = 'Koneksi terputus. Coba hubungkan kembali.';
            disconnectFromCamera();
        });
        socket.on('connect_error', (err) => {
            errorDisplay.textContent = 'Koneksi error: ' + err.message;
            disconnectFromCamera();
        });
    }

    function saveConnectionInfo(ip) {
        localStorage.setItem('lastConnection', JSON.stringify({ ip: ip, timestamp: new Date().getTime() }));
    }

    function loadLastConnection() {
        const lastConnection = localStorage.getItem('lastConnection');
        if (lastConnection) {
            try {
                const conn = JSON.parse(lastConnection);
                ipInput.value = conn.ip;
            } catch (e) {
                console.error('Error loading last connection:', e);
            }
        }
    }

    loadLastConnection();
    ipInput.focus();
});
