import asyncio, inspect, functools, time, concurrent.futures, atexit, os, threading
from typing import Any, Callable, Iterable, get_type_hints
from .module import Modules

class Func:

    def __init__ ( self ):

        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() * 4)
        atexit.register(self._executor.shutdown)

    def __call__ ( self, fn: Callable, *args, **kwargs ):

        return self.execute(fn, *args, **kwargs)

    def name ( self, fn: Callable ):

        return getattr(fn, '__name__', str(fn))

    def doc ( self, fn: Callable ):

        return inspect.getdoc(fn) or ''

    def module ( self, fn: Callable ):

        return getattr(fn, '__module__', 'builtins')

    def file ( self, fn: Callable ):

        try: return inspect.getfile(fn)
        except Exception: return '<built-in>'

    def source ( self, fn: Callable ):

        try: return inspect.getsource(fn)
        except Exception: return ''

    def signature ( self, fn: Callable ):

        try: return str(inspect.signature(fn))
        except Exception: return '(...)'

    def returns ( self, fn: Callable ):

        sig = inspect.signature(fn)
        return str(sig.return_annotation) if sig.return_annotation is not inspect._empty else None

    def args ( self, fn: Callable ):

        try: return list(inspect.signature(fn).parameters.keys())
        except Exception: return []

    def args_count ( self, fn: Callable ):

        return len(inspect.signature(fn).parameters)

    def required_args ( self, fn: Callable ):

        sig = inspect.signature(fn)
        required = []

        for name, param in sig.parameters.items():

            if (
                param.default is inspect._empty
                and param.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            ): required.append(name)

        return required

    def args_defaults ( self, fn: Callable ):

        sig = inspect.signature(fn)
        defaults = {}

        for name, param in sig.parameters.items():
            if param.default is not inspect._empty:
                defaults[name] = param.default

        return defaults

    def args_values ( self, fn: Callable, *args, **kwargs ):

        sig = inspect.signature(fn)
        bound = sig.bind_partial(*args, **kwargs)

        bound.apply_defaults()
        return dict(bound.arguments)

    def annotations ( self, fn: Callable ):

        try: return get_type_hints(fn)
        except Exception: return {}

    def return_annotation ( self, fn: Callable ):

        sig = inspect.signature(fn)
        ret = sig.return_annotation

        return None if ret is inspect._empty else ret

    def info ( self, fn: Callable ):

        return {
            'name'          : self.name(fn),
            'module'        : self.module(fn),
            'args'          : self.args(fn),
            'args_count'    : self.args_count(fn),
            'required_args' : self.required_args(fn),
            'args_defaults' : self.args_defaults(fn),
            'annotations'   : self.annotations(fn),
            'return_type'   : self.return_annotation(fn),
            'returns'       : self.returns(fn),
            'signature'     : self.signature(fn),
            'file'          : self.file(fn),
            'doc'           : self.doc(fn),
        }


    def is_sync ( self, fn: Callable ):

        return not inspect.iscoroutinefunction(fn)

    def is_async ( self, fn: Callable ):

        return inspect.iscoroutinefunction(fn)

    def is_generator ( self, fn: Callable ):

        return inspect.isgeneratorfunction(fn)

    def is_lambda ( self, fn: Callable ):

        return callable(fn) and fn.__name__ == '<lambda>'

    def is_partial ( self, fn: Callable ):

        return isinstance(fn, functools.partial)

    def is_void ( self, fn: Callable ):

        return self.return_annotation(fn) in (None, inspect._empty)


    def _run_loop_isolated ( self, coro ):

        result, error, event = None, None, threading.Event()

        def runner():

            nonlocal result, error

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(coro)

            except Exception as e:
                error = e

            finally:
                try: loop.close()
                except: pass
                event.set()

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        event.wait()

        if error: raise error
        return result

    def _run_new_loop ( self, coro ):

        try: return asyncio.run(coro)
        except RuntimeError: return self._run_loop_isolated(coro)

    def _safe_run_coro ( self, coro ):

        try: loop = asyncio.get_running_loop()
        except RuntimeError: loop = None

        if loop and loop.is_running():

            if loop.is_closed(): return self._run_new_loop(coro)
            future = asyncio.run_coroutine_threadsafe(coro, loop)

            try: return future.result()
            except Exception: return self._run_new_loop(coro)

        if loop and not loop.is_running(): return self._run_new_loop(coro)
        return self._run_new_loop(coro)

    def execute ( self, fn: Callable, *args, **kwargs ):
     
        if not callable(fn) and not inspect.iscoroutine(fn): return fn
        if inspect.iscoroutinefunction(fn): return self._safe_run_coro(fn(*args, **kwargs))
        if inspect.iscoroutine(fn): return self._safe_run_coro(fn)

        return fn(*args, **kwargs)

    async def aexecute ( self, fn: Callable, *args, **kwargs ):

        if not callable(fn) and not inspect.iscoroutine(fn): return fn
        if inspect.iscoroutinefunction(fn): return await fn(*args, **kwargs)

        if inspect.iscoroutine(fn):
            if getattr(fn, "cr_running", False): return fn
            return await fn

        try: loop = asyncio.get_running_loop()
        except RuntimeError: return self.execute(fn, *args, **kwargs)

        func = functools.partial(self.execute, fn, *args, **kwargs)
        return await loop.run_in_executor(self._executor, func)

    def thread ( self, fn: Callable, *args, callback: Callable = None, **kwargs ):

        if not callable(fn) and not inspect.iscoroutine(fn): return fn

        def target(): return self.execute(fn, *args, **kwargs)
        future = self._executor.submit(target)

        def _auto_collect(fut):
            try:
                result = fut.result(0)
                if callable(callback): self.execute(callback, result)
            except Exception: pass

        future.add_done_callback(_auto_collect)
        return future

    async def athread ( self, fn: Callable, *args, callback: Callable = None, **kwargs ):

        if not callable(fn) and not inspect.iscoroutine(fn): return fn

        async def runner():
            try:

                if inspect.iscoroutinefunction(fn) or inspect.iscoroutine(fn):
                    result = await self.aexecute(fn, *args, **kwargs)
                else:
                    result = await asyncio.to_thread(self.execute, fn, *args, **kwargs)

                if callable(callback): await self.aexecute(callback, result)

            except Exception: pass 

        asyncio.create_task(runner())

    def run ( self, fn: Callable, *args, **kwargs ):

        return self.execute(fn, *args, **kwargs)

    async def arun ( self, fn: Callable, *args, **kwargs ):

        return await self.aexecute(fn, *args, **kwargs)

    def retry ( self, fn: Callable, retries: int = 3, delay: float = 0.1, *args, **kwargs ):

        last_exc = None

        for attempt in range(retries):

            try: return self.execute(fn, *args, **kwargs)
            except Exception as e:
                last_exc = e
                if attempt < retries - 1: time.sleep(delay)

        raise last_exc

    async def aretry ( self, fn: Callable, retries: int = 3, delay: float = 0.1, *args, **kwargs ):

        last_exc = None

        for attempt in range(retries):

            try: return await self.aexecute(fn, *args, **kwargs)
            except Exception as e:
                last_exc = e
                if attempt < retries - 1: await asyncio.sleep(delay)

        raise last_exc

    def timeit ( self, fn: Callable, *args, **kwargs ):

        start = time.perf_counter()
        result = self.execute(fn, *args, **kwargs)
        return {'result': result, 'elapsed': round(time.perf_counter() - start, 6) }

    async def atimeit ( self, fn: Callable, *args, **kwargs ):

        start = time.perf_counter()
        result = await self.aexecute(fn, *args, **kwargs)
        return {'result': result, 'elapsed': round(time.perf_counter() - start, 6) }

    def compose ( self, *funcs: Callable ):

        def composed ( value ):
            for fn in reversed(funcs): value = self.execute(fn, value)
            return value

        return composed

    async def acompose ( self, *funcs: Callable ):

        async def composed ( value ):
            for fn in reversed(funcs): value = await self.aexecute(fn, value)
            return value

        return composed

    def map ( self, fn: Callable, iterable: Iterable, max_workers: int = 8 ):

        if inspect.iscoroutinefunction(fn):

            try:
                loop = asyncio.get_running_loop()
                return loop.create_task(self.amap(fn, iterable, max_tasks=max_workers))
            except RuntimeError:
                return asyncio.run(self.amap(fn, iterable, max_tasks=max_workers))

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(fn, iterable))

    async def amap ( self, fn: Callable, iterable: Iterable, max_tasks: int = 32 ):

        sem = asyncio.Semaphore(max_tasks)

        async def worker(item):
            async with sem:
                return await self.aexecute(fn, item)

        tasks = [asyncio.create_task(worker(item)) for item in iterable]
        return await asyncio.gather(*tasks)

    def gather ( self, *funcs: Callable, as_dict: bool = False, **kwargs ):

        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(self.agather(*funcs, as_dict=as_dict, **kwargs))
        except RuntimeError:
            return asyncio.run(self.agather(*funcs, as_dict=as_dict, **kwargs))

    async def agather ( self, *funcs: Callable, as_dict: bool = False, **kwargs ):

        tasks, names = [], []

        for idx, fn in enumerate(funcs):

            name = getattr(fn, "__name__", f"func_{idx}")
            names.append(name)

            if inspect.iscoroutinefunction(fn): tasks.append(fn(**kwargs))
            else: tasks.append(asyncio.to_thread(fn, **kwargs))

        results = await asyncio.gather(*tasks)

        if as_dict: return dict(zip(names, results))
        return results

    def run_on_exit ( self, fn: Callable, *args, **kwargs ):

        def close(): self.run(fn, *args, **kwargs)
        atexit.register(close)

    async def arun_on_exit ( self, fn: Callable, *args, **kwargs ):

        return self.run_on_exit(fn, *args, **kwargs)

    def call ( self, fn: Callable | str, fallback: Callable | Iterable[Callable] = None, handle: bool = False, *args, **kwargs ):

        if callable(fn): return self.execute(fn, *args, **kwargs)

        if isinstance(fn, str):

            parts  = fn.split('.')
            method = parts[-1]
            module = None
            target = None

            mod_name = '.'.join(parts[:-1]).strip('.') or inspect.currentframe().f_back.f_globals.get('__name__', None)
            module = Modules().smart_require(mod_name, handle=False)

            for space in (module, globals(), locals()):

                if not space: continue

                target = space[method] if isinstance(space, dict) else getattr(space, method, None)
                if callable(target): return self.execute(target, *args, **kwargs)

            variants = [
                method,
                ''.join([p.capitalize() for p in method.split('_')]),
                ''.join([p.lower() for p in method.split('_')]),
                ''.join([p.upper() for p in method.split('_')]),
                ''.join([p for p in method.split('_')]),
                method.capitalize(),
                method.lower(),
                method.upper(),
                method.split('_')[0].capitalize(),
                method.split('_')[0].lower(),
                method.split('_')[0].upper(),
                method.split('_')[0].capitalize() + ''.join(x.title() for x in method.split('_')[1:]),
                method.split('_')[0].lower() + ''.join(x.title() for x in method.split('_')[1:]),
                method.split('_')[0].upper() + ''.join(x.title() for x in method.split('_')[1:]),
            ]

            for cname in variants:

                cls = getattr(module, cname, None)
                if not cls: continue

                fn = getattr(cls, method, None)

                if isinstance(fn, staticmethod): return self.execute(fn.__func__, *args, **kwargs)
                if isinstance(fn, classmethod): return self.execute(fn.__func__, cls, *args, **kwargs)

                if inspect.isclass(cls):

                    try: instance = cls()
                    except Exception: continue

                    fn = getattr(instance, method, None)
                    if callable(fn): return self.execute(fn, *args, **kwargs)

        if fallback:

            for fb in set(['__call__', *(fallback if isinstance(fallback, (list, tuple, set)) else [fallback])]):

                if not fb: continue

                result = self.call(fb, None, True, *args, **kwargs)
                if result is not None: return result

        if not handle: raise NameError(f'Function {fn} is not defined')
        return None

    async def acall ( self, fn: Callable | str, fallback: Callable | Iterable[Callable] = None, handle: bool = False, *args, **kwargs ):

        return self.call(fn, fallback, *args, **kwargs)


    def wrap_aware ( self, fn: Callable, sync_impl: Callable = None, async_impl: Callable = None ):

        if self.is_async(fn):

            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):

                if async_impl: return await async_impl(fn, *args, **kwargs)
                return self.execute(fn, *args, **kwargs)

            return wrapper

        else:

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):

                if sync_impl: return sync_impl(fn, *args, **kwargs)

                try:
                    loop = asyncio.get_running_loop()
                    if loop and loop.is_running():
                        return asyncio.run_coroutine_threadsafe(async_impl(fn, *args, **kwargs), loop).result()
                except RuntimeError:
                    return asyncio.run(async_impl(fn, *args, **kwargs))

            return wrapper

    def handle ( self, default: Any = None ):

        def decorator ( fn ):

            async def async_impl ( fn, *args, **kwargs ):
                try: return await self.aexecute(fn, *args, **kwargs)
                except: return await self.aexecute(default) if callable(default) else default

            def sync_impl ( fn, *args, **kwargs ):
                try: return self.execute(fn, *args, **kwargs)
                except: return self.execute(default) if callable(default) else default

            return self.wrap_aware(fn, sync_impl, async_impl)

        return decorator

    def measure ( self, on_call: Callable = None ):

        def decorator ( fn ):

            async def async_impl ( fn, *args, **kwargs ):

                start = time.perf_counter()
                result = await self.aexecute(fn, *args, **kwargs)
                elapsed = round(time.perf_counter() - start, 6)

                if callable(on_call): await self.aexecute(on_call, {'elapsed': elapsed})
                return result

            def sync_impl ( fn, *args, **kwargs ):

                start = time.perf_counter()
                result = self.execute(fn, *args, **kwargs)
                elapsed = round(time.perf_counter() - start, 6)

                if callable(on_call): self.execute(on_call, {'elapsed': elapsed})
                return result

            return self.wrap_aware(fn, sync_impl, async_impl)

        return decorator

    def timeout ( self, seconds: float, on_timeout: Callable = None ):

        def decorator ( fn ):

            async def async_impl ( fn, *args, **kwargs ):

                try: return await asyncio.wait_for(self.aexecute(fn, *args, **kwargs), seconds)
                except: return await self.aexecute(on_timeout) if callable(on_timeout) else on_timeout

            def sync_impl ( fn, *args, **kwargs ):

                try: return asyncio.run(asyncio.wait_for(self.aexecute(fn, *args, **kwargs), seconds))
                except: return self.execute(on_timeout) if callable(on_timeout) else on_timeout

            return self.wrap_aware(fn, sync_impl, async_impl)

        return decorator

    def throttle ( self, rate: int = 60, per_minutes: float = 1, on_over: Callable = None ):

        window = per_minutes * 60

        def decorator ( fn ):

            calls = []
            sync_lock, async_lock = threading.Lock(), asyncio.Lock()

            async def async_impl ( fn, *args, **kwargs ):

                nonlocal calls
                now = time.time()

                async with async_lock:

                    calls[:] = [t for t in calls if now - t < window]
                    if len(calls) >= rate: return await self.aexecute(on_over) if callable(on_over) else on_over

                    calls.append(now)
                    return await self.aexecute(fn, *args, **kwargs)

            def sync_impl ( fn, *args, **kwargs ):

                nonlocal calls
                now = time.time()

                with sync_lock:

                    calls[:] = [t for t in calls if now - t < window]
                    if len(calls) >= rate: return self.execute(on_over) if callable(on_over) else on_over

                    calls.append(now)
                    return self.execute(fn, *args, **kwargs)

            return self.wrap_aware(fn, sync_impl, async_impl)

        return decorator

    def cache ( self, ttl_seconds: float = None ):

        def decorator ( fn ):

            cache_data = {}

            async def async_impl ( fn, *args, **kwargs ):

                nonlocal cache_data

                now = time.time()
                key = (args, tuple(sorted(kwargs.items())))

                if ttl_seconds:

                    expired = []
                  
                    for k, (_, ts) in cache_data.items():
                        if now - ts >= ttl_seconds: expired.append(k)

                    for k in expired: cache_data.pop(k, None)

                if key in cache_data: return cache_data[key][0]

                result = await self.aexecute(fn, *args, **kwargs)
                cache_data[key] = (result, now)

                return result

            def sync_impl ( fn, *args, **kwargs ):

                nonlocal cache_data

                now = time.time()
                key = (args, tuple(sorted(kwargs.items())))

                if ttl_seconds:

                    expired = []

                    for k, (_, ts) in cache_data.items():
                        if now - ts >= ttl_seconds: expired.append(k)

                    for k in expired: cache_data.pop(k, None)

                if key in cache_data: return cache_data[key][0]

                result = self.execute(fn, *args, **kwargs)
                cache_data[key] = (result, now)

                return result

            return self.wrap_aware(fn, sync_impl, async_impl)

        return decorator

    def cache_calls ( self, max_calls: int = 100, typed: bool = False ):

        def decorator ( fn ):

            cache_data = {}

            if self.is_async(fn):

                async def async_impl ( fn, *args, **kwargs ):

                    nonlocal cache_data

                    key = (args, tuple(sorted(kwargs.items())))
                    if key in cache_data: return cache_data[key]

                    result = await self.aexecute(fn, *args, **kwargs)
                    if len(cache_data) >= max_calls: cache_data.pop(next(iter(cache_data)))

                    cache_data[key] = result
                    return result
                
                return self.wrap_aware(fn, None, async_impl)

            else:

                cached_fn = functools.lru_cache(maxsize=max_calls, typed=typed)(fn)

                def sync_impl ( fn, *args, **kwargs ):
                    return cached_fn(*args, **kwargs)

                return self.wrap_aware(fn, sync_impl, None)

        return decorator

    def once ( self ):

        def decorator ( fn ):

            has_run, result = False, None
            sync_lock, async_lock = threading.Lock(), asyncio.Lock()

            async def async_impl ( fn, *args, **kwargs ):

                nonlocal has_run, result

                async with async_lock:
                    if not has_run:
                        result = await self.aexecute(fn, *args, **kwargs)
                        has_run = True

                return result

            def sync_impl ( fn, *args, **kwargs ):

                nonlocal has_run, result

                with sync_lock:
                    if not has_run:
                        result = self.execute(fn, *args, **kwargs)
                        has_run = True

                return result

            return self.wrap_aware(fn, sync_impl, async_impl)

        return decorator

    def debounce ( self, seconds: float ):

        def decorator ( fn ):

            timer = None
            async_lock = asyncio.Lock()

            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):

                nonlocal timer

                async with async_lock:

                    if timer: timer.cancel()

                    async def call_later():
                        await asyncio.sleep(seconds)
                        await self.aexecute(fn, *args, **kwargs)

                    timer = asyncio.create_task(call_later())

            return wrapper

        return decorator

    def on_exit ( self ):

        def decorator(fn):

            self.run_on_exit(fn)

            @functools.wraps(fn)
            def wrapper ( *args, **kwargs ):
                return fn(*args, **kwargs)

            return wrapper

        return decorator
