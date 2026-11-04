from starlette.responses import JSONResponse


class BodyLimitExceeded(Exception):
    pass


class LocalRequestGuard:
    """Local development boundary; this is not an authentication system."""

    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode()
        allowed = {
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        }
        if scope["method"] not in ("GET", "HEAD", "OPTIONS") and origin and origin not in allowed:
            response = JSONResponse(
                {
                    "detail": {
                        "code": "ORIGIN_DENIED",
                        "message": "Cross-origin writes are disabled.",
                    }
                },
                403,
            )
            return await response(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                raise BodyLimitExceeded
            return message

        length = headers.get(b"content-length", b"0")
        if length.isdigit() and int(length) > self.max_bytes:
            response = JSONResponse(
                {
                    "detail": {
                        "code": "UPLOAD_TOO_LARGE",
                        "message": "Request exceeds the size limit.",
                    }
                },
                413,
            )
            return await response(scope, receive, send)
        try:
            return await self.app(scope, bounded_receive, send)
        except BodyLimitExceeded:
            response = JSONResponse(
                {
                    "detail": {
                        "code": "UPLOAD_TOO_LARGE",
                        "message": "Request exceeds the size limit.",
                    }
                },
                413,
            )
            return await response(scope, receive, send)
