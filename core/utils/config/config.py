from typing import Any
from ..micro import module
from .env import Env
import os

config_store = {}

class Config:

    def __init__ ( self ):
        
        self.env = Env()

    def init ( self ):

        self.env.init()

        base_path = module.find('config')
        abs_path = os.path.abspath(base_path)

        if not os.path.isdir(abs_path):
            raise FileNotFoundError(f"Config directory not found: {abs_path}")

        for filename in os.listdir(abs_path):
            
            try:
                
                name = filename[:-3].lower()
                mod = module.require(f"{base_path}.{name}")

                if mod and hasattr(mod, "config"):
                    config_store[name] = mod.config() if callable(mod.config) else mod.config

            except: pass

        return config_store

    def reload ( self ):

        config_store.clear()
        return self.init()

    def set ( self, key: str, value: Any ):
        
        parts = key.split(".")
        current = config_store
    
        for part in parts[:-1]: current = current.setdefault(part, {})

        current[parts[-1]] = value
        return value

    def get ( self, key: str = None, default: Any = None ):
        
        value = config_store

        if key is not None:
            for part in key.split("."):
                if isinstance(value, dict) and part in value: value = value[part]
                else: return self.env.get(key.upper().replace('.', '_'), self.env.get(key, default))

        return value

    def exists ( self, key: str ):

        return self.get(key) is not None

    def mode ( self ):

        return self.env.mode()

    def is_local ( self ):

        return self.env.is_local()

    def is_production ( self ):

        return self.env.is_production()

