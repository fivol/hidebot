from unittest.mock import Mock, seal

from app.base_scenario import BotSignal
from app.bot import BOT_ID
from random import randint

from app.config import MAIN_ADMIN_USERNAME
from app.db import DBMember
from app.scenario_runner import ScenarioRunner


class AttrDict(dict):
    __slots__ = ()
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class FakeUser:
    def __init__(self, chat, id=None, username=None, first_name=None, last_name=None):
        self.chat = chat
        self.id = id
        self.username = username or f'user_{id}'
        self.first_name = first_name
        self.last_name = last_name
        self.is_bot = False

    def send_message(self, text, **kwargs):
        return self.chat.send_message(text, from_user=self, **kwargs)


class FakeTelegramChat:
    def __init__(self, chat_id=None, chat_type='group', chat_username=None):
        self.messages = []
        self.mocked_bot = self._create_mocked_bot()
        self.ids = set()
        self.chat_username = chat_username
        self.chat_type = chat_type
        self.new_messages = []
        self.chat_id = chat_id or self._gen_new_id()
        self.bot_id = BOT_ID

    @property
    def bot_user(self):
        return self.get_new_user(id=self.bot_id)

    def send_message(self, text, from_user, **kwargs):
        mocked_message = self._create_mocked_message(text, from_user=from_user, **kwargs)
        self._send_signal(BotSignal(message=mocked_message, bot=self.mocked_bot))
        return mocked_message

    def send_call_data(self, data, from_user):
        mocked_call = self._create_mocked_call(data, from_user)
        self._send_signal(BotSignal(call=mocked_call, bot=self.mocked_bot))
        return mocked_call

    def get_new_user(self, id=None, **kwargs):
        return FakeUser(self, id=id or self._gen_new_id(), **kwargs)

    def get_admin_user(self):
        return self.get_new_user(username=MAIN_ADMIN_USERNAME)

    @property
    def members_count(self):
        return DBMember.query.filter(DBMember.chat_id == self.chat_id, DBMember.is_kicked.isnot(True)).count()

    @property
    def last_message(self):
        return self.new_messages and self.messages[-1] or None

    @property
    def new_messages_count(self):
        return len(self.new_messages)

    def _gen_new_id(self):
        id = randint(1, 100000)
        if id in self.ids:
            return self._gen_new_id()
        self.ids.add(id)
        return id

    def _create_mocked_bot(self):
        bot = Mock()
        bot.send_message = self._receive_message_handler
        bot.reply_to = self._receive_reply
        seal(bot)
        return bot

    def _receive_message_handler(self, chat_id, text, *args, reply_markup=None, **kwargs):
        message = AttrDict(chat_id=chat_id, text=text, reply_markup=reply_markup, args=args, **kwargs)

        self.messages.append(message)
        self.new_messages.append(message)

    def _receive_reply(self, reply_message, text, **kwargs):
        self._receive_message_handler(reply_message.chat.id, text, reply_message=reply_message, **kwargs)

    def _create_mocked_message(self, text=None, **kwargs):
        message = Mock()
        message.configure_mock(**{
            'id': self._gen_new_id(),
            'text': text,
            'chat.id': self.chat_id,
            'chat.type': self.chat_type,
            'chat.username': self.chat_username,
            'reply_to_message': None,
            'content_type': 'text',
            'new_chat_members': [],
            **kwargs
        })
        return message

    def _create_mocked_call(self, data, from_user):
        call = Mock(spec=True)
        call.data = data
        call.message = self._create_mocked_message(data, from_user=from_user)
        return call

    def _send_signal(self, signal):
        self.new_messages.clear()
        ScenarioRunner.process_signal(signal)
