from datetime import datetime
import typing as t

from app.config import BOT_ID, logger
from app.db import *
from app.utils import lazy_property
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError


class Handler:
    """
    Тут содержатся основные методы для работы с базой данных
    Также кастомные специфичные функции для обращения к бд
    """

    def __init__(self, chat_id: int, user_id: int, chat_username=None):
        logger.info('INIT HANDLER')
        from .db import Session
        self.chat_id = chat_id
        self.user_id = user_id
        self.chat_username = chat_username
        self.session = Session()

    @lazy_property
    def member(self) -> t.Optional[DBMember]:
        chat_member = DBMember.find(self.chat_id)
        return chat_member

    @lazy_property
    def room(self) -> t.Optional[DBRoom]:
        return DBRoom.find(self.member.curr_room_id)

    def _close_session(self):
        try:
            self.session.commit()
        except:
            self.session.rollback()
            # self.session.close()

    def _save_models(self):
        if self.member:
            self.member.save()

    def __del__(self):
        logger.info('---DELETE--- HANDLER')
        self._save_models()
        self._close_session()

    def create_member(self, from_user, update_time=False):
        if self.user_id == from_user.id and self.member:
            return
        user_id = from_user.id != BOT_ID and from_user.id or None
        if user_id:
            self.session.execute(
                insert(DBMember.__table__).values(
                    id=self.chat_id,
                    state=None,
                    first_name=from_user.first_name,
                    last_name=from_user.last_name,
                    username=from_user.username,
                ).on_conflict_do_nothing()
            )

    def add_message(self, message_id, is_from_bot=False, key=None, text=None, content_id: int = None, **kwargs):
        self.session.execute(
            insert(DBMessage.__table__).values(
                message_id=message_id,
                member_id=self.member.id,
                is_from_bot=is_from_bot,
                key=key,
                text=text,
                content_id=content_id
            ).on_conflict_do_nothing()
        )

    def create_room(self, is_private=None, key=None, name=None) -> t.Optional[DBRoom]:
        try:
            return DBRoom.create(is_private=is_private, key=key, name=name, member_id=self.member.id)
        except IntegrityError:
            return None

    def get_room(self, *, key: str = None, name: str = None) -> t.Optional[DBRoom]:
        if not key and not name:
            return None
        return DBRoom.query.filter(
            DBRoom.member == self.member,
            or_(
                DBRoom.key == key,
                DBRoom.name == name
            )
        ).first()

    def add_content(self, content_type: str, text: t.Optional[str], file_id: t.Optional[str]):
        DBContent.create(
            room_id=self.room.id,
            content_type=content_type,
            text=text,
            file_id=file_id
        )

    @staticmethod
    def delete_message_content(message_id: int):
        """Принимает id сообщение в чате. Удаляет соответствующий ему контент
        Ищет соответствие в табличке DBMessage
        Returns True on success and None on Fail
        """
        assert isinstance(message_id, int)
        message = DBMessage.query.filter(DBMessage.message_id == message_id).first()
        if not message:
            return None
        if not message.content:
            return None
        content = message.content
        message.delete()
        content.delete()
        return True

    def get_public_rooms(self) -> t.List[DBRoom]:
        return DBRoom.query.filter(DBRoom.member == self.member,
                                   DBRoom.is_private.is_(False)).all()

    def get_content(self, *, shift: int = None, limit: int = None) -> t.List[DBContent]:
        assert isinstance(shift, int)
        assert isinstance(limit, int)
        return DBContent.query.filter(
            DBContent.room_id == self.room.id,
        ).order_by(DBContent.created_at.desc()).offset(shift).limit(limit).all()

    def get_room_content_count(self):
        return DBContent.query.filter(
            DBContent.room_id == self.room.id
        ).count()

    def get_old_messages(self) -> t.List[DBMessage]:
        return DBMessage.query.filter(
            DBMessage.member_id == self.member.id,
            # DBMessage.created_at < datetime.utcnow() -
            # timedelta(seconds=5)
        ).order_by(DBMessage.created_at)[:-20]

    def get_messages_by_key(self, key: str):
        return DBMessage.query.filter(
            DBMessage.member_id == self.member.id,
            DBMessage.key == key,
        ).all()

    def delete_message(self, message_id: int):
        message = DBMessage.query.filter(
            DBMessage.member_id == self.member.id,
            DBMessage.message_id == message_id,
        ).first()
        if message:
            self.session.delete(message)
        return bool(message)

    def delete_messages(self, ids: t.List[int]):
        """Принимает список айдишников сообщений
        и удаляет их все из базы.
        !!!ID базы данных, а не телеги
        """
        DBMessage.query.filter(
            DBMessage.id.in_(ids)
        ).delete(synchronize_session=False)

    def delete_room(self):
        self.room.delete()
