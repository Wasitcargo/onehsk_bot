from datetime import datetime, timedelta, timezone
from html import escape
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.bot.fsm.admin_discount import DiscountStates
from app.bot.keyboards.admin_discount import (
    discount_cancel_keyboard,
    discount_confirm_keyboard,
    discount_duration_keyboard,
    discount_edit_back_keyboard,
    discount_language_keyboard,
    discount_list_keyboard,
    discount_notify_keyboard,
    discount_notify_media_keyboard,
    discount_panel_keyboard,
    discount_payment_method_keyboard,
    discount_plan_keyboard,
    discount_start_keyboard,
    discount_status_keyboard,
    discount_usage_keyboard,
)
from app.repositories.discount_campaign_repo import DiscountCampaignRepository
from app.repositories.user_repo import UserRepository
from app.services.discount_notification_service import DiscountNotificationService
from app.services.discount_translation_service import DiscountTranslationService
from app.services.payment_qr_service import PaymentQrService, QR_PAYMENT_METHODS
from app.services.subscription_currency_service import format_subscription_price
from app.services.subscription_price_service import PLANS, SubscriptionPriceService

router = Router()

ADMIN_TZ = ZoneInfo("Asia/Shanghai")
_PANEL_CHAT_ID = "discount_panel_chat_id"
_PANEL_MSG_ID = "discount_panel_msg_id"
_EDIT_MODE = "discount_edit_mode"

_LABELS = {
    "status": {
        "free": "Bepul",
        "trial": "Sinov",
        "active": "Faol",
        "expired": "Tugagan",
        "blocked": "Blok",
    },
    "language": {"uz": "UZ", "ru": "RU", "tj": "TJ"},
    "payment": {"visa": "Visa", "alipay": "Alipay", "wechat": "WeChat"},
    "plan": {"10_days": "10 kun", "1_month": "1 oy"},
}


def _is_admin(user_id: int) -> bool:
    admin_ids = [int(x.strip()) for x in settings.ADMIN_IDS.split(",") if x.strip()]
    return user_id in admin_ids


def _none_if_all(value: Optional[str]) -> Optional[str]:
    return None if value in (None, "all") else value


def _fmt_filter(value: Optional[str], default: str = "Hamma") -> str:
    return value or default


def _label(group: str, value: Optional[str]) -> str:
    if not value:
        return "Hamma"
    return _LABELS.get(group, {}).get(value, value)


def _fmt_time(value: Optional[datetime]) -> str:
    if not value:
        return "—"
    return value.astimezone(ADMIN_TZ).strftime("%Y-%m-%d %H:%M")


def _fmt_duration(hours: Optional[int]) -> str:
    if not hours:
        return "—"
    if hours % 24 == 0:
        days = hours // 24
        return f"{days} kun"
    return f"{hours} soat"


def _fmt_quota(value: Optional[int]) -> str:
    return str(value) if value else "Limitsiz"


def _fmt_repeat(value: Optional[int]) -> str:
    return f"Har {value} kunda" if value else "Bir marta"


def _fmt_notify(data: dict) -> str:
    if not data.get("notify_enabled"):
        return "Yuborilmaydi"
    media_type = data.get("notify_media_type")
    if media_type == "photo":
        return "Foto + matn"
    if media_type == "video":
        return "Video + matn"
    return "Faqat matn"


def _cancel_keyboard_for(data: dict):
    return discount_edit_back_keyboard() if data.get(_EDIT_MODE) else discount_cancel_keyboard()


def _message_image_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    document = getattr(message, "document", None)
    if document and (document.mime_type or "").startswith("image/"):
        return document.file_id
    return None


def _selected_qr_methods(payment_method: Optional[str]) -> list[str]:
    if payment_method in QR_PAYMENT_METHODS:
        return [payment_method]
    if payment_method is None:
        return list(QR_PAYMENT_METHODS)
    return []


def _selected_plans(plan_type: Optional[str]) -> list[str]:
    if plan_type in PLANS:
        return [plan_type]
    return list(PLANS)


async def _missing_discount_qr_uploads(session, data: dict) -> list[dict]:
    percent = int(data.get("percent") or 0)
    if percent <= 0:
        return []

    qr_service = PaymentQrService(session)
    price_service = SubscriptionPriceService(session)
    uploads = []
    seen = set()

    for method in _selected_qr_methods(data.get("payment_method")):
        for plan in _selected_plans(data.get("plan_type")):
            price = await price_service.get_price(method, plan)
            if not price:
                continue
            final_amount = qr_service.calculate_discounted_amount(price.amount, percent)
            if await qr_service.has_checkout_qr(
                payment_method=method,
                plan_type=plan,
                amount=final_amount,
                currency=price.currency,
                discount_percent=percent,
            ):
                continue

            key = (method, price.currency, final_amount)
            if key in seen:
                continue
            seen.add(key)
            uploads.append(
                {
                    "payment_method": method,
                    "plan_type": plan,
                    "base_amount": price.amount,
                    "amount": final_amount,
                    "currency": price.currency,
                    "discount_percent": percent,
                }
            )
    return uploads


def _discount_qr_prompt(upload: dict, index: int, total: int, error: Optional[str] = None) -> str:
    method = _label("payment", upload["payment_method"])
    plan = _label("plan", upload["plan_type"])
    base = format_subscription_price(int(upload["base_amount"]), upload["currency"])
    final = format_subscription_price(int(upload["amount"]), upload["currency"])
    lines = [
        "📱 <b>Chegirma uchun QR kod kerak</b>",
        "",
        f"To'lov: <b>{method}</b>",
        f"Tarif: <b>{plan}</b>",
        f"Chegirma: <b>{upload['discount_percent']}%</b>",
        f"Asosiy narx: <b>{base}</b>",
        f"To'lanadigan narx: <b>{final}</b>",
        f"QR: <b>{index}/{total}</b>",
        "",
        "Shu to'lanadigan narxga mos QR kod rasmini yuboring.",
    ]
    if error:
        lines.extend(["", f"⚠️ {escape(error)}"])
    return "\n".join(lines)


def _wizard_text(data: dict, prompt: str, error: Optional[str] = None) -> str:
    start_at = data.get("starts_at")
    duration_hours = data.get("duration_hours")
    ends_at = start_at + timedelta(hours=duration_hours) if start_at and duration_hours else None

    lines = [
        "🎁 <b>Yangi chegirma sozlash</b>",
        "",
        "<blockquote>",
        f"Nomi: <b>{escape(str(data.get('title') or '—'))}</b>",
        f"Target: <b>{escape(str(data.get('target_label') or 'Segment'))}</b>",
        f"Foiz: <b>{data.get('percent') or '—'}%</b>",
        f"Davomiylik: <b>{_fmt_duration(duration_hours)}</b>",
        f"Boshlanish: <b>{_fmt_time(start_at)}</b>",
        f"Tugash: <b>{_fmt_time(ends_at)}</b>",
        f"Status: <b>{_label('status', data.get('audience_status'))}</b>",
        f"Til: <b>{_label('language', data.get('audience_language'))}</b>",
        f"To'lov turi: <b>{_label('payment', data.get('payment_method'))}</b>",
        f"Tarif: <b>{_label('plan', data.get('plan_type'))}</b>",
        f"Limit: <b>{_fmt_quota(data.get('quota_total'))}</b>",
        f"Qoida: <b>{_fmt_repeat(data.get('repeat_interval_days'))}</b>",
        f"Xabar: <b>{_fmt_notify(data)}</b>",
        "</blockquote>",
        "",
        f"➡️ <b>{prompt}</b>",
    ]
    if error:
        lines.extend(["", f"⚠️ {escape(error)}"])
    return "\n".join(lines)


async def _prepare_title_i18n(data: dict) -> dict:
    title = str(data["title"])[:120]
    translated = await DiscountTranslationService().translate_title(title)
    return {
        "title_tj": translated["tj"],
        "title_ru": translated["ru"],
        "title_uz": translated["uz"],
    }


async def _remember_panel(state: FSMContext, callback: CallbackQuery) -> None:
    await state.update_data(
        **{
            _PANEL_CHAT_ID: callback.message.chat.id,
            _PANEL_MSG_ID: callback.message.message_id,
        }
    )


async def _edit_callback_panel(
    callback: CallbackQuery,
    state: FSMContext,
    text: str,
    reply_markup=None,
) -> None:
    await _remember_panel(state, callback)
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        pass


async def _edit_stored_panel(
    message: Message,
    state: FSMContext,
    text: str,
    reply_markup=None,
) -> None:
    data = await state.get_data()
    chat_id = data.get(_PANEL_CHAT_ID)
    message_id = data.get(_PANEL_MSG_ID)
    if chat_id and message_id:
        try:
            await message.bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return
        except Exception:
            pass

    sent = await message.answer(
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await state.update_data(**{_PANEL_CHAT_ID: sent.chat.id, _PANEL_MSG_ID: sent.message_id})


async def _delete_admin_input(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


def _is_edit_mode(data: dict, mode: str) -> bool:
    return data.get(_EDIT_MODE) == mode


async def _clear_edit_mode(state: FSMContext) -> dict:
    await state.update_data(**{_EDIT_MODE: None})
    return await state.get_data()


async def _return_to_preview_callback(callback: CallbackQuery, state: FSMContext) -> None:
    data = await _clear_edit_mode(state)
    await state.set_state(None)
    await _edit_callback_panel(callback, state, _preview(data), discount_confirm_keyboard())


async def _return_to_preview_message(message: Message, state: FSMContext) -> None:
    data = await _clear_edit_mode(state)
    await state.set_state(None)
    await _edit_stored_panel(message, state, _preview(data), discount_confirm_keyboard())


def _preview(data: dict) -> str:
    start_at = data["starts_at"]
    ends_at = start_at + timedelta(hours=data["duration_hours"])
    quota = data.get("quota_total") or "limitsiz"
    repeat = data.get("repeat_interval_days")
    usage = f"har {repeat} kunda" if repeat else "bir marta"
    return (
        "🎁 <b>Chegirma tasdiqlash</b>\n\n"
        f"Nomi: <b>{escape(str(data['title']))}</b>\n"
        f"Foiz: <b>{data['percent']}%</b>\n"
        f"Muddat: <b>{start_at.astimezone(ADMIN_TZ):%Y-%m-%d %H:%M}</b> dan "
        f"<b>{ends_at.astimezone(ADMIN_TZ):%Y-%m-%d %H:%M}</b> gacha\n"
        f"Kimlarga: status=<b>{_fmt_filter(data.get('audience_status'))}</b>, "
        f"til=<b>{_fmt_filter(data.get('audience_language'))}</b>\n"
        f"Target user: <b>{escape(str(data.get('target_label') or '—'))}</b>\n"
        f"To'lov: <b>{_fmt_filter(data.get('payment_method'))}</b>, "
        f"tarif=<b>{_fmt_filter(data.get('plan_type'))}</b>\n"
        f"Limit: <b>{quota}</b>\n"
        f"Qoida: <b>{usage}</b>\n"
        f"Userlarga xabar: <b>{_fmt_notify(data)}</b>\n\n"
        "Tasdiqlaysizmi?"
    )


@router.callback_query(F.data == "adm:discount_panel")
async def admin_discount_panel(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    await callback.answer()
    text = (
        "🎁 <b>Chegirma boshqaruvi</b>\n\n"
        "Admin kampaniya ochadi, checkoutda avtomatik narx tushadi va payment review'da manbasi ko'rinadi."
    )
    try:
        sent = await callback.message.edit_text(
            text,
            reply_markup=discount_panel_keyboard(),
            parse_mode="HTML",
        )
    except Exception:
        sent = await callback.message.answer(
            text,
            reply_markup=discount_panel_keyboard(),
            parse_mode="HTML",
        )
    await state.update_data(**{_PANEL_CHAT_ID: sent.chat.id, _PANEL_MSG_ID: sent.message_id})


@router.callback_query(F.data == "disc:new")
async def discount_new(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    await state.set_state(DiscountStates.waiting_title)
    await callback.answer()
    await _edit_callback_panel(
        callback,
        state,
        _wizard_text({}, "Chegirma nomini yozing. Masalan: May 20%"),
        discount_cancel_keyboard(),
    )


@router.callback_query(F.data == "disc:target")
async def discount_target(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    await state.set_state(DiscountStates.waiting_target_identifier)
    await callback.answer()
    await _edit_callback_panel(
        callback,
        state,
        "🎯 <b>Bitta userga maxsus chegirma</b>\n\n"
        "Telegram ID yoki username yuboring.\n"
        "Misol: <code>123456789</code> yoki <code>@username</code>",
        discount_cancel_keyboard(),
    )


@router.message(StateFilter(DiscountStates.waiting_target_identifier))
async def discount_target_identifier(message: Message, state: FSMContext, session):
    if not _is_admin(message.from_user.id):
        return

    identifier = (message.text or "").strip()
    user = await UserRepository(session).find_by_identifier(identifier)
    await _delete_admin_input(message)
    if not user:
        await _edit_stored_panel(
            message,
            state,
            "❌ User topilmadi.\n\nTelegram ID yoki @username ni qayta yuboring.",
            _cancel_keyboard_for(await state.get_data()),
        )
        return

    target_label = f"{user.full_name or '-'}"
    if user.username:
        target_label += f" (@{user.username})"

    await state.update_data(
        target_telegram_id=user.telegram_id,
        target_label=f"{target_label} / {user.telegram_id}",
        audience_status=None,
        audience_language=None,
        audience_level=None,
    )
    data = await state.get_data()
    if _is_edit_mode(data, "target"):
        await _return_to_preview_message(message, state)
        return

    await state.set_state(DiscountStates.waiting_title)
    await _edit_stored_panel(
        message,
        state,
        _wizard_text(data, "Chegirma nomini yozing. Masalan: VIP 30%"),
        discount_cancel_keyboard(),
    )


@router.message(StateFilter(DiscountStates.waiting_title))
async def discount_title(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    title = (message.text or "").strip()
    if len(title) < 2:
        data = await state.get_data()
        await _delete_admin_input(message)
        await _edit_stored_panel(
            message,
            state,
            _wizard_text(data, "Chegirma nomini yozing. Masalan: May 20%", "Nomi juda qisqa. Qayta yozing."),
            _cancel_keyboard_for(data),
        )
        return
    await state.update_data(title=title[:120])
    data = await state.get_data()
    await _delete_admin_input(message)
    if _is_edit_mode(data, "title"):
        await _return_to_preview_message(message, state)
        return

    await state.set_state(DiscountStates.waiting_percent)
    await _edit_stored_panel(
        message,
        state,
        _wizard_text(data, "Chegirma foizini yozing. Masalan: 20"),
        discount_cancel_keyboard(),
    )


@router.message(StateFilter(DiscountStates.waiting_percent))
async def discount_percent(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    try:
        percent = int((message.text or "").strip())
    except ValueError:
        data = await state.get_data()
        await _delete_admin_input(message)
        await _edit_stored_panel(
            message,
            state,
            _wizard_text(data, "Chegirma foizini yozing. Masalan: 20", "Foiz raqam bo'lishi kerak."),
            _cancel_keyboard_for(data),
        )
        return
    if percent < 1 or percent > 90:
        data = await state.get_data()
        await _delete_admin_input(message)
        await _edit_stored_panel(
            message,
            state,
            _wizard_text(data, "Chegirma foizini yozing. Masalan: 20", "Foiz 1 dan 90 gacha bo'lsin."),
            _cancel_keyboard_for(data),
        )
        return
    await state.update_data(percent=percent)
    data = await state.get_data()
    await _delete_admin_input(message)
    await state.set_state(None)
    if _is_edit_mode(data, "percent"):
        await _return_to_preview_message(message, state)
        return

    await _edit_stored_panel(
        message,
        state,
        _wizard_text(data, "Chegirma qancha davom etadi?"),
        discount_duration_keyboard(),
    )


@router.callback_query(F.data.startswith("disc:duration:"))
async def discount_duration(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    value = callback.data.split(":")[2]
    await callback.answer()
    if value == "custom":
        await state.set_state(DiscountStates.waiting_custom_duration)
        data = await state.get_data()
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Davomiylikni soatda yozing. Masalan: 48"),
            _cancel_keyboard_for(data),
        )
        return
    await state.update_data(duration_hours=int(value))
    data = await state.get_data()
    if _is_edit_mode(data, "duration"):
        await _return_to_preview_callback(callback, state)
        return

    if data.get("target_telegram_id"):
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Qaysi to'lov turiga?"),
            discount_payment_method_keyboard(),
        )
        return
    await _edit_callback_panel(
        callback,
        state,
        _wizard_text(data, "Kimlarga beriladi? Status tanlang"),
        discount_status_keyboard(),
    )


@router.message(StateFilter(DiscountStates.waiting_custom_duration))
async def discount_custom_duration(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    try:
        hours = int((message.text or "").strip())
    except ValueError:
        data = await state.get_data()
        await _delete_admin_input(message)
        await _edit_stored_panel(
            message,
            state,
            _wizard_text(data, "Davomiylikni soatda yozing. Masalan: 48", "Soat raqam bo'lishi kerak."),
            _cancel_keyboard_for(data),
        )
        return
    if hours < 1 or hours > 24 * 365:
        data = await state.get_data()
        await _delete_admin_input(message)
        await _edit_stored_panel(
            message,
            state,
            _wizard_text(data, "Davomiylikni soatda yozing. Masalan: 48", "Muddat 1 soatdan 365 kungacha bo'lsin."),
            _cancel_keyboard_for(data),
        )
        return
    await state.update_data(duration_hours=hours)
    data = await state.get_data()
    await _delete_admin_input(message)
    await state.set_state(None)
    if _is_edit_mode(data, "duration"):
        await _return_to_preview_message(message, state)
        return

    if data.get("target_telegram_id"):
        await _edit_stored_panel(
            message,
            state,
            _wizard_text(data, "Qaysi to'lov turiga?"),
            discount_payment_method_keyboard(),
        )
        return
    await _edit_stored_panel(
        message,
        state,
        _wizard_text(data, "Kimlarga beriladi? Status tanlang"),
        discount_status_keyboard(),
    )


@router.callback_query(F.data.startswith("disc:status:"))
async def discount_status(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.update_data(audience_status=_none_if_all(callback.data.split(":")[2]))
    await callback.answer()
    data = await state.get_data()
    await _edit_callback_panel(
        callback,
        state,
        _wizard_text(data, "Qaysi til segmentiga?"),
        discount_language_keyboard(),
    )


@router.callback_query(F.data.startswith("disc:lang:"))
async def discount_language(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.update_data(audience_language=_none_if_all(callback.data.split(":")[2]))
    await callback.answer()
    data = await state.get_data()
    if _is_edit_mode(data, "audience"):
        await _return_to_preview_callback(callback, state)
        return

    await _edit_callback_panel(
        callback,
        state,
        _wizard_text(data, "Qaysi to'lov turiga?"),
        discount_payment_method_keyboard(),
    )


@router.callback_query(F.data.startswith("disc:method:"))
async def discount_payment_method(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.update_data(payment_method=_none_if_all(callback.data.split(":")[2]))
    await callback.answer()
    data = await state.get_data()
    await _edit_callback_panel(
        callback,
        state,
        _wizard_text(data, "Qaysi tarifga?"),
        discount_plan_keyboard(),
    )


@router.callback_query(F.data.startswith("disc:plan:"))
async def discount_plan(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.update_data(plan_type=_none_if_all(callback.data.split(":")[2]))
    await callback.answer()
    data = await state.get_data()
    if _is_edit_mode(data, "payment_plan"):
        await _return_to_preview_callback(callback, state)
        return

    await _edit_callback_panel(
        callback,
        state,
        _wizard_text(data, "Qachon ishga tushsin?"),
        discount_start_keyboard(),
    )


@router.callback_query(F.data.startswith("disc:start:"))
async def discount_start(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    mode = callback.data.split(":")[2]
    await callback.answer()
    if mode == "scheduled":
        await state.set_state(DiscountStates.waiting_start_at)
        data = await state.get_data()
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Boshlanish vaqtini yozing: YYYY-MM-DD HH:MM. Vaqt zonasi: Asia/Shanghai"),
            _cancel_keyboard_for(data),
        )
        return
    await state.update_data(starts_at=datetime.now(timezone.utc))
    data = await state.get_data()
    if _is_edit_mode(data, "start"):
        await _return_to_preview_callback(callback, state)
        return

    await _edit_callback_panel(
        callback,
        state,
        _wizard_text(data, "Bir martami yoki takrorlanadimi?"),
        discount_usage_keyboard(),
    )


@router.message(StateFilter(DiscountStates.waiting_start_at))
async def discount_start_at(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip()
    try:
        local_dt = datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=ADMIN_TZ)
    except ValueError:
        data = await state.get_data()
        await _delete_admin_input(message)
        await _edit_stored_panel(
            message,
            state,
            _wizard_text(
                data,
                "Boshlanish vaqtini yozing: YYYY-MM-DD HH:MM. Vaqt zonasi: Asia/Shanghai",
                "Format noto'g'ri. Masalan: 2026-05-13 21:30",
            ),
            _cancel_keyboard_for(data),
        )
        return
    await state.update_data(starts_at=local_dt.astimezone(timezone.utc))
    data = await state.get_data()
    await _delete_admin_input(message)
    await state.set_state(None)
    if _is_edit_mode(data, "start"):
        await _return_to_preview_message(message, state)
        return

    await _edit_stored_panel(
        message,
        state,
        _wizard_text(data, "Bir martami yoki takrorlanadimi?"),
        discount_usage_keyboard(),
    )


@router.callback_query(F.data.startswith("disc:usage:"))
async def discount_usage(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    value = callback.data.split(":")[2]
    await callback.answer()
    if value == "repeat":
        await state.set_state(DiscountStates.waiting_repeat_days)
        data = await state.get_data()
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Necha kunda qayta olish mumkin? Masalan: 7"),
            _cancel_keyboard_for(data),
        )
        return
    await state.update_data(repeat_interval_days=None)
    await state.set_state(DiscountStates.waiting_quota)
    data = await state.get_data()
    await _edit_callback_panel(
        callback,
        state,
        _wizard_text(data, "Limit nechta user? 0 yozsangiz limitsiz. Masalan: 20"),
        _cancel_keyboard_for(data),
    )


@router.message(StateFilter(DiscountStates.waiting_repeat_days))
async def discount_repeat_days(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    try:
        days = int((message.text or "").strip())
    except ValueError:
        data = await state.get_data()
        await _delete_admin_input(message)
        await _edit_stored_panel(
            message,
            state,
            _wizard_text(data, "Necha kunda qayta olish mumkin? Masalan: 7", "Kun raqam bo'lishi kerak."),
            _cancel_keyboard_for(data),
        )
        return
    if days < 1 or days > 365:
        data = await state.get_data()
        await _delete_admin_input(message)
        await _edit_stored_panel(
            message,
            state,
            _wizard_text(data, "Necha kunda qayta olish mumkin? Masalan: 7", "Takror oralig'i 1-365 kun bo'lsin."),
            _cancel_keyboard_for(data),
        )
        return
    await state.update_data(repeat_interval_days=days)
    await state.set_state(DiscountStates.waiting_quota)
    data = await state.get_data()
    await _delete_admin_input(message)
    await _edit_stored_panel(
        message,
        state,
        _wizard_text(data, "Limit nechta user? 0 yozsangiz limitsiz. Masalan: 20"),
        _cancel_keyboard_for(data),
    )


@router.message(StateFilter(DiscountStates.waiting_quota))
async def discount_quota(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    try:
        quota = int((message.text or "").strip())
    except ValueError:
        data = await state.get_data()
        await _delete_admin_input(message)
        await _edit_stored_panel(
            message,
            state,
            _wizard_text(data, "Limit nechta user? 0 yozsangiz limitsiz. Masalan: 20", "Limit raqam bo'lishi kerak."),
            _cancel_keyboard_for(data),
        )
        return
    if quota < 0:
        data = await state.get_data()
        await _delete_admin_input(message)
        await _edit_stored_panel(
            message,
            state,
            _wizard_text(data, "Limit nechta user? 0 yozsangiz limitsiz. Masalan: 20", "Limit manfiy bo'lmaydi."),
            _cancel_keyboard_for(data),
        )
        return
    await state.update_data(quota_total=quota or None)
    data = await state.get_data()
    await state.set_state(None)
    await _delete_admin_input(message)
    if _is_edit_mode(data, "usage_quota"):
        await _return_to_preview_message(message, state)
        return

    await _edit_stored_panel(
        message,
        state,
        _wizard_text(data, "Chegirma xabari userlarga yuborilsinmi?"),
        discount_notify_keyboard(),
    )


@router.callback_query(F.data.startswith("disc:notify:"))
async def discount_notify_choice(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return

    value = callback.data.split(":")[2]
    await callback.answer()

    if value == "none":
        await state.update_data(
            notify_enabled=False,
            notify_media_type=None,
            notify_media_file_id=None,
        )
        data = await _clear_edit_mode(state)
        await _edit_callback_panel(callback, state, _preview(data), discount_confirm_keyboard())
        return

    if value == "media":
        await state.update_data(notify_enabled=True)
        await state.set_state(DiscountStates.waiting_notify_media)
        data = await state.get_data()
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Foto yoki video yuboring. Kerak bo'lmasa mediasiz davom eting."),
            discount_notify_media_keyboard(),
        )
        return

    await state.update_data(
        notify_enabled=True,
        notify_media_type=None,
        notify_media_file_id=None,
    )
    data = await _clear_edit_mode(state)
    await _edit_callback_panel(callback, state, _preview(data), discount_confirm_keyboard())


@router.callback_query(F.data == "disc:notify_media_skip")
async def discount_notify_media_skip(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.update_data(
        notify_enabled=True,
        notify_media_type=None,
        notify_media_file_id=None,
    )
    await state.set_state(None)
    data = await _clear_edit_mode(state)
    await callback.answer()
    await _edit_callback_panel(callback, state, _preview(data), discount_confirm_keyboard())


@router.message(StateFilter(DiscountStates.waiting_notify_media))
async def discount_notify_media(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    media_type = None
    media_file_id = None
    if message.photo:
        media_type = "photo"
        media_file_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        media_file_id = message.video.file_id

    if not media_file_id:
        data = await state.get_data()
        await _delete_admin_input(message)
        await _edit_stored_panel(
            message,
            state,
            _wizard_text(
                data,
                "Foto yoki video yuboring. Kerak bo'lmasa mediasiz davom eting.",
                "Faqat foto yoki video qabul qilinadi.",
            ),
            discount_notify_media_keyboard(),
        )
        return

    await state.update_data(
        notify_enabled=True,
        notify_media_type=media_type,
        notify_media_file_id=media_file_id,
    )
    await state.set_state(None)
    data = await _clear_edit_mode(state)
    await _delete_admin_input(message)
    await _edit_stored_panel(message, state, _preview(data), discount_confirm_keyboard())


@router.callback_query(F.data == "disc:review")
async def discount_review(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    data = await state.get_data()
    if any(key not in data for key in ("title", "percent", "duration_hours", "starts_at")):
        await callback.answer("Tasdiqlash uchun ma'lumot yetishmayapti", show_alert=True)
        return
    await callback.answer()
    await _return_to_preview_callback(callback, state)


@router.callback_query(F.data.startswith("disc:edit:"))
async def discount_edit_field(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return

    field = callback.data.split(":")[2]
    data = await state.get_data()
    if any(key not in data for key in ("title", "percent", "duration_hours", "starts_at")):
        await callback.answer("Avval asosiy ma'lumotlarni to'ldiring", show_alert=True)
        return

    await callback.answer()

    if field == "title":
        await state.update_data(**{_EDIT_MODE: "title"})
        await state.set_state(DiscountStates.waiting_title)
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Yangi nomni yozing."),
            discount_edit_back_keyboard(),
        )
        return

    if field == "percent":
        await state.update_data(**{_EDIT_MODE: "percent"})
        await state.set_state(DiscountStates.waiting_percent)
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Yangi foizni yozing. Masalan: 20"),
            discount_edit_back_keyboard(),
        )
        return

    if field == "duration":
        await state.update_data(**{_EDIT_MODE: "duration"})
        await state.set_state(None)
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Yangi davomiylikni tanlang."),
            discount_duration_keyboard(),
        )
        return

    if field == "audience":
        if data.get("target_telegram_id"):
            await state.update_data(**{_EDIT_MODE: "target"})
            await state.set_state(DiscountStates.waiting_target_identifier)
            await _edit_callback_panel(
                callback,
                state,
                "🎯 <b>Bitta userga maxsus chegirma</b>\n\n"
                "Yangi Telegram ID yoki username yuboring.",
                discount_edit_back_keyboard(),
            )
            return

        await state.update_data(**{_EDIT_MODE: "audience"})
        await state.set_state(None)
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Yangi status segmentini tanlang."),
            discount_status_keyboard(),
        )
        return

    if field == "payment_plan":
        await state.update_data(**{_EDIT_MODE: "payment_plan"})
        await state.set_state(None)
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Yangi to'lov turini tanlang."),
            discount_payment_method_keyboard(),
        )
        return

    if field == "start":
        await state.update_data(**{_EDIT_MODE: "start"})
        await state.set_state(None)
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Yangi boshlanish vaqtini tanlang."),
            discount_start_keyboard(),
        )
        return

    if field == "usage_quota":
        await state.update_data(**{_EDIT_MODE: "usage_quota"})
        await state.set_state(None)
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Qayta foydalanish qoidasini tanlang."),
            discount_usage_keyboard(),
        )
        return

    if field == "notify":
        await state.update_data(**{_EDIT_MODE: "notify"})
        await state.set_state(None)
        await _edit_callback_panel(
            callback,
            state,
            _wizard_text(data, "Chegirma xabari userlarga yuborilsinmi?"),
            discount_notify_keyboard(),
        )
        return

    await callback.answer("Noma'lum maydon", show_alert=True)


@router.callback_query(F.data == "disc:confirm")
async def discount_confirm(callback: CallbackQuery, state: FSMContext, session):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    data = await state.get_data()
    required = ["title", "percent", "duration_hours", "starts_at"]
    if any(key not in data for key in required):
        await callback.answer("Ma'lumot yetishmayapti", show_alert=True)
        return

    starts_at = data["starts_at"]
    ends_at = starts_at + timedelta(hours=data["duration_hours"])
    now = datetime.now(timezone.utc)
    if ends_at <= now:
        await callback.answer("Bu chegirma muddati allaqachon tugagan. Boshlanish yoki muddatni o'zgartiring.", show_alert=True)
        return

    missing_qrs = await _missing_discount_qr_uploads(session, data)
    if missing_qrs:
        await state.update_data(discount_qr_uploads=missing_qrs, discount_qr_index=0)
        await state.set_state(DiscountStates.waiting_payment_qr)
        await callback.answer("Alipay/WeChat QR kod kerak", show_alert=True)
        await _edit_callback_panel(
            callback,
            state,
            _discount_qr_prompt(missing_qrs[0], 1, len(missing_qrs)),
            discount_cancel_keyboard(),
        )
        return

    title_i18n = await _prepare_title_i18n(data)
    data.update(title_i18n)
    await state.update_data(**title_i18n)

    repo = DiscountCampaignRepository(session)
    campaign = await repo.create(
        title=data["title"],
        title_tj=title_i18n["title_tj"],
        title_ru=title_i18n["title_ru"],
        title_uz=title_i18n["title_uz"],
        percent=data["percent"],
        starts_at=starts_at,
        ends_at=ends_at,
        audience_status=data.get("audience_status"),
        audience_language=data.get("audience_language"),
        target_telegram_id=data.get("target_telegram_id"),
        payment_method=data.get("payment_method"),
        plan_type=data.get("plan_type"),
        quota_total=data.get("quota_total"),
        repeat_interval_days=data.get("repeat_interval_days"),
        notify_enabled=bool(data.get("notify_enabled")),
        notify_media_type=data.get("notify_media_type"),
        notify_media_file_id=data.get("notify_media_file_id"),
        created_by_telegram_id=callback.from_user.id,
    )
    campaign_id = campaign.id
    await session.commit()
    await callback.answer("Chegirma saqlandi", show_alert=True)

    notify_total = sent_count = failed_count = 0
    should_send_now = data.get("notify_enabled") and starts_at <= now < ends_at
    if should_send_now:
        await callback.message.edit_text(
            f"✅ Chegirma #{campaign_id} saqlandi.\n"
            f"⏳ Xabar userlarga yuborilmoqda...",
            reply_markup=None,
        )
        result = await DiscountNotificationService(session).send_campaign_notification(callback.bot, campaign)
        await session.commit()
        notify_total = result.total
        sent_count = result.sent
        failed_count = result.failed

    await state.clear()
    notify_line = "📣 Userlarga xabar: yuborilmadi"
    if should_send_now:
        notify_line = f"📣 Userlarga xabar: {sent_count}/{notify_total} yuborildi, xato: {failed_count}"
    elif data.get("notify_enabled"):
        notify_line = f"📣 Userlarga xabar: {starts_at.astimezone(ADMIN_TZ):%Y-%m-%d %H:%M} da yuboriladi"

    await callback.message.edit_text(
        f"✅ Chegirma #{campaign_id} saqlandi.\n"
        f"Ishga tushish: {starts_at.astimezone(ADMIN_TZ):%Y-%m-%d %H:%M}\n"
        f"{notify_line}",
        reply_markup=None,
    )


@router.message(StateFilter(DiscountStates.waiting_payment_qr))
async def discount_payment_qr(message: Message, state: FSMContext, session):
    if not _is_admin(message.from_user.id):
        return

    data = await state.get_data()
    uploads = data.get("discount_qr_uploads") or []
    index = int(data.get("discount_qr_index") or 0)
    if not uploads or index >= len(uploads):
        await _delete_admin_input(message)
        await _edit_stored_panel(message, state, "❌ QR jarayoni topilmadi. Chegirmani qayta tasdiqlang.")
        await state.set_state(None)
        return

    current = uploads[index]
    file_id = _message_image_file_id(message)
    if not file_id:
        await _delete_admin_input(message)
        await _edit_stored_panel(
            message,
            state,
            _discount_qr_prompt(
                current,
                index + 1,
                len(uploads),
                "Faqat QR rasm qabul qilinadi. Foto yoki image-fayl yuboring.",
            ),
            discount_cancel_keyboard(),
        )
        return

    await PaymentQrService(session).set_dynamic_file_id(
        payment_method=current["payment_method"],
        amount=int(current["amount"]),
        currency=current["currency"],
        file_id=file_id,
    )
    await session.commit()
    await _delete_admin_input(message)

    index += 1
    if index < len(uploads):
        await state.update_data(discount_qr_index=index)
        await _edit_stored_panel(
            message,
            state,
            _discount_qr_prompt(uploads[index], index + 1, len(uploads)),
            discount_cancel_keyboard(),
        )
        return

    await state.update_data(discount_qr_uploads=None, discount_qr_index=None)
    await state.set_state(None)
    data = await state.get_data()
    await _edit_stored_panel(
        message,
        state,
        "✅ QR kodlar saqlandi.\n\n" + _preview(data),
        discount_confirm_keyboard(),
    )


@router.callback_query(F.data == "disc:list")
async def discount_list(callback: CallbackQuery, session):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    repo = DiscountCampaignRepository(session)
    campaigns = await repo.list_recent(10)
    if not campaigns:
        await callback.answer()
        await callback.message.edit_text(
            "Hozircha chegirma kampaniyasi yo'q.",
            reply_markup=discount_panel_keyboard(),
        )
        return

    lines = ["📋 <b>Oxirgi chegirmalar</b>\n"]
    now = datetime.now(timezone.utc)
    for item in campaigns:
        if not item.is_active:
            status = "o'chirilgan"
        elif item.starts_at > now:
            status = "rejalangan"
        elif item.ends_at <= now:
            status = "tugagan"
        else:
            status = "aktiv"
        if not item.notify_enabled:
            notify_status = "xabar: yo'q"
        elif item.notification_sent_at:
            notify_status = f"xabar: {item.notification_sent_count} yuborildi"
        else:
            notify_status = f"xabar: {_fmt_time(item.starts_at)} da"
        used = await repo.count_used(item.id)
        quota = item.quota_total or "∞"
        target = f" | target: <code>{item.target_telegram_id}</code>" if item.target_telegram_id else ""
        lines.append(
            f"#{item.id} {escape(str(item.title))} — {item.percent}% | {status} | "
            f"{used}/{quota} | {notify_status}{target}"
        )
    await callback.answer()
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=discount_list_keyboard(campaigns),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("disc:disable:"))
async def discount_disable(callback: CallbackQuery, session):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    campaign_id = int(callback.data.split(":")[2])
    repo = DiscountCampaignRepository(session)
    campaign = await repo.get_by_id(campaign_id)
    if not campaign:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await repo.deactivate(campaign)
    await session.commit()
    await callback.answer("O'chirildi", show_alert=True)
    await callback.message.edit_text(
        f"⛔ Chegirma #{campaign_id} o'chirildi.",
        reply_markup=discount_panel_keyboard(),
    )


@router.callback_query(F.data == "disc:cancel")
async def discount_cancel(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "❌ Chegirma yaratish bekor qilindi.",
        reply_markup=discount_panel_keyboard(),
    )
