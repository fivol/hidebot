from time import sleep

import pytest
from sqlalchemy import create_engine

from app.config import USERS_LIST_SIZE_LIMIT, MAIN_ADMIN_USERNAME, MAIN_CHAT_USERNAME
from app.constants import CHAT_HELP_MESSAGE, CommandText
from app.db import init_session, stop_session
import random

from app.bot_mock_driver import FakeTelegramChat

engine_used = False
test_num = 0


@pytest.fixture
def db_engine():
    global engine_used
    global test_num
    while engine_used:
        sleep(random.random() * 0.1)
    engine_used = True
    db_url = 'postgresql://postgres:postgres@localhost:5432/postgres'

    engine = create_engine(db_url, echo=False)
    init_session(engine, drop=True)
    yield
    stop_session()
    test_num += 1
    engine_used = False


@pytest.fixture
def chat(db_engine):
    """Returns main chat (single available group)"""
    yield FakeTelegramChat(chat_username=MAIN_CHAT_USERNAME)


@pytest.fixture
def private_chat(db_engine):
    """Private chat with admin user"""
    yield FakeTelegramChat(chat_type='private')


def test_ping():
    chat = FakeTelegramChat(chat_username=MAIN_CHAT_USERNAME)
    me = chat.get_new_user()
    me.send_message('__ping__')
    assert chat.last_message.text == 'ok'
    assert chat.members_count == 0


def test_2_chats(db_engine):
    c1 = FakeTelegramChat()
    c2 = FakeTelegramChat(chat_username=MAIN_CHAT_USERNAME)
    u1 = c1.get_new_user(username=MAIN_ADMIN_USERNAME)
    u1.send_message('/activity')
    u2 = c2.get_new_user()
    u2.send_message('hi')


class TestUsersIndexing:
    """Done. Tests passed!"""

    def test_join_chat(self, chat):
        me = chat.get_new_user()
        me.send_message(None, content_type='new_chat_members', new_chat_members=[chat.bot_user])
        assert chat.members_count == 1
        me.send_message('holo')
        assert chat.members_count == 1

    def test_users_indexing(self, chat):
        print('begin')
        for i in range(100):
            user = chat.get_new_user()
            user.send_message('hi')
        assert chat.members_count == 100
        assert not chat.messages

    def test_user_indexing(self, chat):
        me = chat.get_new_user()
        other = chat.get_new_user()
        assert chat.members_count == 0
        me.send_message(None, content_type='new_chat_members',
                        new_chat_members=[me])
        assert not chat.new_messages
        assert chat.members_count == 1
        me.send_message(None, content_type='new_chat_members', new_chat_members=[other])
        assert not chat.new_messages
        assert chat.members_count == 2
        assert len(chat.new_messages) == 0

    def test_join_bot_to_chat_agreement(self, chat):
        me = chat.get_new_user()
        me.send_message(None, content_type='new_chat_members', new_chat_members=[chat.bot_user])
        print(chat.new_messages)
        assert chat.new_messages[0].text == 'Теперь я с вами!'
        assert chat.new_messages[1].text == CHAT_HELP_MESSAGE
        assert len(chat.new_messages) == 2

    def test_content_type(self, chat):
        me = chat.get_new_user()
        me.send_message('hi')
        me.send_message(None, content_type='photo')
        me.send_message(None, content_type='photo')
        me.send_message(None, content_type='video')
        assert not chat.new_messages_count
        assert chat.members_count == 1

    def test_many_users(self, chat):
        count = 200
        for i in range(count):
            user = chat.get_new_user()
            user.send_message('hi')
        assert chat.members_count == count

    def test_new_chat_members(self, chat):
        me = chat.get_new_user()
        me.send_message('hello')
        for i in range(10):
            me.send_message(None, content_type='new_chat_members', new_chat_members=[
                chat.get_new_user()
            ])
        assert chat.members_count == 11
        users = [chat.get_new_user() for i in range(5)]
        someone = chat.get_new_user()
        someone.send_message(None, content_type='new_chat_members', new_chat_members=users)
        assert chat.members_count == 17


class TestActivity:
    def test_no_main_chat(self, private_chat):
        me = private_chat.get_admin_user()
        me.send_message('/activity')
        assert private_chat.last_message.text == 'Основной чат еще не создан'

    def test_activity_list(self, chat):
        admin_chat = FakeTelegramChat(chat_type='private')
        admin = admin_chat.get_new_user(username=MAIN_ADMIN_USERNAME)
        user = chat.get_new_user()
        other = chat.get_new_user()
        user.send_message('hi')
        assert not chat.new_messages
        assert chat.members_count == 1
        admin.send_message('/activity')
        response = admin_chat.last_message.text
        assert response.startswith(f"1. Последнее сообщение от @{user.username} было ")
        assert admin_chat.new_messages_count == 1
        other.send_message(None, content_type='new_chat_members', new_chat_members=[other])
        assert chat.members_count == 2
        admin.send_message('/activity')
        assert len(admin_chat.last_message.text.split('\n')) == 2
        for i in range(10):
            user = chat.get_new_user()
            user.send_message('hello')
        assert chat.members_count == 12
        admin.send_message('/activity')
        assert len(admin_chat.last_message.text.split('\n')) == USERS_LIST_SIZE_LIMIT

    def test_enabling(self, private_chat, chat):
        user = chat.get_new_user()
        user.send_message('hi')
        me = private_chat.get_admin_user()
        me.send_message(CommandText.CLEANING_ACTIVATION + ' ...')
        assert private_chat.last_message.text == f'Укажите {CommandText.CLEANING_ACTIVATION} [on|off]'
        me.send_message(CommandText.CLEANING_ACTIVATION + ' on')
        assert private_chat.last_message.text == 'Отслеживание активности запущено'

    def test_idle_set(self, private_chat, chat):
        me2 = chat.get_new_user()
        me2.send_message(None, content_type='photo')
        me = private_chat.get_admin_user()
        me.send_message(CommandText.IDLE_TIME + ' 11')
        assert private_chat.last_message.text == 'Установлено'
        me.send_message(CommandText.IDLE_TIME + ' 43')
        assert private_chat.new_messages_count == 1
        assert private_chat.last_message.text == 'Установлено'

    def test_remove_user(self, private_chat, chat):
        u1 = chat.get_new_user()
        u2 = chat.get_new_user()
        u3 = chat.get_new_user()
        admin = private_chat.get_admin_user()
        u1.send_message('hi')
        u1.send_message(None, content_type='new_chat_members', new_chat_members=[u2])
        assert chat.members_count == 2
        u3.send_message('oops')
        assert chat.members_count == 3
        admin.send_message('/activity')
        assert len(private_chat.last_message.text.split('\n')) == 3
        u1.send_message(None, content_type='left_chat_member', left_chat_member=u3)
        admin.send_message('/activity')
        assert len(private_chat.last_message.text.split('\n')) == 2
        u2.send_message(None, content_type='left_chat_member', left_chat_member=u2)
        assert chat.members_count == 1
        admin.send_message('/activity')
        assert len(private_chat.last_message.text.split('\n')) == 1


class TestRating:
    def test_rating_increase(self, chat):
        users = []
        messages = {}
        for i in range(100):
            user = chat.get_new_user()
            m = user.send_message('hi')
            messages[user.id] = m
            users.append(user)
        assert chat.members_count == 100
        assert not chat.messages
        me = users[0]
        other = users[1]
        other_message = other.send_message('uuu')
        plus_mess = me.send_message('+', reply_to_message=other_message)
        assert chat.last_message.text == \
               '{} ({}) увеличил репутацию {} ({})'.format(
                   '@' + me.username, 0, '@' + other.username, 1
               )
        assert chat.last_message.reply_message == plus_mess
        me.send_message('/rating')
        lines = chat.last_message.text.split('\n')
        assert len(lines) == USERS_LIST_SIZE_LIMIT
        assert lines[0][-1] == '1'
        assert lines[-1][-1] == '0'

    def test_rating_list(self, chat):
        me = chat.get_new_user()
        other = chat.get_new_user()
        assert chat.members_count == 0
        my_hello = me.send_message('Привет всем!')
        assert chat.new_messages_count == 0
        me.send_message('/rating')
        assert chat.last_message.text == f'1. Рейтинг @{me.username}: 0'
        other.send_message('hi')
        assert chat.members_count == 2
        other.send_message('+', reply_to_message=my_hello)
        me.send_message('/rating')
        assert chat.last_message.text == \
               f'1. Рейтинг @{me.username}: 1\n' \
               f'2. Рейтинг @{other.username}: 0'


class TestCommands:
    def test_ping(self, chat):
        me = chat.get_new_user()
        me.send_message('/ping')
        assert chat.last_message.text == 'ping passed'
        me.send_message('hi')
        assert not chat.last_message

    def test_help(self, chat):
        chat.get_new_user().send_message('/help')
        assert chat.last_message.text == CHAT_HELP_MESSAGE
        chat.get_new_user().send_message('hi')
        assert not chat.last_message
        chat.get_new_user().send_message('/help')
        assert chat.last_message.text == CHAT_HELP_MESSAGE

    def test_me(self, chat):
        me = chat.get_new_user(username='abc')
        chat.get_new_user().send_message('ff')
        chat.get_new_user().send_message(None, content_type='new_chat_members',
                                         new_chat_members=[chat.get_new_user()])
        me.send_message('/me')
        assert chat.last_message.text == '@abc'
