import datetime
from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware, types
from aiogram.types import TelegramObject
from aiogram.dispatcher.flags import get_flag
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from aiogram.utils.chat_action import ChatActionSender

from modules.nsu_cab import *
from db.models import User
from config import cfg

from utils import *

class DbSessionMiddleware(BaseMiddleware):
    """Wraps handler with DB session, adds `session: sqlalchemy.ext.asyncio.AsyncSession` to handler """
    def __init__(self, session_pool: async_sessionmaker):
        super().__init__()
        self.session_pool = session_pool

    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: Dict[str, Any]):
        async with self.session_pool() as session:
            data["session"] = session
            return await handler(event, data)

class AuthMiddleware(BaseMiddleware):
    """Updates DB for user, adds `user: models.User` to handler"""
    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: Dict[str, Any]):
        user = data['event_from_user']
        session = data.get('session')
        if session is None: raise Exception('Setup DbSessionMiddleware() first')
        user = await session.merge(User(id=user.id, first_name=user.first_name,username=user.username,last_name=user.last_name, updated=datetime.datetime.now()))
        await session.commit()
        data['user']=user
        return await handler(event, data)

class BanMiddleware(BaseMiddleware):
    FOREVER_BAN_SECONDS=31536000 # ~ year
    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: Dict[str, Any]):
        user = data['user']
        if secs:=user.is_banned(): await data['bot'].send_message(user.id, 'You banned until '+user.banned.strftime('%d.%m.%y %H:%M:%S')) # user.id, 'You are permanently banned' if secs>self.FOREVER_BAN_SECONDS else ('You banned until '+user.banned.strftime('%d.%m.%y %H:%M:%S'))
        else: await handler(event, data)


class LoggingMiddleware(BaseMiddleware):
    def __init__(self, logger):
        super().__init__()
        self.logger = logger

    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], event: types.Update, data: Dict[str, Any]):
        self.logger.debug(f'[{event.event_type}] from {data["event_from_user"].id}, {remove_none(event.dict())}')
        return await handler(event, data)

class NotificationMiddleware(BaseMiddleware):
    '''Middleware for delayed posts'''
    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: Dict[str, Any]):
        user: User = data['user']
        session: AsyncSession = data['session']
        await handler(event, data)
        if user.notification_chat and user.notification_msg:
            await event.bot.copy_message(user.id, user.notification_chat, user.notification_msg)
            user.notification_chat = None
            user.notification_msg = None
            await session.commit()

class StudentMiddleware(BaseMiddleware):
    '''Middlware to add api connection to context, handler must be flagged'''
    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: Dict[str, Any]):
        user: User = data['user']
        session: AsyncSession = data['session']
        
        if not get_flag(data, "student"):
            return await handler(event, data)
        
        if user.login is None or user.password is None:
            return await event.answer('Сначала надо подключить личный кабинет НГУ в /profile')
        if user.cookie:
            s = Student(user.cookie)
        else: 
            try:
                s = await Student.auth(user.login, decrypt(user.password))
            except LoginFailedException:
                return await event.answer("Не удалось войти в аккаунт НГУ, перепривяжи аккаунт в профиле")
            user.cookie = s.cookie
            await session.commit()

        try:
            data['student'] = s
            if not cfg.subjects.get(user.id): 
                m = await event.answer('Синхронизация...')
                async with ChatActionSender.typing(user.id, bot=event.bot):
                    try: 
                        cfg.subjects[user.id] = [await s.subject_detail(i.link) for i in await s.latest_marks()] 
                    except DataMissingException:
                        return await event.answer('Предметы не найдены')
                    
                if isinstance(event, types.Message): await m.delete()
            await handler(event, data)
        except WrongCookieException:
            user.cookie = None
            await session.commit()
            await self.__call__(handler, event, data)
        
        await s.close()
                