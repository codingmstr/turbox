from fastapi import Depends, Request, HTTPException
from typing import Any
from functools import partial
import threading, inspect, time, re
from cachetools import TTLCache
from core.support.utils import *

rate_lock   = threading.Lock()
rate_bucket = TTLCache(maxsize=50000, ttl=3600)

def build_domain_patterns ( domains: list, subdomains: list ) :
    
    if domains and subdomains: return [ f"{str(s).strip('.')}.{str(d).strip('.')}".lower() for d in domains for s in subdomains ]
    elif domains: return [str(d).strip().lower() for d in domains]
    elif subdomains: return [str(s).strip().lower() for s in subdomains]

def match_domain_pattern ( pattern: str, host: str ):
 
    if not host: return False

    pattern = (pattern or "").strip().lower()
    host = host.strip().lower()

    if pattern in ("", "*", "default"): return True

    if "*" in pattern and not "{" in pattern:
        regex = "^" + re.escape(pattern).replace("\\*", ".*") + "$"
        return bool(re.match(regex, host))

    params  = {}
    parts_p = pattern.split(".")
    parts_h = host.split(".")

    if len(parts_p) != len(parts_h): return False

    for pp, ph in zip(parts_p, parts_h):
        
        if pp.startswith("{") and pp.endswith("}"): params[pp.strip("{}")] = ph
        elif pp != ph: return False

    return params or True

def controller_variants ( name: str ):
    
    base = name.strip().replace(".py", "")
    native = base.lower().replace('_controller', "").replace('controller', "")
   
    variants = set([name, name.lower(), f"{name}_controller".lower(), name.title(), name.capitalize()])
    patterns = ["{n}_controller", "{n}Controller", "{n}_Controller", "{n}controller", "{n}"]
    cases    = [base, native.lower(), native.title(), native.capitalize()]

    [variants.add(p.format(n=c)) for c in cases for p in patterns]
    variants.update(['controller', 'Controller'])

    return list(variants)

def resolve_controller_class ( module, ctr_name: str ):

    if not hasattr(module, "__dict__"): raise ValueError("Invalid module passed")

    classes = { name: obj for name, obj in inspect.getmembers(module, inspect.isclass) if obj.__module__ == module.__name__ }

    for variant in controller_variants(ctr_name):
        for cls_name, cls_obj in classes.items():
            if cls_name.lower() == variant.lower():
                return cls_obj

    if classes: return list(classes.values())[0]
    raise ValueError(f"No matching controller found in module {module.__name__}")

def resolve_controller_name ( namespace: str, controller: str ):

    is_root    = controller.startswith(('/', '\\'))
    controller = controller.strip().replace("\\", "/").replace("//", "/").replace(".", "/").strip("/")
    segments   = controller.split("/")
    ctr_name   = segments[-1]
    subpath    = ".".join(segments[:-1]) if len(segments) > 1 else ""
    basepath   = f".{subpath}" if subpath else ""
    
    namespace = namespace.strip('.') or module.find('controllers', True)
    namespace = (namespace.rstrip('.') + basepath) if not is_root else basepath.lstrip('.')

    for name in controller_variants(ctr_name):
        if module.exists(f"{namespace}.{name}"): return name

def resolve_handler ( handler: Any, namespace: str, controller: str ):

    if callable(handler): return handler
    ctrl_name, method = None, None
    
    if isinstance(handler, (list, tuple)) and len(handler) == 2: ctrl_name, method = handler
    elif isinstance(handler, str) and "@" in handler: ctrl_name, method = handler.split("@", 1)
    elif isinstance(handler, str) and ":" in handler: ctrl_name, method = handler.split(":", 1)
    elif isinstance(handler, str) and "." in handler: ctrl_name, method = handler.split(".", 1)
    elif isinstance(handler, str) and controller: ctrl_name, method = controller, handler
    else: raise ValueError(f"Invalid handler format: {handler}")

    ctrl_path = str(ctrl_name).replace("-", "_").replace("\\", "/").strip("/")
    segments  = ctrl_path.split("/")
    ctrl_file = string.snake(segments[-1])
    subpath   = ".".join(map(string.snake, segments[:-1])) if len(segments) > 1 else ""
    namespace = f"{namespace}.{subpath}" if subpath else namespace
    full_path = f"{namespace}.{ctrl_file}"

    mod = module.require(full_path, True)

    if not mod: mod = module.require(f"{namespace}.{resolve_controller_name(namespace, ctrl_file)}", True)
    if not mod: raise ImportError(f"Handler module not found: {namespace} -> {handler}")

    klass = resolve_controller_class(mod, ctrl_file)
    instance = klass()

    if hasattr(instance, method): resolved = getattr(instance, method)
    elif hasattr(instance, "invoke"): resolved = getattr(instance, "invoke")
    elif hasattr(instance, "__call__"): resolved = getattr(instance, "__call__")
    else: raise AttributeError(f"Method '{method}' not found in controller '{klass.__name__}' ")

    return resolved

def resolve_patterns ( path: str, patterns: dict ):

    for param, pattern in patterns.items():
        path = path.replace(f"{{{param}}}", f"{{{param}:{pattern}}}")

    return path

def resolve_middleware ( middleware: str ):

    parts   = str(middleware).split(":", 1)
    file    = str(parts[0]).strip()
    params  = iters.parse(parts[1]) if len(parts) > 1 else []
    mod     = module.require(f"{module.find('middleware', True)}.{file}")
    handler = getattr(mod, "dependency", None) or getattr(mod, "depends", None) or getattr(mod, "handle", None)

    return handler, params


async def limiter_guard ( request: Request, key: str, limit: int, per: float ):

    now    = time.time()
    window = per * 60
    unique = f"{request.client.host}:{key}"

    with rate_lock:

        start, cnt = rate_bucket.get(unique, (0.0, 0))

        if now - start >= window: start, cnt = now, 0
        if cnt + 1 > limit: raise HTTPException(status_code = 429, detail = "Too Many Requests")

        rate_bucket[unique] = (start, cnt + 1)
        return True

async def domain_guard ( request: Request, domains: list, subdomains: list ):

    host = str(request.headers.get('host', '')).split(':')[0].lower()
    patterns = build_domain_patterns(domains, subdomains)

    for pattern in patterns:

        result = match_domain_pattern(pattern, host)

        if isinstance(result, dict): request.path_params['domain'] = request.state.domain = result
        if result: return True

    raise HTTPException(status_code=404, detail=f"Host '{host}' not allowed")

async def core_guards ( request: Request, params: dict ):

    domains = list(params.get('domains'))
    subs    = list(params.get('subdomains'))
    limit   = list(params.get('limit'))
    unique  = str(params.get('key'))

    if limit: await limiter_guard(request, unique, int(limit[0]), float(limit[1]))
    if domains or subs: await domain_guard(request, domains, subs)

    return True

async def middleware_guards ( request: Request, params: dict ):
    
    for middleware in list(params.get('middlewares')):

        handler, prms = resolve_middleware(str(middleware))
        if not handler: continue

        result = await handler(request, *prms) if inspect.iscoroutinefunction(handler) else handler(request, *prms)
        if result is False: raise HTTPException(status_code=403, detail=f"Middleware {handler.__name__} rejected request")

    return True

async def all_guards ( request: Request, params: dict ):

    await core_guards(request, params)
    await middleware_guards(request, params)

    return True

def resolve_guards ( params: dict ):

    return [Depends(partial(all_guards, params=params))]
