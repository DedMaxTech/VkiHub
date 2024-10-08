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


async def timetable_diff_handler(msg: types.Message, user: User, session: AsyncSession):
    q = decode_payload(msg.text.split(' ', 1)[1])[2:] if msg.text.startswith('/start ') else msg.text
    
    wds = None
    for tt in cfg.timetables:
        if tt.groups.get(q):
            wds = tt.groups[q]
            break
    else: wds = cfg.teachers.get(q)
    
    if wds is None: return await msg.answer('Расписание (и изменения) не найдены')
    if cfg.last_timetable_update is None: return await msg.answer('Изменения не найдены')
    if sum(len(wd.diffs) for wd in wds) == 0: return await msg.answer(f'Изменения для {html.link(q, await create_start_link(msg.bot, "t:"+q, True))} по сравнению с расписанием от {cfg.last_timetable_update.strftime("%d.%m.%Y")} не найдены', reply_markup=build_timetable_markup(user))
    await msg.answer(f'Изменения для {html.link(q, await create_start_link(msg.bot, "t:"+q, True))} по сравнению с расписанием от {cfg.last_timetable_update.strftime("%d.%m.%Y")}:\n\n'+'\n─────────────────\n\n'.join([await wd.print_diffs(msg.bot, user, q in cfg.teachers, q not in cfg.teachers) for wd in wds if wd.diffs]), reply_markup=build_timetable_markup(user))
    
    
@router.message(F.text)
async def timetable_handler(msg: types.Message, user: User, session: AsyncSession):
    q = decode_payload(msg.text.split(' ', 1)[1])[2:] if msg.text.startswith('/start ') else msg.text
    if len(cfg.timetables) == 0: 
        return await msg.answer('Расписания не найдены', reply_markup=build_timetable_markup(user))
    q = q.replace('⭐️', '').replace('🕓','')
    if q in cfg.timetables:
        for tt in cfg.timetables:
            if q == tt.name:
                # if tt.name != user.timetable:
                #     user.last_timetable = tt.name
                #     await session.commit()
                await msg.answer(f'Расписание для {tt.name} на {tt.date.day:02d}.{tt.date.month:02d}.{tt.date.year}'+(f'\nДоступно отдельное расписание для {await group_groups(list(tt.groups), msg.bot)}, нажми чтобы посмотреть' if tt.groups else ''), reply_markup=build_timetable_markup(user))
                await msg.answer_media_group([types.InputMediaDocument(media=i) for i in tt.images])
                return
    if q in cfg.classrooms:
        await msg.answer(f"(β) Расписание для кабинета {html.link(q, await create_start_link(msg.bot, 't:'+q, True))}\n\n"+'\n'.join([await wd.print(msg.bot, user,hide_teacher=False, hide_my_group=False) for wd in cfg.classrooms[q]]), reply_markup=build_timetable_markup(user))
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
            if grp != user.timetable:
                user.last_timetable = grp
                await session.commit()
            s = f"(β) Расписание для {html.link(grp, await create_start_link(msg.bot, 't:'+grp, True))}\n\n"+'\n'.join([await wd.print(msg.bot,user,hide_teacher=False, hide_my_group=True) for wd in gr])
            
            if cfg.last_timetable_update:
                changes = sum(len(wd.diffs) for wd in gr)
                if changes > 0: s += html.bold(f'\nНайдено {html.link(f"{changes} {Diff.changes(changes)}", await create_start_link(msg.bot, "d:"+grp, True))} по сравнению с {cfg.last_timetable_update.strftime("%d.%m.%Y")}')
                else: s+= f"\nИзменения не найдены по сравнению с {cfg.last_timetable_update.strftime('%d.%m.%Y')}"
            await msg.answer(s, reply_markup=build_timetable_markup(user))
            await msg.answer_media_group([types.InputMediaDocument(media=i) for i in tt.images])
            # if any(wd.diffs for wd in gr): TODO
            #     await msg.answer('(β) Изменения в расписании:\n'+'\n'.join([await wd.print_diffs(msg.bot) for wd in gr if wd.diffs]))
            return
    if len(q)>3 and any(i for i in cfg.teachers if q.lower() in i.lower()):
        teacher, score = process.extractOne(q, [i for i in cfg.teachers if q.lower() in i.lower()])
        if score>0:
            if teacher != user.timetable:
                user.last_timetable = teacher
                await session.commit()
            empty_tts = [i for i in cfg.timetables if not i.groups]
            
            s = f"(β) Расписание для {html.link(next((c.name for c in cfg.contacts if teacher.split(' ')[0] in c.name and ' '+teacher.split(' ')[-1][0] in c.name and ' '+teacher[-2] in c.name), teacher), await create_start_link(msg.bot, 't:'+teacher, True))}\n\n"+'\n'.join([await wd.print(msg.bot, user, hide_teacher=True, hide_my_group=False) for wd in cfg.teachers[teacher]]) + (f'\n\n❗️Note: временно невозможно получить данные из {",".join([i.name for i in empty_tts])}. Пожалуйста, перепроверьте что у {teacher} нет пар в файлах ниже' if empty_tts else '')
            if cfg.last_timetable_update:
                changes = sum(len(wd.diffs) for wd in cfg.teachers[teacher])
                if changes > 0: s += html.bold(f'\nНайдено {html.link(f"{changes} {Diff.changes(changes)}", await create_start_link(msg.bot, "d:"+teacher, True))} по сравнению с {cfg.last_timetable_update.strftime("%d.%m.%Y")}')
                else: s+= f"\nИзменения не найдены по сравнению с {cfg.last_timetable_update.strftime('%d.%m.%Y')}"
            await msg.answer(s, reply_markup=build_timetable_markup(user))
            for i in empty_tts:
                await msg.answer_media_group([types.InputMediaDocument(media=i) for i in i.images]) 
            return 

    await msg.answer(f'Такое расписание не найдено, выбери вариант ниже, или напиши свою группу или преподователя', reply_markup=build_timetable_markup(user))


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