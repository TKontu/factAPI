class FactAPIError(Exception):
    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(FactAPIError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, code="NOT_FOUND", status_code=404)


class ValidationError(FactAPIError):
    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message, code="VALIDATION_ERROR", status_code=422)


class AuthenticationError(FactAPIError):
    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(message, code="UNAUTHORIZED", status_code=401)


class ConflictError(FactAPIError):
    def __init__(self, message: str = "Resource already exists") -> None:
        super().__init__(message, code="CONFLICT", status_code=409)
