import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from starlette.middleware.gzip import GZipMiddleware

from app.config import settings
from app.bot.create_bot import create_bot
from app.db.session import async_session_maker, init_db
from app.services.course_seed_service import CourseSeedService
from app.services.access_service import AccessService
from app.services.daily_reset_service import DailyResetService
from app.services.expiry_reminder_service import ExpiryReminderService
from app.services.course_reminder_service import CourseReminderService
from app.services.bot_feedback_service import BotFeedbackService
from app.services.ad_campaign_service import AdCampaignService
from app.services.discount_notification_service import DiscountNotificationService
from app.services.partner_service import PartnerService
from app.services.app_error_context_service import AppErrorContextService
from app.services.course_miniapp_result_service import CourseMiniAppResultService
from app.services.course_miniapp_lesson_service import CourseMiniAppLessonService
from app.services.study_miniapp_service import StudyMiniAppService
from app.services.telegram_webapp_auth import extract_verified_webapp_user_id
from app.repositories.user_repo import UserRepository
from app.bot.keyboards.main_menu import main_menu_keyboard
from app.bot.keyboards.course import homework_retry_keyboard
from app.bot.keyboards.subscription import payment_method_keyboard
from app.bot.utils.i18n import t
from app.bot.keyboards.course_miniapp import (
    course_homework_done_keyboard,
    course_miniapp_continue_keyboard,
    course_miniapp_understood_keyboard,
)
from app.bot.utils.course_miniapp import (
    format_miniapp_homework_result,
    format_miniapp_quiz_result,
    normalize_miniapp_lang,
)

logger = logging.getLogger(__name__)

bot, dp = create_bot(settings)
_last_feedback_check_at = None
_study_ai_tasks = set()


async def _send_course_access_expired_offer(session, telegram_id: int) -> None:
    user = await UserRepository(session).get_by_telegram_id(telegram_id)
    if not user:
        return

    lang = user.language if user.language else "ru"
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=t("course_only_active_users", lang),
            reply_markup=main_menu_keyboard(lang),
            parse_mode="HTML",
        )
        await bot.send_message(
            chat_id=telegram_id,
            text=t("payment_method_choose", lang),
            reply_markup=payment_method_keyboard(lang),
            parse_mode="HTML",
        )
    except Exception as error:
        logger.warning("Failed to notify expired course user %s: %s", telegram_id, error)


def _track_study_ai_task(task) -> None:
    _study_ai_tasks.add(task)

    def _done(completed_task):
        _study_ai_tasks.discard(completed_task)
        if completed_task.cancelled():
            return
        error = completed_task.exception()
        if error:
            logger.error(
                "Study Mini App QA discussion failed: %s",
                error,
                exc_info=(type(error), error, error.__traceback__),
            )

    task.add_done_callback(_done)


async def _send_study_quiz_ai_discussion(telegram_id: int, payload: dict) -> None:
    async with async_session_maker() as session:
        await StudyMiniAppService(session).send_quiz_ai_discussion(bot, telegram_id, payload)


async def _seed_lessons() -> None:
    """Run all lesson seed scripts in the background after startup."""
    logger.info("=== SEEDING START: loading all lesson scripts ===")
    try:
        async with async_session_maker() as session:
            count = await CourseSeedService(session).sync_all_lessons()
        logger.info(f"=== SEEDING COMPLETE: {count} lessons in DB ===")
    except Exception as e:
        logger.error(f"=== SEEDING ERROR: {e} ===", exc_info=True)


async def _background_scheduler(bot: Bot) -> None:
    global _last_feedback_check_at

    while True:
        await asyncio.sleep(60)
        try:
            async with async_session_maker() as session:
                _, expired_course_user_ids = await AccessService(session).downgrade_expired_active_users()
                for telegram_id in expired_course_user_ids:
                    await _send_course_access_expired_offer(session, telegram_id)
            async with async_session_maker() as session:
                await DailyResetService(session).send_daily_reset_notifications(bot)
            async with async_session_maker() as session:
                await ExpiryReminderService(session).send_expiry_reminders(bot)
            async with async_session_maker() as session:
                await CourseReminderService(session).send_due_reminders(bot)
            async with async_session_maker() as session:
                await CourseReminderService(session).send_weekly_progress_reports(bot)
            async with async_session_maker() as session:
                await BotFeedbackService(session).send_due_price_discount_offers(bot)
            async with async_session_maker() as session:
                await DiscountNotificationService(session).send_due_notifications(bot)
            async with async_session_maker() as session:
                await PartnerService(session).send_due_payout_reminders(bot)
            async with async_session_maker() as session:
                await AdCampaignService(session).send_due_ads(bot)
            now = datetime.now(timezone.utc)
            if (
                _last_feedback_check_at is None
                or now - _last_feedback_check_at >= timedelta(hours=24)
            ):
                async with async_session_maker() as session:
                    await BotFeedbackService(session).send_due_feedback_requests(bot)
                _last_feedback_check_at = now
        except Exception as e:
            print("Scheduler error:", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()                                          # faqat jadval yaratish (tez)
    seed_task = asyncio.create_task(_seed_lessons())        # background seeding
    polling_task = asyncio.create_task(dp.start_polling(bot))
    scheduler_task = asyncio.create_task(_background_scheduler(bot))
    try:
        yield                                                # /health darhol ishlaydi
    finally:
        seed_task.cancel()
        polling_task.cancel()
        scheduler_task.cancel()
        study_ai_tasks = tuple(_study_ai_tasks)
        for task in study_ai_tasks:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await seed_task
        with contextlib.suppress(asyncio.CancelledError):
            await polling_task
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler_task
        for task in study_ai_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await bot.session.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/miniapp-assets/onehsk-theme.jpeg")
async def onehsk_theme_asset():
    return FileResponse("app/static/assets/onehsk-theme.jpeg", media_type="image/jpeg")


@app.get("/hsk3.html")
async def hsk3_miniapp():
    return FileResponse("app/static/hsk3.html")


@app.get("/hsk4.html")
async def hsk4_miniapp():
    return FileResponse("app/static/hsk4.html")


@app.get("/hsk1.html")
async def hsk1_miniapp():
    return FileResponse("app/static/hsk1.html")


@app.get("/hsk2.html")
async def hsk2_miniapp():
    return FileResponse("app/static/hsk2.html")


@app.get("/study.html")
async def study_miniapp():
    return FileResponse("app/static/study.html")


@app.get("/stroke-order.html")
async def stroke_order_miniapp():
    return FileResponse("app/static/stroke-order.html")


@app.post("/api/miniapp/access")
async def miniapp_access(request: Request):
    telegram_id = extract_verified_webapp_user_id(
        request.headers.get("X-Telegram-Init-Data", ""),
        settings.BOT_TOKEN,
    )
    if not telegram_id:
        return {"ok": False, "error": "invalid_telegram_init_data"}

    async with async_session_maker() as session:
        return await StudyMiniAppService(session).get_access_payload(telegram_id)


@app.get("/api/miniapp/lesson")
async def miniapp_lesson(lesson: int, lang: str = "uz", level: str = "hsk3", block: int | None = None):
    resolved_lang = normalize_miniapp_lang(lang)

    async with async_session_maker() as session:
        payload = await CourseMiniAppLessonService(session).get_payload(lesson, resolved_lang, level=level, block_no=block)
        if not payload:
            return {"ok": False, "error": "lesson_not_found"}
        return {"ok": True, "lesson": payload}


@app.post("/api/miniapp/event")
async def miniapp_event(request: Request):
    payload = await request.json()
    event = str(payload.get("event") or "").strip()

    telegram_id = extract_verified_webapp_user_id(
        request.headers.get("X-Telegram-Init-Data", ""),
        settings.BOT_TOKEN,
    )
    if not telegram_id:
        return {"ok": False, "error": "invalid_telegram_init_data"}

    if event == "bot_return_clicked":
        return {"ok": True}

    async with async_session_maker() as session:
        study_service = StudyMiniAppService(session)

        if event == "subscribe_clicked":
            sent = await study_service.send_subscription_menu(bot, telegram_id)
            return {"ok": bool(sent)}

        if event == "quiz_ai_discuss_clicked":
            _track_study_ai_task(
                asyncio.create_task(_send_study_quiz_ai_discussion(telegram_id, payload))
            )
            return {"ok": True}

        if event in {
            "study_quiz_completed",
            "starred_changed",
            "audio_played",
            "language_changed",
            "level_changed",
        }:
            return {"ok": True}

        if event == "app_error":
            saved = await AppErrorContextService(session).record_miniapp_error(
                telegram_id=telegram_id,
                payload=payload,
            )
            return {"ok": bool(saved)}

        service = CourseMiniAppResultService(session)

        if event == "quiz_completed":
            result = await service.save_quiz_result(telegram_id, payload)
            if result.get("error_key"):
                if result["error_key"] == "course_only_active_users":
                    await _send_course_access_expired_offer(session, telegram_id)
                return {"ok": False, "error": result["error_key"]}

            user = result["user"]
            lang = user.language if user and user.language else "ru"
            if result.get("block_no"):
                reply_markup = course_miniapp_continue_keyboard(lang)
            else:
                reply_markup = course_miniapp_understood_keyboard(lang)
            await bot.send_message(
                chat_id=telegram_id,
                text=format_miniapp_quiz_result(lang, result),
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            return {"ok": True}

        if event == "homework_submitted":
            result = await service.save_homework_result(telegram_id, payload)
            if result.get("error_key"):
                if result["error_key"] == "course_only_active_users":
                    await _send_course_access_expired_offer(session, telegram_id)
                return {"ok": False, "error": result["error_key"]}

            user = result["user"]
            lang = user.language if user and user.language else "ru"
            await bot.send_message(
                chat_id=telegram_id,
                text=format_miniapp_homework_result(lang, result),
                reply_markup=(
                    course_homework_done_keyboard(lang)
                    if result.get("passed")
                    else homework_retry_keyboard(lang)
                ),
                parse_mode="HTML",
            )
            return {"ok": True}

    return {"ok": False, "error": "unknown_event"}
