from pydantic import BaseModel
from datetime import datetime

class MatchTypeBreakdown(BaseModel):
    exact: int
    rule_based: int
    fuzzy: int
    manual: int

class SourceSystemSummary(BaseModel):
    total_count: int
    matched_count: int
    unmatched_count: int
    exception_count: int
    match_rate: float

class ReconciliationReportResponse(BaseModel):
    generated_at: datetime
    total_bank_transactions: int
    total_ledger_transactions: int
    match_rate: float
    breakdown_by_type: MatchTypeBreakdown
    bank_summary: SourceSystemSummary
    ledger_summary: SourceSystemSummary
    total_unresolved_exceptions: int
