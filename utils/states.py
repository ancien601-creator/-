from aiogram.fsm.state import State, StatesGroup


class ClassicContest(StatesGroup):
    select_channel = State()
    enter_content = State()
    enter_content_photo = State()
    select_finish_condition = State()
    enter_finish_value = State()
    enter_winners_count = State()
    select_button_text = State()
    enter_custom_button_text = State()
    enter_sponsors = State()
    confirm = State()


class SlotsContest(StatesGroup):
    select_channel = State()
    enter_content = State()
    enter_content_photo = State()
    enter_slots_count = State()
    select_payment_type = State()
    enter_slot_price = State()
    enter_sponsors = State()
    confirm = State()


class AddChannel(StatesGroup):
    waiting_channel = State()
