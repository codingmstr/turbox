import os, zipfile, tarfile, rarfile, py7zr

class Compressor:

    def __init__ ( self ):

        pass
    
    def zip ( self, folder_path: str, zip_path: str = None, include_root: bool = True ):

        if not os.path.isdir(folder_path): return

        zip_path = zip_path or f"{folder_path}.zip"
        os.makedirs(os.path.dirname(zip_path), exist_ok=True)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:

            for root, _, files in os.walk(folder_path):

                for file in files:

                    file_path = os.path.join(root, file)

                    arcname = os.path.relpath(file_path, folder_path)
                    if include_root: arcname = os.path.join(os.path.basename(folder_path), arcname)

                    zipf.write(file_path, arcname)

        return zip_path

    def tar ( self, folder_path: str, tar_path: str = None, include_root: bool = True, fmt: str = None ):

        if not os.path.isdir(folder_path): return

        ext = {"gz": "w:gz", "bz2": "w:bz2"}.get(fmt, "w")
        fmt = f".tar.{fmt}" if fmt else ".tar"

        tar_path = tar_path or f"{folder_path}{fmt}"
        os.makedirs(os.path.dirname(tar_path), exist_ok=True)

        with tarfile.open(tar_path, ext) as tarf:
            arcname = os.path.basename(folder_path) if include_root else ""
            tarf.add(folder_path, arcname=arcname)

        return tar_path

    def _7z ( self, folder_path: str, z7_path: str = None, include_root: bool = True ):

        if not os.path.isdir(folder_path): return

        z7_path = z7_path or f"{folder_path}.7z"
        os.makedirs(os.path.dirname(z7_path), exist_ok=True)

        with py7zr.SevenZipFile(z7_path, 'w') as _7zf:
            arcname = os.path.basename(folder_path) if include_root else ""
            _7zf.writeall(folder_path, arcname=arcname)

        return z7_path

    def unzip ( self, zip_path: str, extract_to: str = None ):

        if not os.path.isfile(zip_path): return

        extract_to = extract_to or os.path.dirname(zip_path)
        os.makedirs(extract_to, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zipf: zipf.extractall(extract_to)
        return extract_to

    def untar ( self, tar_path: str, extract_to: str = None ):

        if not os.path.isfile(tar_path): return

        extract_to = extract_to or os.path.dirname(tar_path)
        os.makedirs(extract_to, exist_ok=True)

        with tarfile.open(tar_path, "r:*") as tarf: tarf.extractall(extract_to)
        return extract_to

    def unrar (self, rar_path: str, extract_to: str = None ):

        if not os.path.isfile(rar_path): return

        extract_to = extract_to or os.path.dirname(rar_path)
        os.makedirs(extract_to, exist_ok=True)

        with rarfile.RarFile(rar_path) as rarf: rarf.extractall(extract_to)
        return extract_to

    def un7z ( self, z7_path: str, extract_to: str = None ):

        if not os.path.isfile(z7_path): return

        extract_to = extract_to or os.path.dirname(z7_path)
        os.makedirs(extract_to, exist_ok=True)

        with py7zr.SevenZipFile(z7_path, 'r') as _7zf: _7zf.extractall(path=extract_to)
        return extract_to

    def compress ( self, path: str, out_dir: str = None, out_name: str = None, fmt: str = 'zip' ):

        out_dir = out_dir or os.path.dirname(path)
        name = os.path.basename(out_name or path)

        fmt = fmt.lower().strip()
        os.makedirs(out_dir, exist_ok=True)

        if fmt.endswith('gz'): return self.tar(path, os.path.join(out_dir, f"{name}.gz"), fmt='gz')
        elif fmt.endswith('bz2'): return self.tar(path, os.path.join(out_dir, f"{name}.bz2"), fmt='bz2')
        elif fmt.endswith('tar'): return self.tar(path, os.path.join(out_dir, f"{name}.tar"))
        elif fmt.endswith('7z'): return self._7z(path, os.path.join(out_dir, f"{name}.7z"))

        return self.zip(path, os.path.join(out_dir, f"{name}.zip"))

    def extract ( self, file_path: str, extract_to: str = None ):

        if file_path.endswith('.zip'): return self.unzip(file_path, extract_to)
        elif file_path.endswith('.rar'): return self.unrar(file_path, extract_to)
        elif file_path.endswith('.7z'): return self.un7z(file_path, extract_to)
        elif file_path.endswith((".tar", ".tar.gz", ".tar.bz2")): return self.untar(file_path, extract_to)
