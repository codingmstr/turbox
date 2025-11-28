from core import Route, Server, Utils

def index ( req ):
    # Utils.test()
    return "ok"

Route.get("/", index)
Server.run()
