from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == "ADMIN"


class IsReceptionistOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ("ADMIN", "RECEPTIONIST")


class AdminDeleteOnly(BasePermission):
    """DELETE — admin only. All other methods — receptionist or admin."""
    def has_permission(self, request, view):
        if request.method == "DELETE":
            return request.user and request.user.is_authenticated and request.user.role == "ADMIN"
        return request.user and request.user.is_authenticated and request.user.role in ("ADMIN", "RECEPTIONIST")


class ReceptionistViewOnly(BasePermission):
    """GET — receptionist or admin. All other methods — admin only."""
    def has_permission(self, request, view):
        if request.method == "GET":
            return request.user and request.user.is_authenticated and request.user.role in ("ADMIN", "RECEPTIONIST")
        return request.user and request.user.is_authenticated and request.user.role == "ADMIN"
