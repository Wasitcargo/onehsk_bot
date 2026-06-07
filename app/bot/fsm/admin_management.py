from aiogram.fsm.state import State, StatesGroup


class AdminPriceStates(StatesGroup):
    waiting_amount = State()
    waiting_qr = State()
    waiting_rate = State()


class AdminRequiredChannelStates(StatesGroup):
    waiting_channel = State()
