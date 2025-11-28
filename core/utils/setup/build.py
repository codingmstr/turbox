import os, sys, time, shutil, base64, hashlib, subprocess, platform

def _s ( x ):

    k = "MAGIC_KEY_2025"
    x = x[::-1]

    x = base64.b64decode(x)
    h = hashlib.sha256(k.encode()).digest()

    out = bytearray()
    for i, b in enumerate(x): out.append((b ^ h[i % len(h)]) & 0xFF)

    out = bytes(out)
    return out.decode()

def _encode ( text ):

    k = "MAGIC_KEY_2025"
    raw = text.encode()

    h = hashlib.sha256(k.encode()).digest()

    out = bytearray()
    for i, b in enumerate(raw): out.append((b ^ h[i % len(h)]) & 0xFF)

    x = base64.b64encode(bytes(out)).decode()
    return x[::-1]

def encrypt_strings ( root ):

    for path, _, files in os.walk(root):

        for f in files:

            if not f.endswith(".py"): continue

            p = os.path.join(path, f)
            code = open(p, "r", encoding="utf8").read()

            out, buf, inside = [], "", False

            for c in code:

                if c == '"' and not inside:
                    inside = True
                    buf = ""
                    continue

                if c == '"' and inside:
                    inside = False
                    out.append(f'_s("{_encode(buf)}")')
                    continue

                if inside: buf += c
                else: out.append(c)

            open(p, "w", encoding="utf8").write("".join(out))

def cythonize ( root ):

    pyx = []
   
    for path, _, flist in os.walk(root):
        for f in flist:
            if f.endswith(".pyx"):
                pyx.append(os.path.join(path, f))

    if not pyx: return

    cmd = [sys.executable, "-m", "cython", "--3str", "--embed"]
    cmd.extend(pyx)
    subprocess.run(cmd, check=True)

    for f in pyx:

        cfile = f.replace(".pyx", ".c")
        out = f.replace(".pyx", "")

        if not os.path.exists(cfile): continue

        if platform.system().lower().startswith("win"): subprocess.run(["cl", cfile], check=True)
        else: subprocess.run(["gcc", "-O3", cfile, "-o", out], check=True)

def build_nuitka ( entry, name, workers ):

    out_dir = "build"
    exe = os.path.join(out_dir, f"{name}.exe" if platform.system().lower().startswith("win") else name)

    if os.path.exists(out_dir): shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    cmd = [
        sys.executable, "-m", "nuitka",
        entry,
        "--onefile",
        "--standalone",
        "--follow-imports",
        "--prefer-source-code",
        "--lto=yes",
        "--clang",
        "--static-libpython=yes",
        "--assume-yes-for-downloads",
        "--no-asserts",
        "--no-docstrings",
        "--no-pyi-file",
        "--remove-build",
        "--remove-output",
        "--python-flag=-OO",
        "--experimental=use-type-hints",
        "--assume-static-types",
        "--no-progress",
        "--show-scons",
        "--nofollow-import-to=setuptools",
        "--nofollow-import-to=distutils",
        "--nofollow-import-to=pydoc",
        "--nofollow-import-to=Cython",
        "--nofollow-import-to=importlib.metadata",
        f"--jobs={workers}",
        f"--output-filename={exe}"
    ]

    subprocess.run(cmd, check=True)

    if shutil.which("upx"): subprocess.run(["upx", "--lzma", "-9", exe], check=True)
    if shutil.which("strip"): subprocess.run(["strip", "--strip-all", exe], check=True)

    return exe

def build ( entry="main.py", name="server", workers=8 ):

    start = time.perf_counter()

    encrypt_strings(".")
    cythonize(".")

    exe = build_nuitka(entry, name, workers)
    elapsed = round(time.perf_counter() - start, 2)
    size = round(os.path.getsize(exe) / 1024 / 1024, 2)

    return {"binary": exe, "size_mb": size, "build_time": elapsed}
