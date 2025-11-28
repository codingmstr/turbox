from .errors import AuthError, TokenExpiredError, PermissionDeniedError, NotFoundError, MissingParameterError, MethodNotAllowedError
from .errors import RateLimitError, GatewayError, ServerError, ValidationError, ParsingError, NetworkError
from .errors import CircuitBreakerError, DependenciesFailedError, DependenciesRuntimeError, UnexpectedError
from bs4 import BeautifulSoup
from typing import Any
import json, os, time, copy, yaml, xml.etree.ElementTree as ET, csv, io, base64

class BaseResponse:

    def __init__ ( self, request, res = None, url: str = None, method: str = None, rt: float = None, tt: float = None, handler: bool = False ):

        self._request = request.clone()
        self._url     = url or getattr(request, '_base_url', '')
        self._method  = method
        self._handle  = handler
        self._rt      = float(rt or 0)
        self._tt      = float(tt or 0)
        self._ok      = False
        self._success = False
        self._soup    = None
        self._raw     = None
        self._code    = None
        self._status  = None
        self._token   = None
        self._text    = None
        self._message = ''
        self._json    = {}
        self._headers = {}
        self._errors  = {}

        if res: self.set_response(res)

    @classmethod
    def __failed__ ( cls, request: object, code: int = 500, message: str = None, json_data: dict = None, tt: float = None, handler: bool = False ):

        obj = cls(request)

        obj._tt       = float(tt or 0)
        obj._handle   = handler
        obj._code     = code
        obj._status   = code
        obj._message  = message or ''
        obj._errors   = (json_data or {}).get("errors", {})
        obj._json     = {"success": False, "message": obj._message, **(json_data or {})}
        obj._text     = json.dumps(obj._json, ensure_ascii=False)

        try: obj.set_context()
        except: pass

        return obj if obj._handle or getattr(obj._request, '_handle_errors', None) else obj.raise_errors()

    def __bool__ ( self ):

        return bool(self._success)

    def __len__ ( self ):

        return len(self.data() or {})

    def __iter__ ( self ):

        data = self.data()

        if isinstance(data, dict): yield from data.items()
        elif isinstance(data, (list, tuple, set)): yield from data
        else: yield data

    def __getitem__ ( self, key: str ):

        data, json = self.data(), self.json()

        if isinstance(data, dict) and key in data: return data[key]
        if isinstance(json, dict) and key in json: return json[key]

        return self.metrics().get(key)

    def __contains__ ( self, key: str ):

        data, json = self.data(), self.json()

        if isinstance(data, dict) and key in data: return True
        if isinstance(json, dict) and key in json: return True

        return key in self.metrics()

    def __str__ ( self ):

        return json.dumps(self.metrics(), ensure_ascii=False, indent=2)

    def __repr__ ( self ):

        return f"<Response [{self.status()}] {self.url()} {self.message()}>"

    def set_response ( self, res ):

        self._raw     = res
        self._ok      = bool(getattr(res, 'ok', False) or False)
        self._code    = int(getattr(res, 'status_code', 0) or 0)
        self._url     = str(getattr(res, 'url', '') or '')
        self._text    = str(getattr(res, 'text', '') or '')
        self._headers = dict(getattr(res, 'headers', {}) or {})

        try: self._json = res.json()
        except ValueError: self._json = json.loads(res.text) if res.text.strip().startswith('{') else {}
        except Exception: self._json = {}

        try: self.set_context()
        except: pass

        return self if self._handle or getattr(self._request, '_handle_errors', None) else self.raise_errors()

    def set_context ( self ):

        if not isinstance(self._json, dict):
            self._success = self._ok
            self._status  = self._code
            return self

        self._success = bool(self._json.get('success', self._ok))
        self._status  = int(self._json.get('status', self._code))
        self._message = self._json.get('message') or self._json.get('msg') or self._json.get('messages')
        self._errors  = self._json.get('errors', {}) or self._json.get('error', {}) or self._json.get('err', {})

        if isinstance(self._message, (list, tuple, dict)):

            self._errors = self._errors or self._message

            if isinstance(self._message, dict):
                self._message = self._message.get('message', self._message.get('msg')) or [f"{k}: {v}" for k, v in self._message.items()][0]
            elif isinstance(self._message, (list, tuple)): self._message = self._message[0]
            else: self._message = str(self._message or '')

        if self._errors and not self._message:

            if isinstance(self._errors, dict):
                self._message = self._errors.get('message', self._errors.get('msg')) or [f"{k}: {v}" for k, v in self._errors.items()][0]
            elif isinstance(self._errors, (list, tuple)): self._message = self._errors[0]
            else: self._message = str(self._errors or '')

        if not self._message: self._message = "Success" if self._success else "Failed"

        if isinstance(self._message, dict) and self._message: self._message = next(iter(self._message.values()), None)
        if isinstance(self._message, (list, tuple)) and self._message: self._message = self._message[0]
        if isinstance(self._message, (list, tuple)) and self._message: self._message = self._message[0]

        return self

    def raise_errors ( self ):

        code = self.code()
        text = self.text().lower()

        msg = self.message()
        msg = msg if msg and msg.strip().lower() not in ("success", "failed") else None

        if 200 <= code < 300: return self
        if code == 599: raise NetworkError(msg, self)
        if code == 598: raise CircuitBreakerError(msg, self)
        if code == 597: raise DependenciesRuntimeError(msg, self)
        if code == 596: raise DependenciesFailedError(msg, self)
        if code == 422: raise ValidationError(msg, self)
        if code == 404: raise NotFoundError(msg, self)
        if code == 405: raise MethodNotAllowedError(msg, self)
        if code in (429, 420): raise RateLimitError(msg, self)
        if code in (502, 503, 504): raise GatewayError(msg, self)
        if 500 <= code < 600: raise ServerError(msg, self)
        if code == 415: raise ParsingError(msg, self)

        if code in (401, 403):

            TOKEN_EXPIRED_KEYWORDS = ("expired", "token", "authorization", "signature", "credential", "jwt")
            if any(kw in text for kw in TOKEN_EXPIRED_KEYWORDS): raise TokenExpiredError(msg, self)

            if code == 403: raise PermissionDeniedError(msg, self)
            raise AuthError(msg, self)

        if code == 400:

            MISSING_PARAM_KEYWORDS = ("missing", "required", "parameter", "field", "empty")
            if any(kw in text for kw in MISSING_PARAM_KEYWORDS): raise MissingParameterError(msg, self)

            raise ValidationError(msg, self)

        if 400 <= code < 500: raise ValidationError(msg or "Client request error", self)
        raise UnexpectedError(msg, self)


    def raw ( self ):

        return self._raw

    def ok ( self ):

        return bool(self._ok)

    def code ( self ):

        return int(self._code or 0)

    def request_time ( self ):

        return float(self._rt or 0)

    def total_time ( self ):

        return float(self._tt or 0)

    def url ( self ):

        return str(self._url or '')

    def method ( self ):

        return str(self._method or '')

    def text ( self ):

        return str(self._text or '').strip()

    def json ( self ):

        return self._json if isinstance(self._json, dict) else {'data': self._json}

    def data ( self ):

        data = self._json

        if isinstance(data, dict):

            data = dict(data)

            if "items" in data and isinstance(data["items"], (list, tuple, dict)): data = data["items"]
            if "results" in data and isinstance(data["results"], (list, tuple, dict)): data = data["results"]
            if "rows" in data and isinstance(data["rows"], (list, tuple, dict)): data = data["rows"]
            if "records" in data and isinstance(data["records"], (list, tuple, dict)): data = data["records"]
            if "payload" in data and isinstance(data["payload"], (list, tuple, dict)): data = data["payload"]
            if "data" in data and isinstance(data["data"], (list, tuple, dict)): data = data["data"]

            for k in ('errors', 'error', 'status', 'message', 'msg', 'success'):
                data.pop(k, None)

        return list(data) if isinstance(data, (list, tuple, set)) else (data or {})

    def list ( self ):

        if isinstance(self.data(), dict): return list(self.data().values())
        if isinstance(self.data(), (list, tuple, set)): return list(self.data())

        return [self.data()]

    def success ( self ):

        return bool(self._success)

    def status ( self ):

        return self._status

    def message ( self ):

        return str(self._message or '')

    def errors ( self ):

        if isinstance(self._errors, (list, tuple, set, dict)): return self._errors
        return [self._errors]

    def headers ( self, lower: bool = False ):

        h = {**(getattr(self._request, '_headers', {})), **(self._headers or {})}
        return {str(k).lower(): v for k, v in h.items()} if lower else h

    def header ( self, name: str, default: Any = None ):

        h = self.headers(True)
        return str(h.get(name.lower(), default) or h.get(name.lower().replace('_', '-'), default) or '')

    def content_type ( self ):

        return str(self.headers(True).get("content-type") or '').lower()

    def origin ( self ):

        return str(self.headers(True).get('access-control-allow-origin') or '')

    def cache_control ( self ):

        return str(self.headers(True).get('cache-control') or '')

    def user_agent ( self, ):

        return str(self.headers(True).get('user-agent') or self.headers(True).get('server') or '')

    def request ( self ):

        return self._request.clone()

    def unauthorized ( self ):

        return self.code() in (401, 498, 419, 440) or any(kw in self.text() for kw in ("expired", "token", "authorization"))

    def auth_token ( self, key: str = None, default: str = None ):

        if not isinstance(self._json, dict): return ''
        keys = tuple(filter(None, [key, 'token', 'auth_token', 'access_token', 'oauth_token', 'bearer_token']))

        self._token = str(self.expect(*keys, json_data=self.json()) or '').strip()
        if self._token: return self._token

        self._token = str(self.expect(*keys, json_data=self.data()) or '').strip()
        if self._token: return self._token

        self._token = str(self.expect(*keys, json_data=self.meta()) or '').strip()
        if self._token: return self._token

        auth = str(self.headers(True).get('authorization') or '').strip().split()
        self._token = str(auth[1] if len(auth) > 1 else (auth[0] if auth else '') or '').strip()

        return str(self._token or default or '').strip()


    def is_html ( self ):

        ctype = self.content_type()
        return "html" in ctype or self.text().strip().startswith("<!DOCTYPE html") or "<html" in self.text().lower()

    def html ( self, selector: str = None, attr: str = None ):

        if not self.is_html(): return None

        s = self.soup()
        if not s: return None

        if selector:
            if attr: return [el.get(attr) for el in s.select(selector) if el.get(attr)]
            return [el.get_text(strip=True) for el in s.select(selector)]

        return s.prettify()

    def xml ( self ):

        try: return ET.fromstring(self.text())
        except Exception: return None

    def yaml ( self ):

        try: return yaml.safe_load(self.text())
        except Exception: return None

    def csv ( self ):

        try: return list(csv.reader(io.StringIO(self.text())))
        except Exception: return None

    def base64 ( self ):

        try: return base64.b64decode(self.text(), validate=True)
        except Exception: return None

    def soup ( self ):

        if not self._soup and self.is_html(): self._soup = BeautifulSoup(self.text(), "html.parser")
        return self._soup

    def select ( self, selector: str ):

        s = self.soup()
        if not s: return []

        return [el.get_text(strip=True) for el in s.select(selector)]

    def find ( self, tag: str, **attrs ):

        s = self.soup()
        return s.find(tag, attrs=attrs) if s else None

    def links ( self ):

        s = self.soup()
        if not s: return []

        return [a['href'] for a in s.find_all('a', href=True)]

    def images ( self ):

        s = self.soup()
        if not s: return []

        return [img['src'] for img in s.find_all('img', src=True)]

    def scripts ( self ):

        s = self.soup()
        if not s: return []

        return [scr.get('src') or scr.get_text(strip=True) for scr in s.find_all('script')]

    def type ( self ):

        ctype = self.content_type()

        if "json" in ctype: return "json"
        if "html" in ctype: return "html"
        if "xml" in ctype: return "xml"
        if "text" in ctype: return "text"
        if "image" in ctype: return "image"
        if "pdf" in ctype: return "pdf"
        if "csv" in ctype: return "csv"
        if "yaml" in ctype or "yml" in ctype: return "yaml"
        if "zip" in ctype: return "archive"

        return "binary"

    def content ( self ):

        s = self.soup()
        return s.get_text(" ", strip=True) if s else self.text()

    def bytes ( self ):

        return getattr(self._raw, "content", b"") or b""

    def extract ( self, selector: str = None, attr: str = None ):

        s = self.soup()
        if not s: return []

        if attr: return [el.get(attr) for el in s.select(selector) if el.get(attr)]
        return [el.get_text(strip=True) for el in s.select(selector)]

    def preview ( self, limit: int = 300 ):

        text = self.text().strip().replace("\n", " ")
        return (text[:limit] + "...") if len(text) > limit else text

    def auto ( self ):

        t, txt, bcontent = self.type(), self.text(), self.bytes()

        if t == "json": return self.json()
        if isinstance(self._json, (list, tuple)): return self._json

        if txt.startswith("{") or txt.startswith("["):
            try: return json.loads(txt)
            except Exception: pass

        if t == "html": return self.soup() or txt
        if t == "xml": return self.xml()
        if t == "text": return txt
        if t == "pdf": return bcontent
        if t == "image": return bcontent

        y = self.yaml()
        if y is not None: return y

        c = self.csv()
        if c is not None: return c

        b = self.base64()
        if b is not None: return b

        if txt: return txt
        return bcontent

    def resolve_path_ext ( self, path: str ):

        ctype = self.content_type()

        if "json" in ctype: ext = ".json"
        elif "html" in ctype: ext = ".html"
        elif "xml" in ctype: ext = ".xml"
        elif "pdf" in ctype: ext = ".pdf"
        elif "text" in ctype: ext = ".txt"
        elif any(x in ctype for x in ("png", "jpeg", "jpg", "gif", "webp", "bmp")): ext = "." + ctype.split("/")[-1]
        elif any(x in ctype for x in ("mp4", "webm", "mov", "avi", "mkv", "flv")): ext = "." + ctype.split("/")[-1]
        elif any(x in ctype for x in ("mp3", "wav", "ogg", "aac", "m4a", "flac")): ext = "." + ctype.split("/")[-1]
        elif any(x in ctype for x in ("zip", "rar", "tar", "gz", "7z")): ext = "." + ctype.split("/")[-1]
        else: ext = ".bin"

        cd = str(self.headers(True).get('content-disposition') or '')
        filename = None

        if "filename*" in cd: filename = cd.split("filename*=")[-1].strip().split(";")[0].split("''")[-1]
        elif "filename=" in cd: filename = cd.split("filename=")[-1].strip().strip('"').split(";")[0]

        if filename and not path: path = f"downloads/{filename}"

        if not path: path = f"downloads/{int(time.time())}{ext}"
        elif not os.path.splitext(path)[1]: path += ext

        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path, ext


    def clone ( self ):

        instance = object.__new__(self.__class__)
        instance.__dict__.update(copy.deepcopy(self.__dict__))

        return instance

    def meta ( self ):

        meta = {
            "status"    : self.code(),
            "ok"        : self.ok(),
            "type"      : self.type(),
            "url"       : self.url(),
            "size"      : len(self.text().encode('utf-8')),
            "timestamp" : time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            **(dict(self.json().get('meta', {})))
        }

        if isinstance(self._json, dict):

            keywords = (
                'page', 'limit', 'total', 'search', 'sort', 'filters', 'ids', 'count', 'offset',
                'next', 'prev', 'next_page', 'prev_page', 'next_cursor', 'prev_cursor',
                'links', 'pagination', 'pageInfo', 'paging', 'cursor',
            )

            for key in keywords:
                if key in self._json:
                    meta[key] = self._json[key]
                    if isinstance(meta[key], dict): meta.update(meta[key])

        return meta

    def metrics ( self ):

        return {
            "url"          : self.url(),
            "method"       : self.method(),
            "code"         : self.code(),
            "status"       : self.status(),
            "success"      : self.success(),
            "message"      : self.message(),
            "errors"       : self.errors(),
            "auth_token"   : self.auth_token(),
            "user_agent"   : self.user_agent(),
            "content_type" : self.content_type(),
            "type"         : self.type(),
            "request_time" : round(self.request_time(), 4),
            "total_time"   : round(self.total_time(), 4),
            "headers"      : self.headers(),
            "meta"         : self.meta(),
        }

    def summary ( self ):

        return f"{self.method()} {self.url()} [{self.code()}] ({self.request_time():.3f}s / {self.total_time():.3f}s)"

    def expect ( self, *keys: str, default = None, json_data: dict = None, find_key: bool = False ):

        resolved_key = None

        def deep_find ( obj ):

            nonlocal resolved_key

            if isinstance(obj, dict):

                for k, v in obj.items():

                    if str(k).lower() in keys:
                        resolved_key = str(k).lower()
                        return v

                    found = deep_find(v)
                    if found is not None: return found

            elif isinstance(obj, (list, tuple)):

                for item in obj:

                    found = deep_find(item)
                    if found is not None: return found

            return None

        result = deep_find(json_data or self._json)
        result = result if result is not None else default

        return resolved_key if find_key else result


    def find_meta_item ( self, key: str, find_key: bool = False ):

        keys = {
            'page'   : ("page", "current_page", "pageIndex", "page_index"),
            'limit'  : ("limit", "per_page", "size", "pageSize", "first", "last", "count"),
            'offset' : ("offset", "skip"),
            'total'  : ("total", "total_count", "totalCount"),
            'next'   : ("next", "next_page", "nextPage", "hasNextPage", "hasNext"),
            'prev'   : ("prev", "prev_page", "prevPage", "hasPreviousPage", "hasPrev"),
            'cursor_next' : ("next_cursor", "endCursor", "end_cursor"),
            'cursor_prev' : ("prev_cursor", "startCursor", "start_cursor"),
        }

        return self.expect(*(keys.get(key) or ()), json_data=self.meta(), find_key=find_key)

    def is_paginated ( self ):

        return any([
            self.find_meta_item("page"),
            self.find_meta_item("limit"),
            self.find_meta_item("total"),
            self.find_meta_item("next"),
            self.find_meta_item("prev"),
            self.find_meta_item("cursor_next"),
            self.find_meta_item("cursor_prev"),
        ])

    def has_next ( self ):

        if self.find_meta_item("next") or self.find_meta_item("cursor_next"): return True

        page, limit, total = self.find_meta_item("page"), self.find_meta_item("limit"), self.find_meta_item("total")
        if all((page, limit, total)): return (page * limit) < total

        return False

    def has_prev ( self ):

        if self.find_meta_item("prev") or self.find_meta_item("cursor_prev"): return True

        page = self.find_meta_item("page")
        if page and page > 1: return True

        return False

    def current_page_url ( self ):
        
        return self.url()

    def next_page_url ( self ):

        nxt = self.find_meta_item("next")
        if nxt: return str(nxt)

        page  = self.find_meta_item("page")
        limit = self.find_meta_item("limit")
        total = self.find_meta_item("total")

        if all((page, limit, total)) and (page * limit) < total:
            base = self.url().split("?")[0]
            return f"{base}?page={page+1}&limit={limit}"

        return ''

    def prev_page_url ( self ):

        prv = self.find_meta_item("prev")
        if prv: return str(prv)

        page  = self.find_meta_item("page")
        limit = self.find_meta_item("limit")

        if page and page > 1:
            base = self.url().split("?")[0]
            return f"{base}?page={page-1}&limit={limit or ''}"

        return ''

    def next_cursor ( self ):

        return self.find_meta_item("cursor_next")

    def prev_cursor ( self ):

        return self.find_meta_item("cursor_prev")

    def total_pages ( self ):

        page  = self.find_meta_item("page")
        limit = self.find_meta_item("limit")
        total = self.find_meta_item("total")

        if all((page, limit, total)): return max(1, (total + limit - 1) // limit)
        return 0

    def pagination_info ( self ):

        page        = self.find_meta_item("page")
        limit       = self.find_meta_item("limit")
        total       = self.find_meta_item("total")
        cursor_next = self.find_meta_item("cursor_next")
        cursor_prev = self.find_meta_item("cursor_prev")

        return {
            "page"         : page,
            "limit"        : limit,
            "total"        : total,
            "offset"       : self.meta().get("offset"),
            "next"         : self.next_page_url(),
            "prev"         : self.prev_page_url(),
            "next_cursor"  : cursor_next,
            "prev_cursor"  : cursor_prev,
            "has_next"     : self.has_next(),
            "has_prev"     : self.has_prev(),
            "is_paginated" : self.is_paginated(),
            "is_cursor"    : bool(cursor_next or cursor_prev),
            "is_page"      : bool(page and limit),
            "is_graphql"   : bool("pageInfo" in self.meta()),
        }
