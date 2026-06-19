from aiogram.fsm.state import State, StatesGroup

class ClassicCreation(StatesGroup):
    channel = State()
    content_text = State()
    content_photo = State()
    end_condition = State()
    end_value = State()
    winners_count = State()
    button_text = State()
    sponsors = State()
    confirm = State()

class SlotsCreation(StatesGroup):
    channel = State()
    content_text = State()
    content_photo = State()
    slots_count = State()
    payment = State()
    slot_price = State()
    sponsors = State()
    confirm = State()
