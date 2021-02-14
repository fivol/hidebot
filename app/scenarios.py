import math
from enum import Enum, auto
import typing as t
from telebot.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, \
    ReplyKeyboardMarkup, KeyboardButton

from app.base_scenario import BaseScenario, RedirectException
from app.config import CONTENT_ITEMS_LIMIT
from app.constants import HELLO_MESSAGE
from app.db import DBContent


class CallbackQueryData:
    CREATE_PUBLIC_ROOM = 'public_room'
    CREATE_PRIVATE_ROOM = 'private_room'


class TextCommands:
    ENTER_ROOM = 'Зайти в комнату'
    CREATE_ROOM = 'Создать комнату'


class BotSignalType(Enum):
    COMMAND = auto()
    PLAIN_TEXT = auto()
    CALLBACK = auto()
    MEDIA = auto()


class HelloScenario(BaseScenario):

    def before(self):
        self.handler.create_member(self.message.from_user)

    def start(self):
        self.send_message(HELLO_MESSAGE, reply_markup=ReplyKeyboardRemove())
        self.send_message('Теперь создайте свою первую комнату')
        raise RedirectException(MainMenuScenario, 'Создать комнату')

    def default_response(self):
        self.send_message('Наберите /start', reply_markup=ReplyKeyboardRemove())

    default = True

    routes = {
        '/start': start,
    }


class MainMenuScenario(BaseScenario):
    keyboard = ReplyKeyboardMarkup(True)
    keyboard.add(
        KeyboardButton('Список комнат'),
        KeyboardButton('Создать комнату'),
    )

    def after(self):
        pass
        # self.delete_messages(self.handler.get_old_messages())

    def create_room(self):
        new_room_keyboard = InlineKeyboardMarkup()
        new_room_keyboard.add(InlineKeyboardButton('Публичную', callback_data='create_public_room'),
                              InlineKeyboardButton('Приватную', callback_data='create_private_room'))
        self.send_message('Хотите создать публичную или приватную?', reply_markup=new_room_keyboard)

    def room_created(self, name=''):
        text = 'Комната создана'
        if name:
            text = 'Комната "{}" создана'.format(name)
        self.send_message(text)

    def create_public_room(self):
        self.send_message('Введите название комнаты')
        self.set_state(self, self.public_room_done)

    def public_room_done(self):
        """Пользователь прислал название комнаты"""
        name = self.text
        if not name:
            self.send_message('Введите название')
            return
        room = self.handler.create_room(is_private=False, name=name)
        if not room:
            self.send_message('Невозможно создать комнату (возможно такое название уже существует)')
            return
        self.room_created(name)

    def _private_room_done(self):
        """Пользователь прислал ключ скрытой комнаты"""
        self.delete_current_message()
        self.handler.create_room(is_private=True, key=self.message.text)
        self.room_created()

    def handle_new_room_key(self):
        key = self.text
        if not key:
            self.send_message('Пришлите пароль, его можно будет потом изменить')
            return
        if len(key) < 3:
            self.send_message('Слишком короткий')
        elif len(key) > 30:
            self.send_message('Слишком большой')
        else:
            self._private_room_done()
            return
        self.set_state(self, self.handle_new_room_key)

    def create_private_room(self):
        self.send_message(
            'Введите ключ для приватной комнаты\nВнимание! Его нужно обязательно запомнить. '
            'Чтоб зайти в комнату, вам нужно будет ввести именно этот ключ', reply_markup=ReplyKeyboardRemove())
        self.set_state(self, self.handle_new_room_key)

    def rooms_list(self):
        rooms = self.handler.get_public_rooms()
        keyboard = InlineKeyboardMarkup()
        for room in rooms:
            keyboard.add(InlineKeyboardButton(room.name, callback_data=room.name))
        if len(rooms):
            self.send_message(
                'Это ваши публичные комнаты\nЧтобы открыть приватную, пришлите ключ текстом', reply_markup=keyboard)
        else:
            self.send_message('У вас нет публичных комнат, чтобы зайти в приватную, пришлите ее ключ текстом')

    def open(self):
        self.send_message('Главное меню')

    def try_open_room(self):
        room = self.handler.get_room(name=self.call_data or self.text, key=self.text)
        if not room:
            self.send_message('Комната не найдена')
            return
        self.handler.member.curr_room_id = room.id
        raise RedirectException(ExploreRoomScenario, ExploreRoomScenario.show_content)

    def default_response(self):
        self.try_open_room()

    PUBLIC_ROOM = 'PUBLIC_ROOM'

    routes = {
        'Создать комнату': create_room,
        'Список комнат': rooms_list,
    }


class ExploreRoomScenario(BaseScenario):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton('Главное меню'))
    keyboard.add(KeyboardButton('Удалить комнату'))

    available_content_types = [
        'text', 'photo', 'voice', 'video', 'video_note'
    ]

    TEMP_MESSAGES_KEY = 'temp-content'

    def next(self):
        self.set_state(page_num=self.handler.member.state.get('page_num', 0) + 1)
        self.print_content_block(self.handler.member.state['page_num'])

    def prev(self):
        self.set_state(page_num=self.handler.member.state.get('page_num', 0) - 1)
        self.print_content_block(self.handler.member.state['page_num'])

    def add_content(self):
        if self.message.content_type not in self.available_content_types:
            self.send_message('Такой тип контента не поддерживается')
            return
        file_id = None
        content_type = self.message.content_type

        if content_type in ['voice', 'video', 'video_note']:
            file_id = getattr(self.message, content_type).file_id
        if content_type in ['photo']:
            file_id = getattr(self.message, content_type)[-1].file_id

        self.handler.add_content(
            content_type=content_type,
            text=self.text,
            file_id=file_id
        )
        if self.handler.room.is_private:
            self.delete_current_message()

    def show_content(self):
        self.delete_current_message()
        content_count = self.handler.get_room_content_count()
        if self.handler.room.name:
            self.send_message('Открыта комната {}'.format(self.handler.room.name))
        else:
            self.send_message('Открыта секретная комната ****{}'.format(self.handler.room.key[-1]))
        if not content_count:
            self.send_message('Пока комната пуста. Пришлите файлы сюда чтобы добавить')
            return
        self.send_message('-----------------')
        self.print_content_block()

    def _delete_temp_messages(self):
        old_content = self.handler.get_messages_by_key(self.TEMP_MESSAGES_KEY)
        self.delete_messages(old_content)

    def print_content_block(self, page_num=0):
        self._delete_temp_messages()

        limit = CONTENT_ITEMS_LIMIT
        shift = limit * page_num
        pages_count = math.ceil(self.handler.get_room_content_count() / limit)
        content_items = self.handler.get_content(shift=shift, limit=limit)
        self._print_content_list(content_items)
        keyboard = InlineKeyboardMarkup()
        buttons = []
        if page_num > 0:
            buttons.append(InlineKeyboardButton('Предыдущая', callback_data='prev'))
        if page_num + 1 < pages_count:
            buttons.append(InlineKeyboardButton('Следующая', callback_data='next'))
        keyboard.add(*buttons)
        self.send_message('Страница {} из {}'.format(page_num + 1, pages_count), reply_markup=keyboard,
                          key=self.TEMP_MESSAGES_KEY)

    def _print_content_list(self, items: t.List[DBContent]):
        content_type_method = {
            'text': self.bot.send_message,
            'photo': self.bot.send_photo,
            'voice': self.bot.send_voice,
            'video': self.bot.send_video,
            'video_note': self.bot.send_video_note,
        }
        for item in items:
            if item.content_type not in content_type_method:
                continue
            send_method = content_type_method[item.content_type]
            message = send_method(self.chat_id, item.file_id or item.text, disable_notification=True)
            self.handler.add_message(message.id, key=self.TEMP_MESSAGES_KEY)

    def default_response(self):
        self.add_content()

    def to_menu(self):
        self._delete_temp_messages()
        raise RedirectException(MainMenuScenario, MainMenuScenario.open)

    def confirm_delete_room(self):
        if self.text == self.handler.room.name or self.text == self.handler.room.key:
            self.handler.delete_room()
            self.send_message('Комната удалена')
            self.to_menu()
        else:
            self.send_message('Имя неверно, удаление отклонено')

    def delete_room(self):
        self.send_message(
            'Если вы действительно хотите удалить комнату со всем ее содержимым, пришлите ее название / ключ')
        self.set_state(self, self.confirm_delete_room)

    routes = {
        'next': next,
        'prev': prev,
        'Главное меню': to_menu,
        'Удалить комнату': delete_room
    }

    input_messages_key = TEMP_MESSAGES_KEY


class AddContentScenario(BaseScenario):
    def add_content(self):
        content_type = self.message.content_type
        file_id = None
        if content_type in ['video_note', 'voice', 'document', 'audio', 'video']:
            file_id = getattr(self.message, content_type).file_id
        elif content_type == 'photo':
            file_id = getattr(self.message, content_type)[-1].file_id
        if file_id or self.text:
            self.handler.add_content(content_type, self.text, file_id)

        self.send_message('Добавлено')
