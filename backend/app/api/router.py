from fastapi import APIRouter
from app.api.endpoints import auth, transactions, reconciliation, exceptions, audit, secure_demo

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
api_router.include_router(reconciliation.router, prefix="/reconciliation", tags=["reconciliation"])
api_router.include_router(exceptions.router, prefix="/exceptions", tags=["exceptions"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(secure_demo.router, prefix="/secure-demo", tags=["secure-demo"])

