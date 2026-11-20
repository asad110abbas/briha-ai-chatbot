from fastapi import Request
from fastapi.responses import JSONResponse

MESSAGES = {
    "AUTH_REQUIRED": "Please log in.",
    "AUTH_INVALID": "Username or password is incorrect.",
    "AUTH_LOCKED": "Too many attempts. Try again in 15 minutes.",
    "FORBIDDEN": "You don't have access to this.",
    "NOT_FOUND": "Not found.",
    "INPUT_INVALID": "Message is empty or too long.",
    "RATE_LIMITED": "Too many questions. Please wait a minute.",
    "PASSWORD_WEAK": "Password must be at least 8 characters and different from the username.",
    "USERNAME_TAKEN": "This username already exists.",
    "ALIAS_EXISTS": "This alias already exists.",
    "ORIGIN_INVALID": "Request origin not allowed.",
    "INTERNAL": "Something went wrong.",
}


class ApiError(Exception):
    def __init__(self, code: str, status: int, message: str | None = None):
        self.code = code
        self.status = status
        self.message = message or MESSAGES.get(code, code)


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)
