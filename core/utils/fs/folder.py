import os, re, time, shutil, itertools, threading, datetime, fnmatch
from collections import Counter
from typing import Any, Callable
from .checker import Checker
from .compressor import Compressor
from .encryptor import Encryptor
from .manager import Manager
from .watcher import Watcher
from .handler import Handler

@Handler.folder
class Folder:

    def __init__ ( self ):

        self.checker    = Checker()
        self.compressor = Compressor()
        self.encryptor  = Encryptor()
        self.watcher    = Watcher
        self.manager    = Manager
        self.timer      = None

    @Handler.skip
    def new ( self, path: str ):

        os.makedirs(path, exist_ok=True)
        return path

    @Handler.skip
    def exists ( self, path: str ):

        return os.path.isdir(path)

    def name ( self, path: str ):

        return os.path.basename(path)

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

    def rename ( self, path: str, name: str = None ):

        name = name or os.path.basename(path)
        new_path = os.path.join(os.path.dirname(path), os.path.basename(name))

        for i in range(5):

            try:
                os.rename(path, new_path)
                break
            except: pass
            
            time.sleep(0.01)

        return new_path

    def delete ( self, path: str ):

        shutil.rmtree(path, ignore_errors=True)
        return True

    def reset ( self, path: str ):

        self.delete(path)
        return self.new(path)

    def clear ( self, path: str ):

        for item in os.listdir(path):
            item_path = os.path.join(path, item)

            if os.path.isdir(item_path): shutil.rmtree(item_path, ignore_errors=True)
            else: os.remove(item_path)

        return True

    def copy ( self, path: str, copy_to: str ):

        shutil.copytree(path, copy_to, dirs_exist_ok=True)
        return copy_to

    def move ( self, path: str, move_to: str ):

        shutil.move(path, move_to)
        return move_to

    def size ( self, path: str ):

        total = 0

        for root, _, files in os.walk(path):
            for f in files:
                try: total += os.path.getsize(os.path.join(root, f))
                except: pass

        return total

    def size_str ( self, path: str ):

        size = self.size(path)

        for unit in [ 'B', 'KB', 'MB', 'GB', 'TB', 'PB' ]:

            if size < 1024: return f"{size:.2f} {unit}"
            size /= 1024

        return f"{size:.2f} PB"

    def depth ( self, path: str ):

        return max((str(r).count(os.sep) - str(path).count(os.sep)) for r, _, _ in os.walk(path))

    def ctime ( self, path: str ):

        return os.path.getctime(path)

    def atime ( self, path: str ):

        return os.path.getatime(path)

    def mtime ( self, path: str ):

        modified_time = 0

        for root, dirs, files in os.walk(path):
            files = [os.path.join(root, file) for file in files]
            if files: modified_time = max(modified_time, max(os.path.getmtime(file) for file in files))

        return modified_time

    def parent ( self, path: str ):

        return os.path.basename(os.path.dirname(path))

    def parent_path ( self, path: str ):

        return os.path.dirname(path)

    def parent_list ( self, path: str ):

        path = self.full_path(path)
        result = []

        while True:

            path = os.path.dirname(path)
            if not path or path in result: break

            result.append(path)

        return result[::-1]

    def children_list ( self, path ):

        return [os.path.join(path, f) for f in os.listdir(path)]

    def dir_list ( self, path: str ):

        return [os.path.join(path, f) for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]

    def file_list ( self, path: str ):

        return [os.path.join(path, f) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]

    def hidden_list ( self, path: str ):

        return [os.path.join(path, f) for f in os.listdir(path) if os.path.basename(f).startswith('.')]

    def image_list ( self, path: str ):

        return [f for f in self.file_list(path) if self.checker.image(f)]

    def audio_list ( self, path: str ):

        return [f for f in self.file_list(path) if self.checker.audio(f)]

    def video_list ( self, path: str ):

        return [f for f in self.file_list(path) if self.checker.video(f)]

    def archive_list ( self, path: str ):

        return [f for f in self.file_list(path) if self.checker.archive(f)]

    def executable_list ( self, path: str ):

        return [f for f in self.file_list(path) if self.checker.executable(f)]

    def empty_dir_list ( self, path: str ):

        return [d for d in self.dir_list(path) if not os.listdir(d)]

    def empty_file_list ( self, path: str ):

        return [f for f in self.file_list(path) if self.checker.empty(f)]

    def empty_list ( self, path: str ):

        return self.empty_dir_list(path) + self.empty_file_list(path)

    def parents ( self, path: str ):

        return [self.name(p) if self.name(p) else self.drive(path) for p in self.parent_list(path)]

    def childrens ( self, path: str ):

        return [os.path.basename(p) for p in self.children_list(path)]

    def dirs ( self, path: str ):

        return [os.path.basename(p) for p in self.dir_list(path)]

    def files ( self, path: str ):

        return [os.path.basename(p) for p in self.file_list(path)]

    def hiddens ( self, path: str ):

        return [os.path.basename(p) for p in self.hidden_list(path)]

    def images ( self, path: str ):

        return [os.path.basename(p) for p in self.image_list(path)]

    def audios ( self, path: str ):

        return [os.path.basename(p) for p in self.audio_list(path)]

    def videos ( self, path: str ):

        return [os.path.basename(p) for p in self.video_list(path)]

    def archives ( self, path: str ):

        return [os.path.basename(p) for p in self.archive_list(path)]

    def executables ( self, path: str ):

        return [os.path.basename(p) for p in self.executable_list(path)]

    def created_at ( self, path: str ):

        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.ctime(path)))

    def updated_at ( self, path: str ):

        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.mtime(path)))

    def accessed_at ( self, path: str ):

        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.atime(path)))

    def mode ( self, path: str ):

        return oct(os.stat(path).st_mode)

    def chmod ( self, path: str, mode: str ):

        os.chmod(path, int(mode, 8)); return True

    def lock ( self, path: str ):

        return self.chmod(path, '000')

    def unlock ( self, path: str ):

        return self.chmod(path, '777')

    def writable ( self, path: str ):

        return self.chmod(path, '666')

    def readable ( self, path: str ):

        return self.chmod(path, '444')

    def disk_usage ( self, path: str, type: str = 'percent' ):

        total, used, free = shutil.disk_usage(path)

        if not total: return 0
        return (self.size(path) / total) * 100 if type == 'percent' else total

    def categories ( self, path: str ):

        return dict(Counter(str(os.path.splitext(f)[1]).lower() for f in self.files(path)))

    def timestamp ( self, date: str = None ):

        if date is None: return time.time()
        if isinstance(date, (int, float)): return float(date)
        if not isinstance(date, str): return None

        formats = ("%Y", "%Y-%m", "%Y-%m-%d", "%Y-%m-%d %H", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f")
        date = date.strip(" -:") or "1970"

        for fmt in formats:
            try: return datetime.datetime.strptime(date, fmt).timestamp()
            except: pass

        return None

    def resolve_kwargs ( self, **kwargs: Any ):

        keys_mapping = {
            "patterns": ["patterns", "pattern"],
            "extensions": ["ext", "extension", "extensions"],
            "modified_at": ["last_modified", "modified_at", "modified"],
            "created_at": ["created_at", "created"],
            "sensitive": ["case_sensitive", "sensitive"],
            "hidden": ["only_hidden", "only_hiddens", "hidden", "hiddens"],
            "executable": ["only_executable", "only_executables", "executable", "executables"],
            "archive": ["only_archive", "only_archives", "archive", "archives"],
            "empty": ["only_empty", "only_empties", "empty", "empties"],
            "content": ["search_content", "file_content", 'filter_text', 'find_content', "content", "contents"],
            "readable": ["only_readable", "readable", "read_only"],
            "writable": ["only_writable", "writable", "write_only"],
            "max_size": ["max_size", "maxsize"],
            "min_size": ["min_size", "minsize"],
            "size": ["size"],
            "name": ["name"]
        }

        extracted_values = {
            key: next((kwargs[k] for k in aliases if k in kwargs and kwargs[k] is not None), None) 
            for key, aliases in keys_mapping.items()
        }

        extracted_values["patterns"] = extracted_values.get("patterns") or []
        extracted_values["extensions"] = extracted_values.get("extensions") or []

        if not isinstance(extracted_values['patterns'], list): extracted_values['patterns'] = [extracted_values['patterns']]
        if not isinstance(extracted_values['extensions'], list): extracted_values['extensions'] = [extracted_values['extensions']]

        return extracted_values

    def match_path ( self, path: str, **kwargs: Any ):

        kwargs_values = self.resolve_kwargs(**kwargs)
        patterns      = kwargs_values["patterns"]
        extensions    = kwargs_values["extensions"]
        modified_at   = kwargs_values["modified_at"]
        created_at    = kwargs_values["created_at"]
        sensitive     = kwargs_values["sensitive"]
        hidden        = kwargs_values["hidden"]
        executable    = kwargs_values["executable"]
        archive       = kwargs_values["archive"]
        empty         = kwargs_values["empty"]
        content       = kwargs_values["content"]
        readable      = kwargs_values["readable"]
        writable      = kwargs_values["writable"]
        max_size      = kwargs_values["max_size"]
        min_size      = kwargs_values["min_size"]
        size          = kwargs_values["size"]
        name          = kwargs_values["name"]

        try:
            file_size  = os.path.getsize(path)
            file_ctime = os.path.getctime(path)
            file_mtime = os.path.getmtime(path)
            file_name  = os.path.basename(path)
        except: return None

        if empty and not self.checker.empty(path): return None
        if executable and not self.checker.executable(path): return None
        if archive and not self.checker.archive(path): return None
        if hidden and not file_name.startswith('.'): return None
        if readable and not os.access(path, os.R_OK): return None
        if writable and not os.access(path, os.W_OK): return None
        if created_at and self.timestamp(created_at) > file_ctime: return None
        if modified_at and self.timestamp(modified_at) > file_mtime: return None
        if max_size and file_size > max_size: return None
        if min_size and min_size > file_size: return None
        if size and file_size != size: return None

        if name:
            try:
                _file_name, _name = file_name, name

                if not sensitive: _file_name, _name = str(_file_name).lower(), str(_name).lower()
                if _name != _file_name and _name != os.path.splitext(_file_name)[0] and not re.fullmatch(_name, _file_name): return None

            except: return None

        if content:
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
               
                    while chunk := f.read(4096):
                        if content in chunk or re.search(content, chunk): break
                    else: return None

            except: return None
            
        if patterns:
            for pattern in patterns:
                _path, _pattern = path, pattern

                if not sensitive: _path, _pattern = str(_path).lower(), str(_pattern).lower()
                if not fnmatch.fnmatchcase(_path, _pattern) and _pattern not in _path: return None
          
        if extensions:
            for ext in extensions:
                _path, _ext = path, ext

                if not sensitive: _path, _ext = str(_path).lower(), str(_ext).lower()
                if not _path.endswith(_ext) and not fnmatch.fnmatchcase(_path, _ext): return None

        return path

    def walk ( self, path: str, callback: Callable = None, **kwargs: Any ):

        include_dirs  = kwargs.get('include_dirs', True)
        include_files = kwargs.get('include_files', True)
        files_type    = kwargs.get('files_type', None)
        max_depth     = kwargs.get('max_depth', None)
        topdown       = kwargs.get('topdown', True)

        for root, dirs, files in os.walk(path, topdown=topdown):

            if max_depth and str(os.path.relpath(root, path)).count(os.sep) > max_depth - 1: continue
            items = itertools.chain(dirs if include_dirs else [], files if include_files else [])

            for item in items:

                item_path = os.path.normpath(os.path.join(root, item))

                if include_files and files_type and os.path.isfile(item_path):
                    if self.checker.type(item_path) != files_type: continue

                if not self.match_path(item_path, **kwargs): continue

                if callback: callback(item_path)
                yield item_path

    def search ( self, path: str, callback: Callable = None, **kwargs: Any ):

        return self.walk(path, callback, **kwargs)

    def walk_dirs ( self, path: str, callback: Callable = None, **kwargs: Any ):

        return self.walk(path, callback, **{**kwargs, 'include_dirs': True, 'include_files': False})

    def walk_files ( self, path: str, callback: Callable = None, **kwargs: Any ):

        return self.walk(path, callback, **{**kwargs, 'include_dirs': False, 'include_files': True})

    def walk_images ( self, path: str, callback: Callable = None, **kwargs: Any ):

        return self.walk_files(path, callback, **{**kwargs, 'files_type': 'image'})

    def walk_audios ( self, path: str, callback: Callable = None, **kwargs: Any ):

        return self.walk_files(path, callback, **{**kwargs, 'files_type': 'audio'})

    def walk_videos ( self, path: str, callback: Callable = None, **kwargs: Any ):

        return self.walk_files(path, callback, **{**kwargs, 'files_type': 'video'})

    def walk_archives ( self, path: str, callback: Callable = None, **kwargs: Any ):

        return self.walk_files(path, callback, **{**kwargs, 'files_type': 'archive'})

    def walk_executables ( self, path: str, callback: Callable = None, **kwargs: Any ):

        return self.walk_files(path, callback, **{**kwargs, 'files_type': 'executable'})

    def last_modified_file ( self, path: str, **kwargs: Any ):

        return max(self.walk_files(path, **kwargs), key=os.path.getmtime, default=None)

    def last_modified_dir ( self, path: str, **kwargs: Any ):

        file = self.last_modified_file(path, **kwargs)
        return  os.path.dirname(file) if file else None

    def largest_file ( self, path: str, **kwargs: Any ):

        return max(self.walk_files(path, **kwargs), key=os.path.getsize, default=None)

    def largest_dir ( self, path: str, **kwargs: Any ):

        target_dir = None
        size = 0

        for dir in self.walk_dirs(path, **kwargs):

            files = self.files(dir)
            if not files: continue

            dir_size = max(os.path.getsize(os.path.join(dir, file)) for file in files)

            if dir_size > size:
                size = dir_size
                target_dir = dir

        return target_dir

    def largest_file_size ( self, path: str, **kwargs: Any ):

        return os.path.getsize(self.largest_file(path, **kwargs))

    def largest_dir_size ( self, path: str, **kwargs: Any ):

        return self.size(self.largest_dir(path, **kwargs))

    def categorize ( self, path: str, dest: str = None, **kwargs: Any ):

        dest = dest or self.join(self.full_path(self.parent_path(path)), f"{self.name(path)} categories")
        if self.exists(dest): dest = self.new(dest)

        for file in self.walk_files(path, **kwargs):

            category = self.new(os.path.join(dest, f"{self.checker.type(file)}s"))
            new_file = os.path.join(category, os.path.basename(file))
            file_path = new_file
            counter = 1

            while os.path.exists(file_path):
                name, ext = os.path.splitext(new_file)
                file_path = f"{name} ({counter}){ext}"
                counter += 1

            shutil.copy(file, file_path)

        return dest

    def info ( self, path: str ):

        return {
            "name"        : self.name(path),
            "path"        : self.full_path(path),
            "size"        : self.size(path),
            "depth"       : self.depth(path),
            "created_at"  : self.created_at(path),
            "updated_at"  : self.updated_at(path),
            "accessed_at" : self.accessed_at(path),
            "categories"  : self.categories(path),
            "dirs"        : len(self.dir_list(path)),
            "files"       : len(self.file_list(path)),
            "hiddens"     : len(self.hidden_list(path)),
            "images"      : len(self.image_list(path)),
            "audios"      : len(self.audio_list(path)),
            "videos"      : len(self.video_list(path)),
            "archives"    : len(self.archive_list(path)),
            "executables" : len(self.executable_list(path)),
        }

    def tree ( self, path: str, level: int = 0, max_depth: int = None ):

        prefix = "│   " * level
        print(f"{prefix}📁 {os.path.basename(path)}")

        for item in sorted(os.listdir(path)):

            full = os.path.join(path, item)

            if os.path.isdir(full) and (not max_depth or level + 1 < max_depth): self.tree(full, level + 1, max_depth)
            elif os.path.isfile(full): print(f"{prefix}│   📄 {item}")

        return True

    def backup ( self, path: str, dest: str = None, name: str = None, compress: bool = True, **kwargs: Any ):

        dest = dest or self.parent_path(path)
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

        for file in self.walk_files(path, **kwargs):

            try:
                ts = max(os.path.getctime(file), os.path.getmtime(file))
                if ts < threshold_time: os.remove(file)
            except: pass

        return True

    def sync ( self, path: str, dest: str ):

        os.makedirs(dest, exist_ok=True)

        src_files  = []
        dest_files = []

        for root, _, files in os.walk(path):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), path)
                src_files.append(rel)

        for root, _, files in os.walk(dest):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), dest)
                dest_files.append(rel)

        to_sync   = set(src_files)
        to_delete = sorted(set(dest_files) - to_sync, key=lambda x: x.count("/"), reverse=True)

        for rel in to_sync:

            src_path  = os.path.join(path, rel)
            dest_path = os.path.join(dest, rel)

            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

            try:

                changed = (
                    not os.path.exists(dest_path) or
                    os.path.getsize(src_path) != os.path.getsize(dest_path) or
                    os.path.getmtime(dest_path) < os.path.getmtime(src_path)
                )

                if changed:
                    for _ in range(3):
                        try:
                            with open(src_path, "rb") as s, open(dest_path, "wb") as d:
                                while chunk := s.read(8192): d.write(chunk)
                            break
                        except: time.sleep(0.1)

            except: pass

        for rel in to_delete:
            target = os.path.join(dest, rel)

            try:
                if os.path.isfile(target): os.remove(target)
                else: shutil.rmtree(target, ignore_errors=True)
            except: pass

        return dest

    def watch ( self, path: str, callback: Callable, watch_dirs: bool = True ):

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

            try: rel_path = os.path.relpath(changed_path, path if changed_path.startswith(path) else dest)
            except: return

            dest_path = os.path.join(dest if changed_path.startswith(path) else path, rel_path)
            if self.timer: self.timer.cancel()

            def perform_sync ():
               
                try:

                    if os.path.isdir(changed_path): self.sync(changed_path, dest_path)

                    elif os.path.isfile(changed_path):

                        changed = (
                            not os.path.exists(dest_path) or
                            os.path.getsize(changed_path) != os.path.getsize(dest_path) or
                            os.path.getmtime(dest_path) < os.path.getmtime(changed_path)
                        )

                        if not changed: return
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                        for _ in range(3):
                            try:
                                with open(changed_path, "rb") as s, open(dest_path, "wb") as d:
                                    while chunk := s.read(8192): d.write(chunk)
                                break
                            except: time.sleep(0.1)

                    else:
                        if os.path.exists(dest_path):
                            if os.path.isfile(dest_path): os.remove(dest_path)
                            else: shutil.rmtree(dest_path, ignore_errors=True)

                except: pass

            self.timer = threading.Timer(0.5, perform_sync)
            self.timer.start()

        self.watch(path, on_event)
        if reverse: self.watch_sync(dest, path, False, False)

    def encrypt ( self, path: str, key_path: str = None ):

        return self.encryptor.encrypt(path, key_path)

    def decrypt ( self, path: str, key_path: str = None ):

        return self.encryptor.decrypt(path, key_path)

    def compress ( self, path: str, out_dir: str = None, out_name: str = None, fmt: str = None ):

        return self.compressor.compress(path, out_dir, out_name, fmt)

    @Handler.skip
    def extract ( self, path: str, extract_to: str = None ):

        return self.compressor.extract(path, extract_to)

    def upload ( self, path: str, remote_path: str = None, provider: str = 's3', credentials: dict = {}, options: dict = {}, **kwargs: Any ):

        return self.manager().connect(provider, credentials, options).upload_folder(path, remote_path, callback=callback, **kwargs)

    @Handler.skip
    def download ( self, remote_path: str, path: str = None, provider: str = 's3', credentials: dict = {}, options: dict = {}, **kwargs: Any ):

        return self.manager().connect(provider, credentials, options).download_folder(remote_path, path, callback=callback, **kwargs)
