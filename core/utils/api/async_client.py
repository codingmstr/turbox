from threading import Lock
from .request import Request
from .response import Response
from ..micro import func
import json, time

class Model:

    def __init__ ( self, raw: dict ):

        self._raw = raw

    def __getattr__ ( self, name: str ):

        val = self._raw.get(name)

        if isinstance(val, dict): return Model(val)
        if isinstance(val, list): return [Model(x) if isinstance(x, dict) else x for x in val]

        return val

    def __repr__ ( self ):

        return f"<Model {self._raw}>"

    def dict ( self ):
        
        return self._raw

class Resource:

    ACTIONS = {
        "list"     : "GET",
        "get"      : "GET",
        "find"     : "GET",
        "create"   : "POST",
        "add"      : "POST",
        "update"   : "PUT",
        "patch"    : "PATCH",
        "delete"   : "DELETE",
        "destroy"  : "DELETE",
        "remove"   : "DELETE",
        "download" : "GET",
        "upload"   : "POST",
    }

    def __init__ ( self, client, parts: list ):

        self.client = client
        self.parts  = parts

    def __getattr__ ( self, name: str ):

        if name in self.ACTIONS: return lambda **kw: self._send(self.ACTIONS[name], kw)
        return Resource(self.client, self.parts + [name])

    def __call__ ( self, name: str ):

        return Resource(self.client, self.parts + [name])

    def _path ( self ):

        return "/".join(self.parts)

    def _send ( self, method: str, params: dict ):

        res = self.client._call(method, self._path(), **params)

        if isinstance(res, list):
            return [Model(x) if isinstance(x, dict) else x for x in res]

        if isinstance(res, Response):

            data = res.data()

            if isinstance(data, list): return [Model(x) if isinstance(x, dict) else x for x in data]
            if isinstance(data, dict): return Model(data)

            return data

        return res

class AsyncClient:

    def __init__ ( self, base_url: str ):

        self.base_url = base_url.rstrip("/")
        self.req = Request(self.base_url)

        self._cache, self._expire = {}, {}
        self._lock = Lock()
        self._cache_ttl = None

        self._auto_paginate = True
        self._fallback_url = None
        self._metrics = None

    def __enter__ ( self ):

        return self

    def __exit__ ( self, *_ ):

        self.req.__exit__()

    def __getattr__ ( self, name: str ):

        return Resource(self, [name])

    def __call__ ( self, name: str ):

        return Resource(self, [name])

    def set ( self, **options ):

        for k, v in options.items():
            if hasattr(self.req, f"set_{k}"): getattr(self.req, f"set_{k}")(v)
            else: setattr(self.req, f"_{k}", v)

        return self

    def fallback ( self, url: str ):

        self._fallback_url = url.rstrip("/")
        return self

    def cache ( self, ttl: float = None ):

        self._cache_ttl = ttl
        return self

    def paginate ( self, enable = True ):

        self._auto_paginate = enable
        return self

    def metrics ( self, collector ):

        self._metrics = collector
        return self

    def _key ( self, method, endpoint, params ):

        return f"{method}:{endpoint}:{json.dumps(params, sort_keys=True)}"

    def _cache_get ( self, key: str ):

        with self._lock:

            if key in self._cache:

                exp = self._expire.get(key)
                if not exp or time.time() < exp: return self._cache[key]

        return None

    def _cache_set ( self, key: str, value ):

        with self._lock:

            self._cache[key] = value
            self._expire[key] = time.time() + self._cache_ttl if self._cache_ttl else None

        self._cache_ttl = None

    def _record_metrics ( self, method: str, endpoint: str, res: Response ):

        if self._metrics:
            func.thread(self._metrics.record, method, endpoint, res.status(), res.elapsed())

    def _call ( self, method: str, endpoint: str = None, **params ):

        key = self._key(method, endpoint, params)

        cached = self._cache_get(key)
        if cached: return cached

        req = self.req.clone(True)
        res = req.set_params(params).set_data(params).call(method, endpoint)

        if not res.ok() and self._fallback_url:
            alt = self.req.clone(True).set_base_url(self._fallback_url)
            res = alt.set_params(params).set_data(params).call(method, endpoint)

        if self._auto_paginate and hasattr(res, "walk_paginate"):
            res = list(res.walk_paginate())

        if self._cache_ttl: self._cache_set(key, res)

        self._record_metrics(method, endpoint, res)
        return res

    def graph ( self, query: str = None, variables: dict = None, endpoint: str = None ):

        endpoint = endpoint or getattr(self.req, "_gql_endpoint", "graphql")
        res = self._call("POST", endpoint, query=query, variables=variables or {})

        return res.json()

    def upload ( self, *files, endpoint: str = None, data: dict = None ):

        return self.req.upload(*files, endpoint=endpoint, data=data)

    def download ( self, endpoint: str, path: str, resume: bool = True ):

        return self.req.download(endpoint, path, resume=resume)

    def get ( self, endpoint: str, **params ):

        return self._call("GET", endpoint, **params)

    def post ( self, endpoint: str, **params ):

        return self._call("POST", endpoint, **params)

    def put ( self, endpoint: str, **params ):

        return self._call("PUT", endpoint, **params)

    def patch ( self, endpoint: str, **params ):

        return self._call("PATCH", endpoint, **params)

    def delete ( self, endpoint: str, **params ):

        return self._call("DELETE", endpoint, **params)

    def head ( self, endpoint: str, **params ):

        return self._call("HEAD", endpoint, **params)

    def options ( self, endpoint: str, **params ):

        return self._call("OPTIONS", endpoint, **params)
