from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from app.config import settings
from app.repositories.payment_repo import PaymentRepository
from app.repositories.bot_feedback_repo import BotFeedbackRepository
from app.repositories.user_repo import UserRepository
from app.services.discount_service import DiscountService
from app.services.payment_service import PaymentService
from app.services.payment_qr_service import PaymentQrService
from app.services.subscription_currency_service import (
    SubscriptionCurrencyService,
    format_subscription_price,
)
from app.services.subscription_price_service import SubscriptionPriceService
from app.bot.utils.discount_formatter import build_admin_discount_block, build_discount_plan_line
from app.bot.utils.i18n import t
from app.bot.keyboards.subscription import (
    admin_discount_entry_keyboard,
    admin_discount_plan_keyboard,
    discount_payment_method_keyboard,
    feedback_discount_payment_method_keyboard,
    feedback_discount_plan_keyboard,
    subscription_discount_progress_keyboard,
    subscription_discount_ready_keyboard,
    payment_method_keyboard,
)
from app.bot.keyboards.checkout import checkout_keyboard


router = Router()
PAYMENT_METHODS = ("visa", "alipay", "wechat")
PLANS = ("10_days", "1_month")


def _parse_campaign_id(value: str | None) -> int | None:
    if not value:
        return None
    try:
        campaign_id = int(value)
    except (TypeError, ValueError):
        return None
    return campaign_id if campaign_id > 0 else None


def _campaign_back_callback(name: str, campaign_id: int | None) -> str:
    return f"discount_offer:{name}:{campaign_id}" if campaign_id else f"discount_offer:{name}"


async def _plan_price(session, plan_type: str, payment_method: str | None) -> tuple[int, str]:
    price = await SubscriptionPriceService(session).get_price(payment_method, plan_type)
    if price:
        return price.amount, price.currency
    if payment_method in ("alipay", "wechat"):
        return (66 if plan_type == "1_month" else 29), "¥"
    return (89 if plan_type == "1_month" else 29), "TJS"


async def _visa_local_hint(session, amount: int, currency: str) -> str:
    return ""


def _is_card_currency(currency: str) -> bool:
    return (currency or "").strip().lower() in {"tjs", "somoni", "сомони"}


def _card_payment_note(lang: str) -> str:
    notes = {
        "tj": "💳 Бо ҳар гуна корти бонкӣ метавонед пардохт кунед.",
        "ru": (
            "💳 Можно оплатить любой банковской картой.\n"
            "Если ваша карта не в TJS, оплатите эквивалент суммы в TJS по курсу вашего банка на эту карту."
        ),
        "uz": (
            "💳 Istalgan bank kartasi orqali to'lov qilishingiz mumkin.\n"
            "Agar kartangiz TJSda bo'lmasa, bankingiz kursi bo'yicha TJS ekvivalentini shu kartaga yuboring."
        ),
    }
    return notes.get(lang, notes["ru"])


def _card_texts(lang: str) -> dict[str, str]:
    texts = {
        "tj": {
            "main_title": "💎 <b>Тарифҳои обуна</b>",
            "benefits": "Обуна гиред ва аз бот бе лимит истифода баред.",
            "card_note_short": "💳 Бо ҳар гуна корти бонкӣ метавонед пардохт кунед.",
            "card_note_full": (
                "Агар корти шумо корти Тоҷикистон набошад, маблағро бо қурби бонки худ "
                "дар TJS ҳисоб карда ба ҳамин корт фиристед."
            ),
            "referral_hint": "🎁 3 дӯсти нав даъват кунед ва 20% тахфиф гиред.",
            "choose": "👇 <b>Тарифро интихоб кунед:</b>",
            "checkout_title": "💳 Шумо обунаро интихоб кардед",
            "plan_label": "Тариф",
            "price_label": "Нарх",
            "bank_label": "Бонк",
            "bank_name": "DC city",
            "payment_details_label": "Реквизити пардохт",
            "send_screenshot": "Пас аз пардохт скриншотро фиристед.",
        },
        "ru": {
            "main_title": "💎 <b>Тарифы подписки</b>",
            "benefits": "Оформите подписку и пользуйтесь ботом без ограничений.",
            "card_note_short": "💳 Можно оплатить любой банковской картой.",
            "card_note_full": (
                "Если ваша карта не таджикская, рассчитайте сумму в TJS по курсу вашего банка "
                "и отправьте на эту карту."
            ),
            "referral_hint": "🎁 Пригласите 3 новых друзей и получите скидку 20%.",
            "choose": "👇 <b>Выберите тариф:</b>",
            "checkout_title": "💳 Вы выбрали подписку",
            "plan_label": "Тариф",
            "price_label": "Цена",
            "bank_label": "Банк",
            "bank_name": "DC city",
            "payment_details_label": "Реквизиты для оплаты",
            "send_screenshot": "После оплаты отправьте скриншот.",
        },
        "uz": {
            "main_title": "💎 <b>Obuna tariflari</b>",
            "benefits": "Obuna oling va botdan limitsiz foydalaning.",
            "card_note_short": "💳 Istalgan bank kartasi orqali to'lov qilishingiz mumkin.",
            "card_note_full": (
                "Agar kartangiz Tojikiston kartasi bo'lmasa, o'z bankingiz kursi bo'yicha "
                "TJS valyutasida hisoblab shu kartaga yuboring."
            ),
            "referral_hint": "🎁 3 ta yangi do'st taklif qiling va 20% chegirma oling.",
            "choose": "👇 <b>Tarifni tanlang:</b>",
            "checkout_title": "💳 Siz obunani tanladingiz",
            "plan_label": "Tarif",
            "price_label": "Narx",
            "bank_label": "Bank",
            "bank_name": "DC city",
            "payment_details_label": "To'lov rekviziti",
            "send_screenshot": "To'lovdan keyin skrinshot yuboring.",
        },
    }
    return texts.get(lang, texts["ru"])


def _card_plan_label(plan_type: str, lang: str) -> str:
    labels = {
        "tj": {"10_days": "10 рӯз", "1_month": "1 моҳ"},
        "ru": {"10_days": "10 дней", "1_month": "1 месяц"},
        "uz": {"10_days": "10 kunlik", "1_month": "1 oylik"},
    }
    return labels.get(lang, labels["ru"]).get(plan_type, plan_type)


def _card_main_price(amount: int) -> str:
    return f"💸 {amount} TJS 🇹🇯"


def _card_checkout_price(amount: int) -> str:
    return f"💸 {amount} TJS"


def _card_main_plan_line(plan_type: str, lang: str, amount: int) -> str:
    return f"🗓️ {_card_plan_label(plan_type, lang)} — {_card_main_price(amount)}"


def _card_main_text(
    lang: str,
    price_10: tuple[int, str],
    price_1m: tuple[int, str],
    *,
    show_discount_hint: bool,
) -> str:
    texts = _card_texts(lang)
    plan_lines = "\n".join([
        _card_main_plan_line("10_days", lang, price_10[0]),
        _card_main_plan_line("1_month", lang, price_1m[0]),
        "",
        texts["card_note_short"],
    ])
    base = (
        f"{texts['main_title']}\n\n"
        f"{texts['benefits']}\n\n"
        f"<blockquote>{plan_lines}</blockquote>"
    )
    if show_discount_hint:
        base += f"\n\n{texts['referral_hint']}"
    return f"{base}\n\n{texts['choose']}"


def _card_checkout_text(lang: str, checkout_info: dict) -> str:
    texts = _card_texts(lang)
    plan_type = checkout_info["plan_type"]
    price = _card_checkout_price(checkout_info["final_amount"])
    details = settings.PAYMENT_DETAILS.strip()
    lines = [
        texts["checkout_title"],
        "",
        "<blockquote>"
        f"{texts['plan_label']}: 🗓️ {_card_plan_label(plan_type, lang)}\n"
        f"{texts['price_label']}: {price}\n"
        f"{texts['card_note_full']}"
        "</blockquote>",
        "",
        f"{texts['bank_label']}: 🏦 {texts['bank_name']}",
        f"{texts['payment_details_label']}:",
    ]
    if details:
        lines.append(details)
    lines.extend([
        "",
        texts["send_screenshot"],
    ])
    return "\n".join(lines)


async def _discount_plan_line(
    session,
    *,
    lang: str,
    plan: str,
    base: int,
    currency: str,
    percent: int = 0,
) -> str:
    final = int(round(base * (100 - percent) / 100)) if percent > 0 else base
    local_equivalents = ""
    if (currency or "").strip().lower() in {"usd", "$"}:
        local_equivalents = await SubscriptionCurrencyService(session).format_local_equivalents(final)
    return build_discount_plan_line(
        lang=lang,
        plan=plan,
        base=base,
        currency=currency,
        percent=percent,
        local_equivalents=local_equivalents,
    )


async def _admin_discount_choices(session, user):
    service = DiscountService(session)
    plan_choices = {}
    for plan in ("10_days", "1_month"):
        choice = await service.get_best_admin_discount(
            user=user,
            plan_type=plan,
            payment_method=user.payment_method,
        )
        if choice.source == "admin_campaign" and choice.ends_at and choice.starts_at:
            plan_choices[plan] = choice
    return plan_choices


async def _admin_discount_matrix(session, user, campaign_id: int | None = None):
    service = DiscountService(session)
    choices = {}
    for method in PAYMENT_METHODS:
        for plan in PLANS:
            if campaign_id:
                choice = await service.get_campaign_discount(
                    campaign_id=campaign_id,
                    user=user,
                    plan_type=plan,
                    payment_method=method,
                )
            else:
                choice = await service.get_best_admin_discount(
                    user=user,
                    plan_type=plan,
                    payment_method=method,
                )
            if choice.source == "admin_campaign" and choice.ends_at and choice.starts_at:
                choices[(method, plan)] = choice
    return choices


def _available_methods(choices: dict[tuple[str, str], object]) -> list[str]:
    return [method for method in PAYMENT_METHODS if any(key[0] == method for key in choices)]


def _available_plans(choices: dict[tuple[str, str], object], payment_method: str) -> list[str]:
    return [plan for plan in PLANS if (payment_method, plan) in choices]


async def _admin_discount_offer(session, user, lang: str, *, as_window: bool = False) -> str | None:
    plan_choices = await _admin_discount_choices(session, user)
    if not plan_choices:
        return None

    main_choice = max(plan_choices.values(), key=lambda item: item.percent)
    lines = []
    for plan in ("10_days", "1_month"):
        base, currency = await _plan_price(session, plan, user.payment_method)
        choice = plan_choices.get(plan)
        percent = choice.percent if choice else 0
        lines.append(
            await _discount_plan_line(
                session,
                lang=lang,
                plan=plan,
                base=base,
                currency=currency,
                percent=percent,
            )
        )

    return build_admin_discount_block(
        lang=lang,
        discount=main_choice,
        percent=main_choice.percent,
        starts_at=main_choice.starts_at,
        ends_at=main_choice.ends_at,
        quota_total=main_choice.quota_total,
        repeat_interval_days=main_choice.repeat_interval_days,
        plan_lines="\n".join(lines),
        discount_button_hint=not as_window,
        now=datetime.now(timezone.utc),
    )


def _plan_label(plan_type: str, lang: str) -> str:
    labels = {
        "tj": {"10_days": "10 рӯз", "1_month": "1 моҳ"},
        "ru": {"10_days": "10 дней", "1_month": "1 месяц"},
        "uz": {"10_days": "10 kunlik", "1_month": "1 oylik"},
    }
    return labels.get(lang, labels["ru"]).get(plan_type, plan_type)


def _discount_price_detail_line(
    *,
    lang: str,
    plan: str,
    base: int,
    final: int,
    currency: str,
    percent: int,
    icon: str = "📅",
) -> str:
    return "\n".join([
        f"{icon} <b>{_plan_label(plan, lang)}</b>",
        f"💰 {t('subscription_original_price_label', lang)}: "
        f"<s>{format_subscription_price(base, currency)}</s>",
        f"💎 {t('subscription_discounted_price_label', lang)}: "
        f"<b>{format_subscription_price(final, currency)}</b> (-{percent}%)",
    ])


def _discount_plan_card(
    *,
    lang: str,
    plan: str,
    base: int,
    final: int,
    currency: str,
    percent: int,
    icon: str,
) -> str:
    detail = _discount_price_detail_line(
        lang=lang,
        plan=plan,
        base=base,
        final=final,
        currency=currency,
        percent=percent,
        icon=icon,
    )
    return (
        "<blockquote>"
        f"{detail}"
        "</blockquote>"
    )


async def _visa_plan_line(session, plan_type: str, lang: str, amount: int, currency: str) -> str:
    price = format_subscription_price(amount, currency)
    return f"{_plan_label(plan_type, lang)} — {price}"


def _compact_plan_line(plan_type: str, lang: str, amount: int, currency: str) -> str:
    return f"🗓️ {_plan_label(plan_type, lang)} - {format_subscription_price(amount, currency)}"


async def build_subscription_main_text_for_user(session, user, lang: str) -> str:
    price_10 = await _plan_price(session, "10_days", getattr(user, "payment_method", None))
    price_1m = await _plan_price(session, "1_month", getattr(user, "payment_method", None))

    is_card_payment = all(
        _is_card_currency(currency)
        for _, currency in (price_10, price_1m)
    )
    if is_card_payment:
        return _card_main_text(lang, price_10, price_1m, show_discount_hint=not user.discount_used)
    else:
        plan_lines = "\n".join([
            _compact_plan_line("10_days", lang, price_10[0], price_10[1]),
            _compact_plan_line("1_month", lang, price_1m[0], price_1m[1]),
        ])
        base = (
            f"{t('subscription_main_title', lang)}\n\n"
            f"🚀 {t('subscription_main_visa_benefits', lang)}\n\n"
            f"{plan_lines}"
        )
        if not user.discount_used:
            base += f"\n\n{t('subscription_referral_hint', lang)}"
        return f"{base}\n\n{t('subscription_main_choose', lang)}"


async def build_subscription_discount_progress_text(
    session,
    lang: str,
    referral_link: str,
    count: int,
    discount_eligible: bool = False,
    discount_used: bool = False,
    payment_method: str = None,
) -> str:
    base = (
        f"{t('subscription_discount_title', lang)}\n\n"
        f"{t('subscription_discount_link_label', lang)}\n"
        f"{referral_link}\n\n"
        f"{t('subscription_discount_progress', lang, count=count)}"
    )

    if discount_eligible and not discount_used:
        price_10 = await _plan_price(session, "10_days", payment_method)
        price_1m = await _plan_price(session, "1_month", payment_method)
        discount_10 = int(round(price_10[0] * 0.8))
        discount_1m = int(round(price_1m[0] * 0.8))
        card_10 = _discount_plan_card(
            lang=lang,
            plan="10_days",
            base=price_10[0],
            final=discount_10,
            currency=price_10[1],
            percent=20,
            icon="📦",
        )
        card_1m = _discount_plan_card(
            lang=lang,
            plan="1_month",
            base=price_1m[0],
            final=discount_1m,
            currency=price_1m[1],
            percent=20,
            icon="🌟",
        )

        base += (
            f"\n\n{t('subscription_discount_ready', lang)}\n\n"
            f"{card_10}\n\n"
            f"{card_1m}"
        )

    return base


def build_subscription_main_keyboard_for_user(user, lang: str, show_referral: bool = True) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=t("subscription_button_10_days", lang),
                callback_data="subscription:plan:10_days",
            ),
            InlineKeyboardButton(
                text=t("subscription_button_1_month", lang),
                callback_data="subscription:plan:1_month",
            ),
        ],
    ]
    if show_referral and not user.discount_used:
        rows.append([
            InlineKeyboardButton(
                text=t("subscription_referral_discount_button", lang),
                callback_data="subscription:referral_discount",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text=t("payment_back", lang),
            callback_data="subscription:change_payment_method",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def build_subscription_main_view(session, user, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    return (
        await build_subscription_main_text_for_user(session, user, lang),
        build_subscription_main_keyboard_for_user(user, lang),
    )


async def build_admin_discount_entry_view(
    session,
    user,
    lang: str,
    campaign_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup] | None:
    choices = await _admin_discount_matrix(session, user, campaign_id=campaign_id)
    if not choices:
        return None
    return (
        t("subscription_admin_discount_entry_text", lang),
        admin_discount_entry_keyboard(lang, campaign_id=campaign_id),
    )


async def build_admin_discount_payment_view(
    session,
    user,
    lang: str,
    campaign_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup] | None:
    choices = await _admin_discount_matrix(session, user, campaign_id=campaign_id)
    methods = _available_methods(choices)
    if not methods:
        return None
    if len(methods) == 1:
        return await build_admin_discount_plan_view(
            session,
            user,
            lang,
            methods[0],
            choices=choices,
            campaign_id=campaign_id,
        )
    return (
        t("subscription_admin_discount_payment_choose", lang),
        discount_payment_method_keyboard(lang, methods, campaign_id=campaign_id),
    )


async def build_admin_discount_plan_view(
    session,
    user,
    lang: str,
    payment_method: str,
    *,
    choices: dict[tuple[str, str], object] | None = None,
    campaign_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup] | None:
    choices = choices or await _admin_discount_matrix(session, user, campaign_id=campaign_id)
    plans = _available_plans(choices, payment_method)
    if not plans:
        return None

    lines = []
    for plan in plans:
        choice = choices[(payment_method, plan)]
        base, currency = await _plan_price(session, plan, payment_method)
        lines.append(
            await _discount_plan_line(
                session,
                lang=lang,
                plan=plan,
                base=base,
                currency=currency,
                percent=choice.percent,
            )
        )

    back_callback = (
        _campaign_back_callback("back_payment", campaign_id)
        if len(_available_methods(choices)) > 1
        else _campaign_back_callback("back_entry", campaign_id)
    )
    return (
        t("subscription_admin_discount_plan_choose", lang, lines="\n".join(lines)),
        admin_discount_plan_keyboard(
            lang,
            plans=plans,
            payment_method=payment_method,
            campaign_id=campaign_id,
            back_callback=back_callback,
        ),
    )


async def _get_available_feedback_offer(session, user, feedback_id: int):
    return await BotFeedbackRepository(session).get_available_price_offer(
        feedback_id=feedback_id,
        telegram_id=user.telegram_id,
    )


async def build_feedback_discount_payment_view(
    session,
    user,
    lang: str,
    feedback_id: int,
) -> tuple[str, InlineKeyboardMarkup] | None:
    feedback = await _get_available_feedback_offer(session, user, feedback_id)
    if not feedback:
        return None
    return (
        t("feedback_price_offer_payment_choose", lang),
        feedback_discount_payment_method_keyboard(feedback.id, lang),
    )


async def build_feedback_discount_plan_view(
    session,
    user,
    lang: str,
    feedback_id: int,
    payment_method: str,
) -> tuple[str, InlineKeyboardMarkup] | None:
    feedback = await _get_available_feedback_offer(session, user, feedback_id)
    if not feedback:
        return None

    lines = []
    for plan in PLANS:
        base, currency = await _plan_price(session, plan, payment_method)
        final = int(round(base * 0.8))
        lines.append(
            _discount_price_detail_line(
                lang=lang,
                plan=plan,
                base=base,
                final=final,
                currency=currency,
                percent=20,
            )
        )

    return (
        t("feedback_price_offer_plan_choose", lang, lines="\n".join(lines)),
        feedback_discount_plan_keyboard(feedback.id, lang, payment_method),
    )


async def _replace_with_text(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    parse_mode: str | None = "HTML",
    disable_web_page_preview: bool = True,
) -> None:
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )
        return
    except Exception:
        pass

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
    )


async def _replace_with_expired_offer(callback: CallbackQuery, lang: str, key: str) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    await _replace_with_text(
        callback,
        t(key, lang),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def build_checkout_text(session, lang: str, checkout_info: dict) -> str:
    plan_type = checkout_info["plan_type"]
    base_amount = checkout_info["base_amount"]
    final_amount = checkout_info["final_amount"]
    discount_applied = checkout_info["discount_applied"]
    currency = checkout_info["currency"]
    is_qr = (currency == "¥")

    if _is_card_currency(currency):
        return _card_checkout_text(lang, checkout_info)

    if lang == "tj":
        plan_label = "10 рӯз" if plan_type == "10_days" else "1 моҳ"
        plan_line = f"📦 Тариф: <b>{plan_label}</b>"
    elif lang == "uz":
        plan_label = "10 kunlik" if plan_type == "10_days" else "1 oylik"
        plan_line = f"📦 Tarif: <b>{plan_label}</b>"
    else:
        plan_label = "10 дней" if plan_type == "10_days" else "1 месяц"
        plan_line = f"📦 Тариф: <b>{plan_label}</b>"

    title_key = "checkout_title_qr" if is_qr else "checkout_title_visa"
    local_hint = await _visa_local_hint(session, final_amount, currency)
    card_note = _card_payment_note(lang) if not is_qr else ""

    if not is_qr and not discount_applied:
        return "\n".join([
            t(title_key, lang),
            "",
            f"<blockquote>{plan_line} — 💵 {t('subscription_price_label', lang)}: "
            f"<b>{format_subscription_price(final_amount, currency)}</b>{local_hint}</blockquote>",
            "",
            card_note,
            "",
            f"{t('payment_details_label', lang)}: {settings.PAYMENT_DETAILS}",
            "",
            t("payment_send_screenshot", lang),
        ])

    lines = [
        t(title_key, lang),
        "",
        plan_line,
        "",
    ]

    if discount_applied:
        lines.append(
            f"💰 {t('subscription_original_price_label', lang)}: "
            f"<s>{format_subscription_price(base_amount, currency)}</s>"
        )
        percent = checkout_info.get("discount_percent", 20)
        lines.append(
            f"💎 {t('subscription_discounted_price_label', lang)}: "
            f"<b>{format_subscription_price(final_amount, currency)}</b> (-{percent}%)"
        )
    else:
        lines.append(
            f"💵 {t('subscription_price_label', lang)}: "
            f"<b>{format_subscription_price(final_amount, currency)}</b>"
        )
    if local_hint:
        lines.append(local_hint.lstrip())

    lines.append("")

    if is_qr:
        lines.append(t("checkout_qr_scan", lang))
    else:
        lines.append(card_note)
        lines.append("")
        lines.append(f"{t('payment_details_label', lang)}: {settings.PAYMENT_DETAILS}")

    lines.extend([
        "",
        t("payment_send_screenshot", lang),
    ])

    return "\n".join(lines)


@router.callback_query(F.data == "subscription:open")
async def subscription_open_handler(callback: CallbackQuery, session):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)

    if not user:
        await callback.answer()
        return

    lang = user.language if user.language else "ru"

    await callback.answer()
    await callback.message.edit_text(
        t("payment_method_choose", lang),
        reply_markup=payment_method_keyboard(lang),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("discount_offer:open"))
async def discount_offer_open_handler(callback: CallbackQuery, session):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)

    if not user:
        await callback.answer()
        return

    lang = user.language or "ru"
    parts = callback.data.split(":")
    campaign_id = _parse_campaign_id(parts[2] if len(parts) > 2 else None)
    await callback.answer()

    view = await build_admin_discount_payment_view(session, user, lang, campaign_id=campaign_id)
    if not view:
        await _replace_with_expired_offer(callback, lang, "subscription_admin_discount_expired")
        return

    text, keyboard = view
    await _replace_with_text(
        callback,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("feedback_discount:open:"))
async def feedback_discount_open_handler(callback: CallbackQuery, session):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    lang = user.language or "ru"
    feedback_id = int(callback.data.split(":")[2])
    view = await build_feedback_discount_payment_view(session, user, lang, feedback_id)
    if not view:
        await callback.answer()
        await _replace_with_expired_offer(callback, lang, "feedback_price_offer_expired")
        return

    await callback.answer()
    text, keyboard = view
    await _replace_with_text(
        callback,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("feedback_discount:method:"))
async def feedback_discount_method_handler(callback: CallbackQuery, session):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    parts = callback.data.split(":")
    feedback_id = int(parts[2])
    payment_method = parts[3]
    lang = user.language or "ru"

    if payment_method not in PAYMENT_METHODS:
        await callback.answer()
        await _replace_with_expired_offer(callback, lang, "feedback_price_offer_expired")
        return

    user.payment_method = payment_method
    await session.flush()

    view = await build_feedback_discount_plan_view(
        session,
        user,
        lang,
        feedback_id,
        payment_method,
    )
    if not view:
        await callback.answer()
        await _replace_with_expired_offer(callback, lang, "feedback_price_offer_expired")
        return

    await callback.answer()
    text, keyboard = view
    await _replace_with_text(
        callback,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("feedback_discount:plan:"))
async def feedback_discount_plan_handler(callback: CallbackQuery, session):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    parts = callback.data.split(":")
    feedback_id = int(parts[2])
    payment_method = parts[3]
    plan = parts[4]
    lang = user.language or "ru"

    if payment_method not in PAYMENT_METHODS or plan not in PLANS:
        await callback.answer()
        await _replace_with_expired_offer(callback, lang, "feedback_price_offer_expired")
        return

    feedback = await _get_available_feedback_offer(session, user, feedback_id)
    if not feedback:
        await callback.answer()
        await _replace_with_expired_offer(callback, lang, "feedback_price_offer_expired")
        return

    user.payment_method = payment_method
    await session.flush()

    payment_service = PaymentService(session)
    payment, checkout_info, error_key = await payment_service.create_checkout_draft(
        telegram_id=callback.from_user.id,
        plan_type=plan,
        force_feedback_discount=True,
        feedback_id=feedback.id,
    )

    if not payment or not checkout_info or checkout_info.get("discount_source") != "feedback_price_offer":
        await callback.answer()
        await _replace_with_expired_offer(callback, lang, "feedback_price_offer_expired")
        return

    await user_repo.set_selected_plan_type(user, plan)
    await _show_checkout(callback, user_repo, user, lang, plan, checkout_info)
    await session.commit()
    await callback.answer()


@router.callback_query(F.data.startswith("discount_offer:method:"))
async def discount_offer_method_handler(callback: CallbackQuery, session):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    parts = callback.data.split(":")
    campaign_id = None
    payment_method = None
    if len(parts) >= 4:
        campaign_id = _parse_campaign_id(parts[2])
        payment_method = parts[3] if campaign_id else parts[2]
    elif len(parts) >= 3:
        payment_method = parts[2]

    if payment_method not in PAYMENT_METHODS:
        await callback.answer()
        await _replace_with_expired_offer(callback, user.language or "ru", "subscription_admin_discount_expired")
        return

    user.payment_method = payment_method
    await session.commit()

    lang = user.language or "ru"
    view = await build_admin_discount_plan_view(
        session,
        user,
        lang,
        user.payment_method,
        campaign_id=campaign_id,
    )
    await callback.answer()
    if not view:
        await _replace_with_expired_offer(callback, lang, "subscription_admin_discount_expired")
        return

    text, keyboard = view
    await _replace_with_text(
        callback,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("discount_offer:change_payment"))
async def discount_offer_change_payment_handler(callback: CallbackQuery, session):
    user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return
    lang = user.language or "ru"
    parts = callback.data.split(":")
    campaign_id = _parse_campaign_id(parts[2] if len(parts) > 2 else None)
    await callback.answer()
    view = await build_admin_discount_payment_view(session, user, lang, campaign_id=campaign_id)
    if not view:
        await _replace_with_expired_offer(callback, lang, "subscription_admin_discount_expired")
        return
    text, keyboard = view
    await _replace_with_text(
        callback,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("discount_offer:back_entry"))
async def discount_offer_back_entry_handler(callback: CallbackQuery, session):
    user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return
    lang = user.language or "ru"
    parts = callback.data.split(":")
    campaign_id = _parse_campaign_id(parts[2] if len(parts) > 2 else None)
    view = await build_admin_discount_entry_view(session, user, lang, campaign_id=campaign_id)
    await callback.answer()
    if not view:
        await _replace_with_expired_offer(callback, lang, "subscription_admin_discount_expired")
        return
    text, keyboard = view
    await _replace_with_text(
        callback,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("discount_offer:back_payment"))
async def discount_offer_back_payment_handler(callback: CallbackQuery, session):
    user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return
    lang = user.language or "ru"
    parts = callback.data.split(":")
    campaign_id = _parse_campaign_id(parts[2] if len(parts) > 2 else None)
    view = await build_admin_discount_payment_view(session, user, lang, campaign_id=campaign_id)
    await callback.answer()
    if not view:
        await _replace_with_expired_offer(callback, lang, "subscription_admin_discount_expired")
        return
    text, keyboard = view
    await _replace_with_text(
        callback,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "subscription:referral_discount")
async def subscription_referral_discount_handler(callback: CallbackQuery, session):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)

    if not user:
        await callback.answer()
        return

    # Guard: if user already used discount — ignore silently
    if user.discount_used:
        await callback.answer()
        return

    await user_repo.ensure_referral_code(user)

    # Only start the offer once — do NOT reset count on repeated clicks
    if not user.discount_offer_started_at:
        await user_repo.start_discount_offer(user)

    await session.flush()

    lang = user.language if user.language else "ru"
    referral_link = f"https://t.me/{settings.BOT_USERNAME}?start={user.referral_code}"
    count = user.discount_referral_count

    text = await build_subscription_discount_progress_text(
        session,
        lang,
        referral_link,
        count,
        discount_eligible=user.discount_eligible,
        discount_used=user.discount_used,
        payment_method=user.payment_method,
    )
    keyboard = (
        subscription_discount_ready_keyboard(lang)
        if user.discount_eligible and not user.discount_used
        else subscription_discount_progress_keyboard(lang)
    )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )

    await user_repo.set_discount_progress_message(
        user=user,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    await session.commit()
    await callback.answer()


@router.callback_query(F.data == "subscription:back_to_main")
async def subscription_back_to_main_handler(callback: CallbackQuery, session):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)

    if not user:
        await callback.answer()
        return

    lang = user.language if user.language else "ru"
    text, keyboard = await build_subscription_main_view(session, user, lang)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    await user_repo.clear_discount_progress_message(user)
    await session.commit()


@router.callback_query(F.data == "payment:visa")
async def payment_visa_handler(callback: CallbackQuery, session):

    await callback.answer()

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        return

    user.payment_method = "visa"
    await session.commit()

    lang = user.language if user.language else "ru"
    text, keyboard = await build_subscription_main_view(session, user, lang)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "payment:alipay")
async def payment_alipay_handler(callback: CallbackQuery, session):

    await callback.answer()

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        return

    user.payment_method = "alipay"
    await session.commit()

    lang = user.language if user.language else "ru"
    text, keyboard = await build_subscription_main_view(session, user, lang)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "payment:wechat")
async def payment_wechat_handler(callback: CallbackQuery, session):

    await callback.answer()

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        return

    user.payment_method = "wechat"
    await session.commit()

    lang = user.language if user.language else "ru"
    text, keyboard = await build_subscription_main_view(session, user, lang)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "checkout:change_plan")
async def checkout_change_plan_handler(callback: CallbackQuery, session):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)

    if not user:
        await callback.answer()
        return

    lang = user.language if user.language else "ru"

    draft = await PaymentRepository(session).get_latest_draft_by_user(callback.from_user.id)
    await user_repo.set_selected_plan_type(user, None)
    await session.commit()

    if draft and draft.discount_source == "admin_campaign":
        view = await build_admin_discount_plan_view(
            session,
            user,
            lang,
            draft.payment_method or user.payment_method or "visa",
            campaign_id=draft.discount_campaign_id,
        )
        if not view:
            await _replace_with_expired_offer(callback, lang, "subscription_admin_discount_expired")
            return
        text, keyboard = view
        await _replace_with_text(
            callback,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        await callback.answer()
        return

    if draft and draft.discount_source == "feedback_price_offer":
        feedback = await BotFeedbackRepository(session).get_latest_available_price_offer(callback.from_user.id)
        if not feedback:
            await _replace_with_expired_offer(callback, lang, "feedback_price_offer_expired")
            return
        view = await build_feedback_discount_plan_view(
            session,
            user,
            lang,
            feedback.id,
            draft.payment_method or user.payment_method or "visa",
        )
        if not view:
            await _replace_with_expired_offer(callback, lang, "feedback_price_offer_expired")
            return
        text, keyboard = view
        await _replace_with_text(
            callback,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        await callback.answer()
        return

    text, keyboard = await build_subscription_main_view(session, user, lang)

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        # message is a photo (QR checkout) — delete and send new text message
        await callback.message.delete()
        await callback.message.answer(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    await callback.answer()


async def _show_checkout(callback: CallbackQuery, user_repo: UserRepository, user, lang: str, plan: str, checkout_info: dict):
    text = await build_checkout_text(user_repo.session, lang, checkout_info)
    keyboard = checkout_keyboard(lang)

    checkout_msg_id: int | None = None

    if checkout_info["currency"] == "¥":
        qr = await PaymentQrService(user_repo.session).get_checkout_qr(
            payment_method=user.payment_method,
            plan_type=plan,
            amount=checkout_info["final_amount"],
            currency=checkout_info["currency"],
            discount_percent=checkout_info.get("discount_percent", 0),
        )
        if qr:
            photo = qr.file_id if qr.file_id else FSInputFile(qr.file_path)
            try:
                await callback.message.delete()
            except Exception:
                pass
            sent = await callback.message.answer_photo(
                photo,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            checkout_msg_id = sent.message_id
        else:
            missing_text = (
                f"{t('payment_qr_missing', lang)}\n\n"
                f"📦 <b>{_plan_label(plan, lang)}</b>\n"
                f"💵 {t('subscription_price_label', lang)}: "
                f"<b>{format_subscription_price(checkout_info['final_amount'], checkout_info['currency'])}</b>"
            )
            sent = await callback.message.edit_text(
                missing_text,
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            checkout_msg_id = callback.message.message_id
    else:
        try:
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            checkout_msg_id = callback.message.message_id
        except Exception:
            await callback.message.delete()
            sent = await callback.message.answer(
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            checkout_msg_id = sent.message_id

    await user_repo.set_pending_checkout_msg_id(user, checkout_msg_id)


@router.callback_query(F.data.startswith("discount_offer:plan:"))
async def discount_offer_plan_handler(callback: CallbackQuery, session):
    await callback.answer()

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        return

    lang = user.language or "ru"
    parts = callback.data.split(":")
    campaign_id = None
    if len(parts) >= 5:
        campaign_id = _parse_campaign_id(parts[2])
        if campaign_id:
            payment_method = parts[3]
            plan = parts[4]
        else:
            payment_method = parts[2]
            plan = parts[3]
    elif len(parts) >= 4:
        payment_method = parts[2]
        plan = parts[3]
    else:
        payment_method = user.payment_method
        plan = parts[-1]

    if payment_method not in PAYMENT_METHODS:
        payment_method = None

    if plan not in PLANS:
        await _replace_with_expired_offer(callback, lang, "subscription_admin_discount_expired")
        return

    if not payment_method:
        view = await build_admin_discount_payment_view(session, user, lang, campaign_id=campaign_id)
        if not view:
            await _replace_with_expired_offer(callback, lang, "subscription_admin_discount_expired")
            return
        text, keyboard = view
        await _replace_with_text(
            callback,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    user.payment_method = payment_method
    await session.flush()

    payment_service = PaymentService(session)
    payment, checkout_info, error_key = await payment_service.create_checkout_draft(
        telegram_id=callback.from_user.id,
        plan_type=plan,
        force_admin_discount=True,
        admin_discount_campaign_id=campaign_id,
    )

    if (
        not payment
        or not checkout_info
        or checkout_info.get("discount_source") != "admin_campaign"
        or (campaign_id and checkout_info.get("discount_campaign_id") != campaign_id)
    ):
        await _replace_with_expired_offer(callback, lang, "subscription_admin_discount_expired")
        return

    await user_repo.set_selected_plan_type(user, plan)
    await _show_checkout(callback, user_repo, user, lang, plan, checkout_info)
    await session.commit()


@router.callback_query(F.data.startswith("subscription:plan:"))
async def subscription_plan_handler(callback: CallbackQuery, session):
    await callback.answer()

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)

    if not user:
        return

    lang = user.language or "ru"

    if not user.payment_method:
        await callback.message.edit_text(
            t("payment_method_choose", lang),
            reply_markup=payment_method_keyboard(lang),
            parse_mode="HTML",
        )
        return

    plan = callback.data.split(":")[-1]

    payment_service = PaymentService(session)
    payment, checkout_info, error_key = await payment_service.create_checkout_draft(
        telegram_id=callback.from_user.id,
        plan_type=plan,
    )

    if not payment or not checkout_info:
        if error_key:
            await callback.message.answer(t(error_key, lang))
        return

    await user_repo.set_selected_plan_type(user, plan)
    await _show_checkout(callback, user_repo, user, lang, plan, checkout_info)
    await session.commit()


@router.callback_query(F.data == "payment:back")
async def payment_back_handler(callback: CallbackQuery, session):
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "payment:retry")
async def payment_retry_handler(callback: CallbackQuery, session):
    from app.repositories.user_repo import UserRepository

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    lang = user.language if user.language else "ru"
    text, keyboard = await build_subscription_main_view(session, user, lang)
    await callback.answer()
    await callback.message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "subscription:change_payment_method")
async def subscription_change_payment_method_handler(callback: CallbackQuery, session):
    await callback.answer()

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)

    if not user:
        return

    lang = user.language if user.language else "ru"

    await callback.message.edit_text(
        t("payment_method_choose", lang),
        reply_markup=payment_method_keyboard(lang),
        parse_mode="HTML",
    )
