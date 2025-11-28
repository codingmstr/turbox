import os, sys, psutil, asyncio, uvicorn, orjson, multiprocessing

_CONTEXT = []
_HEATERS = []
_PTR     = 0

def _alloc_context ( size ):

    global _CONTEXT

    for _ in range(size):
        _CONTEXT.append({ "scope": None, "receive": None, "send": None, "buf": bytearray(1024 * 128), "resp": bytearray(1024 * 128)})

    return True

def get_context():

    global _PTR

    ctx = _CONTEXT[_PTR]
    _PTR = (_PTR + 1) % len(_CONTEXT)

    return ctx

class _JSON:

    __slots__ = ("v",)

    def __init__ ( self, v ):

        self.v = v

    def render ( self ):

        return orjson.dumps(self.v, option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY)

class _Ring:

    __slots__ = ("buf", "n", "p")

    def __init__ ( self, size ):

        self.buf = [None] * size
        self.n = size
        self.p = 0

    def push ( self, x ):

        self.buf[self.p] = x
        self.p = (self.p + 1) % self.n

    def next ( self ):

        x = self.buf[self.p]
        self.p = (self.p + 1) % self.n

        return x

def _coroutine_ring ( size ):

    r = _Ring(size)

    async def w():
        while True:
            await asyncio.sleep(0)

    for _ in range(size):
        r.push(w())

    return r

def _scheduler ():

    q = []
    loop = asyncio.get_event_loop()

    async def pump():
        while True:
            if q:
                fn = q.pop()
                try: fn()
                except: pass
            await asyncio.sleep(0)

    loop.create_task(pump())

    def submit(fn):
        q.append(fn)

    return submit

def _cpu_affinity ():

    try:
        p = psutil.Process(os.getpid())
        p.cpu_affinity(list(range(psutil.cpu_count())))
    except: pass

    return True

def _event_loop ():

    try:
        import uvloop
        uvloop.install()
    except: pass

    loop = asyncio.get_event_loop()
    loop.set_debug(False)
    loop.slow_callback_duration = 0

    return True

def _run_boot ():

    for fn in _HEATERS:
        try: fn()
        except: pass
  
    return True

def boot ( *fns ):

    for fn in fns:
        if callable(fn):
            _HEATERS.append(fn)

    return True

def runtime ():

    _alloc_context(256)
    _cpu_affinity()
    _event_loop()
    _coroutine_ring(128)
    _scheduler()
    _run_boot()

    return True

def startup ( app, host="0.0.0.0", port=8000, workers: int = None, reload: bool = False ):

    runtime()

    uvicorn.run(
        app,
        host=host,
        port=port,
        loop="uvloop",
        http="httptools",
        backlog=4096,
        workers=workers or max(1, multiprocessing.cpu_count() // 2),
        reload=reload
    )
