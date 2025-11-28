
class ApiError(Exception):

    def __init__ ( self, message: str = None, response = None ):

        self.response = response
        self.status   = response.code()      if response else None
        self.body     = response.text()      if response else None
        self.headers  = response.headers()   if response else None
        self.url      = response.url()       if response else None

        super().__init__(message or self.default_message)

    @property
    def default_message ( self ):
        return self.__class__.__name__

class AuthError(ApiError):
    default_message = "Unauthorized"

class TokenExpiredError(AuthError):
    default_message = "Token expired"

class PermissionDeniedError(AuthError):
    default_message = "Permission denied"

class NotFoundError(ApiError):
    default_message = "Resource not found"

class MethodNotAllowedError(ApiError): 

    default_message = "HTTP method not allowed"

class MissingParameterError(ApiError):
    default_message = "Missing parameter"

class RateLimitError(ApiError):
    default_message = "Rate limit exceeded"

class ServerError(ApiError):
    default_message = "Server error"

class GatewayError(ApiError):
    default_message = "Bad gateway response"

class ValidationError(ApiError):
    default_message = "Validation failed"

class ParsingError(ApiError):
    default_message = "Failed to parse response"

class NetworkError(ApiError):
    default_message = "Network communication failure"

class CircuitBreakerError(ApiError):
    default_message = "The circuit breaker limit has been exceeded"

class DependenciesFailedError(ApiError):
    default_message = "Dependencies failed"

class DependenciesRuntimeError(ApiError):
    default_message = "Dependencies runtime error occurred"

class UnexpectedError(ApiError):
    default_message = "Unexpected error occurred"
