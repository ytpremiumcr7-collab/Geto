"""Auth package — import submodules explicitly to avoid heavy side effects."""

from app.auth.models import Principal

__all__ = ["Principal"]
