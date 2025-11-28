from fastapi.responses import JSONResponse

def ok ( data=None, message="Success" ):
    return JSONResponse(content={
        "success": True,
        "message": message,
        "data": data or {}
    })

def error ( message="Error", code=400 ):
    return JSONResponse(status_code=code, content={
        "success": False,
        "message": message
    })
