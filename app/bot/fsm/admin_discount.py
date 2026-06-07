from aiogram.fsm.state import State, StatesGroup


class DiscountStates(StatesGroup):
    waiting_target_identifier = State()
    waiting_title = State()
    waiting_percent = State()
    waiting_custom_duration = State()
    waiting_start_at = State()
    waiting_repeat_days = State()
    waiting_quota = State()
    waiting_payment_qr = State()
    waiting_notify_media = State()
