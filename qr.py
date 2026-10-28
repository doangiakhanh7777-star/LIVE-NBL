"""4.3.0: tiny QR code encoder (byte mode, error correction M, versions 1-15) for pairing
the phone app. No extra library in the installer."""

ECC_M = [0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24]
BLOCKS_M = [0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10]


def _mul(x, y):
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs(data, degree):
    div = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            div[j] = _mul(div[j], root)
            if j + 1 < degree:
                div[j] ^= div[j + 1]
        root = _mul(root, 2)
    out = [0] * degree
    for b in data:
        f = b ^ out.pop(0)
        out.append(0)
        for i, c in enumerate(div):
            out[i] ^= _mul(c, f)
    return out


def _raw_modules(v):
    r = (16 * v + 128) * v + 64
    if v >= 2:
        n = v // 7 + 2
        r -= (25 * n - 10) * n - 55
        if v >= 7:
            r -= 36
    return r


def _align(v):
    if v == 1:
        return []
    n = v // 7 + 2
    step = (v * 8 + n * 3 + 5) // (n * 4 - 4) * 2
    size = v * 4 + 17
    out = [6]
    pos = size - 7
    for _ in range(n - 1):
        out.insert(1, pos)
        pos -= step
    return out


def encode(text):
    """Returns the QR matrix as rows of booleans (True = dark)."""
    data = text.encode('utf-8')
    for v in range(1, 16):
        cap = _raw_modules(v) // 8 - ECC_M[v] * BLOCKS_M[v]
        cbits = 8 if v < 10 else 16
        if 4 + cbits + len(data) * 8 <= cap * 8:
            break
    else:
        raise ValueError('QR: nội dung quá dài')
    bits = [0, 1, 0, 0] + [(len(data) >> i) & 1 for i in range(cbits - 1, -1, -1)]
    for b in data:
        bits += [(b >> i) & 1 for i in range(7, -1, -1)]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    words = [int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(words) < cap:
        words.append(pad)
        pad ^= 0xEC ^ 0x11
    nb, ecc = BLOCKS_M[v], ECC_M[v]
    raw = _raw_modules(v) // 8
    short = nb - raw % nb
    slen = raw // nb
    blocks, k = [], 0
    for i in range(nb):
        n = slen - ecc + (0 if i < short else 1)
        d = words[k:k + n]
        k += n
        e = _rs(d, ecc)
        if i < short:
            d = d + [0]
        blocks.append(d + e)
    final = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != slen - ecc or j >= short:
                final.append(blk[i])

    size = v * 4 + 17
    mod = [[False] * size for _ in range(size)]
    fn = [[False] * size for _ in range(size)]

    def put(x, y, dark):
        mod[y][x] = bool(dark)
        fn[y][x] = True

    for i in range(size):
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    put(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    al = _align(v)
    last = len(al) - 1
    for i, ax in enumerate(al):
        for j, ay in enumerate(al):
            if (i, j) in ((0, 0), (0, last), (last, 0)):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    put(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)

    def fmt_bits(mask):
        d = mask  # error correction M = 00
        r = d
        for _ in range(10):
            r = (r << 1) ^ ((r >> 9) * 0x537)
        b = (d << 10 | r) ^ 0x5412
        g = lambda i: (b >> i) & 1
        for i in range(6):
            put(8, i, g(i))
        put(8, 7, g(6)); put(8, 8, g(7)); put(7, 8, g(8))
        for i in range(9, 15):
            put(14 - i, 8, g(i))
        for i in range(8):
            put(size - 1 - i, 8, g(i))
        for i in range(8, 15):
            put(8, size - 15 + i, g(i))
        put(8, size - 8, 1)

    fmt_bits(0)
    if v >= 7:
        r = v
        for _ in range(12):
            r = (r << 1) ^ ((r >> 11) * 0x1F25)
        b = v << 12 | r
        for i in range(18):
            bit = (b >> i) & 1
            a, c = size - 11 + i % 3, i // 3
            put(a, c, bit)
            put(c, a, bit)

    i = 0
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                up = ((right + 1) & 2) == 0
                y = size - 1 - vert if up else vert
                if not fn[y][x] and i < len(final) * 8:
                    mod[y][x] = bool((final[i >> 3] >> (7 - (i & 7))) & 1)
                    i += 1
        right -= 2

    masks = [lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
             lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
             lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
             lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0]

    def apply(m):
        f = masks[m]
        for y in range(size):
            for x in range(size):
                if not fn[y][x] and f(x, y):
                    mod[y][x] = not mod[y][x]

    def penalty():
        p = 0
        for grid in (mod, [list(c) for c in zip(*mod)]):
            for row in grid:
                run = 1
                for a, b in zip(row, row[1:]):
                    if a == b:
                        run += 1
                    else:
                        p += run - 2 if run >= 5 else 0
                        run = 1
                p += run - 2 if run >= 5 else 0
        for y in range(size - 1):
            for x in range(size - 1):
                if mod[y][x] == mod[y][x + 1] == mod[y + 1][x] == mod[y + 1][x + 1]:
                    p += 3
        dark = sum(map(sum, mod))
        p += abs(dark * 20 - size * size * 10) // (size * size) * 10
        return p

    best = None
    for m in range(8):
        apply(m); fmt_bits(m)
        score = penalty()
        if best is None or score < best[0]:
            best = (score, m)
        apply(m)
    apply(best[1]); fmt_bits(best[1])
    return mod
