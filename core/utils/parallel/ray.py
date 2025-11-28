from typing import Iterable, Callable, Any
import ray, asyncio, inspect, math, os, copy, threading

@ray.remote
class Worker:

    def __init__ ( self, handler, context = None, retries = None, stream_ref = None, error_ref = None, progress_ref = None ):

        self.handler      = handler
        self.context      = context
        self.stream_ref   = stream_ref
        self.error_ref    = error_ref
        self.progress_ref = progress_ref
        self.retries      = max(int(retries or 0), 0)
        self.attempts      = 0

    async def execute ( self, item: Any ):

        try:

            handler = self.handler

            if inspect.iscoroutinefunction(handler): return await handler(item, **self.context)
            if inspect.iscoroutine(handler): return await handler

            if callable(handler): result = handler(item, **self.context)
            else: result = handler

            if inspect.iscoroutine(result): return await result
            if inspect.iscoroutinefunction(result): return await result()
            if callable(result): return result()

            return result

        except Exception as e:
            
            if self.attempts < self.retries:
                self.attempts += 1
                return await self.execute(item)

            if self.error_ref: self.error_ref.call.remote(e)

        return None

    async def run ( self, items: list, offset: int = 0, total: int = 0 ):

        results = []
        total = total or len(items)

        for i, item in enumerate(items):
      
            self.attempts = 0
            index = offset + i
      
            result = await self.execute(item)
            results.append(result)

            if self.stream_ref: await self.stream_ref.push.remote(index, result)

            if self.progress_ref:
                info = {"done": index + 1, "total": total, "percent": round((index + 1) / total * 100, 2)}
                self.progress_ref.call.remote(info)

        return results

@ray.remote
class Streamer:

    def __init__ ( self, callback: Callable ):

        self.callback = callback
        self.queue = {}
        self.next  = 0

    def in_queue ( self, index, value ):

        if len(self.queue) > 100000:
            self.queue.clear()
            self.next = 0

        self.queue[index] = value

    def call ( self, value: Any ):

        def runner ():
            
            try:
                result = self.callback(value)
                if inspect.iscoroutine(result): asyncio.run(result)
            except: pass

        threading.Thread(target=runner, daemon=True).start()

    async def push ( self, index: int, value: Any ):

        self.in_queue(index, value)

        while self.next in self.queue:
            
            data = self.queue.pop(self.next)

            if inspect.iscoroutinefunction(self.callback): await self.callback(data)
            else: self.callback(data)

            self.next += 1

class Ray:

    def __init__ ( self ):

        self._items        = []
        self._context      = []
        self._handler      = None
        self._cpu_count    = 0
        self._chunk_size   = 0
        self._tasks        = []
        self._results      = []
        self._started      = False
        self._retries      = None
        self._timeout      = None
        self._stream_ref   = None
        self._error_ref    = None
        self._progress_ref = None

    def __enter__ ( self ):

        if not self._started: self.start()
        return self

    def __exit__ ( self, *args ):

        self.shutdown()

    def _cleanup_ ( self ):
        
        for ref in [self._stream_ref, self._error_ref, self._progress_ref]:
            try: ray.kill(ref, no_restart=True) if ref else None
            except: pass

        self._stream_ref = self._error_ref = self._progress_ref = None
        return self

    def status ( self ):

        if not ray.is_initialized(): return { "status": "stopped" }

        info = ray.cluster_resources()
        return { "status": "running", "cpus": info.get("CPU", 0), "gpus": info.get("GPU", 0), "nodes": len(ray.nodes()) }

    def shutdown ( self ):

        if self._tasks:
            
            for task in self._tasks:
                try: ray.cancel(task, force=True)
                except Exception: pass
            
            try: ray.wait(self._tasks, num_returns=len(self._tasks), timeout=1.0)
            except Exception: pass

        if ray.is_initialized(): ray.shutdown()

        self._started = False
        return self._cleanup_()

    def work ( self ):

        for i in range(self._cpu_count):

            total = len(self._items)

            start = i * self._chunk_size
            end = min(start + self._chunk_size, total)

            if start >= end: break

            worker_actor = Worker.remote(self._handler, self._context, self._retries, self._stream_ref, self._error_ref, self._progress_ref)
            self._tasks.append(worker_actor.run.remote(self._items[start:end], start, total))

        return self

    def wait ( self ):

        try:
            batches = ray.get(self._tasks, timeout=self._timeout or None)
            self._results = [x for batch in batches for x in batch]
        except: pass
        return self
        
        try:
          
            asyncio.get_running_loop()

            async def _wait_async():
                done, _ = await asyncio.wait(self._tasks)
                results = await asyncio.gather(*done)
                self._results = [x for batch in results for x in batch]

            asyncio.create_task(_wait_async())
     
        except RuntimeError:
            batches = ray.get(self._tasks)
            self._results = [x for batch in batches for x in batch]

        return self

    def collect ( self ):

        if not self._results: self.wait()
        return self._results

    async def gather_handler ( self, function, **kwargs ):
        
        if not callable(function): return None

        params = inspect.signature(function).parameters
        kwargs = {k: v for k, v in kwargs.items() if k in params}

        if inspect.iscoroutinefunction(function): return await function(**kwargs)
        if inspect.iscoroutine(function): return await function

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: function(**kwargs))

    def gather ( self, *functions, **kwargs ):

        return self.run(functions, self.gather_handler, **kwargs)

    def start (
        self, ray_address: str = None, num_cpus: int = None, dashboard_port: int = None,
        reset: bool = False, env: dict = None ):

        os.environ.update(env or {})
        os.environ.setdefault("RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO", "0")
     
        address = ray_address or os.environ.get("RAY_ADDRESS") or None

        if ray.is_initialized():

            if not reset:
                self._started = True
                return self

            ray.shutdown()

        try:
            
            ray.init(
                address=address if address not in ("", None) else None,
                ignore_reinit_error=True,
                num_cpus=num_cpus or os.cpu_count(),
                dashboard_port=dashboard_port or 8265,
            )

        except ValueError:
            ray.init(address="auto", ignore_reinit_error=True)

        self._started = True
        return self

    def run (
        self, items: Iterable, handler: Callable, context: dict = None,
        max_workers: int = None, retries: int = None, collect: bool = False, timeout: float = None,
        on_stream: Callable = None, on_error: Callable = None, on_progress: Callable = None ):

        if not self._started: self.start()

        self._items        = list(items)
        self._context      = copy.deepcopy(context or {})
        self._handler      = handler
        self._retries      = retries
        self._timeout      = timeout
      
        self._stream_ref   = Streamer.remote(on_stream) if on_stream else None
        self._error_ref    = Streamer.remote(on_error) if on_error else None
        self._progress_ref = Streamer.remote(on_progress) if on_progress else None

        cpu_available      = ray.cluster_resources().get("CPU", os.cpu_count())
        self._cpu_count    = max(1, min(max_workers or int(cpu_available), len(self._items)))
        self._chunk_size   = max(1, math.ceil(len(self._items) / self._cpu_count))

        self.work()

        if collect: return self.collect()
        return self
