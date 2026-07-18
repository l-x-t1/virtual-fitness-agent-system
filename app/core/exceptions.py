class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "BAD_REQUEST", details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or []


class AuthenticationError(AppError):
    def __init__(self, message: str = "登录状态无效或已过期"):
        super().__init__(message, 401, "AUTHENTICATION_ERROR")


class PermissionDenied(AppError):
    def __init__(self, message: str = "需要管理员权限"):
        super().__init__(message, 403, "PERMISSION_DENIED")
