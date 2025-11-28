from typing import Callable
import turbox, os

class Utils:
    
    @staticmethod
    def test ():

        print(turbox.Request())
        print(turbox.Response())
        print(turbox.Route())
        print(turbox.Server())

class Route:

    _router = turbox.Route()

    @staticmethod
    def add ( method: str, path: str, handler: Callable ):

        Route._router.add(method, path, handler)
        return Route

    @staticmethod
    def get ( path: str, handler: Callable ):

        return Route.add("GET", path, handler)

    @staticmethod
    def post ( path: str, handler: Callable ):

        return Route.add("POST", path, handler)

    @staticmethod
    def put ( path: str, handler: Callable ):

        return Route.add("PUT", path, handler)

    @staticmethod
    def delete ( path: str, handler: Callable ):

        return Route.add("DELETE", path, handler)

    @staticmethod
    def patch ( path: str, handler: Callable ):

        return Route.add("PATCH", path, handler)

    @staticmethod
    def options ( path: str, handler: Callable ):

        return Route.add("OPTIONS", path, handler)

class Server:

    _server               = turbox.Server()
    _host: str            = '127.0.0.1'
    _port: int            = 8000
    _workers: int         = os.cpu_count() or 1
    _keep_alive: bool     = True
    _backlog: int         = 16384
    _max_connections: int = 100_000

    @staticmethod
    def bind ( host: str, port: int ):

        Server._host = host
        Server._port = port

        return Server

    @staticmethod
    def workers ( count: int ):

        Server._workers = count
        return Server

    @staticmethod
    def config ( max_connections: int = 100_000, backlog: int = 16384, keep_alive: bool = True ):

        Server._max_connections = max_connections
        Server._backlog = backlog
        Server._keep_alive = keep_alive

        return Server

    @staticmethod
    def run ():

        Server._server.bind(Server._host, Server._port)
        Server._server.workers(Server._workers)
        Server._server.config(Server._max_connections, Server._backlog, Server._keep_alive)
        Server._server.run()
