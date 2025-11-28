from fastapi import FastAPI
import uvicorn, asyncio
from core.support.utils import *
from core.routing import route

def create_app ():

    config.init()

    app = FastAPI(
        title       = config.get("app.name"),
        version     = '1.0.0',
        description = config.get("app.description"),
        # docs_url    = module.find('docs'),
        # redoc_url   = module.find('redoc'),
    )

    asyncio.gather(
        route.init(app),
    )

    return app

def run ():

    uvicorn.run(
        "main:app",
        host=config.get("app.host", "127.0.0.1"),
        port=int(config.get("app.port", 8000)),
        reload=config.is_local()
    )
