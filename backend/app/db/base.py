from typing import Any
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    id: Any
    __name__: str

    # Automatically generate __tablename__ based on class names
    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

# Register all models here so they load with Base.metadata
from app.models.user import User
from app.models.bank_config import BankConfiguration
from app.models.raw_transaction import RawTransaction
from app.models.transaction import NormalizedTransaction
from app.models.match import MatchResult
from app.models.exception import ExceptionQueue
from app.models.audit import AuditLog


