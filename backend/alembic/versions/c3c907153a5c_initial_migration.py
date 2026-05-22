"""Initial database migration for multi-bank reconciliation engine

Revision ID: c3c907153a5c
Revises: None
Create Date: 2026-05-21 19:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3c907153a5c'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), server_default='analyst', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index('idx_users_username', 'users', ['username'])

    # 2. Create bank_configurations table
    op.create_table(
        'bank_configurations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_name', sa.String(length=100), nullable=False),
        sa.Column('account_number', sa.String(length=50), nullable=False),
        sa.Column('statement_format', sa.String(length=10), nullable=False),
        sa.Column('parser_rules', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_number')
    )
    op.create_index(op.f('ix_bank_configurations_account_number'), 'bank_configurations', ['account_number'], unique=True)
    op.create_index(op.f('ix_bank_configurations_id'), 'bank_configurations', ['id'], unique=False)

    # 3. Create raw_transactions table
    op.create_table(
        'raw_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_config_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('raw_payload', sa.JSON(), nullable=False),
        sa.Column('ingested_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='STAGED', nullable=False),
        sa.ForeignKeyConstraint(['bank_config_id'], ['bank_configurations.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_raw_transactions_id'), 'raw_transactions', ['id'], unique=False)
    op.create_index('idx_raw_tx_config', 'raw_transactions', ['bank_config_id'], unique=False)
    # GIN index on raw_transactions.raw_payload (for PostgreSQL JSONB)
    op.execute("CREATE INDEX idx_raw_tx_payload_gin ON raw_transactions USING GIN(raw_payload)")

    # 4. Create match_results table
    op.create_table(
        'match_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('match_type', sa.String(length=20), nullable=False),
        sa.Column('matched_at', sa.DateTime(), nullable=False),
        sa.Column('matching_rules_applied', sa.Text(), nullable=True),
        sa.Column('similarity_score', sa.Float(), nullable=False),
        sa.Column('resolved_by', sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_match_results_id'), 'match_results', ['id'], unique=False)
    op.create_index(op.f('ix_match_results_match_type'), 'match_results', ['match_type'], unique=False)

    # 5. Create normalized_transactions table
    op.create_table(
        'normalized_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('raw_tx_id', sa.Integer(), nullable=True),
        sa.Column('bank_config_id', sa.Integer(), nullable=False),
        sa.Column('source_system', sa.String(length=20), nullable=False),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('value_date', sa.Date(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='USD', nullable=False),
        sa.Column('reference', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('bank_account', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='UNMATCHED', nullable=False),
        sa.Column('match_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['bank_config_id'], ['bank_configurations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['match_id'], ['match_results.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['raw_tx_id'], ['raw_transactions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_normalized_transactions_id'), 'normalized_transactions', ['id'], unique=False)
    op.create_index(op.f('ix_normalized_transactions_amount'), 'normalized_transactions', ['amount'], unique=False)
    op.create_index(op.f('ix_normalized_transactions_bank_account'), 'normalized_transactions', ['bank_account'], unique=False)
    op.create_index(op.f('ix_normalized_transactions_reference'), 'normalized_transactions', ['reference'], unique=False)
    op.create_index(op.f('ix_normalized_transactions_source_system'), 'normalized_transactions', ['source_system'], unique=False)
    op.create_index(op.f('ix_normalized_transactions_status'), 'normalized_transactions', ['status'], unique=False)
    op.create_index(op.f('ix_normalized_transactions_transaction_date'), 'normalized_transactions', ['transaction_date'], unique=False)
    
    # Specialized indices for performance optimization
    op.execute("CREATE INDEX idx_norm_tx_recon_matching ON normalized_transactions(bank_account, currency, abs(amount), status, transaction_date)")
    op.execute("CREATE INDEX idx_norm_tx_upper_reference ON normalized_transactions(UPPER(reference)) WHERE reference IS NOT NULL")
    
    # Foreign keys standard indexing
    op.create_index('idx_norm_tx_raw', 'normalized_transactions', ['raw_tx_id'], unique=False)
    op.create_index('idx_norm_tx_config', 'normalized_transactions', ['bank_config_id'], unique=False)
    op.create_index('idx_norm_tx_match', 'normalized_transactions', ['match_id'], unique=False)

    # 6. Create exceptions table
    op.create_table(
        'exceptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaction_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='OPEN', nullable=False),
        sa.Column('error_type', sa.String(length=50), nullable=False),
        sa.Column('resolution_action', sa.String(length=20), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', sa.String(length=50), nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['transaction_id'], ['normalized_transactions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exceptions_error_type'), 'exceptions', ['error_type'], unique=False)
    op.create_index(op.f('ix_exceptions_id'), 'exceptions', ['id'], unique=False)
    op.create_index(op.f('ix_exceptions_status'), 'exceptions', ['status'], unique=False)
    op.create_index('idx_exceptions_tx', 'exceptions', ['transaction_id'], unique=False)
    op.create_index('idx_exceptions_status_open', 'exceptions', ['status'], postgresql_where=sa.text("status = 'OPEN'"))

    # 7. Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('table_name', sa.String(length=50), nullable=True),
        sa.Column('record_id', sa.Integer(), nullable=True),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('performed_by', sa.String(length=50), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_audit_logs_performed_by'), 'audit_logs', ['performed_by'], unique=False)
    op.create_index(op.f('ix_audit_logs_table_name'), 'audit_logs', ['table_name'], unique=False)
    op.create_index('idx_audit_logs_time', 'audit_logs', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('exceptions')
    op.drop_table('normalized_transactions')
    op.drop_table('match_results')
    op.drop_table('raw_transactions')
    op.drop_table('bank_configurations')
    op.drop_table('users')
