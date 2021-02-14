from time import sleep

import pytest
from sqlalchemy import create_engine

from app.db import init_session, stop_session

from app.bot_mock_driver import FakeTelegramChat


@pytest.fixture
def db_engine():
    db_url = 'postgresql://postgres:postgres@localhost:5432/postgres'

    engine = create_engine(db_url, echo=False)
    init_session(engine, drop=True)
    yield
    stop_session()


@pytest.fixture
def chat(db_engine):
    """Returns chat"""
    yield FakeTelegramChat(chat_type='private')
