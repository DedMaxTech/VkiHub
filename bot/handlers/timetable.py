import random
from aiogram import Router, html
from aiogram.filters import Command
from aiogram import types , flags, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.deep_linking import decode_payload

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from fuzzywuzzy import process, fuzz

from db.models import User
from messages.basic import *
from config import cfg


router = Router()

@router.message(Command("schedule"))
@flags.command('Расписание звонков')
async def schedule(message: types.Message):
    await message.answer(rings_tt, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text='Закрепить вверху', callback_data='pin_tt')]]), parse_mode='HTML')

@router.callback_query(F.data == 'pin_tt')
async def profile_callback(cb: types.CallbackQuery):
    await cb.message.pin(True)
    await cb.message.delete_reply_markup()
    
@router.message(F.text)
async def timetable_handler(msg: types.Message):
    q = decode_payload(msg.text.split(' ', 1)[1])[2:] if msg.text.startswith('/start ') else msg.text
    if len(cfg.timetables) == 0: 
        return await msg.answer('Расписания не найдены', reply_markup=build_timetable_markup(cfg.timetables))
    if q in cfg.timetables:
        for tt in cfg.timetables:
            if q == tt.name:
                await msg.answer(f'Расписание для {tt.name} на {tt.date.day:02d}.{tt.date.month:02d}.{tt.date.year}'+(f'\nДоступно отдельное расписание для {", ".join(sorted(set(i[:-1] for i in tt.groups)))}' if tt.groups else ''), reply_markup=build_timetable_markup(cfg.timetables))
                await msg.answer_media_group([types.InputMediaDocument(media=i) for i in tt.images])
                return
        
    if q[0].isdigit():
        gr = None
        for tt in cfg.timetables:
            for grp in tt.groups:
                if q in grp:
                    gr = tt.groups[grp]
                    break
            if gr: break
        if gr:
            await msg.answer(f'[beta] Расписание для {grp}\n\n'+'\n'.join([await wd.print(msg.bot) for wd in gr])+beta)
            await msg.answer_media_group([types.InputMediaDocument(media=i) for i in tt.images])
            return
    if len(q)>3 and any(i for i in cfg.teachers if q.lower() in i.lower()):
        word, score = process.extractOne(q, [i for i in cfg.teachers if q.lower() in i.lower()])
        if score>20:
            return await msg.answer(f'[beta] Расписание для {word}\n\n'+'\n'.join([await wd.print(msg.bot, for_teacher=True) for wd in cfg.teachers[word]]) + beta)
    await msg.answer(f'Такое расписание не найдено, выбери вариант ниже, или напиши свою группу или преподователя', reply_markup=build_timetable_markup(cfg.timetables))


@router.inline_query(~F.query.startswith('!'))
async def inline_list_users(inline_query: types.InlineQuery, session: AsyncSession):
    searched = []
    for c in cfg.contacts:
        if ' ' not in inline_query.query and inline_query.query.lower() not in c.str().lower():
            continue
        score = fuzz.WRatio(inline_query.query.lower(), c.str())
        searched.append((c, score))
    searched.sort(key=lambda x: x[1], reverse=True)
    res = [types.InlineQueryResultArticle(
        id=c.email,title=c.name, thumbnail_url=c.photo,
        input_message_content=types.InputTextMessageContent(message_text=c.str()),
        description=(f'Tg: @{c.tg_username}\n' if c.tg_username else '') +c.title+'\n'+c.email
    ) for c,s in searched[:50]]
    await inline_query.answer(results=res, is_personal=False,cache_time=10, switch_pm_text='Контакты колледжа',switch_pm_parameter='awesome')