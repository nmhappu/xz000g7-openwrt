#!/usr/bin/env python3
# Read-only TFTP server with RFC2347/2348 option (blksize/tsize) support
# and a robust EOF terminator. usage: python tftp_serve2.py <port> <root>
import socket, struct, sys, os

port = int(sys.argv[1]); root = sys.argv[2]
srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', port))
print(f"SERVE2 udp/{port} root={root}", flush=True)
def bn(p): return struct.unpack('!H', p[2:4])[0]
def op(p): return struct.unpack('!H', p[:2])[0] if len(p) >= 2 else 0
while True:
    data, addr = srv.recvfrom(2048)
    if op(data) != 1:
        continue
    parts = data[2:].split(b'\x00')
    fname = parts[0].decode('latin1')
    rest = parts[2:]; opts = {}
    i = 0
    while i + 1 < len(rest):
        k = rest[i].decode('latin1').lower(); v = rest[i+1].decode('latin1')
        if k: opts[k] = v
        i += 2
    path = os.path.join(root, os.path.basename(fname))
    print(f"RRQ {addr} file={fname} opts={opts}", flush=True)
    ts = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); ts.settimeout(2)
    if not os.path.isfile(path):
        ts.sendto(b'\x00\x05\x00\x01not found\x00', addr); print("  404", flush=True); ts.close(); continue
    buf = open(path, 'rb').read(); total = len(buf)
    blksize = 512; oack = {}
    if 'blksize' in opts:
        try: blksize = max(8, min(1468, int(opts['blksize']))); oack['blksize'] = str(blksize)
        except: pass
    if 'tsize' in opts: oack['tsize'] = str(total)
    if 'timeout' in opts: oack['timeout'] = opts['timeout']
    if oack:
        pkt = b'\x00\x06' + b''.join(k.encode()+b'\x00'+v.encode()+b'\x00' for k, v in oack.items())
        acked = False
        for _ in range(10):
            ts.sendto(pkt, addr)
            try:
                a, _a = ts.recvfrom(2048)
                if op(a) == 4 and bn(a) == 0: acked = True; break
            except socket.timeout: continue
        if not acked:
            print("  OACK not acked -> fall back to 512", flush=True); blksize = 512
        else:
            print(f"  OACK {oack}", flush=True)
    print(f"  serving {total} bytes blksize={blksize}", flush=True)
    blk = 1; off = 0
    while True:
        chunk = buf[off:off+blksize]
        pkt = struct.pack('!HH', 3, blk & 0xFFFF) + chunk
        last = (len(chunk) < blksize)
        got = False
        for _ in range((30 if last else 12)):
            ts.sendto(pkt, addr)
            try:
                a, _a = ts.recvfrom(2048)
                if op(a) == 4 and bn(a) == (blk & 0xFFFF): got = True; break
            except socket.timeout: continue
        if last:
            print(f"  DONE {total} bytes (final {'acked' if got else 'sent'})", flush=True); break
        if not got:
            print(f"  TIMEOUT block {blk}", flush=True); break
        off += blksize; blk += 1
    ts.close()
