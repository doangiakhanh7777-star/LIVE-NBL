import struct, sys
def imports(path):
    d = open(path, 'rb').read()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    if d[pe:pe+4] != b'PE\0\0': return []
    nsec = struct.unpack_from('<H', d, pe+6)[0]; optsz = struct.unpack_from('<H', d, pe+20)[0]
    opt = pe+24; magic = struct.unpack_from('<H', d, opt)[0]
    dd = opt + (112 if magic == 0x20b else 96)
    names = []
    secs = [struct.unpack_from('<8sIIII', d, opt+optsz+40*i) for i in range(nsec)]
    def off(rva):
        for _, vs, va, rs, ro in secs:
            if va <= rva < va+max(vs, rs): return rva-va+ro
        return None
    for idx in (1, 13):   # import + delay import
        rva, size = struct.unpack_from('<II', d, dd+8*idx)
        if not rva: continue
        o = off(rva)
        while o is not None:
            if idx == 1:
                f = struct.unpack_from('<5I', d, o); nrva = f[3]; o += 20
                if not any(f): break
            else:
                f = struct.unpack_from('<8I', d, o); nrva = f[1]; o += 32
                if not any(f): break
            no = off(nrva)
            if no is None: break
            names.append(d[no:d.index(b'\0', no)].decode('latin1').lower())
    return names
if __name__ == '__main__':
    for p in sys.argv[1:]: print(p, imports(p))
