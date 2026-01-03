"""Create user_states table (idempotent for existing deployments)."""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_user_states"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_states (
            user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            step VARCHAR(128) NOT NULL DEFAULT 'none',
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            locked_until TIMESTAMPTZ NULL,
            lock_reason VARCHAR(255) NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_states_step ON user_states(step);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_states_updated_at ON user_states(updated_at);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_states CASCADE;")
