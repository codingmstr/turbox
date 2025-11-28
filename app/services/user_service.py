# services/user_service.py
class UserService:
    async def list_users (self):
        return ["Alice", "Bob", "Charlie"]

    async def create_user (self, data):
        return { "id": 1, "name": data.get("name") }
