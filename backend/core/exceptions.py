from fastapi import HTTPException, status


class NotFoundError(HTTPException):
    def __init__(self, detail: str = "Not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ForbiddenError(HTTPException):
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class UnauthorizedError(HTTPException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ConflictError(HTTPException):
    def __init__(self, detail: str = "Conflict"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class ValidationError(HTTPException):
    def __init__(self, detail: str = "Validation error"):
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


class PayloadTooLargeError(HTTPException):
    def __init__(self, detail: str = "Payload too large"):
        super().__init__(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=detail)


class BadRequestError(HTTPException):
    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class RequestTooLargeError(HTTPException):
    """413: the request body passed the configured upload limit."""

    MESSAGE = "Request exceeds the configured size limit."

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"code": "request_too_large", "message": self.MESSAGE},
        )

    @classmethod
    def body(cls, request_id: str | None = None) -> dict:
        return {
            "code": "request_too_large",
            "message": cls.MESSAGE,
            "fieldErrors": {},
            "requestId": request_id,
        }
