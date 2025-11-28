from fastapi.responses import JSONResponse

class BaseController:

    def index ( self ):
        return JSONResponse({'status': True, 'items': []})

    def store ( self ):
        return JSONResponse({'status': True, 'item': {}})

    def show ( self, id: int ):
        return JSONResponse({'status': True, 'item': {}})

    def update ( self, id: int ):
        return JSONResponse({'status': True, 'item': {}})

    def destroy ( self, id: int ):
        return JSONResponse({'status': True})
