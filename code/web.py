import socket, threading, time, os
from datetime import datetime

HOST       = "0.0.0.0"
TCP_PORT   = 8000
UDP_PORT   = 9000
BACKLOG    = 5
BUF_SIZE   = 4096
TIMEOUT    = 5

server_running = True
mode = "threaded"   # "single" atau "threaded"
conn_id = 0

# ---------- HTTP HANDLER ----------

def handle_http(client, addr, conn_no):  # NEW: tambah conn_no
    start = time.time()
    client.settimeout(TIMEOUT)

    try:
        data = client.recv(BUF_SIZE)
        if not data:
            return

        # parse request line
        req_line = data.decode(errors="ignore").split("\r\n")[0]
        parts = req_line.split()
        if len(parts) < 3:
            return

        method, path, _ = parts
        if method not in ("GET", "HEAD"):
            body = f"<h1>501 Not Implemented</h1><p>{method} not supported</p>"
            resp = (
                "HTTP/1.1 501 Not Implemented\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
                f"{body}"
            )
            client.sendall(resp.encode())
            return

        # resolve path -> filename
        if path == "/" or path == "":
            filename = "index.html"
        else:
            filename = path.lstrip("/").split("?")[0] or "index.html"

        filepath = os.path.join("static", filename)

        if os.path.isfile(filepath):
            with open(filepath, "rb") as f:
                content = f.read()

            ctype = "text/html; charset=utf-8"
            header = (
                "HTTP/1.1 200 OK\r\n"
                f"Content-Type: {ctype}\r\n"
                f"Content-Length: {len(content)}\r\n"
                "Connection: close\r\n\r\n"
            )
            client.sendall(header.encode())
            if method == "GET":
                client.sendall(content)
            status = 200
            size = len(content)
        else:
            body = f"<h1>404 Not Found</h1><p>{filename} tidak ditemukan</p>"
            resp = (
                "HTTP/1.1 404 Not Found\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
                f"{body}"
            )
            client.sendall(resp.encode())
            status = 404
            size = len(body)

        # LOG singkat
        dur = (time.time() - start) * 1000
        print(
            f"[HTTP][Conn #{conn_no}] {datetime.now()} "   # NEW: tampilkan Connection #
            f"{addr[0]}:{addr[1]} \"{method} {path}\" {status} "
            f"size={size}B time={dur:.1f}ms"
        )

    except Exception as e:
        print(f"[HTTP-ERROR][Conn #{conn_no}] {addr} -> {e}")  # NEW: ikutkan conn_no di error
    finally:
        try:
            client.close()
        except:
            pass

# ---------- UDP ECHO SERVER ----------

def udp_echo_server():
    global server_running
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, UDP_PORT))
    s.settimeout(1.0)
    print(f"[UDP] Echo server on {HOST}:{UDP_PORT}")

    while server_running:
        try:
            data, addr = s.recvfrom(BUF_SIZE)
            s.sendto(data, addr)
            print(f"[UDP] echo {len(data)}B to {addr[0]}:{addr[1]}")
        except socket.timeout:
            continue
        except Exception as e:
            if server_running:
                print(f"[UDP-ERROR] {e}")

# ---------- TCP ACCEPTOR ----------

def tcp_acceptor():
    global server_running, conn_id  # NEW: pakai conn_id
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, TCP_PORT))
    s.listen(BACKLOG)
    s.settimeout(0.5)
    print(f"[TCP] HTTP server on {HOST}:{TCP_PORT} mode={mode}")

    while server_running:
        try:
            client, addr = s.accept()

            # NEW: setiap ada koneksi baru, increment dan print
            conn_id += 1
            current_conn = conn_id
            print(f"[TCP] Connection #{current_conn} from {addr[0]}:{addr[1]}")

            if mode == "single":
                handle_http(client, addr, current_conn)
            else:  # threaded
                threading.Thread(
                    target=handle_http,
                    args=(client, addr, current_conn),
                    daemon=True
                ).start()
        except socket.timeout:
            continue
        except Exception as e:
            if server_running:
                print(f"[ACCEPT-ERROR] {e}")

# ---------- MAIN ----------

def ensure_static():
    if not os.path.isdir("static"):
        os.makedirs("static")
    index_path = os.path.join("static", "index.html")
    if not os.path.isfile(index_path):
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("<h1>Web Server Socket Programming</h1><p>Running on port 8000</p>")

def choose_mode():
    global mode
    m = input("Pilih mode (1=single, 2=threaded) [2]: ").strip()
    mode = "single" if m == "1" else "threaded"

if __name__ == "__main__":
    ensure_static()
    choose_mode()

    t_tcp = threading.Thread(target=tcp_acceptor, daemon=True)
    t_udp = threading.Thread(target=udp_echo_server, daemon=True)
    t_tcp.start()
    t_udp.start()

    print("Server running. Ctrl+C untuk berhenti.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server_running = False
        print("\nServer stopped.")
