import inspect
from dataclasses import dataclass

from telebot import TeleBot
from telebot.types import Message, CallbackQuery
import typing as t

from app.bot_utils import BotUtils
from app.config import logger
from app.db import DBMessage
from app.handlers import Handler

from concurrent.futures import ThreadPoolExecutor


@dataclass
class BotSignal:
    message: Message = None
    call: CallbackQuery = None
    bot: TeleBot = None


class ResolvedRoute:
    def __init__(self, value=None, args=()):
        self.value = value
        self.args = args

    def __bool__(self):
        return bool(self.value)


class RoutePattern:
    def __init__(self, text=None, func=None, regex=None, content_type=None):
        self.text = text
        self.func = func
        self.regex = regex
        self.content_type = content_type

    def fit_signal(self, signal: BotSignal, value):
        call_text = signal.call and signal.call.data or not signal.call and signal.message.text or ''
        resolved = self.fit_text(call_text, value)
        if resolved:
            return resolved
        if self.content_type == signal.message.content_type:
            return ResolvedRoute(value)
        return ResolvedRoute()

    def fit_text(self, text: str, value):
        assert isinstance(text, str)
        if self.text == text:
            return ResolvedRoute(value)
        if self.text and self.text.startswith('/') and text.startswith(self.text):
            return ResolvedRoute(value, tuple(text.split(' ')[1:]))
        if self.func and self.func(text):
            return ResolvedRoute(value)
        if self.regex:
            raise NotImplementedError
        return ResolvedRoute()

    def fit(self, text: str = None, signal=None, value=None):
        if signal:
            return self.fit_signal(signal, value)
        return self.fit_text(text, value)

    @classmethod
    def from_value(cls, value):
        if isinstance(value, str):
            return cls(text=value)
        if inspect.isfunction(value):
            return cls(func=value)
        raise TypeError


class MemberStateHandler(dict):
    """
    Класс обработчик состояние участника чата. Его можно интерактивно менять в сценарии
    Конструктор обрабатывает все случаи создания класса, для удобства это можно сделать
    очень коротко
    """

    @classmethod
    def to_str(cls, value):
        if isinstance(value, str):
            return value
        if hasattr(value, '__name__'):
            return value.__name__
        if isinstance(value, BaseScenario):
            return value.__class__.__name__
        return value

    def __init__(self, *args, **kwargs):
        state_dict = kwargs.copy()
        args_items = args

        if len(args_items) >= 1:
            state_dict['scenario'] = args_items[0]
        if len(args_items) >= 2:
            state_dict['appeal'] = args_items[1]
        if len(args_items) >= 3:
            state_dict['args'] = args_items[2:]

        if not kwargs and len(args) == 1:
            value = args[0]
            if isinstance(value, MemberStateHandler):
                state_dict = value.__state
            elif isinstance(value, dict):
                state_dict = value
            elif isinstance(value, list) or isinstance(value, tuple):
                state_dict = self.__class__(*value).__state
            elif value is None:
                state_dict = {}

        if state_dict.get('scenario'):
            state_dict['scenario'] = self.to_str(state_dict['scenario'])
        if state_dict.get('appeal'):
            state_dict['appeal'] = self.to_str(state_dict['appeal'])
        self.__state = state_dict
        assert isinstance(state_dict, dict)
        super().__init__(**state_dict)


class RedirectException(Exception):
    """В любом методе сценария можно кинуть это исключения и оно будет корректно обработано
    """

    def __init__(self, *args, process_signal=False, **kwargs):
        self.process_signal = process_signal
        self.state = MemberStateHandler(*args, **kwargs)


class StopSignalException(Exception):
    """Raise in before() or method to stop process signal"""
    pass


SINGLE_SHOW_KEY = 'SINGLE_SHOW_KEY'


class BaseScenario:
    """
    Базовый класс для создания сценариев. Остальные наследуются от него
    Реализует самые важные общие части функционала сценария
    Хранит данные обращения - message, call, bot
    Экземпляр этого класса создается каждый раз при обращении к боту
    """

    def __init__(self, message=None, call=None, bot=None, handler=None, first_time=True):
        self.message: Message = message
        self.call: CallbackQuery = call
        self.text: str = self.message.text or ''
        self.call_data = call and call.data or ''
        self.handler: Handler = handler
        self.chat_id = self.handler.chat_id
        self.bot: TeleBot = bot
        self.reply_keyboard = None
        self.utils = BotUtils(bot, handler=handler,
                              chat_id=self.chat_id,
                              user_id=self.message.from_user.id, )
        self.handler.create_member(self.message.from_user)
        if first_time and self.handler.member:
            self._handle_receive_message()

    def _handle_receive_message(self):
        self.delete_messages(self.handler.get_messages_by_key(SINGLE_SHOW_KEY))
        if not self.call_data:
            self.handler.add_message(
                message_id=self.message.id,
                is_from_bot=False,
                key=self.incoming_key,
                text=self.text
            )

    def send_message(self, text, *args, reply_markup=None, key=None, auto_delete=True, content_id: int = None,
                     **kwargs):
        if not text:
            return

        key = key or self.default_outgoing_key
        if auto_delete:
            key = SINGLE_SHOW_KEY

        if reply_markup is None:
            reply_markup = self.keyboard

        message = self.bot.send_message(self.chat_id, text, *args, reply_markup=reply_markup, parse_mode='Markdown',
                                        **kwargs)
        self.handler.add_message(message.id, is_from_bot=True, key=key, text=text, content_id=content_id)
        return message

    def delete_message(self, message_id: int, delete_from_db=True):
        deleted = True

        if delete_from_db:
            deleted = self.handler.delete_message(message_id)
        if deleted:
            self.bot.delete_message(self.chat_id, message_id)

    def delete_current_message(self):
        """Удаляет из чата только что отправленное пользователем сообщение"""
        if not self.message:
            return
        self.delete_message(message_id=self.message.id)

    def delete_messages(self, messages: t.List[DBMessage]):
        if not messages:
            return
        with ThreadPoolExecutor(max_workers=20) as executor:
            for message in messages:
                executor.submit(self.delete_message, message_id=message.message_id, delete_from_db=False)
        self.handler.delete_messages([m.id for m in messages])

    def send_file(self, file_id, content_type, caption=None):
        # TODO implement sending file
        pass

    def default_response(self):
        """Вызывается при отсутствии подходящего метода сценария"""
        self.send_message('NotImplementedError :(')

    def set_state(self, *args, **kwargs):
        if not self.handler.member:
            self.handler.create_member(self.message.from_user)
            # TODO Продумать, нужно ли здесь создавать пользователя
            # raise Exception('You must create user before using redirection')

        curr_member_state = self.handler.member.state or {}
        new_chat_state = {
            **curr_member_state,
            **dict(MemberStateHandler(*args, **kwargs))
        }
        self.handler.member.state = new_chat_state

    @property
    def state(self):
        return self.handler.member and MemberStateHandler(self.handler.member.state)

    @classmethod
    def update_state(cls, db_object, **new_state):
        curr_state = db_object and db_object.state or {}
        db_object.state = {**curr_state, **new_state}

    def is_group(self):
        return self.message.chat.type in ['group', 'supergroup']

    def is_private(self):
        return self.message.chat.type == 'private'

    def before(self):
        """Executes before main handler method"""
        pass

    def after(self):
        """Executes after main handler method"""
        pass

    def default_callback_answer(self):
        if self.call:
            self.bot.answer_callback_query(self.call.id)

    routes: dict = {}
    """
        routes это словарь для выбора метода
        Ключом является текст, значением метод или объект из которого можно сконструировать
        MemberStateHandler
        см описание ScenarioRunner для понятности
        Пример:
        routes = {
            '/start': start_method,
            'hello': hello_method,
            'Main menu': (MainMenuScenario, 'open_menu_method') # это передается в конструктор MemberStateHandler
        }
    """
    default = False
    """
        Если default == True, то сценарий выбирается при умолчанию, при отсутствии четкий указаний
        Только один наследник может иметь True, иначе будет ошибка
    """

    keyboard = None
    """
        Добавляет к сообщению из данного класса клавиатуру если она не определена
        (в классе наследнике можно указывать keyboard = ....)
    """

    incoming_key = None
    """
        Для каждого приходящего или отправленного сообщения ставится в соответствие ключ в базе данных
        Значение этого поля будет выставлено автоматически для сообщений пришедших в данном сценарии
        (переопределить в наследнике если необходимо)
    """
    default_outgoing_key = None
    """
        Если в функцию send_message не передан ключ, то по умолчанию ставится этот
    """
