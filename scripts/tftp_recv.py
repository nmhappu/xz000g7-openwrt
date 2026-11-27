#!/usr/bin/env python3
# Minimal TFTP server: accepts ONE WRQ (PUT) upload, saves it, exits.
# usage: python tftp_recv.py <port> <out_path>
import socket, sys, struct

port = int(sys.argv[1]); out = sys.argv[2]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('0.0.0.0', port))
print(f"LISTEN udp/{port} -> {out}", flush=True)
s.settimeout(120)
try:
    data, addr = s.recvfrom(2048)
except socket.timeout:
    print("ERR: no WRQ within 120s", flush=True); sys.exit(1)
op = struct.unpack('!H', data[:2])[0]
if op != 2:
    print(f"ERR: expected WRQ, got op {op}", flush=True); sys.exit(1)
parts = data[2:].split(b'\x00')
print(f"WRQ from {addr}: file={parts[0].decode('latin1')}", flush=True)
f = open(out, 'wb')
s.sendto(struct.pack('!HH', 4, 0), addr)   # ACK block 0
expected = 1; total = 0; s.settimeout(15)
while True:
    try:
        pkt, a = s.recvfrom(2048)
    except socket.timeout:
        print(f"ERR: data timeout at {total} bytes", flush=True); break
    op = struct.unpack('!H', pkt[:2])[0]
    if op == 3:  # DATA
        blk = struct.unpack('!H', pkt[2:4])[0]
        payload = pkt[4:]
        if blk == (expected & 0xFFFF):
            f.write(payload); total += len(payload)
            s.sendto(struct.pack('!HH', 4, blk), a)
            expected += 1
            if len(payload) < 512:
                print(f"DONE total={total}", flush=True); break
        else:
            s.sendto(struct.pack('!HH', 4, blk), a)  # re-ack (dup/retransmit)
    elif op == 2:
        s.sendto(struct.pack('!HH', 4, 0), a)
f.close()
print(f"FINAL {out} = {total} bytes", flush=True)
