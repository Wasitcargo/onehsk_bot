"""create course tables

Revision ID: 0010a_create_course_tables
Revises: 0010
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0010a_create_course_tables"
down_revision = "0010"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("course_lessons"):
        op.create_table(
            "course_lessons",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("level", sa.String(length=32), nullable=False),
            sa.Column("lesson_order", sa.Integer(), nullable=False),
            sa.Column("lesson_code", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("goal", sa.Text(), nullable=False, server_default=""),
            sa.Column("intro_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("vocabulary_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("dialogue_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("grammar_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("exercise_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("answers_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("homework_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("review_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("lesson_code", name="uq_course_lessons_lesson_code"),
        )
        op.create_index("ix_course_lessons_level", "course_lessons", ["level"])
        op.create_index("ix_course_lessons_lesson_order", "course_lessons", ["lesson_order"])
        op.create_index("ix_course_lessons_lesson_code", "course_lessons", ["lesson_code"], unique=True)
        op.create_index("ix_course_lessons_is_active", "course_lessons", ["is_active"])

    if not _has_table("course_progress"):
        op.create_table(
            "course_progress",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("level", sa.String(length=32), nullable=False),
            sa.Column("current_lesson_id", sa.Integer(), nullable=True),
            sa.Column("current_step", sa.String(length=32), nullable=False, server_default="intro"),
            sa.Column("completed_lessons_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reminder_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("reminder_time", sa.Time(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["current_lesson_id"], ["course_lessons.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("user_id", name="uq_course_progress_user_id"),
        )
        op.create_index("ix_course_progress_user_id", "course_progress", ["user_id"], unique=True)
        op.create_index("ix_course_progress_level", "course_progress", ["level"])
        op.create_index("ix_course_progress_current_lesson_id", "course_progress", ["current_lesson_id"])

    if not _has_table("course_attempts"):
        op.create_table(
            "course_attempts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("lesson_id", sa.Integer(), nullable=False),
            sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("answers_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["lesson_id"], ["course_lessons.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_course_attempts_user_id", "course_attempts", ["user_id"])
        op.create_index("ix_course_attempts_lesson_id", "course_attempts", ["lesson_id"])


def downgrade() -> None:
    if _has_table("course_attempts"):
        op.drop_index("ix_course_attempts_lesson_id", table_name="course_attempts")
        op.drop_index("ix_course_attempts_user_id", table_name="course_attempts")
        op.drop_table("course_attempts")

    if _has_table("course_progress"):
        op.drop_index("ix_course_progress_current_lesson_id", table_name="course_progress")
        op.drop_index("ix_course_progress_level", table_name="course_progress")
        op.drop_index("ix_course_progress_user_id", table_name="course_progress")
        op.drop_table("course_progress")

    if _has_table("course_lessons"):
        op.drop_index("ix_course_lessons_is_active", table_name="course_lessons")
        op.drop_index("ix_course_lessons_lesson_code", table_name="course_lessons")
        op.drop_index("ix_course_lessons_lesson_order", table_name="course_lessons")
        op.drop_index("ix_course_lessons_level", table_name="course_lessons")
        op.drop_table("course_lessons")
