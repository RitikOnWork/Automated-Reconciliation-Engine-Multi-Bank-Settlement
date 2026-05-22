import logging
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Configure basic console logger matching standard layouts
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("api_request_logger")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Intercepts incoming HTTP requests, logs details, 
        calculates execution overhead, and writes standard status code summaries.
        """
        start_time = time.perf_counter()
        
        # Log request ingestion details
        client_host = request.client.host if request.client else "unknown"
        logger.info(f"--> Inbound request: {request.method} {request.url.path} (Client: {client_host})")
        
        try:
            response = await call_next(request)
            
            process_time = (time.perf_counter() - start_time) * 1000
            
            logger.info(
                f"<-- Outbound response: {request.method} {request.url.path} "
                f"Status: {response.status_code} | Duration: {process_time:.2f}ms"
            )
            
            # Append timing metric as an HTTP Header for performance reviews
            response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
            return response
            
        except Exception as e:
            process_time = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"### Request Failure: {request.method} {request.url.path} "
                f"Error: {str(e)} | Duration: {process_time:.2f}ms"
            )
            raise e
