from dotenv import load_dotenv
from typing import Any
from ..micro import module
import os

class Env:

    def __init__ ( self ):

        self.loaded = False

    def init ( self ):

        search_order = []

        if self.is_local(): search_order = ['env_local', 'env']
        else: search_order = ['env_production', 'env', 'env_local']

        for name in search_order:
            path = os.path.join(os.getcwd(), module.find(name))

            if os.path.isfile(path):
                load_dotenv(dotenv_path=path, override=False)
                break

        secrets_path = os.path.join(os.getcwd(), module.find('env_secrets'))
        if os.path.isfile(secrets_path): load_dotenv(dotenv_path=secrets_path, override=False)

        self.loaded = True
        return dict(os.environ)

    def reload ( self ):

        return self.init()

    def get ( self, key: str = None, default: Any = None ):
        
        if key is None: return dict(os.environ)
        return os.getenv(key, default)

    def exists ( self, key: str ):

        return self.get(key) is not None

    def mode ( self ):

        return (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("NODE_ENV") or "local").lower().strip()

    def is_local ( self ):

        return self.mode() == "local"

    def is_production ( self ):

        return self.mode() == "production"
