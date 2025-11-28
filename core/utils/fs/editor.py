from typing import Any, Union, Callable, List, IO
from string import Template
import shutil, difflib, chardet, os, re

class Editor:

    def __init__ ( self ):

        pass

    def read ( self, path: str ):

        with open(path, 'r', encoding='utf-8', errors='ignore') as f: return f.read()

    def write ( self, path: str, content: str ):

        with open(path, 'w', encoding='utf-8', errors='ignore') as f: f.write(content)
        return len(content)

    def append ( self, path: str, content: str ):

        with open(path, 'a', encoding='utf-8', errors='ignore') as f: f.write(content)
        return len(content)

    def safe_write ( self, path: str, content: str ):

        backup = f"{path}.bak"

        try:
            if os.path.exists(path): shutil.copy2(path, backup)
            with open(path, "w", encoding="utf-8", errors="ignore") as f: f.write(content)

            if os.path.exists(backup): os.remove(backup)
            return True

        except Exception as e:
            if os.path.exists(backup): shutil.move(backup, path)
            raise e

    def safe_append ( self, path: str, content: str ):

        backup = f"{path}.bak"

        try:
            if os.path.exists(path): shutil.copy2(path, backup)
            with open(path, "a", encoding="utf-8", errors="ignore") as f: f.write(content)

            if os.path.exists(backup): os.remove(backup)
            return True

        except Exception as e:
            if os.path.exists(backup): shutil.move(backup, path)
            raise e

    def lines ( self, path: str ):

        with open(path, 'r', encoding='utf-8', errors='ignore') as f: return f.read().splitlines()

    def diff ( self, path_a: str, path_b: str ):

        a_lines = self.lines(path_a)
        b_lines = self.lines(path_b)

        diff_lines = difflib.unified_diff(a_lines, b_lines, fromfile=path_a, tofile=path_b, lineterm='')
        return "\n".join(diff_lines)

    def open ( self, path: str, mode: str = "r", encoding: str = None ):

        if "b" in mode: return open(path, mode)
        else: return open(path, mode, encoding=encoding or 'utf-8')

    def close ( self, file: IO ):

        if hasattr(file, "close"): file.close()
        return getattr(file, "name", None)

    def rewind ( self, file: IO ):

        if hasattr(file, "seek"): file.seek(0)
        return getattr(file, "name", None)

    def detect_encoding ( self, path: str ):

        with open(path, "rb") as f: raw = f.read(4096)

        result = chardet.detect(raw)
        return result.get("encoding", "utf-8")

    def render ( self, path: str, context: dict ):

        text = self.read(path)
        tpl  = Template(text)

        return tpl.safe_substitute(context)

    def _pattern ( self, expr: Union[str, re.Pattern], escape: bool = True ):

        if isinstance(expr, re.Pattern): return expr.pattern
        return re.escape(expr) if escape else expr

    def replace ( self, path: str, target: Union[str, re.Pattern], repl: Union[str, Callable], count: int = 0, flags: int = re.MULTILINE ):

        text = self.read(path)

        pattern = target if isinstance(target, re.Pattern) else re.escape(target)
        new_text, n = re.subn(pattern, repl, text, count=count, flags=flags)

        if n: self.safe_write(path, new_text)
        return n

    def replace_between ( self, path: str, start: Union[str, re.Pattern], end: Union[str, re.Pattern], repl: str, flags: int = re.DOTALL ):

        text = self.read(path)
        s, e = self._pattern(start), self._pattern(end)

        pattern = f"({s})(.*?){e}"
        new_text, n = re.subn(pattern, lambda m: f"{m.group(1)}{repl}{end}", text, flags=flags)

        if n: self.safe_write(path, new_text)
        return n

    def insert_after ( self, path: str, target: Union[str, re.Pattern], insert_text: str, flags: int = re.MULTILINE ):

        text = self.read(path)
        def replacer ( m ): return m.group(0) + insert_text

        pattern = target if isinstance(target, re.Pattern) else re.escape(target)
        new_text, n = re.subn(pattern, replacer, text, flags=flags)

        if n: self.safe_write(path, new_text)
        return n

    def insert_before ( self, path: str, target: Union[str, re.Pattern], insert_text: str, flags: int = re.MULTILINE ):

        text = self.read(path)
        def replacer ( m ): return insert_text + m.group(0)

        pattern = target if isinstance(target, re.Pattern) else re.escape(target)
        new_text, n = re.subn(pattern, replacer, text, flags=flags)

        if n: self.safe_write(path, new_text)
        return n

    def delete ( self, path: str, target: Union[str, re.Pattern], flags: int = re.MULTILINE ):

        text = self.read(path)

        pattern = target if isinstance(target, re.Pattern) else re.escape(target)
        new_text, n = re.subn(pattern, "", text, flags=flags)

        if n: self.safe_write(path, new_text)
        return n

    def delete_between ( self, path: str, start: Union[str, re.Pattern], end: Union[str, re.Pattern], flags: int = re.DOTALL ):

        text = self.read(path)
        s, e = self._pattern(start), self._pattern(end)

        pattern = f"{s}.*?{e}"
        new_text, n = re.subn(pattern, "", text, flags=flags)

        if n: self.safe_write(path, new_text)
        return n

    def delete_until ( self, path: str, start: Union[str, re.Pattern], flags: int = re.DOTALL ):

        text = self.read(path)
        s = self._pattern(start)

        pattern = f"^.*?{s}"
        new_text, n = re.subn(pattern, "", text, flags=flags)

        if n: self.safe_write(path, new_text)
        return n

    def delete_after ( self, path: str, end: Union[str, re.Pattern], flags: int = re.DOTALL ):

        text = self.read(path)
        e = self._pattern(end)

        pattern = f"{e}.*$"
        new_text, n = re.subn(pattern, "", text, flags=flags)

        if n: self.safe_write(path, new_text)
        return n

    def replace_line ( self, path: str, line_no: int, new_text: str ):

        lines = self.lines(path)

        if 1 <= line_no <= len(lines):
            lines[line_no - 1] = new_text
            self.safe_write(path, "\n".join(lines))
            return True

        return False

    def insert_line ( self, path: str, line_no: int, text: str ):

        lines = self.lines(path)

        if line_no < 1: line_no = 1
        if line_no > len(lines): line_no = len(lines) + 1

        lines.insert(line_no - 1, text)
        self.safe_write(path, "\n".join(lines))

        return True

    def delete_line ( self, path: str, line_no: int ):

        lines = self.lines(path)

        if 1 <= line_no <= len(lines):
            del lines[line_no - 1]
            self.safe_write(path, "\n".join(lines))
            return True

        return False

    def replace_block ( self, path: str, start_line: int, end_line: int, new_content: str ):

        lines = self.lines(path)

        if 1 <= start_line <= end_line <= len(lines):
            lines[start_line-1:end_line] = new_content.splitlines()
            self.safe_write(path, "\n".join(lines))
            return True

        return False

    def extract ( self, path: str, target: Union[str, re.Pattern], flags: int = re.MULTILINE ):
  
        text = self.read(path)
        pattern = target if isinstance(target, re.Pattern) else re.escape(target)
        return [m.group(0) for m in re.finditer(pattern, text, flags)]

    def extract_between ( self, path: str, start: Union[str, re.Pattern], end: Union[str, re.Pattern], flags: int = re.DOTALL ):

        text = self.read(path)
        s, e = self._pattern(start), self._pattern(end)

        pattern = f"{s}(.*?){e}"
        return [m.group(1) for m in re.finditer(pattern, text, flags)]

    def extract_lines ( self, path: str, start_line: int, end_line: int ) -> List[str]:

        lines = self.lines(path)

        if start_line < 1: start_line = 1
        if end_line > len(lines): end_line = len(lines)

        return lines[start_line - 1:end_line]

    def edit ( self, path: str, func: Callable[[str], str] ):

        text = self.read(path)
        new_text = func(text)

        if new_text != text:
            self.safe_write(path, new_text)
            return True

        return False

    def map_lines ( self, path: str, func: Callable[[str], Any] ):

        lines = self.lines(path)
        new_lines = [func(line) for line in lines]

        self.safe_write(path, "\n".join(map(str, new_lines)))
        return True

    def surround ( self, path: str, target: Union[str, re.Pattern], prefix: str, suffix: str, flags: int = re.MULTILINE ):

        text = self.read(path)

        pattern = target if isinstance(target, re.Pattern) else re.escape(target)
        new_text, n = re.subn(pattern, lambda m: prefix + m.group(0) + suffix, text, flags=flags)

        if n: self.safe_write(path, new_text)
        return n

    def move_block ( self, path: str, start: Union[str, re.Pattern], end: Union[str, re.Pattern], new_pos: Union[str, re.Pattern] ):

        lines = self.lines(path)
        start_idx = end_idx = new_pos_idx = None

        for i, line in enumerate(lines):
            if start_idx is None and re.search(start, line): start_idx = i
            if start_idx is not None and re.search(end, line):
                end_idx = i
                break

        if start_idx is None or end_idx is None: return False

        block = lines[start_idx:end_idx + 1]
        del lines[start_idx:end_idx + 1]

        for i, line in enumerate(lines):
            if re.search(new_pos, line):
                new_pos_idx = i
                break

        if new_pos_idx is None: new_pos_idx = len(lines) - 1

        insert_at = new_pos_idx + 1
        lines[insert_at:insert_at] = block

        self.safe_write(path, "\n".join(lines))
        return True

    def dict_to_env ( self, path: str, data: dict, append: bool = False ):

        mode = "a" if append else "w"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        with open(path, mode, encoding="utf-8", errors="ignore") as f:
            for k, v in data.items(): f.write(f"{k}={v}\n")

        return path

    def compile_env_vars ( self, env_data: dict ):

        pattern = re.compile(r"\${(\w+)}|\{(\w+)\}")

        def compile_var ( match ):

            key = match.group(1) or match.group(2)
            if key in env_data: return env_data[key]

            val = os.getenv(key)
            return val if val is not None else match.group(0)

        for k, v in env_data.items():

            expanded = re.sub(pattern, compile_var, v)
            env_data[k] = expanded

        return env_data

    def resolve_env_var ( self, value: str ):

        return self.compile_env_vars({"_": value}).get("_", value)

    def env_to_dict ( self, path: str ):

        env_data = {}
        if not os.path.isfile(path): return env_data

        with open(path, "r", encoding="utf-8", errors="ignore") as f:

            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue

                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    env_data[k] = v

        return self.compile_env_vars(env_data)

    def env_get ( self, path: str, key: str ):

        return self.env_to_dict(path).get(key)

    def env_set ( self, path: str, key: str, value: str ):

        lines = []
        found = False

        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip().startswith(f"{key}="):
                        lines.append(f"{key}={value}")
                        found = True
                    else: lines.append(line.rstrip("\n"))

        if not found: lines.append(f"{key}={value}")

        with open(path, "w", encoding="utf-8", errors="ignore") as f:
            f.write("\n".join(lines))

        return True

    def env_delete ( self, path: str, key: str ):

        if not os.path.isfile(path): return False
        new_lines = []

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip().startswith(f"{key}="):
                    new_lines.append(line.rstrip("\n"))

        with open(path, "w", encoding="utf-8", errors="ignore") as f:
            f.write("\n".join(new_lines))

        return True

    def env_merge ( self, base_path: str, new_path: str ):

        base, new = {}, {}

        if os.path.isfile(base_path):
            with open(base_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("#"):
                        k, v = line.split("=", 1)
                        base[k.strip()] = v.strip()

        if os.path.isfile(new_path):
            with open(new_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("#"):
                        k, v = line.split("=", 1)
                        new[k.strip()] = v.strip()

        base.update(new)

        with open(base_path, "w", encoding="utf-8", errors="ignore") as f:
            for k, v in base.items():
                f.write(f"{k}={v}\n")

        return True

    def env_diff ( self, base_path: str, compare_path: str ):

        base_env    = self.env_to_dict(base_path)
        compare_env = self.env_to_dict(compare_path)

        diff = {
            "added"    : { k:v for k,v in compare_env.items() if k not in base_env },
            "removed"  : { k:v for k,v in base_env.items() if k not in compare_env },
            "changed"  : { k:(base_env[k], compare_env[k]) for k in base_env if k in compare_env and base_env[k] != compare_env[k] },
            "unchanged": { k:v for k,v in base_env.items() if k in compare_env and base_env[k] == compare_env[k] }
        }

        return diff

    def env_comment ( self, path: str, key: str, comment: str ):

        if not os.path.isfile(path): return False

        new_lines = []
        added = False

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not added and line.strip().startswith(f"{key}="):
                    new_lines.append(f"# {comment}")
                    added = True

                new_lines.append(line.rstrip("\n"))

        with open(path, "w", encoding="utf-8", errors="ignore") as f:
            f.write("\n".join(new_lines))

        return True

    def load_env ( self, path: str, override: bool = False ):

        if not os.path.isfile(path): return False

        for key, value in self.env_to_dict(path).items():
            if not override and key in os.environ: continue
            os.environ[key] = value

        return True
