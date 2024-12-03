from contextlib import asynccontextmanager
import random
from typing import AsyncGenerator, Coroutine
from aiogram import Router, html, flags
import aiogram
from aiogram.filters import Command
from aiogram import types , flags, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import MagicData

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from fuzzywuzzy import process, fuzz

from db.models import User
from messages.basic import *
from config import cfg
from handlers.basic import profile
from modules.nsu_cab import *

router = Router()



@router.message(Command("marks"))
@router.callback_query(F.data == CD_MARKS_V2)
@flags.student
@flags.command('Оценки')
async def cmd_marksv2(msg: types.Message, session: AsyncSession, user:User, student: Student):
    if (isinstance(msg, types.CallbackQuery)):
        await msg.answer()
        msg = msg.message

    await msg.answer(f'Последние {str(user.marks_count) + "оценок" if user.marks_count >= 12 or not user.marks_count else "оценок"}\n{user.repr_mark_row}\nСтарые➡️Новые',
                    reply_markup=build_marks_kb(cfg.subjects[user.id], user.marks_row, user.marks_count, add_buttons=[[InlineKeyboardButton(text='🪄Настроить отображение оценок', callback_data=CD_CURTOMIZE_MARKS)]]))


@router.callback_query(F.data == '1')
async def callback_marks(cb: types.CallbackQuery, session: AsyncSession, user:User):
    await cb.answer('Зачем жмал')

@router.inline_query(F.query.startswith('!s'))
async def inline_marks(inline_query: types.InlineQuery, session: AsyncSession, user:User):
    # return await inline_query.answer(results=[], is_personal=True,cache_time=5, switch_pm_text='Оценки не роби', switch_pm_parameter='abc')
    if not user.login or not user.password:
        return await inline_query.answer(results=[], is_personal=True,cache_time=5, switch_pm_text='Необходимо привязать аккаунт НГУ', switch_pm_parameter='abc')
    
    try:
        if user.cookie: s = Student(user.cookie)
        else: 
            s = await Student.auth(user.login, decrypt(user.password))
            user.cookie = s.cookie
            await session.commit()
        if not cfg.subjects.get(user.id): 
            try:
                cfg.subjects[user.id] = [await s.subject_detail(i.link) for i in await s.latest_marks()] 
            except DataMissingException:
                return await inline_query.answer(results=[], is_personal=True,cache_time=5, switch_pm_text='Оценки в профиле не найдены, проверь на сайте и попробуй ещё раз позже', switch_pm_parameter='abc')
        subj = next((i for i in cfg.subjects[user.id] if i.name == inline_query.query.replace('!s', '').strip()), None)
        if not subj: return await inline_query.answer(results=[], is_personal=True,cache_time=5, switch_pm_text='Предмет не найден', switch_pm_parameter='abc')
        
        await inline_query.answer(results=[types.InlineQueryResultArticle(
            id=str(random.randint(0,10000000)),title=f'{i.date}{", "+mark(i.mark, user.marks_row, True, False) if i.mark else ""}{", Н" if i.is_absent else ""}{", ⚠️"+i.type + " "  if i.type else ""}',  # + "⬜️"*20
            thumbnail_url=get_thumb(i.mark, i.is_absent),
            input_message_content=types.InputTextMessageContent(message_text=f'{html.bold(subj.name)}\n{i.date}{f"({i.type})" if i.type else ""}: {mark(i.mark, user.marks_row, True, False)} {"Н" if i.is_absent else ""}\n{i.theme}'),
            description=i.theme
        ) for i in reversed(subj.marks) if not i.are_empty], is_personal=True,cache_time=60, switch_pm_parameter='abc', switch_pm_text=subj.name)
        await s.close()
    except WrongCookieException:
        user.cookie = None
        await session.commit()
        return await inline_marks(inline_query, session, user)
    except LoginFailedException:
        return await inline_query.answer(results=[], is_personal=True,cache_time=5, switch_pm_text='Не удалось войти в аккаунт НГУ', switch_pm_parameter='abc')

@router.inline_query(F.query =='Мои приказы')
async def inline_marks(inline_query: types.InlineQuery, session: AsyncSession, user:User):
    # return await inline_query.answer(results=[], is_personal=True,cache_time=5, switch_pm_text='Оценки не роби', switch_pm_parameter='abc')
    if not user.login or not user.password:
        return await inline_query.answer(results=[], is_personal=True,cache_time=5, switch_pm_text='Необходимо привязать аккаунт НГУ', switch_pm_parameter='abc')
    
    try:
        if user.cookie: s = Student(user.cookie)
        else: 
            s = await Student.auth(user.login, decrypt(user.password))
            user.cookie = s.cookie
            await session.commit()
        
        await inline_query.answer(results=[types.InlineQueryResultArticle(
            id=str(random.randint(0,10000000)),title=i.title, 
            input_message_content=types.InputTextMessageContent(message_text=f'{html.bold(i.title)}\n{i.body.strip()}'),
            description=i.body
        ) for i in await s.orders()], is_personal=True,cache_time=60, switch_pm_parameter='abc', switch_pm_text="Мои приказы:")
        await s.close()
    except aiogram.exceptions.TelegramBadRequest as e: logger.error(e)
    except WrongCookieException:
        user.cookie = None
        await session.commit()
        return await inline_marks(inline_query, session, user)
    except LoginFailedException:
        return await inline_query.answer(results=[], is_personal=True,cache_time=5, switch_pm_text='Не удалось войти в аккаунт НГУ', switch_pm_parameter='abc')
