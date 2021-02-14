from app.config import BOT_ID
from app.handlers import Handler
from telebot import apihelper
import re


def get_exception_name(exc: apihelper.ApiTelegramException):
    return re.search(r': (\w+)', exc.result_json.get('description')).group(1)


class BotUtils:
    def __init__(self, bot, user_id=None, chat_id=None, message=None, handler=None):
        self.user_id = user_id
        self.chat_id = chat_id
        self.message = message
        self.bot = bot
        if not handler:
            handler = Handler(chat_id=chat_id, user_id=user_id)
        self.handler = handler

    def is_admin(self):
        is_admin = self.bot.get_chat_member(self.chat_id, BOT_ID).status == 'administrator'
        self.handler.chat.is_admin = is_admin
        self.handler.chat.save()
        return is_admin

    def kick_member(self, user_id=None):
        if not user_id:
            user_id = self.user_id
        self.bot.kick_chat_member(self.chat_id, user_id)
