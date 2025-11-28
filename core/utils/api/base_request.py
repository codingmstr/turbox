import os, base64, time, hashlib, copy, mimetypes, random, jwt, email.utils
from typing import Any, Callable, Iterable
from ..micro import func

class BaseRequest:

    def __init__ ( self, base_url: str = None ):

        self.reset()
        self._base_url = base_url

    def __enter__ ( self ):

        return self

    def __exit__ ( self, *_ ):

        self.__init__()

    def reset ( self ):

        self._base_url         = ''
        self._endpoint         = ''
        self._gql_endpoint     = ''
        self._query            = ''
        self._timeout          = 120
        self._chunk            = True
        self._stream           = False
        self._stop_stream      = False
        self._handle_errors    = False
        self._verify           = True
        self._proxy            = None
        self._session          = None
        self._impersonate      = 'chrome120'

        self._headers          = {}
        self._cookies          = {}
        self._params           = {}
        self._data             = {}
        self._variables        = {}
        self._files            = []
        self._deps             = []
        self._limits           = []
        self._calls            = {}
        self._oauth2           = {}
        self._on_before        = []
        self._on_after         = []
        self._on_retry         = []
        self._on_success       = []
        self._on_error         = []
        self._on_stream        = []
        self._on_progress      = []

        self._max_retries      = 0
        self._base_delay       = 0
        self._max_delay        = 0
        self._last_delay       = 0
        self._retry_codes      = []
        self._retry_mode       = 'exponential'

        self._cb_state         = "closed"
        self._cb_failures      = 0
        self._cb_open_time     = 0
        self._cb_threshold     = 5
        self._cb_cooldown      = 10
        self._cb_half_open_try = False

        return self

    def set ( self, dict_value: dict = None, **options: Any ):

        for k, v in ({**(dict_value or {}), **options}).items():
            if hasattr(self, f"_{k}"): setattr(self, f"_{k}", v)

        return self

    def clone ( self, deep: bool = False ):

        instance = object.__new__(self.__class__)

        safe_dict = {k: v for k, v in self.__dict__.items() if k not in ("_session", "_sse_buffer")}
        instance.__dict__.update(copy.deepcopy(safe_dict) if deep else safe_dict)

        return instance


    def on_before ( self, *fn: Callable, reset: bool = False ):

        if reset: self._on_before = fn
        else: self._on_before.extend(fn)

        return self

    def on_after ( self, *fn: Callable, reset: bool = False ):

        if reset: self._on_after = fn
        else: self._on_after.extend(fn)

        return self

    def on_retry ( self, *fn: Callable, reset: bool = False ):

        if reset: self._on_retry = fn
        else: self._on_retry.extend(fn)

        return self

    def on_success ( self, *fn: Callable, reset: bool = False ):

        if reset: self._on_success = fn
        else: self._on_success.extend(fn)

        return self

    def on_error ( self, *fn: Callable, reset: bool = False ):

        if reset: self._on_error = fn
        else: self._on_error.extend(fn)

        return self

    def on_stream ( self, *fn: Callable, reset: bool = False ):

        if reset: self._on_stream = fn
        else: self._on_stream.extend(fn)

        return self

    def on_progress ( self, *fn: Callable, reset: bool = False ):

        if reset: self._on_progress = fn
        else: self._on_progress.extend(fn)

        return self

    def set_dependencies ( self, *fn: Callable, reset: bool = False ):

        if reset: self._deps = fn
        else: self._deps.extend(fn)

        return self

    def set_base_url ( self, url: str = '' ):

        self._base_url = str(url or '')
        return self

    def set_endpoint ( self, endpoint: str = '' ):

        self._endpoint = str(endpoint or '')
        return self

    def set_gql_endpoint ( self, endpoint: str = 'graphql' ):

        self._gql_endpoint = endpoint
        return self

    def set_query ( self, query: str = '' ):

        self._query = query
        return self

    def set_timeout ( self, timeout: float = 120 ):

        self._timeout = float(timeout or 0)
        return self

    def set_stream ( self, stream: bool = False ):

        self._stream = stream
        return self

    def set_verify ( self, verify: bool = True ):

        self._verify = verify
        return self

    def set_handler ( self, handle: bool = False ):

        self._handle_errors = handle
        return self

    def set_proxy ( self, url: str ):

        self._proxy = url
        return self

    def set_impersonate ( self, impersonate: str ):

        self._impersonate = impersonate
        return self

    def set_retry ( self, max_retries: int = None, codes: Iterable = None, mode: str = None ):

        if max_retries is not None : self._max_retries = max_retries
        if codes is not None: self._retry_codes = codes
        if mode is not None: self._retry_mode  = mode

        return self

    def set_delay ( self, base_delay: float = 0.2, max_delay: float = 10 ):

        self._base_delay = base_delay
        self._max_delay  = max_delay

        return self

    def set_limit ( self, rate: int = 60, per_minutes: float = 1, endpoint: str = None, method: str = None ):

        current = (rate, per_minutes, endpoint, method)

        for i, lm in enumerate(self._limits):
            if lm[2] == endpoint and lm[3] == method:
                self._limits[i] = current
                break
        else: self._limits.append(current)

        return self

    def set_breaker ( self, threshold: int = 5, cooldown: float = 10 ):

        self._cb_threshold = threshold
        self._cb_cooldown = cooldown

        return self

    def set_headers ( self, dict_value: dict = None, reset: bool = False, **kwargs ):

        value = {**(dict_value or {}), **kwargs}

        if reset: self._headers = value
        else: self._headers.update(value)

        return self

    def set_cookies ( self, dict_value: dict = None, reset: bool = False, **kwargs ):

        value = {**(dict_value or {}), **kwargs}

        if reset: self._cookies = value
        else: self._cookies.update(value)

        return self

    def set_params ( self, dict_value: dict = None, reset: bool = False, **kwargs ):

        value = {**(dict_value or {}), **kwargs}

        if reset: self._params = value
        else: self._params.update(value)

        return self

    def set_data ( self, dict_value: dict = None, reset: bool = False, **kwargs ):

        value = {**(dict_value or {}), **kwargs}

        if reset: self._data = value
        else: self._data.update(value)

        return self

    def set_variables ( self, dict_value: dict = None, reset: bool = False, **kwargs ):

        value = {**(dict_value or {}), **kwargs}

        if reset: self._variables = value
        else: self._variables.update(value)

        return self

    def set_files ( self, *args, reset: bool = False ):

        if reset: self._files = self.resolve_files(*args)
        else: self._files.extend(self.resolve_files(*args))

        return self

    def set_token ( self, token: str, prefix: str = "Bearer" ):

        self._headers["Authorization"] = f"{prefix} {str(token or '').strip()}"
        return self

    def set_bearer_token ( self, token: str ):

        self.set_token(token, "Bearer")
        return self

    def set_basic_token ( self, client_id: str, client_secret: str ):

        self.set_token(base64.b64encode(f"{client_id}:{client_secret}".encode()).decode(), "Basic")
        self._headers['Content-Type'] = 'application/x-www-form-urlencoded'

        return self

    def set_jwt_token ( self, payload: dict, secret: str, algorithm: str = "HS256", exp: int = 3600 ):

        self.set_token(jwt.encode({**payload, "exp": int(time.time()) + exp}, secret, algorithm=algorithm), "Bearer")
        return self

    def set_api_keys ( self, public_key: str, secret_key: str, header_public: str = "X-Public-Key", header_secret: str = "X-Secret-Key" ):

        self._headers[header_public] = public_key
        self._headers[header_secret] = secret_key

        return self

    def set_hmac_signature ( self, message: str, secret_key: str, header_name: str = "X-Signature" ):

        signature = hashlib.sha256((message + secret_key).encode()).hexdigest()
        self._headers[header_name] = signature

        return self


    def reset_limiter ( self ):

        self._limits = []
        self._calls  = {}

        return self

    def reset_retries ( self ):

        self._max_retries    = 0
        self._base_delay     = 0
        self._max_delay      = 0
        self._last_delay     = 0
        self._retry_codes    = []
        self._retry_mode     = 'exponential'

        return self

    def reset_breaker ( self ):

        self._cb_state     = "closed"
        self._cb_failures  = 0
        self._cb_open_time = 0
        self._cb_threshold = 5
        self._cb_cooldown  = 10

        return self

    def clear_dependencies ( self ):

        self._deps = []
        return self

    def clear_auth ( self ):

        self._oauth2 = {}
        self._headers.pop("Authorization", None)

        return self

    def clear_session ( self ):

        self._session = None
        return self

    def clear_proxy ( self ):

        self._proxy = None
        return self

    def clear_params ( self ):

        self._params = {}
        return self

    def clear_data ( self ):

        self._data = {}
        return self

    def clear_variables ( self ):

        self._variables = {}
        return self

    def clear_headers ( self ):

        self._headers = {}
        return self

    def clear_cookies ( self ):

        self._cookies = {}
        return self

    def clear_files ( self ):

        self._files = []
        return self

    def clear_hooks ( self ):

        self._on_before   = []
        self._on_after    = []
        self._on_retry    = []
        self._on_success  = []
        self._on_error    = []
        self._on_stream   = []
        self._on_progress = []

        return self

    def stop_stream ( self ):

        self._stop_stream = True


    def new_instance ( self, item: Any ):

        instance = self.clone(True)
        method, endpoint = 'get', ''

        if isinstance(item, str): method, endpoint = 'get', str(item or '')

        elif isinstance(item, dict):

            method   = str(item.get('method') or 'get')
            endpoint = str(item.get('endpoint') or item.get('url') or item.get('path') or '')
            headers  = dict(item.get('headers', {}))
            cookies  = dict(item.get('cookies', {}))
            params   = dict(item.get('params', {}))
            data     = dict(item.get('data', {}))
            files    = list(item.get('files', []))

            if headers: instance.set_headers(**headers)
            if cookies: instance.set_cookies(**cookies)
            if params:  instance.set_params(**params)
            if data:    instance.set_data(**data)
            if files:   instance.set_files(*files)

        elif isinstance(item, (list, tuple, set)):

            if len(item) == 1: method, endpoint = 'get', str(item[0] or '')
            elif len(item) > 1: method, endpoint = str(item[0] or 'get'), str(item[1] or '')

        return instance, method, endpoint

    def resolve_method_url ( self, method: str = None, endpoint: str = None ):

        method   = str(method or 'get').strip().upper()
        endpoint = str(endpoint or self._endpoint or '').strip().strip('/')
        base_url = str(self._base_url or '').strip().strip('/')
        full_url = (endpoint if endpoint.startswith('http') else f"{base_url}/{endpoint}").strip('/')

        if not full_url.startswith("http"): raise ValueError(f"Invalid URL resolved: {full_url}")
        if method not in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD']: raise ValueError(f"Invalid Method: {method}") 

        return method, full_url

    def read_file ( self, path: str ):

        with open(path, 'rb') as f:
            return f.read()

    def resolve_file ( self, path: str ):

        resolved, files = [], []

        if os.path.isfile(path):
            resolved.append(os.path.abspath(path))

        elif os.path.isdir(path):
            for root, _, file_list in os.walk(path):
                for f in file_list:
                    full_path = os.path.join(root, f)
                    resolved.append(os.path.abspath(full_path))

        elif isinstance(path, (list, tuple, set)):
            [resolved.extend(self.resolve_file(p)) for p in path]

        for f in list(dict.fromkeys(resolved)):

            filename = os.path.basename(f)
            name = os.path.splitext(filename)[0]

            files.append({
                "name": name,
                "filename": filename,
                "local_path": f if self._chunk else None,
                "data": self.read_file(f) if not self._chunk else None,
                "content_type": mimetypes.guess_type(f)[0] or "application/octet-stream"
            })

        return files

    def resolve_files ( self, *paths ):

        files, unique, seen = [], [], set()

        for item in paths:

            if not item: continue

            elif isinstance(item, dict):

                valid = True

                for key, val in item.items():

                    if isinstance(val, tuple) and len(val) == 3 and getattr(val[1], "read", None):

                        filename = val[0]
                        fileobj  = val[1]
                        mimetype = val[2] or "application/octet-stream"

                        files.append({
                            "name": key,
                            "filename": filename,
                            "local_path": fileobj.name if self._chunk else None,
                            "data": fileobj.read() if not self._chunk else None,
                            "content_type": mimetype
                        })

                        if not self._chunk: fileobj.seek(0)
                        valid = False

                if valid: files.append(item)

            elif isinstance(item, str):
                files.extend(self.resolve_file(item))

            elif isinstance(item, os.PathLike):
                files.extend(self.resolve_file(os.fspath(item)))

            elif isinstance(item, (list, tuple, set)):

                for x in item:

                    if not x: continue

                    if isinstance(x, dict): files.append(x)
                    elif isinstance(x, (str, os.PathLike)): files.extend(self.resolve_file(os.fspath(x)))
                    elif isinstance(x, tuple) and len(x) == 3 and getattr(x[1], "read", None):

                        files.append({
                            "name": os.path.splitext(x[0])[0],
                            "filename": x[0],
                            "local_path": x[1].name if self._chunk else None,
                            "data": x[1].read() if not self._chunk else None,
                            "content_type": x[2] or "application/octet-stream"
                        })

                        if not self._chunk: x[1].seek(0)

            elif isinstance(item, tuple) and len(item) == 3 and getattr(item[1], "read", None):

                files.append({
                    "name": os.path.splitext(item[0])[0],
                    "filename": item[0],
                    "local_path": item[1].name if self._chunk else None,
                    "data": item[1].read() if not self._chunk else None,
                    "content_type": item[2] or "application/octet-stream"
                })
                
                if not self._chunk: item[1].seek(0)

            elif getattr(item, "read", None):

                filename = os.path.basename(item.name)

                files.append({
                    "name": os.path.splitext(filename)[0],
                    "filename": filename,
                    "local_path": item.name if self._chunk else None,
                    "data": item.read() if not self._chunk else None,
                    "content_type": mimetypes.guess_type(filename)[0] or "application/octet-stream"
                })

                if not self._chunk: item.seek(0)

        for f in files:
            key = f.get("local_path") or (f.get("name"), f.get("filename"))

            if key not in seen:
                seen.add(key)
                unique.append(f)

        return unique

    def find_limiter ( self, endpoint: str, method: str ):

        limits = list(reversed(self._limits))

        for rate, per_minutes, ep, m in limits:
            if ep == endpoint and m == method:
                return (rate, per_minutes)

        for rate, per_minutes, ep, m in limits:
            if ep == endpoint and m is None:
                return (rate, per_minutes)

        for rate, per_minutes, ep, m in limits:
            if ep is None and m is None:
                return (rate, per_minutes)

        return None

    def check_limiter ( self, endpoint: str, method: str ):

        selected = self.find_limiter(endpoint, method)
        if not selected: return True

        max_calls, per_minutes = selected
        if not max_calls or not per_minutes: return True

        key = ((endpoint or '').split('?', 1)[0], method or '')

        now, window = time.time(), per_minutes * 60
        if key not in self._calls: self._calls[key] = []

        calls = [t for t in self._calls[key] if now - t < window]
        self._calls[key] = calls
        if len(calls) >= max_calls: return False

        self._calls[key].append(now)
        return True

    def resolve_delay ( self, attempt: int, res = None ):

        if res:

            retry_after = res.headers.get("Retry-After")

            if retry_after:

                try: return float(retry_after)
                except ValueError: return max(0.01, email.utils.parsedate_to_datetime(retry_after).timestamp() - time.time())
    
        base, max_delay, mode = self._base_delay, self._max_delay, self._retry_mode

        if mode == "exponential":
            delay = base * (2 ** attempt)

        elif mode == "jitter":
            delay = random.uniform(0, base * (2 ** attempt))

        elif mode == "decorrelated":
            prev = self._last_delay or base
            delay = random.uniform(base, prev * 3)
            self._last_delay = delay

        else: delay = base * (2 ** attempt)

        if max_delay > 0: delay = min(delay, max_delay)
        return max(0.01, delay)

    def circuit_allowed ( self ):

        state = self._cb_state
        now = time.time()

        if state == "closed": return True

        if state == "open":

            if now < self._cb_open_time + self._cb_cooldown: return False

            self._cb_state = "half-open"
            self._cb_half_open_try = False

            return True

        if not self._cb_half_open_try:
            self._cb_half_open_try = True
            return True

        return False

    def circuit_update ( self, success: bool ):

        if success:

            self._cb_state = "closed"
            self._cb_failures = 0
            self._cb_half_open_try = False
            return

        self._cb_failures += 1

        if self._cb_failures >= self._cb_threshold:

            self._cb_state = "open"
            self._cb_open_time = time.time()
            self._cb_failures = 0
            self._cb_half_open_try = False

    def parse_stream ( self, chunk: bytes ):

        try: text = chunk.decode(errors="ignore")
        except: return

        buf = getattr(self, "_sse_buffer", None)
        if not buf: buf = self._sse_buffer = {"data": [], "event": None, "id": None, "retry": None, "_partial": ""}

        if buf["_partial"]:
            text = buf["_partial"] + text
            buf["_partial"] = ""

        lines = text.splitlines(keepends=False)

        if not text.endswith("\n") and not text.endswith("\r"):
            if lines: buf["_partial"] = lines.pop()

        for line in lines:

            if not line.strip():

                if buf["data"]:
                    yield {"event": buf["event"] or "message", "data": "\n".join(buf["data"]), "id": buf["id"], "retry": buf["retry"]}

                buf["data"].clear()
                buf["event"] = None
                buf["id"]    = None
                buf["retry"] = None

                continue

            if line.startswith(":"): continue

            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.lstrip()

            else: k, v = line.strip(), ""

            if k == "data": buf["data"].append(v)
            elif k == "event": buf["event"] = v
            elif k == "id": buf["id"] = v
            elif k == "retry":
                try: buf["retry"] = int(v)
                except: pass

    def dispatch ( self, event: str | list, *args, **kwargs ):

        events = event if isinstance(event, list) else [event]

        for ev in events:

            if ev == 'before':     hooks = self._on_before
            elif ev == 'after':    hooks = self._on_after
            elif ev == 'retry':    hooks = self._on_retry
            elif ev == 'success':  hooks = self._on_success
            elif ev == 'error':    hooks = self._on_error
            elif ev == 'stream':   hooks = self._on_stream
            elif ev == 'progress': hooks = self._on_progress
            else: continue

            for fn in hooks:
                if callable(fn):
                    func.thread(fn, *args, **kwargs)

        return self

    async def adispatch ( self, event: str | list, *args, **kwargs ):

        events = event if isinstance(event, list) else [event]

        for ev in events:

            if ev == 'before':     hooks = self._on_before
            elif ev == 'after':    hooks = self._on_after
            elif ev == 'retry':    hooks = self._on_retry
            elif ev == 'success':  hooks = self._on_success
            elif ev == 'error':    hooks = self._on_error
            elif ev == 'stream':   hooks = self._on_stream
            elif ev == 'progress': hooks = self._on_progress
            else: continue

            for fn in hooks:
                if callable(fn):
                    await func.athread(fn, *args, **kwargs)

        return self
