import math
from concurrent.futures import as_completed
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum, auto
import typing as t

from sqlalchemy.exc import IntegrityError
from telebot.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, \
    InlineKeyboardMarkup, InlineKeyboardButton, User

from app.base_scenario import BaseScenario, RedirectException, StopSignalException
from app.config import CONTENT_ITEMS_LIMIT
from app.constants import HELLO_MESSAGE, REFERENCE
from app.db import DBContent


class BotSignalType(Enum):
    COMMAND = auto()
    PLAIN_TEXT = auto()
    CALLBACK = auto()
    MEDIA = auto()


class InlineButton:
    back = InlineKeyboardButton('⬅ Назад', callback_data='back')
    menu = InlineKeyboardButton('☰ Главное меню', callback_data='menu')
    reference = InlineKeyboardButton('📕 Справка', callback_data='reference')
    settings = InlineKeyboardButton('⚙ Настройки комнат', callback_data='settings')
    create_room = InlineKeyboardButton('📄 Создать комнату', callback_data='create_room')

    @staticmethod
    def with_callback(button: InlineKeyboardButton, callback_data: str):
        return InlineKeyboardButton(button.text, callback_data=callback_data)


class HelloScenario(BaseScenario):

    def before(self):
        self.handler.create_member(self.message.from_user)

    def start(self):
        self.send_message(HELLO_MESSAGE, reply_markup=ReplyKeyboardRemove())
        self.send_message('Теперь создайте свою первую комнату', auto_delete=True)
        raise RedirectException(MainMenuScenario, 'Создать комнату')

    def default_response(self):
        self.send_message('Наберите /start', reply_markup=ReplyKeyboardRemove())

    default = True

    routes = {
        '/start': start,
    }


class RoomsListUtils(BaseScenario):
    def _send_rooms_list(self, additional_buttons: list = None):
        rooms = self.handler.get_public_rooms()
        keyboard = InlineKeyboardMarkup()
        for room in rooms:
            keyboard.add(InlineKeyboardButton(room.name.capitalize(), callback_data=room.name))
        if additional_buttons:
            for btn in additional_buttons:
                keyboard.add(btn)
        keyboard.add(InlineButton.back)
        self.send_message('Пришлите ключ текстом, если хотите указать приватную комнату. Публичные:',
                          reply_markup=keyboard if len(rooms) else ReplyKeyboardRemove(), auto_delete=True)
        if len(rooms) == 0:
            self.send_message('У вас пока нет ни одной публичной комнаты', reply_markup=keyboard)

    def _accept_chosen_room(self):
        room_key = self._get_chosen_room_nickname()
        if not self.call_data:
            self.delete_current_message()
        room = self.handler.get_room(key=room_key, name=room_key)
        return room

    def _get_chosen_room_nickname(self):
        return (self.call_data or self.text or '').capitalize()

    def default_response(self):
        raise RedirectException('MainMenuScenario')


class RoomSettingsScenario(RoomsListUtils):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton('🗑 Удалить', callback_data='Удалить'),
                 InlineKeyboardButton('✏ Переименовать', callback_data='Переименовать'))
    keyboard.add(InlineKeyboardButton('🔑 Поменять видимость', callback_data='Поменять видимость'))
    keyboard.add(InlineButton.menu)

    # Do not use Enum in this
    class RoomAction:
        delete = 'DELETE'
        rename = 'RENAME'
        change_visibility = 'VISIBILITY'

    def open(self):
        self.send_message('Выберите действие', auto_delete=True)

    def delete_room(self):
        self._send_rooms_list()
        self.set_state(action=self.RoomAction.delete)

    def rename_room(self):
        self._send_rooms_list()
        self.set_state(action=self.RoomAction.rename)

    def change_visibility(self):
        self._send_rooms_list()
        self.set_state(action=self.RoomAction.change_visibility)

    def to_menu(self):
        raise RedirectException('MainMenuScenario', 'open')

    def _confirm_delete_room(self):
        if self.call_data == 'yes':
            self.handler.delete_room(self.state.get('room_id'))
            self.send_message('Комната удалена', auto_delete=True)
        else:
            self.open()

    def _confirm_rename_room(self):
        self.set_state(action=None)
        new_name = self.text
        if not new_name:
            self.send_message('Нужен новый ключ для комнаты', auto_delete=True)

        self.handler.rename_room(self.state.get('room_id'), new_name)
        self.delete_current_message()
        self.send_message('Комната теперь называется {}'.format(new_name), auto_delete=True)

    def _confirm_change_room_privacy(self):
        if self.call_data == 'yes':
            self.handler.change_room_privacy(self.state.get('room_id'))
            self.set_state(action=None)
            self.send_message('Готово!')
        else:
            self.open()

    def default_response(self):
        room = self._accept_chosen_room()
        room_key = self._get_chosen_room_nickname()
        if not room:
            self.send_message('Такой комнаты не существует', auto_delete=True)
            return

        yesno_keyboard = InlineKeyboardMarkup()
        yesno_keyboard.add(InlineKeyboardButton('Да', callback_data='yes'),
                           InlineKeyboardButton('Нет', callback_data='no'))

        action = self.state.get('action')
        if action == self.RoomAction.delete:
            # Проверка, действительно ли пользователь хочет удалить комнату
            self.set_state(self, self._confirm_delete_room, room_id=room.id)
            self.send_message('Вы уверены, что хотите безвозвратно удалить комнату "{}"?'.format(room_key),
                              reply_markup=yesno_keyboard, auto_delete=True)
        if action == self.RoomAction.rename:
            # Переименовать комнату
            self.set_state(self, self._confirm_rename_room, room_id=room.id)
            self.send_message('Введите новое название (если комната приватная, для нее будет заменен ключ доступа)',
                              reply_markup=ReplyKeyboardRemove(), auto_delete=True)

        if action == self.RoomAction.change_visibility:
            # Изменить видимость комнаты
            self.set_state(self, self._confirm_change_room_privacy, room_id=room.id)
            if room.is_private:
                self.send_message(
                    'Вы уверены, что хотите сделать комнату "{}" публичной? Ее можно будет переименовать'.format(
                        room_key),
                    reply_markup=yesno_keyboard, auto_delete=True)
            else:
                self.send_message(
                    'Вы уверены, что хотите сделать комнату "{}" приватной? '
                    'Ее ключ можно будет переименовать'.format(room_key),
                    reply_markup=yesno_keyboard, auto_delete=True)

    routes = {
        'back': open,
        'Удалить': delete_room,
        'Переименовать': rename_room,
        'Поменять видимость': change_visibility,
        'Меню': to_menu,
        'menu': to_menu,
    }


class ContentAddingScenario(RoomsListUtils):
    available_content_types = [
        'text', 'photo', 'voice', 'video', 'video_note'
    ]

    def _get_user_name(self, user: User):
        return user.username or user.first_name

    def _get_author(self):
        return self.message.forward_signature \
               or self.message.forward_sender_name \
               or self.message.forward_from and self._get_user_name(self.message.forward_from) \
               or self.message.forward_from_chat and self.message.forward_from_chat.username

    def _add_content(self, room_id):
        if self.message.content_type not in self.available_content_types:
            self.send_message('Такой тип контента не поддерживается')
            raise StopSignalException()
        file_id = None
        content_type = self.message.content_type

        if content_type in ['voice', 'video', 'video_note']:
            file_id = getattr(self.message, content_type).file_id
        if content_type in ['photo']:
            file_id = getattr(self.message, content_type)[-1].file_id

        author = self._get_author()
        text = (self.text or self.message.caption or '') + (author and f'\n(от {author})' or '')
        content_id = self.handler.add_content(
            content_type=content_type,
            text=text.strip(),
            file_id=file_id,
            room_id=room_id
        )
        return content_id

    def _receive_target_room(self):
        """Пользователь уже выбрал комнату, в которую хочет добавить контент"""
        room = self._accept_chosen_room()
        if not room:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton('Создать', callback_data='create_room'),
                         InlineKeyboardButton('Повторить поиск', callback_data='repeat_choose'))
            keyboard.add(InlineButton.menu)
            self.send_message('Комната не найдена', reply_markup=keyboard)
        else:
            content_id = self.state.get('content_id')
            self.handler.set_content_room(content_id, room.id)
            self.send_message('Добавлено!', reply_markup=ReplyKeyboardRemove())
            raise RedirectException(MainMenuScenario, MainMenuScenario.open)

    def choose_room(self):
        content_id = self._add_content(None)
        self.set_state(content_id=content_id)
        self.delete_current_message()
        self.send_message('В какую комнату вы хотите это отправить?',
                          reply_markup=ReplyKeyboardRemove())
        self.set_state(self, self._receive_target_room)
        self._send_rooms_list(additional_buttons=[
            InlineButton.create_room
        ])

    def default_response(self):
        raise RedirectException('MainMenuScenario')

    def repeat_choose(self):
        self.send_message('Введите ключ комнаты, если хотите добавить туда')
        self.set_state(self, self._receive_target_room)

    routes = {

    }


class MainMenuScenario(ContentAddingScenario):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton('📚 Список комнат', callback_data='Список комнат'),
    )
    keyboard.add(
        InlineButton.create_room,
        InlineButton.settings,
    )
    keyboard.add(InlineButton.reference)

    def after(self):
        pass

    def show_reference(self):
        reference_texts = REFERENCE.strip().split('\n\n')
        for ref_text in reference_texts[:-1]:
            self.send_message(ref_text, reply_markup=ReplyKeyboardRemove())

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineButton.back)
        self.send_message(reference_texts[-1], reply_markup=keyboard)

    def create_room(self):
        new_room_keyboard = InlineKeyboardMarkup()
        new_room_keyboard.add(InlineKeyboardButton('📂 Публичную', callback_data='create_public_room'),
                              InlineKeyboardButton('🔒 Приватную', callback_data='create_private_room'))
        new_room_keyboard.add(InlineButton.back)
        self.send_message('Хотите создать публичную или приватную?', reply_markup=new_room_keyboard, auto_delete=True)

    def room_created(self, name='', room_id: int = None):
        text = 'Комната создана'
        if name:
            text = 'Комната "{}" создана'.format(name)

        # Если сейчас пользователь в сценарии добавления контента
        if self.state.get('content_id'):
            self.handler.set_content_room(self.state.get('content_id'), room_id)
            self.set_state(content_id=None)
            text += '\nСообщение добавлено!'
            self.send_message(text, auto_delete=True)

            # Если мы сюда попали из пересылаемого сообщения, на этом все заканчивается
            # В противном случае отправляемся в комнату
            return

        self.send_message(text, auto_delete=True, reply_markup=ReplyKeyboardRemove())

        self.handler.member.curr_room_id = room_id
        raise RedirectException(ExploreRoomScenario, ExploreRoomScenario.show_content)

    def create_public_room(self):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineButton.with_callback(InlineButton.back, 'create_room'))
        self.set_state(self, self.public_room_done)
        self.send_message('Введите название комнаты', auto_delete=True, reply_markup=keyboard)

    def _new_room_done(self, is_private, name, key):
        """Пользователь прислал название комнаты"""
        nickname = name or key
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineButton.with_callback(InlineButton.back, 'create_room'))
        if not nickname:
            self.set_state(self, self.public_room_done)
            if not self.call_data:
                self.delete_current_message()
            self.send_message('Введите название текстом', reply_markup=keyboard)
            return

        self.delete_current_message()
        if self.handler.get_room(name=nickname, key=nickname) is not None:
            self.set_state(self, self.public_room_done)
            self.send_message('Такая комната уже существует. Придумайте другое название', reply_markup=keyboard)
            return

        room = self.handler.create_room(is_private=is_private, name=name, key=key)
        if not room:
            self.send_message('Невозможно создать комнату (возможно такое название уже существует)')
            return

        if is_private:
            self.room_created('', room.id)
        else:
            self.room_created(nickname, room.id)

    def public_room_done(self):
        self._new_room_done(is_private=False, name=self.text, key=None)

    def _private_room_done(self):
        """Пользователь прислал ключ скрытой комнаты"""
        self._new_room_done(is_private=True, name=None, key=self.text)

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
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineButton.with_callback(InlineButton.back, 'create_room'))
        self.send_message(
            'Введите ключ для приватной комнаты\nВнимание! Его нужно обязательно запомнить. '
            'Чтоб зайти в комнату, вам нужно будет ввести именно этот ключ', reply_markup=keyboard,
            auto_delete=True
        )
        self.set_state(self, self.handle_new_room_key)

    def open(self):
        # Чтобы при создании новой комнаты не было памяти от сброшенной попытки на лету добавить контент
        self.set_state(content_id=None)
        self.send_message('Главное меню', auto_delete=True)

    def try_open_room(self):
        if not self.call_data:
            self.delete_current_message()

        room = self.handler.get_room(name=self.call_data or self.text, key=self.text)
        if not room:
            self.send_message('Комната не найдена', auto_delete=True)
            return
        self.handler.member.curr_room_id = room.id
        raise RedirectException(ExploreRoomScenario, ExploreRoomScenario.show_content)

    def default_response(self):
        if self.message.forward_from or self.message.forward_from_chat or self.message.forward_from_message_id \
                or self.message.forward_signature or self.message.forward_sender_name:
            self.choose_room()
        elif self.call_data or self.message.content_type == 'text':
            self.try_open_room()
        else:
            self.choose_room()

    def open_room(self):
        self._send_rooms_list()

    def to_settings(self):
        raise RedirectException(RoomSettingsScenario, RoomSettingsScenario.open)

    PUBLIC_ROOM = 'PUBLIC_ROOM'

    routes = {
        'Создать комнату': create_room,
        'create_room': create_room,
        'Список комнат': open_room,
        'Настройки комнат': to_settings,
        'settings': to_settings,
        'menu': open,
        'back': open,
        'reference': show_reference
    }


class ExploreRoomScenario(ContentAddingScenario):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineButton.menu)

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
        content_id = self._add_content(self.handler.room.id)
        self.handler.set_message_content_id(self.message.id, content_id)

        if self.handler.room.is_private:
            self.delete_current_message()

        self.send_message('Добавлено', auto_delete=True)

    def delete_content(self):
        """Удаляет контент из комнаты. Можно переслать сообщение из комнаты и '.' (точкой)"""
        target_message = self.message.reply_to_message
        self.delete_current_message()
        if not target_message:
            self.send_message('Чтобы удалить что-то из комнаты, перешлите сообщение, добавив точку')
        try:
            # Удаляем из 4ех мест. Строку в бд отвечающую удаляемому сообщения
            # Строку контента. Сообщение-индикатор об удалении (точка) и само сообщение контента
            result = self.handler.delete_message_content(target_message.id)
            if result is None:
                raise AssertionError

            self.delete_message(target_message.id, delete_from_db=False)
            self.send_message('Удалено', auto_delete=True, reply_markup=ReplyKeyboardRemove())
        except (IntegrityError, AssertionError):
            self.send_message('Такого контента не существует')

    def show_content(self):
        content_count = self.handler.get_room_content_count()
        if self.handler.room.name:
            self.send_message('Открыта комната {} 📖'.format(self.handler.room.name),
                              reply_markup=ReplyKeyboardRemove())
        else:
            self.send_message('Открыта секретная комната 🔓', reply_markup=ReplyKeyboardRemove())
        if not content_count:
            self.send_message('Пока комната пуста. Пришлите (или перешлите) сюда что-угодно!')
            return
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
            buttons.append(InlineKeyboardButton('⬅ Предыдущая', callback_data='prev'))
        if page_num + 1 < pages_count:
            buttons.append(InlineKeyboardButton('Следующая ➡', callback_data='next'))
        keyboard.add(*buttons)
        keyboard.add(InlineButton.menu)
        self.send_message('📑 Страница {} из {}'.format(page_num + 1, pages_count),
                          key=self.TEMP_MESSAGES_KEY, reply_markup=keyboard, auto_delete=False)

    def _print_content_list(self, items: t.List[DBContent]):
        content_type_method = {
            'text': self.bot.send_message,
            'photo': self.bot.send_photo,
            'voice': self.bot.send_voice,
            'video': self.bot.send_video,
            'video_note': self.bot.send_video_note,
        }
        with ThreadPoolExecutor(max_workers=20) as executor:
            tasks = []
            for item in items:
                if item.content_type not in content_type_method:
                    self.send_message('Неподдерживаемый вид контента', auto_delete=True)
                    return
                send_method = content_type_method[item.content_type]
                kwargs = {}
                if item.file_id and item.text:
                    kwargs['caption'] = item.text
                task = executor.submit(send_method, self.chat_id, item.file_id or item.text,
                                       **kwargs, disable_notification=True)
                tasks.append(task)
            for task, item in zip(as_completed(tasks), items):
                message = task.result()
                self.handler.add_message(message.id, key=self.TEMP_MESSAGES_KEY, content_id=item.id)

    def default_response(self):
        self.add_content()

    def to_menu(self):
        self._delete_temp_messages()
        raise RedirectException(MainMenuScenario, MainMenuScenario.open)

    routes = {
        'next': next,
        'prev': prev,
        'menu': to_menu,
        'Главное меню': to_menu,
        '.': delete_content,
        '/delete': delete_content,
        '/del': delete_content,
        'delete': delete_content,
        'remove': delete_content,
    }

    incoming_key = TEMP_MESSAGES_KEY

    default_outgoing_key = TEMP_MESSAGES_KEY
