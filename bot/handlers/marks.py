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

    await msg.answer(f'Последние 5 оценок\n{user.repr_mark_row}\nСтарые➡️Новые',
                    reply_markup=build_marks_kb(cfg.subjects[user.id], user.marks_row, use_callbacks=False,
                                                add_buttons=[[InlineKeyboardButton(text = 'Смотреть через сообщения(👎)', callback_data=CD_MARKS)]]))


@router.callback_query(F.data == CD_MARKS)
@flags.student
async def cmd_marks(cb: types.CallbackQuery, session: AsyncSession, user:User, student: Student):
    await cb.message.edit_text(f'Последние 5 оценок\n{user.repr_mark_row}\nNote: Лучше используй дефолтный вариант с inline режимом', 
                               reply_markup=build_marks_kb(cfg.subjects[user.id], user.marks_row, use_callbacks=True,
                                                           add_buttons=[[InlineKeyboardButton(text = 'Открыть нормальный вариант дневника', callback_data=CD_MARKS_V2)]]))


@router.callback_query(SubjectDetail.filter())
@flags.student
async def callback_marks(cb: types.CallbackQuery, callback_data: SubjectDetail, session: AsyncSession, user:User):
    if callback_data.link == '1': return await cb.answer('Зачем жмал')
    kb = InlineKeyboardBuilder()
    subj = [i for i in cfg.subjects[user.id] if i.link == link_base+callback_data.link][0]
    for i in subj.marks:
        if i.are_empty: continue
        kb.button(text = f'{i.date}: {"🚷" if i.is_absent else ""}{mark(i.mark, user.marks_row)} {i.theme}' + ("🟰"*80 if i.type=="КН" else "‎  "*50)+'.', callback_data='1')
    kb.button(text = '⬅️Назад', callback_data=CD_MARKS)
    await cb.message.edit_text(subj.name, reply_markup=kb.adjust(1).as_markup())

@router.callback_query(F.data == '1')
async def callback_marks(cb: types.CallbackQuery, session: AsyncSession, user:User):
    await cb.answer('Зачем жмал')

@router.inline_query(F.query.startswith('!s'))
async def inline_marks(inline_query: types.InlineQuery, session: AsyncSession, user:User):
    # return await inline_query.answer(results=[], is_personal=True,cache_time=5, switch_pm_text='Оценки не роби', switch_pm_parameter='abc')
    if not user.login or not user.password:
        return await inline_query.answer(results=[], is_personal=True,cache_time=5, switch_pm_text='Необходимо привязать аккаунт НГУ', switch_pm_parameter='abc')
    
    try:
        subj = base64.b64decode(inline_query.query[2:]).decode('utf-8')
    except Exception:
        return await inline_query.answer(results=[], is_personal=True,cache_time=5, switch_pm_text='Не меняй строку поиска!', switch_pm_parameter='abc')
    
    try:
        if user.cookie: s = Student(user.cookie)
        else: 
            s = await Student.auth(user.login, decrypt(user.password))
            user.cookie = s.cookie
            await session.commit()
        if not cfg.subjects.get(user.id): 
            cfg.subjects[user.id] = [await s.subject_detail(i.link) for i in await s.latest_marks()] 
        
        subj = [i for i in cfg.subjects[user.id] if i.link == link_base+subj]
        if not subj: return await inline_query.answer(results=[], is_personal=True,cache_time=5, switch_pm_text='Предмет не найден', switch_pm_parameter='abc')
        subj = subj[0]
        
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
