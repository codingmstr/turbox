from multiprocessing import Queue, shared_memory
from typing import Iterable, Callable, Any
import multiprocessing, asyncio, inspect, math, time, copy, threading, struct, pickle

class Streamer:

    def __init__ ( self, callback: Callable ):

        self.callback = callback

    async def dispatch ( self, value: Any ):

        handler = self.callback

        if inspect.iscoroutinefunction(handler): return await handler(value)
        if inspect.iscoroutine(handler): return await handler(lambda: handler)

        result = handler(value) if callable(handler) else handler

        if inspect.iscoroutinefunction(result): return await result()
        if inspect.iscoroutine(result): return await result
        if callable(result): return result()

        return result

class Process:

    def __init__ ( self ):

        self._queue        = Queue()
        self._cpu_count    = 0
        self._chunk_size   = 0
        self._workers      = 0
        self._attempts     = 0
        self._level        = 0
        self._levels       = 0
        self._items        = []
        self._context      = []
        self._processes    = []
        self._threads      = []
        self._results      = []
        self._index_map    = []
        self._shared       = None
        self._memory       = None
        self._memory_name  = None
        self._timeout      = None
        self._retries      = None
        self._handler      = None
        self._handler_ref  = None
        self._stream_ref   = None
        self._error_ref    = None
        self._start_ref    = None
        self._cancel_ref   = None
        self._complete_ref = None

    def _kill_ ( self ):

        for p in self._processes:
            try:
                if p.exitcode is None:
                    p.join(timeout=1)
                    if p.is_alive(): p.terminate()
            except: pass

        return self

    def _close_ ( self ):

        if self._queue:
            self._queue.close()
            self._queue.join_thread()
    
        return self

    def _unlink_ ( self ):

        if self._memory:
           
            try: self._memory.buf.release()
            except: pass

            self._memory.close()
            self._memory.unlink()

        return self

    def _cleanup_ ( self ):

        try: self._kill_()
        except: pass

        try: self._close_()
        except: pass

        try: self._unlink_()
        except: pass

        return self

    def _release_ ( self ):
        
        start = time.time()
       
        while any(t.is_alive() for t in self._threads) and time.time() - start < self._timeout:
            time.sleep(0.0001)

        return self

    def _fetch_ ( self ):

        while True:
            try: self._results.append(self._queue.get_nowait())
            except: break

        return self

    def _dispatch_ ( self, type: str, data: Any ):

        ref = getattr(self, f"_{type}_ref", None)
        if not ref: return

        thread = threading.Thread(target=lambda: asyncio.run(ref.dispatch(data)), daemon=True)
        thread.start()
        self._threads.append(thread)

    def _encode_ ( self, items: list ):

        index_map = []
        buffers   = []
        offset    = 0

        for item in items:
           
            blob = pickle.dumps(item, protocol=pickle.HIGHEST_PROTOCOL)
            size = len(blob)

            buffers.append(struct.pack("<I", size) + blob)
            index_map.append((offset, offset + 4 + size))
            offset += 4 + size

        combined = b"".join(buffers)
        shm = shared_memory.SharedMemory(create=True, size=len(combined))
        shm.buf[:len(combined)] = combined

        self._memory = shm
        self._memory_name = shm.name
        self._index_map = index_map

        return self

    def _decode_ ( self, indexes: list ):
        
        items = []
        memory = shared_memory.SharedMemory(name=self._memory_name)

        try:

            for idx in indexes:

                start, end = self._index_map[idx]
                raw = bytes(memory.buf[start:end])

                size = struct.unpack_from("<I", raw, 0)[0]
                items.append(pickle.loads(raw[4:4 + size]))

        finally: memory.close()

        return items

    def _execute_ ( self, item: Any ):

        for _ in range(self._retries):

            try: return asyncio.run(self._handler_ref.dispatch(item))
            except Exception as e: self._dispatch_('error', e)

    def worker ( self, indexes: list, queue: Queue, items: list ):

        try:

            if not items: items = self._decode_(indexes)
            results = []

            if len(items) > 1 and self._level < self._levels:

                process = Process().run(
                    items = items,
                    handler = self._handler,
                    context = self._context,
                    timeout = self._timeout,
                    retries = self._retries,
                    max_workers = self._workers,
                    nested_levels = self._levels,
                    start = False
                )

                process._stream_ref = self._stream_ref
                process._error_ref  = self._error_ref
                process._level      = self._level = self._level + 1

                results = process.start().collect()

            else:

                for item in items:

                    self._attempts = 0

                    result = self._execute_(item)
                    results.append(result)

                    self._dispatch_('stream', result)

            queue.put((indexes, results))
            self._release_()

        except Exception as e: self._dispatch_('error', e)

    def start ( self ):

        if self._shared: self._encode_(self._items)
        self._dispatch_('start', self)

        total = len(self._items)
        items = []

        for i in range(self._cpu_count):

            start = i * self._chunk_size
            end = min(start + self._chunk_size, total)

            if start >= end: break
            if not self._shared: items = self._items[start:end]

            process = multiprocessing.Process(target=self.worker, args=(list(range(start, end)), self._queue, items))
            process.daemon = False

            process.start()
            self._processes.append(process)

        return self

    def wait ( self ):

        try:
            
            all_batches = []

            for _ in range(len(self._processes)):

                try: all_batches.append(self._queue.get(timeout=self._timeout))
                except Exception: break

            all_batches.sort(key=lambda x: x[0][0])
            self._results = [r for _, batch in all_batches for r in batch]

            for p in self._processes: p.join()

        finally:

            self._dispatch_('complete', self._results)
            self._cleanup_()

        return self

    def collect ( self ):
        
        if not self._results: self.wait()
        return self._results

    def cancel ( self ):

        self._fetch_()._cleanup_()
        self._dispatch_('cancel', self._results)

        return self._results

    def run (
        self, items: Iterable, handler: Callable, context: dict = None, max_workers: int = None, shared: bool = False,
        nested_levels: int = 1, timeout: float = 5.0, retries: int = 3, collect: bool = False, start: bool = True,
        on_stream: Callable = None, on_error: Callable = None, on_cancel: Callable = None,
        on_start: Callable = None, on_complete: Callable = None ):

        self._items        = list(items)
        self._handler      = handler
        self._timeout      = timeout
        self._retries      = retries
        self._workers      = max_workers
        self._levels       = nested_levels
        self._shared       = shared

        self._context      = copy.deepcopy(context or {})
        self._cpu_count    = max(1, min(max_workers or multiprocessing.cpu_count(), len(self._items)))
        self._chunk_size   = max(1, math.ceil(len(self._items) / self._cpu_count))

        self._handler_ref  = Streamer(handler) if handler else None
        self._stream_ref   = Streamer(on_stream) if on_stream else None
        self._error_ref    = Streamer(on_error) if on_error else None
        self._cancel_ref   = Streamer(on_cancel) if on_cancel else None
        self._start_ref    = Streamer(on_start) if on_start else None
        self._complete_ref = Streamer(on_complete) if on_complete else None

        if start: self.start()
        if collect: return self.collect()

        return self
