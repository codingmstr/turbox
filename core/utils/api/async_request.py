import time, os, json, asyncio
from curl_cffi import requests, CurlMime
from .base_request import BaseRequest
from .async_response import AsyncResponse
from ..micro import func

class AsyncRequest(BaseRequest):

    def session ( self ):

        if self._session: return self._session
        self._session = requests.AsyncSession(impersonate=self._impersonate)

        if self._proxy: self._session.proxies = {"http": self._proxy, "https": self._proxy}
        return self._session

    async def run_dependencies ( self, *args, endpoint: str = None, started_at: float = 0 ):

        if not self.check_limiter(endpoint, args[0]):
            await self.adispatch('error', {'message': 'To Many Requests', 'code': 429})
            return AsyncResponse.__failed__(self, 429, None, None, time.perf_counter() - started_at)

        for fn in self._deps:

            if not callable(fn): continue

            try:

                result = await func.arun(fn, *args)

                if not result:
                    await self.adispatch('error', {'message': f"Dependency {fn.__name__} failed", 'code': 596})
                    return AsyncResponse.__failed__(self, 596, f"Dependency {fn.__name__} failed", None, time.perf_counter() - started_at)

            except Exception as e:
                await self.adispatch('error', {'message': f"Runtime Error in Dependency {fn.__name__}", 'code': 597, 'error': e})
                return AsyncResponse.__failed__(self, 597, f"Runtime Error in Dependency {fn.__name__}", None, time.perf_counter() - started_at)

        return True

    async def execute ( self, method: str = None, endpoint: str = None, data: dict = None, graph: bool = False, *paths ):

        method, url = self.resolve_method_url('post' if (paths or self._files) and not method else method, endpoint)
        await self.adispatch('before', self.clone())

        for attempt in range(self._max_retries + 1):

            mp = None
            requested = False
            started_at = time.perf_counter()

            if not self.circuit_allowed():
                await self.adispatch('error', {'error': {'message': 'The circuit breaker limit has been exceeded', 'code': 598}})
                return AsyncResponse.__failed__(self, 598, None, None, time.perf_counter() - started_at)

            if attempt: await self.adispatch('retry', self.clone())

            try:

                dep = await self.run_dependencies(self, method, url, endpoint=endpoint, started_at=started_at)
                if isinstance(dep, AsyncResponse): return dep

                headers     = dict(self._headers)
                json_data   = {**(self._data or {}), **(data or {})}
                json_params = {**(self._params or {}), **(data or {})}

                if graph:
                    headers.setdefault("Content-Type", "application/json")
                    json_data = {'query': self._query, 'variables': data or self._variables or {}}

                if (paths or self._files) and method not in ('GET', 'DELETE') and not graph:

                    parts = [*(self._files or []), *self.resolve_files(*paths)]

                    for k, v in json_data.items():
                        parts.append({"name": k, "data": json.dumps(v) if isinstance(v, (dict, list, tuple, set)) else str(v)})

                    mp = CurlMime.from_list(parts)

                req_at = time.perf_counter()

                res = await self.session().request(
                    method,
                    url,
                    multipart=mp,
                    headers=headers,
                    params=json_params if not mp and method in ('GET', 'DELETE') else None,
                    json=json_data if not mp and method not in ('GET', 'DELETE') else None,
                    cookies=self._cookies,
                    timeout=self._timeout,
                    verify=self._verify,
                    stream=self._stream
                )

                elapsed = time.perf_counter() - req_at
                self.circuit_update(res.ok)

                text = res.text[:200].lower() if res.text else ""
                unauth = res.status_code in (401, 498, 419, 440) or any(kw in text for kw in ("expired", "token", "authorization"))

                if (res.status_code in self._retry_codes or (self._oauth2 and unauth)) and attempt < self._max_retries:
                    await asyncio.sleep(self.resolve_delay(attempt, res))
                    continue

                ended_at = time.perf_counter() - started_at
                requested = True

                await self.adispatch(['after', 'success'], AsyncResponse(self, res, url, method, elapsed, ended_at, True))
                return AsyncResponse(self, res, url, method, elapsed, ended_at)

            except Exception as e:

                await self.adispatch('error', {'message': 'Network error', 'code': 599, 'error': e})
                self.circuit_update(False)

                if attempt < self._max_retries:
                    await asyncio.sleep(self.resolve_delay(attempt))
                    continue

                elif requested: raise

                ended_at = time.perf_counter() - started_at

                await self.adispatch('after', AsyncResponse.__failed__(self, 599, None, None, ended_at, True))
                return AsyncResponse.__failed__(self, 599, None, None, ended_at)

            finally:
                try:
                    if mp: await asyncio.to_thread(mp.close)
                except: pass

    async def download ( self, endpoint: str = None, path: str = None, method: str = None, stream: bool = True, resume: bool = True ):

        method, url = self.resolve_method_url(method, endpoint)
        await self.adispatch('before', self.clone())

        for attempt in range(self._max_retries + 1):

            requested = False
            started_at = time.perf_counter()

            if not self.circuit_allowed():
                await self.adispatch('error', {'error': {'message': 'The circuit breaker limit has been exceeded', 'code': 598}})
                return AsyncResponse.__failed__(self, 598, None, None, time.perf_counter() - started_at)

            if attempt: await self.adispatch('retry', self.clone())

            try:

                dep = await self.run_dependencies(self, method, url, endpoint=endpoint, started_at=started_at)
                if isinstance(dep, AsyncResponse): return dep

                headers = dict(self._headers)
                start   = 0

                if stream:

                    headers.setdefault("Accept-Encoding", "identity")
                    headers.setdefault("Cache-Control", "no-transform")

                    if resume and path and os.path.exists(path):
                        start = os.path.getsize(path)
                        if start > 0: headers["Range"] = f"bytes={start}-"

                req_at = time.perf_counter()

                res = await self.session().request(
                    method,
                    url,
                    headers=headers,
                    json=self._data if method not in ('GET','DELETE') else None,
                    params=self._params,
                    cookies=self._cookies,
                    timeout=self._timeout,
                    verify=self._verify,
                    stream=stream
                )

                if stream:

                    if start > 0 and (res.status_code != 206 or "Content-Range" not in res.headers):

                        req_at = time.perf_counter()
                        headers.pop("Range", None)
                        start = 0

                        res = await self.session().request(
                            method,
                            url,
                            headers=headers,
                            json=self._data if method not in ('GET','DELETE') else None,
                            params=self._params,
                            cookies=self._cookies,
                            timeout=self._timeout,
                            verify=self._verify,
                            stream=stream
                        )

                    if res.status_code == 416:

                        elapsed = time.perf_counter() - req_at
                        self.circuit_update(True)

                        ended_at = time.perf_counter() - started_at
                        await self.adispatch('after', AsyncResponse(self, res, url, method, elapsed, ended_at, True))
                        return AsyncResponse(self, res, url, method, elapsed, ended_at)

                elapsed = time.perf_counter() - req_at
                self.circuit_update(res.ok)

                text = (getattr(res, "text", "") or "")[:200].lower()
                unauth = res.status_code in (401, 498, 419, 440) or any(kw in text for kw in ("expired", "token", "authorization"))

                if (res.status_code in self._retry_codes or (self._oauth2 and unauth)) and attempt < self._max_retries:
                    await asyncio.sleep(self.resolve_delay(attempt, res))
                    continue

                ended_at = time.perf_counter() - started_at
                requested = True

                await self.adispatch('after', AsyncResponse(self, res, url, method, elapsed, ended_at, True))
                res = AsyncResponse(self, res, url, method, elapsed, ended_at)

                await res.save(path, stream=stream, on_progress=self._on_progress, start=start)
                res._tt = time.perf_counter() - started_at

                await self.adispatch('success', res)
                return res

            except Exception as e:

                await self.adispatch('error', {'message': 'Network error', 'code': 599, 'error': e})
                self.circuit_update(False)

                if attempt < self._max_retries:
                    await asyncio.sleep(self.resolve_delay(attempt))
                    continue

                elif requested: raise

                ended_at = time.perf_counter() - started_at

                await self.adispatch('after', AsyncResponse.__failed__(self, 599, None, None, ended_at, True))
                return AsyncResponse.__failed__(self, 599, None, None, ended_at)

    async def upload ( self, *paths: str, endpoint: str = None, method: str = None, data: dict = None ):

        return await self.execute(method, endpoint, data, False, *paths)

    async def oauth2 ( self, client_id: str, client_secret: str, endpoint: str = 'oauth2/token', scope: str = '', grant: str = 'client_credentials', token_key: str = None, refresh_in: int = None ):

        self.set_basic_token(client_id, client_secret).set_data(grant_type=grant, scope=scope)
        res = await self.execute('post', endpoint)

        if not res.ok():

            self.clear_headers().set_data(client_id=client_id, client_secret=client_secret, grant_type=grant, scope=scope)
            res = await self.execute('post', endpoint)

        self.set_token(res.auth_token(token_key), prefix=res.json().get('token_type') or 'Bearer')
        refresh_in = refresh_in or int(res.json().get("expires_in", 0))

        if refresh_in:

            self._oauth2 = {
                "endpoint": endpoint,
                "client_id": client_id,
                "client_secret":client_secret,
                "scope": scope,
                "grant": grant,
                "token_key": token_key,
                "refresh_in": refresh_in,
                "expiry": time.time() + refresh_in,
            }

        else: self._oauth2 = {}

        return self

    async def refresh_oauth2 ( self ):

        c = self._oauth2
        if not c or not c.get("expiry") or time.time() < c["expiry"]: return self
        return self.oauth2(c["client_id"], c["client_secret"], c["endpoint"], c["scope"], c["grant"], c["token_key"], c["refresh_in"])

    async def call ( self, method: str = None, endpoint: str = None ):

        await self.refresh_oauth2()
        return await self.execute(method, endpoint)

    async def get ( self, endpoint: str = None ):

        return await self.call('get', endpoint)

    async def post ( self, endpoint: str = None ):

        return await self.call('post', endpoint)

    async def put ( self, endpoint: str = None ):

        return await self.call('put', endpoint)

    async def patch ( self, endpoint: str = None ):

        return await self.call('patch', endpoint)

    async def delete ( self, endpoint: str = None ):

        return await self.call('delete', endpoint)

    async def options ( self, endpoint: str = None ):

        return await self.call('options', endpoint)

    async def head ( self, endpoint: str = None ):

        return await self.call('head', endpoint)

    async def graph ( self, query: str = None, variables: dict = None ):

        prev_query = query
        if query: self.set_query(query)

        try: return await self.execute('post', self._gql_endpoint, variables, True)
        finally: self.set_query(prev_query)

    async def json ( self, endpoint: str = None, method: str = None ):

        res = await self.call(method, endpoint)
        return res.json()

    async def stream ( self, method: str = None, endpoint: str = None, sse: bool = True, chunk_size: int = 65536 ):

        prev_stream = self._stream
        self.set_stream(True)

        try: res = await self.call(method, endpoint)
        finally: self.set_stream(prev_stream)

        async for chunk in res.aiter_content(chunk_size):

            if self._stop_stream:
                self._stop_stream = False
                break

            if not chunk: continue

            if sse:
                for value in self.parse_stream(chunk):
                    await self.adispatch('stream', value)
                    yield value

            else: 
                await self.adispatch('stream', chunk)
                yield chunk

    async def multi ( self, requests_list: list ):

        results = []

        for item in requests_list:

            if not item: continue

            instance, method, endpoint = self.new_instance(item)
            result = await instance.call(method, endpoint)

            await self.adispatch('stream', result)
            results.append(result)

        return results

    async def gather ( self, requests_list: list, max_workers: int = 1024 ):

        sem = asyncio.Semaphore(max_workers)

        async def worker ( item ):

            async with sem:

                instance, method, endpoint = self.new_instance(item)
                result = await instance.call(method, endpoint)

                await self.adispatch('stream', result)
                return result

        tasks = [asyncio.create_task(worker(item)) for item in requests_list]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def dos ( self, count: int = 1, method: str = None, endpoint: str = None, max_workers: int = 1024 ):

        return await self.gather([(method, endpoint) for _ in range(count)], max_workers)
