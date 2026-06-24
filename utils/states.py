from aiogram.fsm.state import State, StatesGroup


class ClassicContest(StatesGroup):
    select_channel = State()
    enter_content = State()
    select_finish_condition = State()
    enter_finish_value = State()
    enter_winners_count = State()
    select_button_text = State()
    enter_custom_button_text = State()
    enter_sponsors = State()
    confirm = State()


class SlotsContest(StatesGroup):
    select_channel = State()
    ask_content = State()
    enter_content = State()
    enter_slots_count = State()
    enter_max_attempts = State()
    select_payment_type = State()
    enter_slot_price = State()
    enter_sponsors = State()
    confirm = State()


class LotteryContest(StatesGroup):
    select_channel = State()
    ask_content = State()
    enter_content = State()
    select_payment_type = State()
    enter_ticket_price = State()
    enter_max_tickets = State()
    enter_sponsors = State()
    confirm = State()


class LotteryBuy(StatesGroup):
    enter_quantity = State()


class BattleContest(StatesGroup):
    select_channel = State()
    ask_content = State()
    enter_content = State()
    enter_limit = State()
    enter_round1_time = State()
    enter_round2_time = State()
    enter_round3_time = State()
    enter_sponsors = State()
    confirm = State()


class AddChannel(StatesGroup):
    waiting_channel = State()
