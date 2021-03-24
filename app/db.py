from datetime import timedelta

from sqlalchemy import *
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker, relationship
from sqlalchemy_mixins import ActiveRecordMixin, ReprMixin, TimestampsMixin
import typing as t

from app.config import PG_URL, TEST

Base = declarative_base()


class BaseModel(Base, ActiveRecordMixin, ReprMixin, TimestampsMixin):
    __abstract__ = True
    __repr__ = ReprMixin.__repr__


class DBMember(BaseModel):
    __tablename__ = 'member'
    id = Column(BigInteger, nullable=False, primary_key=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    state = Column(JSON, default={})
    curr_room_id = Column(Integer, nullable=True)


class DBRoom(BaseModel):
    __tablename__ = 'room'
    id = Column(BigInteger, primary_key=True)
    member_id = Column(Integer, ForeignKey('member.id'))
    member = relationship(DBMember, foreign_keys=[member_id])
    is_private = Column(Boolean, nullable=False)
    content_items = relationship("DBContent", cascade="all, delete-orphan")
    key = Column(String, nullable=True)
    name = Column(String, nullable=True)


class DBContent(BaseModel):
    __tablename__ = 'content'
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('room.id'), nullable=False)
    content_type = Column(String, nullable=False)
    text = Column(Text, nullable=True)
    file_id = Column(String)


class DBMessage(BaseModel):
    __tablename__ = 'message'
    id = Column(Integer, primary_key=True)
    message_id = Column(BigInteger, nullable=False)
    member_id = Column(Integer, ForeignKey('member.id'), nullable=True)
    member = relationship(DBMember)
    is_from_bot = Column(Boolean, nullable=False)
    content_id = Column(Integer, ForeignKey('content.id'), nullable=True)
    content = relationship(DBContent, foreign_keys=[content_id])
    text = Column(String, nullable=True)
    key = Column(String, nullable=True)
    __table_args__ = (
        UniqueConstraint('message_id', 'member_id'),
    )


Session: t.Optional[scoped_session] = None


def init_session(engine_, drop=False):
    global Session
    global engine
    engine = engine_
    Session = scoped_session(sessionmaker(bind=engine, autocommit=False, autoflush=True))

    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    BaseModel.set_session(Session)


def stop_session():
    Session.remove()
    engine.dispose()


engine = create_engine(PG_URL, echo=False)
init_session(engine, drop=TEST)
