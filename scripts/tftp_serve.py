#!/usr/bin/env python3
# Minimal read-only TFTP server (serves files for U-Boot `tftpboot`).
# usage: python tftp_serve.py <port> <root_dir>
import socket, struct, sys, os

port = int(sys.argv[1]); root = sys.argv[2]
srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', port))
print(f"SERVE udp/{port} root={root}", flush=True)
while True:
    data, addr = srv.recvfrom(2048)
    if len(data) < 2 or struct.unpack('!H', data[:2])[0] != 1:   # not RRQ
        continue
    fname = data[2:].split(b'\x00')[0].decode('latin1')
    path = os.path.join(root, os.path.basename(fname))
    print(f"RRQ from {addr}: {fname}", flush=True)
    ts = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); ts.settimeout(2)
    if not os.path.isfile(path):
        ts.sendto(b'\x00\x05\x00\x01not found\x00', addr); print("  404 not found", flush=True); ts.close(); continue
    with open(path, 'rb') as fh: buf = fh.read()
    total = len(buf)
    print(f"  serving {total} bytes", flush=True)
    blk = 1; off = 0
    while True:
        chunk = buf[off:off+512]
        pkt = struct.pack('!HH', 3, blk & 0xFFFF) + chunk
        last = len(chunk) < 512
        retries = 3 if last else 8
        ok = False
        for _ in range(retries):
            ts.sendto(pkt, addr)
            try:
                ack, a = ts.recvfrom(2048)
                if struct.unpack('!H', ack[:2])[0] == 4 and struct.unpack('!H', ack[2:4])[0] == (blk & 0xFFFF):
                    ok = True; break
            except socket.timeout:
                continue
        if last:
            # terminator / short final block: data already delivered; don't hang on its ACK
            print(f"  DONE {total} bytes (final {'acked' if ok else 'sent'})", flush=True); break
        if not ok:
            print(f"  TIMEOUT at block {blk}", flush=True); break
        off += 512; blk += 1
    ts.close()
