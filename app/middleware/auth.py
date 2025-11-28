from fastapi import HTTPException

def dependency():
    user = {"id": 1, "role": "admin"}
    if not user:
        raise HTTPException(status_code = 401, detail = "Unauthorized")
    return user
