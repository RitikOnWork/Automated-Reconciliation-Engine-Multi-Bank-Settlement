import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("exception_handling_middleware")


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """
        Catches unhandled application-level exceptions,
        intercepts them, and formats clean, structured JSON envelopes.
        """
        try:
            return await call_next(request)
        except StarletteHTTPException as ex:
            # Handle standard HTTP exceptions (e.g. 404, 401)
            logger.warning(f"HTTP exception caught: {ex.detail} (Status: {ex.status_code})")
            return JSONResponse(
                status_code=ex.status_code,
                content={
                    "success": False,
                    "error": {
                        "code": "HTTP_EXCEPTION",
                        "message": ex.detail,
                        "details": None
                    }
                }
            )
        except Exception as err:
            # Catch-all for unhandled server issues (500)
            logger.critical(f"Unhandled exception caught: {str(err)}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "success": False,
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "An unexpected error occurred on the server.",
                        "details": str(err) if request.app.debug else None
                    }
                }
            )
