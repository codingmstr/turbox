from fastapi import FastAPI, APIRouter
from fastapi.responses import RedirectResponse
from typing import Union, Any
import pkgutil, os, json, copy
from .helpers import *

class RouteCall:

    def __init__ ( self, ctx: dict ):
        
        self.ctx = {**ctx}
        self._start()

    def _start ( self ):

        return self \
            ._set('route_path', self._get('path')) \
            ._set('route_name', self._get('name')) \
            ._set('path', '') \
            .namespace(self._get('namespace', module.find('controllers', True))) \
            .controller(self._get('controller')) \
            .middleware(*list(self._get('middlewares'))) \
            .handler(self._get('handler')) \
            .path(self._get('path'))

    def _set ( self, key: str, value: Any, merge=False ):
        
        current = self._get(key)

        if merge: self.ctx[key] = iters.unique([current, value] if current else [value])
        else: self.ctx[key] = value

        return self

    def _get ( self, key: str, default = '' ):
        
        return self.ctx.get(key) or default

    def group ( self, value: str ):

        return self._set("group", value)

    def namespace ( self, value: str ):

        return self._set("namespace", module.normalize(value))
    
    def controller ( self, value: str ):

        return self._set("controller", resolve_controller_name(self._get('namespace'), value))

    def handler ( self, value: Any  ):

        return self._set("handler", resolve_handler(value, self._get('namespace'), self._get('controller')))

    def method ( self, *args  ):

        return self._set("methods", [str(m).upper() for m in args], True)

    def domain ( self, *args ):
        
        return self._set("domains", args, True)

    def subdomain ( self, *args ):

        return self._set("subdomains", args, True)
    
    def middleware ( self, *args ):

        return self._set("middlewares", args, True)

    def tag ( self, *args ):
        
        return self._set("tags", args, True)

    def version ( self, value: Union[int, str] ):
        
        ver = f"v{value}" if str(value).isdigit() else str(value)
        return self._set("version", ver)._set("prefix", string.join(ver, self._get("prefix"), separator='/')).path(self._get('route_path'))

    def prefix ( self, value: str ):
        
        return self._set("prefix", string.join(self._get('prefix'), value, separator='/')).path(self._get('route_path'))

    def path ( self, value: str  ):

        return self._set("path", '/' + string.join(self._get('prefix'), value, separator='/'))

    def name ( self, value: str ):

        return self._set("name", string.join(self._get('route_name'), value))

    def limit ( self, limit: int, per: float = 1 ):
        
        return self._set("limit", (limit, per))
    
    def where ( self, **patterns ):

        return self._set("patterns", patterns, True)

    def build ( self ):
        
        self._set('key', string.join(self._get('path'), *self._get('subdomains'), *self._get('domains'), *self._get('methods')))
        self._set('path', resolve_patterns(str(self._get('path', '')), dict(self._get('patterns', {}))))
        self._set('depends', resolve_guards({**self.ctx}))

        return {**self.ctx}

    async def init ( self, router: APIRouter ):

        context = self.build()

        router.add_api_route(
            path=str(context.get('path')),
            endpoint=context.get('handler'),
            methods=list(context.get('methods')),
            name=str(context.get('name')),
            tags=list(context.get('tags')),
            dependencies=list(context.get('depends'))
        )

        obj = router.routes[-1]
        obj.extra = {**getattr(obj, "extra", {}), **context}

        return router

class Route:

    def __init__ ( self ):

        self.ctx     = dict()
        self._routes = []
        self._stack  = [self._object()]

    def __enter__ ( self ):

        self._stack.append(self._object())
        return self

    def __exit__(  self, *args ):

        if len(self._stack) > 1:
           
            self._stack.pop()
            prev = copy.deepcopy(self._stack[-1])

            self.ctx.clear()
            self.ctx.update(prev)

        return False

    def _object ( self ):

        return {
            "methods"     : [],
            "path"        : '',
            "prefix"      : '',
            "name"        : '',
            "namespace"   : '',
            "controller"  : '',
            "handler"     : None,
            "middlewares" : [],
            "tags"        : [],
            "version"     : None,
            "limit"       : None,
            "patterns"    : [],
            "group"       : '',
            "domains"     : [],
            "subdomains"  : [],
            "key"         : '',
        }

    def _apply ( self, path: str, method: Any, handler: Any ):

        call = RouteCall({
            **self._object(),
            **self.ctx,
            'path'    : path,
            'handler' : handler,
            'methods' : [str(m).upper() for m in iters.flatten(iters.ensure(method))],
        })

        self._routes.append(call)
        return call

    def _set ( self, key: str, value: Any, merge=False ):
        
        current = self._get(key)

        if merge: self.ctx[key] = iters.unique([current, value] if current else [value])
        else: self.ctx[key] = value

        return self
    
    def _get ( self, key: str, default = '' ):
        
        return self.ctx.get(key) or default

    def group ( self, value: str ):

        return self._set("group", value)

    def namespace ( self, value: str ):

        return self._set('namespace', value)
    
    def controller ( self, value: str ):

        return self._set('controller', value)
    
    def domain ( self, *args ):
        
        return self._set("domains", args, True)

    def subdomain ( self, *args ):

        return self._set("subdomains", args, True)
    
    def middleware ( self, *args ):

        return self._set("middlewares", args, True)

    def tag ( self, *args ):

        return self._set("tags", args, True)

    def version ( self, value: Union[int, str] ):

        return self._set("version", f"v{value}" if str(value).isdigit() else value)

    def prefix ( self, value: str ):
        
        return self._set("prefix", string.join(self._get('prefix'), value, separator='/'))

    def name ( self, value: str ):

        return self._set("name", string.join(self._get('name'), value))

    def limit ( self, limit: int, per: float = 1 ):
        
        return self._set("limit", (limit, per))

    def where ( self, **patterns ):

        return self._set("patterns", patterns, True)

    def get ( self, path: str, handler: Any = None ):
        
        return self._apply(path, 'get', handler)
   
    def post ( self, path: str, handler: Any = None ):
        
        return self._apply(path, 'post', handler)
   
    def put ( self, path: str, handler: Any = None ):
        
        return self._apply(path, 'put', handler)
   
    def delete ( self, path: str, handler: Any = None ):
        
        return self._apply(path, 'delete', handler)
    
    def patch ( self, path: str, handler: Any = None ):
        
        return self._apply(path, 'patch', handler)
    
    def options ( self, path: str, handler: Any = None ):
        
        return self._apply(path, 'options', handler)

    def fallback ( self, handler: Any = None ):

        return self._apply("/{path_name:path}", "get", handler)

    def redirect ( self, path: str, target: str, status: int = 302 ):

        async def handler(): return RedirectResponse(url=target, status_code=status)
        return self._apply(path, "get", handler)

    def any ( self, path: str, handler: Any = None, only: Any = None, except_: Any = None ):

        methods = ['get', 'post', 'put', 'delete', 'patch', 'options']
        
        if only: methods = [m for m in methods if m in iters.ensure(only)]
        if except_: methods = [m for m in methods if m not in iters.ensure(except_)]

        return self._apply(path, methods, handler)

    def resource ( self, controller: str = None, name: str = None, tag: Any = None, only: Any = None, except_: Any = None ):

        actions = {
            "index"   : ("get", "", f"{name}.index"),
            "store"   : ("post", "", f"{name}.store"),
            "show"    : ("get", "/{id}", f"{name}.show"),
            "update"  : ("put", "/{id}", f"{name}.update"),
            "destroy" : ("delete", "/{id}", f"{name}.destroy"),
        }

        with self.controller(controller).prefix(name).tag(tag):
            
            only    = set(only or ["index", "store", "show", "update", "destroy"])
            except_ = set(except_ or [])
        
            for action, (method, path, route_name) in actions.items():

                if action in except_: continue
                if only and action not in only: continue

                self._apply(path, method, action).name(route_name)

    def routes ( self ):

        return [dict(r.ctx) for r in self._routes]

    def list ( self ):
       
        routes = self.routes()

        print(f"{'METHODS':<10} {'PATH':<40} {'CONTROLLER':<25} {'NAME':<30} {'TAGS'}")
        print('-'*120)

        for ctx in routes:

            methods = ','.join(ctx.get('methods', []))
            path = ctx.get('path', '-')
            controller = ctx.get('controller') or '-'
            name = ctx.get('name') or '-'
            tags = ','.join(ctx.get('tags', []))
          
            print(f"{methods:<10} {path:<40} {controller:<25} {name:<30} {tags}")

        print('-'*120)
        print(f"{'TOTAL':<10} {len(routes)} routes".ljust(120))

    def dump ( self ):
        
        result = []
        
        for r in self.routes():
            
            data = dict(r)
            handler = data.get("handler")
            
            if callable(handler):
                func_name = handler.__name__
                cls_name = handler.__self__.__class__.__name__ if hasattr(handler, "__self__") else None
                data["handler"] = f"{cls_name}.{func_name}" if cls_name else func_name
            
            result.append(data)

        return json.dumps(result, indent=4)
    
    def build ( self, path: str = None ):
  
        path = module.normalize(path or module.find('routes', True))
        dirp = os.path.abspath(path.strip().replace(".", "/"))
        
        if os.path.isdir(dirp):
            
            for _, module_name, _ in pkgutil.iter_modules([dirp]):
                module.require(f"{path}.{module_name}")

        elif os.path.isfile(dirp):
            
            mod_name = os.path.splitext(os.path.basename(dirp))[0]
            module.require(f"{path}.{mod_name}")

        return self._routes

    async def init ( self, app: FastAPI ):

        self.build()

        router = APIRouter()
        for r in self._routes: await r.init(router)

        app.include_router(router)
        return app

route = Route()
