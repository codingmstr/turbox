from fastapi import HTTPException

def dependency(permission: str = None):
    allowed = ["view_users", "edit_posts", "manage_admins"]
    if permission not in allowed:
        raise HTTPException(status_code = 403, detail = f"Permission denied: {permission}")
    return True
