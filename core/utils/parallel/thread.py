from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Callable, Any
import asyncio, inspect, threading, math, time, copy

# class Thread:

#     def __init__ ( self ):
   
#         self._threads   = []
#         self._results   = []
#         self._lock      = threading.Lock()
#         self._on_start  = None
#         self._on_done   = None
#         self._on_error  = None
#         self._timeout   = None
#         self._retries   = 0
#         self._handler   = None
#         self._context   = {}
#         self._items     = []

#     def _execute_ ( self, item: Any, index: int ):

#         if self._on_start:
#             try: self._on_start(item, index)
#             except Exception: pass

#         for attempt in range(self._retries + 1):
        
#             try:
               
#                 result = self._run_handler(item)
#                 with self._lock: self._results.append(result)
               
#                 if self._on_done:
#                     try: self._on_done(result, index)
#                     except Exception: pass
#                 return
           
#             except Exception as e:
#                 if attempt >= self._retries:
#                     if self._on_error:
#                         try: self._on_error(e, item)
#                         except Exception: pass

#     def _run_handler ( self, item: Any ):
       
#         handler = self._handler

#         if inspect.iscoroutinefunction(handler): return asyncio.run(handler(item, **self._context))
#         if inspect.iscoroutine(handler): return asyncio.run(handler)

#         result = handler(item, **self._context) if callable(handler) else handler

#         if inspect.iscoroutinefunction(result): return asyncio.run(result())
#         if inspect.iscoroutine(result): return asyncio.run(result)
#         if callable(result): return result()

#         return result

#     def start ( self ):

#         if not self._handler or not self._items: return self
#         self._threads = []

#         for i, item in enumerate(self._items):
          
#             t = threading.Thread(target=self._execute_, args=(item, i), daemon=True)
#             t.start()
#             self._threads.append(t)

#         return self

#     def wait ( self ):
        
#         start_time = time.time()
        
#         for t in self._threads:
#             t.join(timeout=self._timeout)
#             if self._timeout and (time.time() - start_time) > self._timeout: break

#         return self

#     def collect ( self ):

#         self.wait()
#         return self._results

#     def run (
#         self, handler: Callable, items: Iterable = None, context: dict = None, retries: int = 0, collect: bool = False,
#         timeout: float = None, on_start: Callable = None, on_done: Callable = None, on_error: Callable = None ):

#         self._handler   = handler
#         self._items     = list(items or [])
#         self._context   = context or {}
#         self._retries   = retries
#         self._timeout   = timeout
#         self._on_start  = on_start
#         self._on_done   = on_done
#         self._on_error  = on_error

#         self.start()
#         if collect: return self.collect()

#         return self

class Streamer:

    def __init__ ( self, callback: Callable ):

        self.callback = callback

    async def dispatch ( self, value: Any ):

        fn = self.callback

        if inspect.iscoroutinefunction(fn): return await fn(value)
        if inspect.iscoroutine(fn): return await fn

        result = fn(value) if callable(fn) else fn

        if inspect.iscoroutine(result): return await result
        if callable(result): return result()

        return result

class Thread:

    def __init__ ( self ):

        self._items        = []
        self._context      = {}
        self._handler      = None
        self._threads      = []
        self._results      = []
        self._errors       = []
        self._chunk_size   = 1
        self._max_workers  = 0
        self._timeout      = None
        self._retries      = 0
        self._stream_ref   = None
        self._error_ref    = None
        self._start_ref    = None
        self._cancel_ref   = None
        self._complete_ref = None
        self._stop_flag    = threading.Event()

    def _dispatch_ ( self, type: str, data: Any ):

        ref = getattr(self, f"_{type}_ref", None)
        if not ref: return

        threading.Thread(target=lambda: asyncio.run(ref.dispatch(data)), daemon=True).start()

    def _execute_ ( self, item: Any ):

        for _ in range(max(1, self._retries)):

            if self._stop_flag.is_set(): return None

            try:

                result = self._handler(item, **self._context) if callable(self._handler) else self._handler

                if inspect.iscoroutine(result): result = asyncio.run(result)
                if inspect.iscoroutinefunction(result): result = asyncio.run(result())

                self._dispatch_('stream', result)
                return result

            except Exception as e:
                self._dispatch_('error', e)
                time.sleep(0.001)

        return None

    def _work_ ( self, items: list ):

        results = []

        for item in items:

            if self._stop_flag.is_set(): break
            results.append(self._execute_(item))

        return results

    def start ( self ):

        self._dispatch_('start', self)
        total = len(self._items)
        self._chunk_size = max(1, math.ceil(total / max(1, self._max_workers)))

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:

            futures = []

            for i in range(0, total, self._chunk_size):
                chunk = self._items[i : i + self._chunk_size]
                futures.append(executor.submit(self._work_, chunk))

            try:

                for f in as_completed(futures, timeout=self._timeout):

                    if self._stop_flag.is_set(): break

                    res = f.result()
                    if res: self._results.extend(res)

            except Exception as e: self._dispatch_('error', e)

        self._dispatch_('complete', self._results)
        return self

    def cancel ( self ):

        self._stop_flag.set()
        self._dispatch_('cancel', self._results)
        return self

    def collect ( self ):

        return self._results

    def run (
        self, items: Iterable, handler: Callable, context: dict = None,
        max_workers: int = None, timeout: float = None, retries: int = 0,
        on_stream: Callable = None, on_error: Callable = None,
        on_start: Callable = None, on_cancel: Callable = None, on_complete: Callable = None,
        collect: bool = False, start: bool = True ):

        self._items        = list(items)
        self._context      = copy.deepcopy(context or {})
        self._handler      = handler
        self._max_workers  = max(1, max_workers or (len(self._items) or 1))
        self._timeout      = timeout
        self._retries      = retries

        self._stream_ref   = Streamer(on_stream) if on_stream else None
        self._error_ref    = Streamer(on_error) if on_error else None
        self._cancel_ref   = Streamer(on_cancel) if on_cancel else None
        self._start_ref    = Streamer(on_start) if on_start else None
        self._complete_ref = Streamer(on_complete) if on_complete else None

        if start: self.start()
        if collect: return self.collect()
        return self
