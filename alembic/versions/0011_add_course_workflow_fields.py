"""add course workflow fields

Revision ID: 0011_add_course_workflow_fields
Revises: 0010_add_expiry_reminder_sent_at_to_users
Create Date: 2026-04-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_add_course_workflow_fields"
down_revision = "0010a_create_course_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "course_progress",
        sa.Column("waiting_for", sa.String(length=50), nullable=False, server_default="none"),
    )
    op.add_column(
        "course_progress",
        sa.Column("last_completed_lesson_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "course_progress",
        sa.Column("needs_review_prompt", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "course_progress",
        sa.Column("homework_status", sa.String(length=30), nullable=False, server_default="none"),
    )
    op.add_column(
        "course_progress",
        sa.Column("next_study_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_foreign_key(
        "fk_course_progress_last_completed_lesson_id",
        "course_progress",
        "course_lessons",
        ["last_completed_lesson_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "course_attempts",
        sa.Column("attempt_type", sa.String(length=30), nullable=False, server_default="quiz"),
    )
    op.add_column(
        "course_attempts",
        sa.Column("step_name", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "course_attempts",
        sa.Column("ai_feedback", sa.Text(), nullable=True),
    )

    op.alter_column("course_progress", "waiting_for", server_default=None)
    op.alter_column("course_progress", "needs_review_prompt", server_default=None)
    op.alter_column("course_progress", "homework_status", server_default=None)
    op.alter_column("course_attempts", "attempt_type", server_default=None)


def downgrade() -> None:
    op.drop_column("course_attempts", "ai_feedback")
    op.drop_column("course_attempts", "step_name")
    op.drop_column("course_attempts", "attempt_type")

    op.drop_constraint(
        "fk_course_progress_last_completed_lesson_id",
        "course_progress",
        type_="foreignkey",
    )
    op.drop_column("course_progress", "next_study_at")
    op.drop_column("course_progress", "homework_status")
    op.drop_column("course_progress", "needs_review_prompt")
    op.drop_column("course_progress", "last_completed_lesson_id")
    op.drop_column("course_progress", "waiting_for")
