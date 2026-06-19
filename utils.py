from aiogram import Bot
import json

async def check_subscriptions(bot: Bot, user_id: int, channels: list[str]) -> bool:
    """Проверяет подписку на каналы (передаются с @)."""
    for channel in channels:
        try:
            chat = await bot.get_chat(channel)
            member = await bot.get_chat_member(chat_id=chat.id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception as e:
            print(f"Ошибка проверки подписки на {channel}: {e}")
            return False
    return True

async def update_post_message(bot: Bot, contest: dict, new_text: str = None, reply_markup=None):
    """Обновляет пост в канале."""
    try:
        if new_text:
            await bot.edit_message_text(
                chat_id=contest['channel_id'],
                message_id=contest['message_id'],
                text=new_text,
                reply_markup=reply_markup
            )
        else:
            await bot.edit_message_reply_markup(
                chat_id=contest['channel_id'],
                message_id=contest['message_id'],
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Ошибка обновления поста: {e}")

def generate_contest_post(contest: dict) -> str:
    text = contest.get('text') or ""
    if contest['type'] == 'classic':
        if contest['end_condition'] == 'time':
            text += f"\n\n🕒 Итоги будут подведены {contest['end_value']} (МСК)."
        else:
            text += f"\n\n👥 Итоги после набора {contest['end_value']} участников."
        text += f"\n🎯 Победителей: {contest['winners_count']}"
    else:  # slots
        text += f"\n\n🎰 Слотов: {contest['slots_count']}"
        if contest['payment_required']:
            text += f"\n💰 Стоимость слота: {contest['slot_price']} ⭐"
        else:
            text += "\n🆓 Участие бесплатное"
    return text
