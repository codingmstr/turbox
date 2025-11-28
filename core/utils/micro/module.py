from importlib import util
from typing import Any
import importlib, pkgutil, os, sys, types, re

class Modules:

    _global_cache = {}

    def __init__ ( self ):

        self.cache = Modules._global_cache

    def find ( self, name: str, as_module: bool = False ):

        map = {
            'models'         : 'app/models',
            'resources'      : 'app/resources',
            'repositories'   : 'app/repositories',
            'services'       : 'app/services',
            'requests'       : 'app/requests',
            'controllers'    : 'app/controllers',
            'middleware'     : 'app/middleware',
            'providers'      : 'app/providers',
            'support'        : 'app/support',
            'helpers'        : 'app/helpers',
            'events'         : 'app/events',
            'jobs'           : 'app/jobs',
            'mails'          : 'app/mails',
            'routes'         : 'routes',
            'config'         : 'config',
            'public'         : 'public',
            'tests'          : 'tests',
            'storage'        : 'storage/public',
            'logs'           : 'storage/logs',
            'views'          : 'resources/views',
            'docs'           : 'resources/docs',
            'redoc'          : 'resources/redoc',
            'migrations'     : 'database/migrations',
            'seeders'        : 'database/seeders',
            'factories'      : 'database/factories',
            'env'            : '.env',
            'env_local'      : '.env.local',
            'env_production' : '.env.production',
            'env_secrets'    : '.env.secrets',
        }
        
        name = map.get(name, name)
        return name.replace('/', '.') if as_module else name

    def normalize ( self, path: str ):

        return path.strip().replace("\\", ".").replace("/", ".").replace("..", ".").strip(".")

    def get ( self, name: str, default: Any = None ):

        return self.cache.get(self.normalize(name), default)

    def register ( self, name: str, module: types.ModuleType ):

        self.cache[self.normalize(name)] = module
        sys.modules[self.normalize(name)] = module

        return module

    def exists ( self, name: str ):

        try: return self.get(name) or util.find_spec(self.normalize(name)) is not None
        except: return False

    def require ( self, name: str, handle: bool = False, reload: bool = False ):

        path = self.normalize(name)
        if path in self.cache and not reload: return self.get(path)

        try:
            module = importlib.import_module(path)
            if reload: module = importlib.reload(module)
            return self.register(path, module)

        except:
            if handle: return None
            raise

    def load ( self, *paths, recursive: bool = False, reload: bool = False ):

        for path in paths:

            path = self.normalize(path)
            dirp = os.path.abspath(path.strip().replace(".", "/"))

            if os.path.isdir(dirp):

                for _, mod_name, is_pkg in pkgutil.iter_modules([dirp]):

                    mod_full = f"{path}.{mod_name}"
                    self.require(mod_full, True, reload)

                    if recursive and is_pkg: self.load(mod_full, recursive=True, reload=reload)

            elif os.path.isfile(dirp):

                mod_name = os.path.splitext(os.path.basename(dirp))[0]
                self.require(f"{path}.{mod_name}", True, reload)

        return True

    def discover ( self, *paths, recursive: bool = False ):

        found = {}

        for path in paths:

            path = self.normalize(path)
            dirp = os.path.abspath(path.strip().replace(".", "/"))

            if not os.path.isdir(dirp): continue

            for _, mod_name, is_pkg in pkgutil.iter_modules([dirp]):

                mod_full = f"{path}.{mod_name}"

                found[mod_full] = {
                    "package": path,
                    "name": mod_name,
                    "is_package": is_pkg,
                    "loaded": mod_full in self.cache
                }

                if recursive and is_pkg: found.update(self.discover(mod_full, recursive=True))

        return found

    def smart_require ( self, name: str, variant_hint: str = None, handle: bool = True, reload: bool = False ):

        path = self.normalize(name)

        discovered = self.require(path, reload=reload)
        if discovered: return discovered

        base = re.sub(r'\.py$', '', path.split('.')[-1])
        parent = '.'.join(path.split('.')[:-1])
        variants = set()

        core = re.sub(r'(_|-)+', '_', base)
        pure = re.sub(rf'(_?{re.escape(variant_hint)}_?|{re.escape(variant_hint)})$', '', core, flags=re.I) if variant_hint else core
        
        tokens = { pure, core, base, pure.lower(), pure.title(), pure.capitalize() }
        patterns = [ '{n}', '{n}_{v}', '{v}_{n}', '{n}{v}', '{n}_{v}', '{n}-{v}', '{v}-{n}' ]

        for n in tokens:

            for v in ([variant_hint] if variant_hint else []):
                for p in patterns: variants.add(p.format(n=n, v=v))

            variants.add(n)

        variants.update({ base, core, pure, f"{pure}_{variant_hint or ''}", f"{pure}{(variant_hint or '').capitalize()}" })
        variants = [str(v).strip('_-') for v in variants if v]

        for variant in variants:

            full = f"{parent}.{variant}" if parent else variant
            if self.exists(full): return self.require(full, handle, reload)

        if handle: return None
        raise ImportError(f"Module '{name}' not found, tried variant: {variant_hint}")
