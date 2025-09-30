"""FastAPI dependencies shared across routers."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status


@dataclass
class AuthenticatedUser:
    user_id: str
    realtor_id: str


def get_current_user(
    realtor_id: str | None = Header(default=None, alias="X-Realtor-Id"),
    user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> AuthenticatedUser:
    """Resolve the current user based on custom headers.

    In producción este punto debería validar tokens firmados o sesiones. Por ahora
    requerimos encabezados explícitos para simplificar la integración con el
    microservicio front-end.
    """

    if not realtor_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el encabezado X-Realtor-Id para identificar al asesor",
        )

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el encabezado X-User-Id para identificar al usuario",
        )

    return AuthenticatedUser(user_id=user_id, realtor_id=realtor_id)


AuthenticatedUserDependency = Depends(get_current_user)


__all__ = ["AuthenticatedUser", "AuthenticatedUserDependency", "get_current_user"]
