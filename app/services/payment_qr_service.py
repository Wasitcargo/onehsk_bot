from dataclasses import dataclass
from pathlib import Path

from app.repositories.bot_setting_repo import BotSettingRepository
from app.services.subscription_price_service import DEFAULT_SUBSCRIPTION_PRICES


QR_PAYMENT_METHODS = ("alipay", "wechat")

_STATIC_PAYMENTS = Path(__file__).resolve().parent.parent / "static" / "payments"

_STATIC_QR_FILES: dict[tuple[str, str, int], Path] = {
    ("alipay", "10_days", 0): _STATIC_PAYMENTS / "alipay_10_days.jpg",
    ("alipay", "10_days", 20): _STATIC_PAYMENTS / "alipay_10_days_discount.jpg",
    ("alipay", "1_month", 0): _STATIC_PAYMENTS / "alipay_1_month.jpg",
    ("alipay", "1_month", 20): _STATIC_PAYMENTS / "alipay_1_month_discount.jpg",
    ("wechat", "10_days", 0): _STATIC_PAYMENTS / "wechat_10_days.jpg",
    ("wechat", "10_days", 20): _STATIC_PAYMENTS / "wechat_10_days_discount.jpg",
    ("wechat", "1_month", 0): _STATIC_PAYMENTS / "wechat_1_month.jpg",
    ("wechat", "1_month", 20): _STATIC_PAYMENTS / "wechat_1_month_discount.jpg",
}


@dataclass(frozen=True)
class PaymentQrCode:
    file_id: str | None = None
    file_path: str | None = None


class PaymentQrService:
    def __init__(self, session):
        self.session = session
        self.settings = BotSettingRepository(session)

    @staticmethod
    def calculate_discounted_amount(amount: int, percent: int) -> int:
        return int(round(amount * (100 - percent) / 100))

    @staticmethod
    def _currency_key(currency: str | None) -> str:
        value = (currency or "").strip().lower()
        if value in {"¥", "yuan", "cny", "rmb"}:
            return "yuan"
        cleaned = "".join(ch for ch in value if ch.isalnum())
        return cleaned or "unknown"

    @classmethod
    def setting_key(cls, payment_method: str, amount: int, currency: str | None = "¥") -> str:
        return f"payment_qr:{payment_method}:{cls._currency_key(currency)}:{int(amount)}"

    @staticmethod
    def static_qr_path(
        *,
        payment_method: str | None,
        plan_type: str,
        amount: int,
        discount_percent: int = 0,
    ) -> str | None:
        method = payment_method if payment_method in QR_PAYMENT_METHODS else None
        if not method:
            return None

        default = DEFAULT_SUBSCRIPTION_PRICES.get((method, plan_type))
        if not default:
            return None

        default_amount = default[0]
        percent = int(discount_percent or 0)
        static_percent = None
        if percent == 0 and int(amount) == default_amount:
            static_percent = 0
        elif percent == 20 and int(amount) == PaymentQrService.calculate_discounted_amount(default_amount, 20):
            static_percent = 20

        if static_percent is None:
            return None

        path = _STATIC_QR_FILES.get((method, plan_type, static_percent))
        if path and path.exists():
            return str(path)
        return None

    async def get_dynamic_file_id(
        self,
        *,
        payment_method: str,
        amount: int,
        currency: str | None = "¥",
    ) -> str | None:
        if payment_method not in QR_PAYMENT_METHODS:
            return None
        value = await self.settings.get(self.setting_key(payment_method, amount, currency))
        return value.strip() if value else None

    async def set_dynamic_file_id(
        self,
        *,
        payment_method: str,
        amount: int,
        file_id: str,
        currency: str | None = "¥",
    ) -> None:
        if payment_method not in QR_PAYMENT_METHODS:
            return
        await self.settings.set(self.setting_key(payment_method, amount, currency), file_id)

    async def get_checkout_qr(
        self,
        *,
        payment_method: str | None,
        plan_type: str,
        amount: int,
        currency: str | None = "¥",
        discount_percent: int = 0,
    ) -> PaymentQrCode | None:
        static_path = self.static_qr_path(
            payment_method=payment_method,
            plan_type=plan_type,
            amount=amount,
            discount_percent=discount_percent,
        )
        if static_path:
            return PaymentQrCode(file_path=static_path)

        if payment_method not in QR_PAYMENT_METHODS:
            return None

        file_id = await self.get_dynamic_file_id(
            payment_method=payment_method,
            amount=amount,
            currency=currency,
        )
        return PaymentQrCode(file_id=file_id) if file_id else None

    async def has_checkout_qr(
        self,
        *,
        payment_method: str | None,
        plan_type: str,
        amount: int,
        currency: str | None = "¥",
        discount_percent: int = 0,
    ) -> bool:
        return bool(
            await self.get_checkout_qr(
                payment_method=payment_method,
                plan_type=plan_type,
                amount=amount,
                currency=currency,
                discount_percent=discount_percent,
            )
        )
