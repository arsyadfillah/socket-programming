import socket
import threading
import time
from datetime import datetime

# ========== KONFIGURASI ==========
PROXY_HOST, TCP_PORT, UDP_PORT = '0.0.0.0', 8080, 9090
WEB_SERVER_IP, WEB_SERVER_PORT = '192.168.0.102', 8000
TIMEOUT, MAX_THREADS, BUFFER_SIZE = 10, 20, 4096
CACHE_TIMEOUT = 15
running = True

# ========== CACHE DENGAN TIMEOUT ==========
class Cache:
    def __init__(self, timeout=15):
        self.cache = {}
        self.hits = self.misses = 0
        self.timeout = timeout
    
    def get(self, key):
        if key in self.cache:
            val, t = self.cache[key]
            if time.time() - t > self.timeout:
                del self.cache[key]
                self.misses += 1
                return None
            self.hits += 1
            return val
        self.misses += 1
        return None
    
    def set(self, key, value):
        self.cache[key] = (value, time.time())
    
    def clean(self):
        expired = [k for k, (_, t) in self.cache.items() 
                  if time.time() - t > self.timeout]
        for k in expired: 
            del self.cache[k]
        return len(expired)
    
    def stats(self):
        self.clean()
        total = self.hits + self.misses
        rate = (self.hits / total * 100) if total > 0 else 0
        return {'size': len(self.cache), 'hits': self.hits, 
                'misses': self.misses, 'rate': rate}

cache = Cache(CACHE_TIMEOUT)

# ========== THREAD POOL ==========
class ThreadPool:
    def __init__(self, max_workers):
        self.semaphore = threading.Semaphore(max_workers)
        self.active = 0
    
    def submit(self, target, args):
        self.semaphore.acquire()
        self.active += 1
        def worker():
            target(*args)
            self.semaphore.release()
            self.active -= 1
        threading.Thread(target=worker, daemon=True).start()

pool = None

# ========== CACHE CLEANER ==========
def cache_cleaner():
    while running:
        time.sleep(5)
        cleaned = cache.clean()
        if cleaned > 0:
            print(f"🧹 Removed {cleaned} expired items")

# ========== STATISTICS ==========
def stats_monitor():
    while running:
        time.sleep(10)
        s = cache.stats()
        print(f"📊 Threads: {pool.active}/{MAX_THREADS} | "
              f"Cache: {s['hits']}H/{s['misses']}M ({s['rate']:.1f}%) | "
              f"Size: {s['size']}")

# ========== LOGGING ==========
def log(proto, client, target, cache_stat, size, proc_time):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {proto} | {client[0]}:{client[1]} → "
          f"{target} | Cache:{cache_stat:4} | Bytes:{size:6} | Time:{proc_time:.3f}s")

# ========== UDP HANDLER ==========
def udp_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((PROXY_HOST, UDP_PORT))
    print(f"✅ UDP: Port {UDP_PORT} | ECHO mode")
    
    while running:
        try:
            data, client = sock.recvfrom(BUFFER_SIZE)
            if len(data) >= 500:
                sock.sendto(data, client)
                log('UDP', client, "PROXY:ECHO", 'N/A', len(data), 0.001)
            else:
                sock.sendto(data, (WEB_SERVER_IP, 9000))
                log('UDP', client, f"{WEB_SERVER_IP}:{9000}", 'N/A', len(data), 0.001)
        except: pass

# ========== TCP HANDLER ==========
def tcp_handler(client_sock, client_addr):
    start = time.time()
    try:
        client_sock.settimeout(TIMEOUT)
        request = client_sock.recv(BUFFER_SIZE)
        
        req_str = request.decode('utf-8', errors='ignore')
        if req_str.startswith('GET'):
            path = req_str.split()[1]
            if path == '/index': req_str = req_str.replace('/index', '/index.html')
            elif path == '/test': req_str = req_str.replace('/test', '/test.html')
            request = req_str.encode()
        
        cache_stat = 'MISS'
        if request.startswith(b'GET'):
            key = req_str.split('\r\n')[0] if req_str else request.split(b'\r\n')[0]
            cached = cache.get(key)
            if cached:
                client_sock.sendall(cached)
                log('TCP', client_addr, f"{WEB_SERVER_IP}:{WEB_SERVER_PORT}", 
                    'HIT', len(cached), time.time()-start)
                return
        
        with socket.create_connection((WEB_SERVER_IP, WEB_SERVER_PORT), timeout=TIMEOUT) as s:
            s.sendall(request)
            response = b''
            while True:
                try:
                    chunk = s.recv(BUFFER_SIZE)
                    if not chunk: break
                    response += chunk
                except socket.timeout: break
            
            if response:
                client_sock.sendall(response)
                if cache_stat == 'MISS' and b'200 OK' in response and request.startswith(b'GET'):
                    cache.set(key, response)
                log('TCP', client_addr, f"{WEB_SERVER_IP}:{WEB_SERVER_PORT}", 
                    cache_stat, len(request)+len(response), time.time()-start)
            else:
                client_sock.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                log('TCP', client_addr, f"{WEB_SERVER_IP}:{WEB_SERVER_PORT}", 
                    cache_stat, 0, time.time()-start)
    except socket.timeout:
        client_sock.sendall(b"HTTP/1.1 504 Gateway Timeout\r\n\r\n")
        log('TCP', client_addr, f"{WEB_SERVER_IP}:{WEB_SERVER_PORT}", 
            cache_stat, 0, time.time()-start)
    except: pass
    finally: 
        try: client_sock.close()
        except: pass

# ========== MAIN SERVER ==========
def start_proxy():
    global running, pool
    
    print("="*50)
    print(f"🚀 PROXY | TCP:{TCP_PORT} | UDP:{UDP_PORT}")
    print(f"📡 Target: {WEB_SERVER_IP}:{WEB_SERVER_PORT}")
    print("="*50)
    
    pool = ThreadPool(MAX_THREADS)
    
    threading.Thread(target=udp_server, daemon=True).start()
    threading.Thread(target=cache_cleaner, daemon=True).start()
    threading.Thread(target=stats_monitor, daemon=True).start()
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((PROXY_HOST, TCP_PORT))
    sock.listen(100)
    sock.settimeout(1.0)
    print(f"✅ TCP: Port {TCP_PORT} | Threads: {MAX_THREADS}")
    print("📊 Stats setiap 10 detik")
    print("="*50)
    
    try:
        while running:
            try:
                client, addr = sock.accept()
                pool.submit(tcp_handler, (client, addr))
            except socket.timeout:
                continue
    except KeyboardInterrupt:
        print("\n⚠️  Shutting down...")
    
    running = False
    sock.close()
    time.sleep(1)
     
if __name__ == "__main__":
    try:
        start_proxy()
    except KeyboardInterrupt:
        print("\n🛑 Forced exit")
        print("\n" + "="*50)
        s = cache.stats()
        print(f"📊 FINAL STATS")
        print("-"*50)
        print(f"• Threads: {pool.active}/{MAX_THREADS}")
        print(f"• Cache: {s['hits']}H/{s['misses']}M ({s['rate']:.1f}%)")
        print(f"• Cache Size: {s['size']} items")
        print("="*50)
        print("✅ Proxy stopped")
        print("="*50)