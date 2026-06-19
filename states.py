from aiogram.fsm.state import StatesGroup, State

class CreateContest(StatesGroup):
    channel = State()        # Ввод ID или username целевого канала
    content = State()        # Текст и/или фото конкурса
    finish_type = State()    # Выбор условия завершения
    winners_count = State()  # Количество победителей
    button_text = State()    # Текст на инлайн-кнопке под постом
    sponsors = State()       # Добавление спонсорских каналов
