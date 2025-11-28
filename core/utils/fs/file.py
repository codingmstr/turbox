import os, re, time, shutil, threading, hashlib
from typing import Any, Callable
from .checker import Checker
from .editor import Editor
from .compressor import Compressor
from .encryptor import Encryptor
from .manager import Manager
from .watcher import Watcher
from .handler import Handler

@Handler.file
class File(Checker, Editor):

    def __init__ ( self ):

        self.compressor = Compressor()
        self.encryptor  = Encryptor()
        self.manager    = Manager
        self.watcher    = Watcher
        self.timer      = None

    @Handler.skip
    def exists ( self, path: str ):

        return os.path.isfile(path)

    @Handler.skip
    def new ( self, path: str, content: str = '' ):

        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8', errors='ignore') as f: f.write(content)

        return path

    def name ( self, path: str ):

        return os.path.basename(path)

    def extension ( self, path: str ):

        return os.path.splitext(path)[1].lstrip('.')

    def drive ( self, path: str ):

        return os.path.splitdrive(path)[0]

    def normalize ( self, path: str ):

        return os.path.normpath(path)

    def join ( self, *paths: str ):

        cleaned = [p.strip('/').replace('\\', '/') for p in paths if p not in (None, '', '/')]
        return self.normalize('/'.join(cleaned).replace('//', '/'))

    def path ( self, path: str ):

        return os.path.abspath(path)

    def full_path ( self, path: str ):

        return os.path.abspath(path)

    def dir_path ( self, path: str ):

        return os.path.dirname(os.path.abspath(path))

    def dir_name ( self, path: str ):

        return os.path.basename(os.path.dirname(os.path.abspath(path)))

    def parent_path ( self, path: str ):

        return os.path.dirname(self.dir_name(path))

    def parent_name ( self, path: str ):

        return os.path.basename(self.dir_name(path))

    def rename ( self, path: str, new_name: str ):

        new_path = os.path.join(os.path.dirname(path), new_name)
        os.rename(path, new_path)
        return new_path

    def delete ( self, path: str ):

        try: os.remove(path)
        except: pass
        return True

    def copy ( self, path: str, dest: str ):

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(path, dest)
        return dest

    def move ( self, path: str, dest: str ):

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(path, dest)
        return dest

    def size ( self, path: str ):

        return os.path.getsize(path)

    def size_str ( self, path: str ):

        size = self.size(path)

        for unit in [ 'B', 'KB', 'MB', 'GB', 'TB' ]:
            if size < 1024: return f"{size:.2f} {unit}"
            size /= 1024

        return f"{size:.2f} PB"

    def ctime ( self, path: str ):

        return os.path.getctime(path)

    def mtime ( self, path: str ):

        return os.path.getmtime(path)

    def atime ( self, path: str ):

        return os.path.getatime(path)

    def created_at ( self, path: str ):

        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.ctime(path)))

    def updated_at ( self, path: str ):

        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.mtime(path)))

    def accessed_at ( self, path: str ):

        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.atime(path)))

    def checksum ( self, path: str, algo: str = 'md5' ):

        h = hashlib.new(algo)

        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)

        return h.hexdigest()

    def info ( self, path: str ):

        return {
            "name"        : self.name(path),
            "path"        : os.path.abspath(path),
            "size"        : self.size_str(path),
            "extension"   : self.extension(path),
            "mime"        : self.mime(path),
            "created_at"  : self.created_at(path),
            "updated_at"  : self.updated_at(path),
            "accessed_at" : self.accessed_at(path),
            "checksum"    : self.checksum(path)
        }

    def chmod ( self, path: str, mode: str ):

        os.chmod(path, int(mode, 8))
        return True

    def lock ( self, path: str ):

        return self.chmod(path, '000')

    def unlock ( self, path: str ):

        return self.chmod(path, '777')

    def readable ( self, path: str ):

        return os.access(path, os.R_OK)

    def writable ( self, path: str ):

        return os.access(path, os.W_OK)

    def executable ( self, path: str ):

        return os.access(path, os.X_OK)

    def find ( self, path: str, pattern: str, case: bool = False ):

        flags = 0 if case else re.IGNORECASE

        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            matches = [ line.strip() for line in f if re.search(pattern, line, flags) ]

        return matches

    def replace ( self, path: str, old: str, new: str ):

        text = self.read(path)
        self.write(path, text.replace(old, new))
        return True

    def lines ( self, path: str ):

        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return [ line.rstrip('\n') for line in f ]

    def head ( self, path: str, n: int = 10 ):

        return self.lines(path)[:n]

    def tail ( self, path: str, n: int = 10 ):

        return self.lines(path)[-n:]

    def backup ( self, path: str, dest: str = None, name: str = None, compress: bool = True, **kwargs: Any ):

        dest = dest or os.path.dirname(path)
        name = name or f"{os.path.basename(path)}_backup_{time.strftime('%Y-%m-%d_%H-%M-%S')}"

        if compress: return self.compress(path, dest, name, **kwargs)
        return self.copy(path, os.path.join(dest, name))

    def cleanup ( self, path: str, **kwargs: float ):

        total_seconds = (
            kwargs.get('years', 0) * 31536000 +
            kwargs.get('months', 0) * 2628000 +
            kwargs.get('days', 0) * 86400 +
            kwargs.get('hours', 0) * 3600 +
            kwargs.get('minutes', 0) * 60 +
            kwargs.get('seconds', 0)
        )

        threshold_time = time.time() - total_seconds

        try:
            ts = max(os.path.getctime(path), os.path.getmtime(path))
            if ts < threshold_time: os.remove(path)
        except: pass
        
        return True

    def sync ( self, src: str, dest: str ):

        os.makedirs(os.path.dirname(dest), exist_ok=True)

        try:
            changed = (
                not os.path.exists(dest) or
                os.path.getsize(src) != os.path.getsize(dest) or
                os.path.getmtime(dest) < os.path.getmtime(src)
            )

            if not changed: return dest

            for _ in range(3):

                try:
                    with open(src, "rb") as s, open(dest, "wb") as d:
                        while chunk := s.read(8192): d.write(chunk)

                    shutil.copystat(src, dest)
                    break
                except: time.sleep(0.1)
        except: pass

        return dest

    def watch ( self, path: str, callback: Callable, watch_dirs: bool = False ):

        return self.watcher(path, callback, watch_dirs).start()

    def watch_backup ( self, path: str, dest: str = None, name: str = None, compress: bool = True, **kwargs: Any ):

        self.backup(path, dest, name, compress, **kwargs)

        def on_event ( event, src, _ ):

            if self.timer: self.timer.cancel()
            self.timer = threading.Timer(0.5, lambda: self.backup(path, dest, name, compress, **kwargs))
            self.timer.start()

        self.watch(path, on_event)

    def watch_cleanup ( self, path: str, **kwargs: float ):

        def worker ():
            while True:
                self.cleanup(path, **kwargs)
                time.sleep(1)

        threading.Thread(target=worker).start()

    def watch_sync ( self, path: str, dest: str, init: bool = True, reverse: bool = True ):

        if init: self.sync(path, dest)

        def on_event ( event, changed_path: str, _ ):

            if not os.path.isfile(changed_path): return
            if self.timer: self.timer.cancel()

            def perform_sync ():

                try:

                    target = dest if changed_path == path else path

                    changed = (
                        not os.path.exists(target) or
                        os.path.getsize(changed_path) != os.path.getsize(target) or
                        os.path.getmtime(target) < os.path.getmtime(changed_path)
                    )

                    if not changed: return
                    os.makedirs(os.path.dirname(target), exist_ok=True)

                    for _ in range(3):
                        try:
                            with open(changed_path, "rb") as s, open(target, "wb") as d:
                                while chunk := s.read(8192): d.write(chunk)

                            shutil.copystat(changed_path, target)
                            break
                        except: time.sleep(0.1)

                except: pass

            self.timer = threading.Timer(0.5, perform_sync)
            self.timer.start()

        self.watch(path, on_event)
        if reverse: self.watch_sync(dest, path, False, False)

    def encrypt ( self, path: str, key_path: str = None ):

        return self.encryptor.encrypt(path, key_path)

    def decrypt ( self, path: str, key_path: str = None ):

        return self.encryptor.decrypt(path, key_path)

    def compress ( self, path: str, out_dir: str = None, fmt: str = 'zip' ):

        out_dir = out_dir or os.path.dirname(path)
        return self.compressor.compress(path, out_dir, fmt=fmt)

    def extract ( self, path: str, extract_to: str = None ):

        extract_to = extract_to or os.path.dirname(path)
        return self.compressor.extract(path, extract_to)

    def upload ( self, path: str, remote_path: str = None, provider: str = 's3', credentials: dict = {}, options: dict = {}, **kwargs: Any ):

        return self.manager().connect(provider, credentials, options).upload_file(path, remote_path, **kwargs)

    @Handler.skip
    def download ( self, remote_path: str, path: str = None, provider: str = 's3', credentials: dict = {}, options: dict = {}, **kwargs: Any ):

        return self.manager().connect(provider, credentials, options).download_file(remote_path, path, **kwargs)
