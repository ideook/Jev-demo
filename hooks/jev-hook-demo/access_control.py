"""Synthetic access policy used only for the Jev hook experiment."""


def can_read(role: str, user_id: str, owner_id: str, authenticated: bool) -> bool:
    if not authenticated:
        return False
    if role == "admin":
        return True
    return role == "employee" and user_id == owner_id
