import datetime
import socket
import threading
import time
import webbrowser
import csv
import webbrowser
import os
PROXY_IP = "192.168.26.180"   # IP Proxy Server
TCP_PORT = 8080
UDP_PORT = 9090


# =========================================================
#  MODE: HTTP via TCP
# ========================================================= 
def http_request(path="/"):
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(8)
        client.connect((PROXY_IP, TCP_PORT))

        # ===== TAMBAHAN: PENGATURAN PATH OTOMATIS =====
        if path == "/index":
            # Untuk index.html di folder static
            request_path = "index.html"
        elif path == "/test":
            # Untuk test.html di folder static
            request_path = "test.html"
        else:
            # Biarkan path asli jika input lainnya
            request_path = path
        # ==============================================

        request = f"GET {request_path} HTTP/1.1\r\nHost: {PROXY_IP}\r\n\r\n"
        client.send(request.encode())

        response = client.recv(4096).decode()
        print("===== HTTP RESPONSE =====")
        print(response)
        print("=========================")

        # buka otomatis di browser
        filename = "received_page.html"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(response)

        webbrowser.open(filename)

        client.close()

    except Exception as e:
        print(f"[ERROR] HTTP Request failed: {e}")


# =========================================================
#  MODE: UDP QoS Testing
# =========================================================
def udp_qos_test(packet_count=50, packet_size=512, interval=0.05):
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(8)

    latencies = []          # hanya yang sukses (float ms)
    per_packet = []         # panjang = packet_count, isi float ms atau None (LOST)
    packet_sent = 0
    packet_received = 0

    test_start = None       # timestamp send paket pertama
    test_end = None         # timestamp event terakhir (recv/timeout) paket terakhir

    for i in range(packet_count):
        message = ("X" * packet_size).encode()

        send_time = time.time()
        if test_start is None:
            test_start = send_time

        try:
            client.sendto(message, (PROXY_IP, UDP_PORT))
            packet_sent += 1

            data, _ = client.recvfrom(2048)
            recv_time = time.time()

            latency_ms = (recv_time - send_time) * 1000.0
            latencies.append(latency_ms)
            per_packet.append(latency_ms)
            packet_received += 1

            print(f"Packet {i+1}/{packet_count}, Latency: {latency_ms:.2f} ms")
            test_end = recv_time  # update terus, terakhir = recv terakhir

        except socket.timeout:
            timeout_time = time.time()
            per_packet.append(None)
            print(f"Packet {i+1}/{packet_count}: LOST")
            test_end = timeout_time  # terakhir = timeout terakhir (kalau paket terakhir lost)

        # sleep hanya di antara paket, bukan setelah paket terakhir
        if i != packet_count - 1:
            time.sleep(interval)

    client.close()

    # ---------- QoS Calculation ----------
    # durasi test yang "fair" (tanpa sleep setelah paket terakhir)
    if test_start is None:
        test_duration = 0.0
    else:
        # kalau semuanya lost dan test_end belum ke-set, pakai time.now()
        if test_end is None:
            test_end = time.time()
        test_duration = max(0.0, test_end - test_start)

    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

    # jitter "umum": rata-rata perubahan delay antar paket yang berhasil diterima
    if len(latencies) > 1:
        jitter = sum(abs(latencies[i] - latencies[i-1]) for i in range(1, len(latencies))) / (len(latencies) - 1)
    else:
        jitter = 0.0

    packet_loss = ((packet_sent - packet_received) / packet_sent * 100.0) if packet_sent else 0.0

    # throughput berbasis payload murni (packet_size) dibagi durasi test
    if test_duration > 0:
        throughput = (packet_received * packet_size * 8) / test_duration  # bps
    else:
        throughput = 0.0

    print("\n===== QoS RESULT =====")
    print(f"Sent: {packet_sent}")
    print(f"Received: {packet_received}")
    print(f"Packet Loss: {packet_loss:.2f}%")
    print(f"Avg Latency (RTT): {avg_latency:.2f} ms")
    print(f"Jitter (avg |Δdelay|): {jitter:.2f} ms")
    print(f"Throughput: {throughput:.2f} bps ({throughput/1000:.2f} kbps)")
    print(f"Test Duration: {test_duration:.4f} s")
    print("======================\n")

    # Save CSV
    with open("qos_result.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)

        writer.writerow(["QoS Test Results"])
        writer.writerow([])

        writer.writerow(["SUMMARY METRICS"])
        writer.writerow(["Metric", "Value", "Unit"])
        writer.writerow(["Packets Sent", packet_sent, "packets"])
        writer.writerow(["Packets Received", packet_received, "packets"])
        writer.writerow(["Packet Loss", f"{packet_loss:.2f}", "%"])
        writer.writerow(["Average Latency (RTT)", f"{avg_latency:.4f}", "ms"])
        writer.writerow(["Minimum Latency", f"{min(latencies):.4f}" if latencies else "0", "ms"])
        writer.writerow(["Maximum Latency", f"{max(latencies):.4f}" if latencies else "0", "ms"])
        writer.writerow(["Jitter (avg |Δdelay|)", f"{jitter:.4f}", "ms"])
        writer.writerow(["Throughput (payload-based)", f"{throughput:.2f}", "bps"])
        writer.writerow(["Test Duration", f"{test_duration:.4f}", "seconds"])
        writer.writerow([])

        writer.writerow(["DETAILED LATENCY PER PACKET"])
        writer.writerow(["Packet No.", "Latency (ms)"])
        for idx, lat in enumerate(per_packet, 1):
            writer.writerow([idx, f"{lat:.4f}" if lat is not None else "LOST"])

    print("QoS results saved to qos_result.csv")


# =========================================================
#  MODE: MULTI CLIENT (5 parallel)
# =========================================================

def spawn_multi_clients(n=5):
    threads = []
    for i in range(n):
        t = threading.Thread(target=http_request, args=("/index.html",))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("\n===== MULTI CLIENT DONE =====")

# =========================================================
#  MAIN MENU
# =========================================================

def main():
    while True:
        print("\n====== CLIENT MENU ======")
        print("1. HTTP Request - Index Page (/static/index.html)")
        print("2. HTTP Request - Test Page (/static/test.html)")
        print("3. UDP QoS Test")
        print("4. Multi Client (5 clients)")
        print("5. Exit")
        choice = input("Pilih: ")

        if choice == "1":
            # Langsung request index.html di static folder
            http_request("/index")
            
        elif choice == "2":
            # Langsung request test.html di static folder
            http_request("/test")
            
        elif choice == "3":
            count = int(input("Jumlah paket: "))
            udp_qos_test(packet_count=count)

        elif choice == "4":
            spawn_multi_clients()

        elif choice == "5":
            break

        else:
            print("Pilihan tidak valid!")

if __name__ == "__main__":
    main()