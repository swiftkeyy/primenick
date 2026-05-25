from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    user_tier = postgresql.ENUM("free", "vip_500", "vip_1000", "vip_3000", "vip_unlimited", name="user_tier", create_type=False)
    vip_plan_type = postgresql.ENUM("free", "vip_500", "vip_1000", "vip_3000", "vip_unlimited", name="vip_plan_type", create_type=False)
    username_status = postgresql.ENUM("generated", "available", "unavailable", "reserved", "sold", "expired", "locked", name="username_status", create_type=False)
    reservation_status = postgresql.ENUM("active", "expired", "purchased", "cancelled", name="reservation_status", create_type=False)
    payment_status = postgresql.ENUM("pending", "waiting_for_capture", "succeeded", "cancelled", "refunded", "expired", name="payment_status", create_type=False)
    abuse_severity = postgresql.ENUM("low", "medium", "high", "critical", name="abuse_severity", create_type=False)
    ban_scope = postgresql.ENUM("telegram_id", "ip", "fingerprint", "subnet", name="ban_scope", create_type=False)
    ban_severity = postgresql.ENUM("low", "medium", "high", "critical", name="ban_severity", create_type=False)
    for enum in [user_tier, vip_plan_type, username_status, reservation_status, payment_status, abuse_severity, ban_scope, ban_severity]:
        enum.create(op.get_bind(), checkfirst=True)

    op.create_table("users",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64)),
        sa.Column("first_name", sa.String(128)),
        sa.Column("tier", user_tier, server_default="free", nullable=False),
        sa.Column("vip_until", sa.DateTime(timezone=True)),
        sa.Column("is_banned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("quota_frozen", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("require_captcha", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("abuse_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_ip", sa.String(64)),
        sa.Column("last_fingerprint", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("telegram_id"))

    op.create_table("username_assets",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("normalized", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("style", sa.String(32), nullable=False),
        sa.Column("rarity_score", sa.Integer(), nullable=False),
        sa.Column("status", username_status, nullable=False),
        sa.Column("price_rub", sa.Numeric(12, 2)),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("availability_platform", sa.String(24), server_default="telegram", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("length(normalized) between 4 and 32", name="ck_username_assets_username_length_valid"),
        sa.UniqueConstraint("normalized", "availability_platform", name="uq_asset_normalized_platform"))
    op.create_index("ix_username_assets_status_rarity", "username_assets", ["status", "rarity_score"])

    op.create_table("username_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("username_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("normalized", sa.String(32), nullable=False),
        sa.Column("status", reservation_status, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("auto_renew", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("lock_token", sa.String(128), nullable=False),
        sa.Column("price_snapshot_rub", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("normalized", "status", name="uq_active_reservation_normalized_status"))
    op.create_index("ix_reservations_user_status", "username_reservations", ["user_id", "status"])
    op.create_index("ix_reservations_expiry", "username_reservations", ["status", "expires_at"])

    op.create_table("vip_generation_credits",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("credits_total", sa.Integer(), nullable=False),
        sa.Column("credits_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan_type", vip_plan_type, nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("ix_vip_credits_reset", "vip_generation_credits", ["reset_at"])

    op.create_table("generation_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generation_type", sa.String(64), nullable=False),
        sa.Column("credits_spent", sa.Integer(), nullable=False),
        sa.Column("ip", sa.String(64)),
        sa.Column("fingerprint", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("ix_generation_usage_user_created", "generation_usage_logs", ["user_id", "created_at"])
    op.create_index("ix_generation_usage_fp_created", "generation_usage_logs", ["fingerprint", "created_at"])

    op.create_table("payments",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_payment_id", sa.String(128), unique=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("amount_rub", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("confirmation_url", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("ix_payments_user_status", "payments", ["user_id", "status"])

    op.create_table("payment_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("payload_hash", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("provider", "event_id", name="uq_provider_event_id"))

    op.create_table("payment_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("payments.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("ip", sa.String(64)),
        sa.Column("details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))

    op.create_table("availability_checks",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("normalized", sa.String(32), nullable=False),
        sa.Column("platform", sa.String(24), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("available", sa.Boolean()),
        sa.Column("status_code", sa.Integer()),
        sa.Column("proxy_id", sa.String(128)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_class", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("ix_availability_norm_platform_created", "availability_checks", ["normalized", "platform", "created_at"])

    op.create_table("abuse_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger()), sa.Column("user_id", sa.String(64)),
        sa.Column("ip", postgresql.INET()), sa.Column("fingerprint", sa.String(128)),
        sa.Column("event_type", sa.String(96), nullable=False), sa.Column("severity", abuse_severity, nullable=False),
        sa.Column("score_delta", sa.Integer(), nullable=False), sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("ix_abuse_events_tg_created", "abuse_events", ["telegram_id", "created_at"])
    op.create_index("ix_abuse_events_ip_created", "abuse_events", ["ip", "created_at"])
    op.create_index("ix_abuse_events_fp_created", "abuse_events", ["fingerprint", "created_at"])
    op.create_index("ix_abuse_events_type_created", "abuse_events", ["event_type", "created_at"])

    op.create_table("bans",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("scope", ban_scope, nullable=False), sa.Column("value", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("severity", ban_severity, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)), sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("scope", "value", "active", name="uq_active_ban_scope_value"))
    op.create_index("ix_bans_scope_value_active", "bans", ["scope", "value", "active"])

    op.create_table("suspicious_activity",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger()), sa.Column("ip", postgresql.INET()), sa.Column("subnet", postgresql.CIDR()),
        sa.Column("fingerprint", sa.String(128)), sa.Column("activity_type", sa.String(96), nullable=False),
        sa.Column("counter", sa.Integer(), server_default="1", nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.create_index("ix_suspicious_lookup", "suspicious_activity", ["telegram_id", "ip", "fingerprint", "activity_type"])

    op.create_table("audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("actor_user_id", sa.String(64)), sa.Column("telegram_id", sa.BigInteger()), sa.Column("ip", postgresql.INET()),
        sa.Column("fingerprint", sa.String(128)), sa.Column("action", sa.String(96), nullable=False),
        sa.Column("entity_type", sa.String(64)), sa.Column("entity_id", sa.String(64)),
        sa.Column("metadata_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("ix_audit_actor_created", "audit_logs", ["actor_user_id", "created_at"])
    op.create_index("ix_audit_action_created", "audit_logs", ["action", "created_at"])

    op.create_table("rate_limit_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("scope", sa.String(64), nullable=False), sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column("allowed", sa.Integer(), nullable=False), sa.Column("limit_value", sa.Integer(), nullable=False),
        sa.Column("remaining", sa.Integer(), nullable=False), sa.Column("retry_after_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("ix_rate_limit_scope_created", "rate_limit_decisions", ["scope", "created_at"])
    op.create_index("ix_rate_limit_key_created", "rate_limit_decisions", ["key_hash", "created_at"])


def downgrade() -> None:
    for table in ["rate_limit_decisions","audit_logs","suspicious_activity","bans","abuse_events","availability_checks","payment_audit_logs","payment_webhook_events","payments","generation_usage_logs","vip_generation_credits","username_reservations","username_assets","users"]:
        op.drop_table(table)
    for enum in ["ban_severity","ban_scope","abuse_severity","payment_status","reservation_status","username_status","vip_plan_type","user_tier"]:
        postgresql.ENUM(name=enum, create_type=False).drop(op.get_bind(), checkfirst=True)
