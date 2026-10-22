from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.telegram.callbacks import NoopCallback

router = Router(name="fallback")


@router.callback_query(NoopCallback.filter())
async def ignore_info_button(callback: CallbackQuery, bot: Bot) -> None:
    await bot.answer_callback_query(callback.id)


@router.message(~F.text)
async def reply_only_text(message: Message, bot: Bot) -> None:
    await bot.send_message(chat_id=message.chat.id, text=texts.ONLY_TEXT)
