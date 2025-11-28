import os, functools, inspect

class Handler:

    @staticmethod
    def folder_handler ( func, self, *args, **kwargs ):

        bound = inspect.signature(func).bind_partial(self, *args, **kwargs)
        bound.apply_defaults()

        path = bound.arguments.get("path") or bound.arguments.get("folder") or bound.arguments.get("local_path")

        if path:

            abs_path = os.path.abspath(str(path or '.'))

            if not os.path.exists(abs_path): os.makedirs(abs_path, exist_ok=True)
            if not os.path.isdir(abs_path): raise FileNotFoundError(f"Invalid dir path: {abs_path}")

            for key in ("path", "folder", "local_path"):
                if key in bound.arguments: bound.arguments[key] = abs_path

        return func(self, *bound.args, **bound.kwargs)

    @staticmethod
    def file_handler ( func, self, *args, **kwargs ):

        bound = inspect.signature(func).bind_partial(self, *args, **kwargs)
        bound.apply_defaults()

        path = bound.arguments.get("path") or bound.arguments.get("file") or bound.arguments.get("local_path")

        if path:

            abs_path = os.path.abspath(str(path or '.'))

            if not os.path.exists(os.path.dirname(abs_path)): os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            if not os.path.exists(abs_path): open(abs_path, 'w').close()
            if not os.path.isfile(abs_path): raise FileNotFoundError(f"Invalid file path: {abs_path}")

            for key in ("path", "file", "local_path"):
                if key in bound.arguments: bound.arguments[key] = abs_path

        return func(self, *bound.args, **bound.kwargs)

    @staticmethod
    def handle ( func, type: str ):

        @functools.wraps(func)
        def wrapper ( self, *args, **kwargs ):

            if getattr(func, "_skipped_handler", False): return func(self, *args, **kwargs)

            if type == 'folder': return Handler.folder_handler(func, self, *args, **kwargs)
            else: return Handler.file_handler(func, self, *args, **kwargs)

        return wrapper

    @staticmethod
    def skip ( func ):

        func._skipped_handler = True
        return func

    @staticmethod
    def wrap ( cls, cls_type: str ):

        for attr_name, attr_value in vars(cls).items():
            if callable(attr_value) and not str(attr_name).startswith("__"):
                if isinstance(attr_value, staticmethod): setattr(cls, attr_name, staticmethod(Handler.handle(attr_value.__func__, cls_type)))
                elif isinstance(attr_value, classmethod): setattr(cls, attr_name, classmethod(Handler.handle(attr_value.__func__, cls_type)))
                else: setattr(cls, attr_name, Handler.handle(attr_value, cls_type))

        return cls

    @staticmethod
    def folder ( cls ):

        return Handler.wrap(cls, 'folder')
    
    @staticmethod
    def file ( cls ):

        return Handler.wrap(cls, 'file')
