import logging
import jwt
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings
from app.db.session import SessionLocal
from app.services.audit_logger import ImmutableAuditLogger

logger = logging.getLogger("api_audit_middleware")

class AuditLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Intercepts mutating HTTP requests, extracts compliance metrics (such as operator ID,
        client IP, and request details), and writes an entry into the cryptographic audit trail.
        """
        method = request.method
        path = request.url.path

        # Only audit mutating actions (POST, PUT, DELETE, PATCH)
        # Avoid auditing the authentication endpoints directly through middleware to prevent double logging
        is_mutating = method in ["POST", "PUT", "DELETE", "PATCH"]
        is_auth = "/auth/" in path
        is_verify = "/audit/verify" in path

        if not (is_mutating and not is_auth and not is_verify):
            return await call_next(request)

        # Extract operator identity from stateless JWT Bearer Token
        auth_header = request.headers.get("Authorization")
        performed_by = "anonymous"
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = jwt.decode(
                    token,
                    settings.JWT_SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM]
                )
                performed_by = payload.get("sub", "anonymous")
            except Exception:
                pass

        # Resolve client IP address
        ip_address = request.client.host if request.client else "unknown"

        # Determine action type based on endpoint path conventions
        action_type = "API_MUTATION"
        comments = f"Executed API mutation {method} {path}"
        table_name = None

        if "/statements" in path or "/upload" in path:
            action_type = "STATEMENT_UPLOAD"
            comments = "Uploaded transaction statement sheet via API"
            table_name = "raw_transactions"
        elif "/reconciliation/run" in path:
            action_type = "RECONCILIATION_RUN"
            comments = "Initiated automated multi-engine settlement run"
            table_name = "match_results"
        elif "/exceptions" in path:
            action_type = "EXCEPTION_RESOLVE"
            comments = f"Modified exception queue entry via API"
            table_name = "exceptions"
        elif "/config" in path:
            action_type = "CONFIG_UPDATE"
            comments = f"Updated matching parameters or tolerance thresholds"
            table_name = "bank_configs"

        # Execute request downstream to let the action complete
        try:
            response = await call_next(request)
            
            # Log action only if the API call succeeded (returns a 2xx or 3xx status)
            if 200 <= response.status_code < 400:
                db = SessionLocal()
                try:
                    ImmutableAuditLogger.log_action(
                        db=db,
                        action=action_type,
                        performed_by=performed_by,
                        table_name=table_name,
                        ip_address=ip_address,
                        comments=f"{comments} | Status: {response.status_code}"
                    )
                    logger.info(f"Compliance audit logged: {action_type} by user {performed_by}")
                except Exception as db_err:
                    logger.error(f"Failed to log cryptographic audit entry in middleware: {db_err}")
                finally:
                    db.close()
                    
            return response
        except Exception as e:
            # Re-raise exceptions to let global handlers catch them
            raise e
