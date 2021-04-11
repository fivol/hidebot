"""
Чтобы запустить бота, нужно исполнить этот файл, начнется бесконечный пуллинг запросов
"""

from telebot.types import Message, CallbackQuery
from telebot import TeleBot

from app.base_scenario import BotSignal
from app.config import *
from app.scenario_runner import ScenarioRunner

bot = TeleBot(BOT_API_KEY)


class BotMessagesRouter:
    bot = bot
    """
    Единственная часть приложения, которая принимает сигналы непосредственно от
    telegram API
    Перенаправляет все на ScenarioRunner
    """

    @staticmethod
    @bot.callback_query_handler(func=lambda call: True)
    def main_callback_handler(call: CallbackQuery):
        ScenarioRunner.process_signal(
            BotSignal(call=call, bot=BotMessagesRouter.bot)
        )

    @staticmethod
    @bot.message_handler(
        content_types=['audio', 'photo', 'voice', 'video', 'sticker', 'contact', 'location', 'animation',
                       'document', 'text', 'video_note', 'left_chat_member', 'new_chat_members'])
    def main_handler(message: Message):
        ScenarioRunner.process_signal(
            BotSignal(message=message, bot=BotMessagesRouter.bot)
        )
