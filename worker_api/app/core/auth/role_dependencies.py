"""
Role-based FastAPI dependencies for JWT role claims.

Provides RoleChecker dependency class and convenience shortcuts
(require_super_admin, require_admin, require_end_user) that validate
the JWT ``role`` claim and load the corresponding entity from the DB.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.auth.jwt import verify_token
from app.core.database import get_db
from app.models.admin_users import AdminUser
from app.models.admins import Admin

_bearer_scheme = HTTPBearer()


class RoleChecker:
    """Dependency that validates JWT role claim and returns the appropriate user."""

    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
        db: Session = Depends(get_db),
    ) -> dict:
        payload = verify_token(credentials.credentials)

        role: str | None = payload.get("role")
        if role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' not authorized",
            )

        user_id: int | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: missing 'sub'",
            )
        user_id = int(user_id)

        if role in ("super_admin", "admin"):
            admin = db.query(Admin).filter(Admin.id == user_id).first()
            if not admin:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Admin not found",
                )
            if admin.status != "active" and role != "super_admin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Account is {admin.status}",
                )
            return {"id": admin.id, "role": role, "entity": admin}

        if role == "end_user":
            user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                )
            if user.status != "active":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Account is {user.status}",
                )
            return {
                "id": user.id,
                "role": role,
                "entity": user,
                "admin_id": user.admin_id,
            }

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid role",
        )


# Convenience dependencies for use in route handlers:
#
#   @router.get("/admin-only")
#   def admin_route(current=Depends(require_admin)): ...
#
#   @router.get("/any-auth")
#   def any_auth(current=Depends(require_super_admin | require_admin)):  # NOT valid syntax
#       # For multiple roles, use RoleChecker(["super_admin", "admin"]) directly.
#
require_super_admin = RoleChecker(["super_admin"])
require_admin = RoleChecker(["admin"])
require_end_user = RoleChecker(["end_user"])
