from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Backward-compatible alias for older middleware and seed scripts.
SessionLocal = async_session_maker

_BOOTSTRAP_COLUMNS: dict[str, dict[str, str]] = {
    "users": {
        "username": "VARCHAR(64)",
        "payment_method": "VARCHAR",
        "voice_mode": "VARCHAR(20) DEFAULT 'none' NOT NULL",
        "bonus_questions_used": "INTEGER DEFAULT 0 NOT NULL",
        "referral_code": "VARCHAR(64)",
        "referred_by_telegram_id": "BIGINT",
        "start_date": "TIMESTAMP WITH TIME ZONE",
        "end_date": "TIMESTAMP WITH TIME ZONE",
        "discount_offer_started_at": "TIMESTAMP WITH TIME ZONE",
        "discount_referral_count": "INTEGER DEFAULT 0 NOT NULL",
        "discount_eligible": "BOOLEAN DEFAULT false NOT NULL",
        "discount_used": "BOOLEAN DEFAULT false NOT NULL",
        "referral_trial_count_started_at": "TIMESTAMP WITH TIME ZONE",
        "referral_trial_progress_chat_id": "BIGINT",
        "referral_trial_progress_message_id": "BIGINT",
        "last_limit_reset_at": "TIMESTAMP WITH TIME ZONE",
        "daily_limit_offer_sent_at": "TIMESTAMP WITH TIME ZONE",
        "discount_progress_chat_id": "BIGINT",
        "discount_progress_message_id": "BIGINT",
        "selected_plan_type": "VARCHAR(32)",
        "pending_checkout_msg_id": "INTEGER",
        "expiry_reminder_sent_at": "TIMESTAMP WITH TIME ZONE",
        "course_promo_sent": "BOOLEAN DEFAULT false NOT NULL",
    },
    "payments": {
        "checkout_msg_id": "INTEGER",
        "screenshot_msg_id": "INTEGER",
        "waiting_msg_id": "INTEGER",
        "payment_method": "VARCHAR(16)",
        "base_amount": "INTEGER",
        "discount_source": "VARCHAR(32) DEFAULT 'none' NOT NULL",
        "discount_percent": "INTEGER DEFAULT 0 NOT NULL",
        "discount_campaign_id": "INTEGER",
        "discount_title": "VARCHAR(120)",
        "discount_details": "TEXT",
    },
    "discount_campaigns": {
        "title_tj": "VARCHAR(180)",
        "title_ru": "VARCHAR(180)",
        "title_uz": "VARCHAR(180)",
        "reason": "VARCHAR(500)",
        "reason_tj": "VARCHAR(700)",
        "reason_ru": "VARCHAR(700)",
        "reason_uz": "VARCHAR(700)",
        "target_telegram_id": "BIGINT",
        "notify_enabled": "BOOLEAN DEFAULT false NOT NULL",
        "notify_media_type": "VARCHAR(16)",
        "notify_media_file_id": "VARCHAR(512)",
        "notification_sent_at": "TIMESTAMP WITH TIME ZONE",
        "notification_sent_count": "INTEGER DEFAULT 0 NOT NULL",
        "notification_failed_count": "INTEGER DEFAULT 0 NOT NULL",
    },
    "bot_feedbacks": {
        "price_offer_due_at": "TIMESTAMP WITH TIME ZONE",
        "price_offer_sent_at": "TIMESTAMP WITH TIME ZONE",
        "price_offer_used_at": "TIMESTAMP WITH TIME ZONE",
        "disliked_attachment_file_id": "VARCHAR(256)",
        "disliked_attachment_type": "VARCHAR(16)",
        "admin_reply_text": "TEXT",
        "admin_replied_by": "BIGINT",
        "admin_replied_at": "TIMESTAMP WITH TIME ZONE",
    },
    "ai_usage_budgets": {
        "payment_id": "INTEGER",
        "plan_type": "VARCHAR(32) DEFAULT '1_month' NOT NULL",
        "amount": "INTEGER DEFAULT 0 NOT NULL",
        "currency": "VARCHAR(16) DEFAULT 'somoni' NOT NULL",
        "total_budget_usd": "DOUBLE PRECISION DEFAULT 0 NOT NULL",
        "segment_1_budget_usd": "DOUBLE PRECISION DEFAULT 0 NOT NULL",
        "segment_2_budget_usd": "DOUBLE PRECISION DEFAULT 0 NOT NULL",
        "segment_1_spent_usd": "DOUBLE PRECISION DEFAULT 0 NOT NULL",
        "segment_2_spent_usd": "DOUBLE PRECISION DEFAULT 0 NOT NULL",
        "current_window_spent_usd": "DOUBLE PRECISION DEFAULT 0 NOT NULL",
        "window_started_at": "TIMESTAMP WITH TIME ZONE",
        "cooldown_until": "TIMESTAMP WITH TIME ZONE",
        "starts_at": "TIMESTAMP WITH TIME ZONE",
        "ends_at": "TIMESTAMP WITH TIME ZONE",
        "status": "VARCHAR(16) DEFAULT 'active' NOT NULL",
        "created_at": "TIMESTAMP WITH TIME ZONE",
        "updated_at": "TIMESTAMP WITH TIME ZONE",
    },
    "ai_usage_events": {
        "budget_id": "INTEGER",
        "user_telegram_id": "BIGINT DEFAULT 0 NOT NULL",
        "source": "VARCHAR(32) DEFAULT 'unknown' NOT NULL",
        "model": "VARCHAR(80) DEFAULT 'unknown' NOT NULL",
        "prompt_tokens": "INTEGER DEFAULT 0 NOT NULL",
        "completion_tokens": "INTEGER DEFAULT 0 NOT NULL",
        "total_tokens": "INTEGER DEFAULT 0 NOT NULL",
        "cost_usd": "DOUBLE PRECISION DEFAULT 0 NOT NULL",
        "created_at": "TIMESTAMP WITH TIME ZONE",
    },
    "portfolio_transactions": {
        "transaction_type": "VARCHAR(16) DEFAULT 'expense' NOT NULL",
        "source": "VARCHAR(40) DEFAULT 'manual_expense' NOT NULL",
        "amount_usd": "DOUBLE PRECISION DEFAULT 0 NOT NULL",
        "original_amount": "DOUBLE PRECISION",
        "original_currency": "VARCHAR(16)",
        "payment_id": "INTEGER",
        "user_telegram_id": "BIGINT",
        "admin_telegram_id": "BIGINT",
        "note": "TEXT",
        "created_at": "TIMESTAMP WITH TIME ZONE",
    },
    "partners": {
        "signup_bonus_granted_at": "TIMESTAMP WITH TIME ZONE",
    },
    "partner_payouts": {
        "recipient_qr_code_file_id": "VARCHAR(512)",
        "local_currency": "VARCHAR(8) DEFAULT 'TJS' NOT NULL",
        "processing_by_telegram_id": "BIGINT",
        "processing_started_at": "TIMESTAMP WITH TIME ZONE",
    },
}


async def _has_table(conn, table_name: str) -> bool:
    return await conn.run_sync(
        lambda sync_conn, table_name=table_name: inspect(sync_conn).has_table(table_name)
    )


async def _ensure_bootstrap_columns(conn) -> None:
    # Alembic owns schema creation. These patches only keep older Railway
    # schemas bootable if they were created before all migrations existed.
    for table_name, columns in _BOOTSTRAP_COLUMNS.items():
        if not await _has_table(conn, table_name):
            continue
        existing_columns = await conn.run_sync(
            lambda sync_conn, table_name=table_name: {
                column["name"]
                for column in inspect(sync_conn).get_columns(table_name)
            }
        )
        for column_name, column_type in columns.items():
            if column_name in existing_columns:
                continue
            try:
                await conn.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                )
            except ProgrammingError as exc:
                if "already exists" not in str(exc).lower():
                    raise


async def _ensure_bootstrap_indexes(conn) -> None:
    if not await _has_table(conn, "partner_payouts"):
        return
    await conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_partner_payouts_one_open_per_partner
            ON partner_payouts (partner_id)
            WHERE status IN ('pending', 'deadline_set', 'processing')
            """
        )
    )


async def init_db():
    async with engine.begin() as conn:
        await _ensure_bootstrap_columns(conn)
        await _ensure_bootstrap_indexes(conn)
