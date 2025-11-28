from .base_response import BaseResponse
from typing import Callable
from ..micro import func
import json

class Response(BaseResponse):

    def iter_content ( self, chunk_size: int = 65536 ):

        if not self.raw(): return

        try:
            for chunk in self.raw().iter_content(chunk_size=chunk_size):
                yield chunk
        except Exception: return

    def save ( self, path: str = None, stream: bool = False, on_progress: Callable = None, chunk_size: int = 65536, start: int = 0 ):

        path, ext = self.resolve_path_ext(path)

        if stream:

            range  = str(self.headers().get("Content-Range") or '')
            length = str(self.headers().get("Content-Length") or '')

            if range:
                try: full_size = int(range.split("/")[-1])
                except: full_size = None

            elif length.isdigit(): full_size = int(length) + start
            else: full_size = None

            size, downloaded, last_reported = full_size, start, 0

            if not size: chunk_size = 16 * 1024
            elif size > 5 * 1024**3: chunk_size = 1 * 1024**2
            elif size > 500 * 1024**2: chunk_size = 512 * 1024
            elif size > 10 * 1024**2: chunk_size = 256 * 1024
            else: chunk_size = 64 * 1024

            with open(path, "ab" if start > 0 else "wb") as f:

                for chunk in self.iter_content(chunk_size):

                    if not chunk: continue

                    f.write(chunk)
                    downloaded += len(chunk)

                    if callable(on_progress) and (downloaded - last_reported) > (size * 0.01):
                        func.thread(on_progress, downloaded, size, (downloaded / size) * 100 if size and size > 0 else 0)
                        last_reported = downloaded

        else:

            if ext == ".json":
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self._json, f, ensure_ascii=False, indent=4)

            elif ext in (".txt", ".html", ".xml"):
                with open(path, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(self.text())

            else:
                with open(path, "wb") as f:
                    f.write(self.bytes())

        return path

    def paginate ( self, page: int = 1, limit: int = 15 ):

        page  = max(1, int(page))
        limit = max(1, int(limit))

        req      = self._request.clone()
        method   = (self.method() or "GET").upper()
        base_url = self.url().split("?", 1)[0]

        page_key        = self.find_meta_item('page', True)
        limit_key       = self.find_meta_item('limit', True)
        offset_key      = self.find_meta_item('offset', True)
        cursor_next_key = self.find_meta_item('cursor_next', True)
        cursor_prev_key = self.find_meta_item('cursor_prev', True)

        if page_key or offset_key:

            params = dict(req._params or {})
            if limit_key: params[limit_key] = limit
           
            if page_key: params[page_key] = page
            elif offset_key: params[offset_key] = (page - 1) * limit

            return req.set_params(params).set_data(params).call(method, base_url)

        if cursor_next_key or cursor_prev_key:

            res = self.clone()
            current = int(res.find_meta_item("page") or 1)

            if page == current: return res

            max_walk = abs(page - current)
            direction = "next" if page > current else "prev"

            for _ in range(max_walk):

                cursor = res.next_cursor() if direction == "next" else res.prev_cursor()
                if not cursor: break

                params = {**(req._params or {}), "cursor": cursor}
                res = req.clone().set_params(params).set_data(params).call(method, base_url)

            return res

        params = {**(req._params or {}), "page": page, "limit": limit}
        return req.set_params(params).set_data(params).call(method, base_url)

    def next_page ( self, limit: int = None ):

        current = int(self.find_meta_item("page") or self.find_meta_item("offset") or 1)
        limit   = limit or int(self.find_meta_item("limit") or 15)

        if current >= self.total_pages(): return self
        return self.paginate(current + 1, limit)

    def prev_page ( self, limit: int = None ):

        current = int(self.find_meta_item("page") or self.find_meta_item("offset") or 1)
        limit   = limit or int(self.find_meta_item("limit") or 15)

        if current <= 1: return self
        return self.paginate(current - 1, limit)

    def first_page ( self, limit: int = None ):

        limit = limit or int(self.find_meta_item("limit") or 15)
        return self.paginate(1, limit)

    def last_page ( self, limit: int = None ):

        total = self.total_pages()
        limit = limit or int(self.find_meta_item("limit") or 15)

        if total < 1: return self
        return self.paginate(total, limit)

    def walk_paginate ( self, start: int = 1, limit: int = None, direction: str = 'next', max_pages: int = None ):

        direction = 'prev' if 'prev' in str(direction).lower() else 'next'

        limit   = limit or int(self.find_meta_item("limit") or 15)
        current = int(self.find_meta_item("page") or 1)
        visited = 1

        res = self if start == current else self.paginate(start, limit)
        yield res

        while True:

            if max_pages and visited >= max_pages: break

            if direction == "next":
                if not res.has_next(): break
                res = res.next_page(limit)

            elif direction == "prev":
                if not res.has_prev(): break
                res = res.prev_page(limit)

            yield res
            visited += 1
