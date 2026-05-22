import logging
import os
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.config import settings
from app.models.user import User
from app.security import get_password_hash, verify_password, create_access_token

logger = logging.getLogger("auth_service")

class AuthService:
    """
    Enterprise-grade security service encapsulating credentials validation,
    session JWT generation, user registration, and environment secret auditing.
    """

    @staticmethod
    def validate_environment_secrets() -> Dict[str, Any]:
        """
        Audits active environment configuration credentials for safety.
        Warns if cryptographic secrets are default or possess insufficient entropy.
        """
        warnings = []
        is_secure = True

        # 1. Audit JWT Secret Key
        secret = settings.JWT_SECRET_KEY
        if not secret:
            is_secure = False
            warnings.append("CRITICAL: JWT_SECRET_KEY environment secret is missing entirely!")
        elif len(secret) < 32:
            is_secure = False
            warnings.append("WARNING: JWT_SECRET_KEY has insufficient entropy (< 256 bits).")
        elif secret == "949f1db8dfde7b864a7cd254c6001d9f828a2a8b94154425712adcd5b36440c9":
            warnings.append("NOTICE: JWT_SECRET_KEY is using the local development default value.")

        # 2. Audit Database Password Strength
        db_pass = settings.POSTGRES_PASSWORD
        if db_pass == "postgres_secure_pass" or db_pass == "postgres":
            warnings.append("NOTICE: POSTGRES_PASSWORD is using common development defaults.")

        # Log audit report summary
        if warnings:
            logger.warning("🔒 SECURITY AUDIT REPORT DETECTED THE FOLLOWING ISSUES:")
            for warn in warnings:
                logger.warning(f"  ├── {warn}")
        else:
            logger.info("🔒 SECURITY AUDIT REPORT: Environment configuration is secure.")

        return {
            "is_secure": is_secure,
            "warnings_count": len(warnings),
            "details": warnings
        }

    @classmethod
    def register_new_user(cls, db: Session, username: str, password_raw: str, role: str) -> User:
        """Registers a new system operator, hashing passwords with secure bcrypt parameters."""
        # Enforce uppercase/lowercase formatting for roles to keep consistency
        valid_roles = ["viewer", "analyst", "admin", "system"]
        target_role = str(role).lower().strip()
        if target_role not in valid_roles:
            raise ValueError(f"Invalid user role: '{role}'. Permitted: {valid_roles}")

        hashed_pass = get_password_hash(password_raw)
        
        user = User(
            username=username.strip(),
            hashed_password=hashed_pass,
            role=target_role,
            is_active=True
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
