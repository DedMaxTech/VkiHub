import asyncio
import logging
import time
import aiogram
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from aiohttp.client_exceptions import TooManyRedirects
from aiogram import exceptions

from messages.basic import *

from .types import *
from .timetable import *
from db.models import User
from config import cfg
from utils import send_error_message
from modules.nsu_cab import *

logger = logging.getLogger('bot')

async def loop(bot: aiogram.Bot, sessionmaker: async_sessionmaker):
    loop = asyncio.get_running_loop()
    try: # init everything
        try:
            cfg.timetables = await get_all_timetables() #get timetables pdfs
            await pdfs_to_image(bot, cfg.timetables) # cache photos
            m = await bot.send_message(cfg.superuser, f'Timetables loaded, {len(cfg.timetables)} found')
            
            for tt in cfg.timetables: # parse all timetables
                try:
                    await loop.run_in_executor(None, parse_schedule_from_pdf, tt)
                    m = await m.edit_text(m.text+f'\nParsed {tt.name}: {", ".join(tt.groups.keys())}')
                except ConvertingError as e:
                    await bot.send_message(cfg.superuser, f'Failed to parse {tt.name}, {e}')
            find_cogroups_in_timetables(cfg.timetables)
            
            cfg.teachers = parse_teachers_timetable(cfg.timetables) # convert for teachers
        except TooManyRedirects:
            await bot.send_message(cfg.superuser, f'Failed to load timetables, to many redirects')
        
        
        
        ###### loading contacts ############
        creds = None
        if (cfg.base_dir/'temp/auth_token.json').is_file():
            creds = Credentials.from_authorized_user_file(cfg.base_dir/'temp/auth_token.json')
            if creds.expired:
                try: creds.refresh(Request())
                except: creds = None

        if not creds or not creds.valid:
            await bot.send_message(cfg.superuser, 'No google auth token or expired, run `bot/get_auth_token.py` and send back `auth_token.json` or put directly on server to `temp/auth_token.json`\nContacts will not be loaded', parse_mode='Markdown')
        else:
            cfg.contacts.extend(get_contacts(creds))
            await bot.send_message(cfg.superuser, f'Contacts loaded, {len(cfg.contacts)} found')
            async with sessionmaker() as session:
                users: list[User] = (await session.scalars(select(User))).all()
                for u in users:
                    if u.is_visible and u.fio:
                        c = next((c for c in cfg.contacts if c.name == u.fio or c.name == u.google_fio), None)
                        if c: c.tg_username = u.username
        ####################################
        
    except Exception as e:
        return await send_error_message(bot, e, 'Error in main loop on startup\nLOOP NOT STARTED')
    
    # to trigger nsu.cab load only once a hour
    loop_counter = 100000
    while 1:
        try:
            async with sessionmaker() as session:
                users: list[User] = (await session.scalars(select(User))).all()
            
                tm = time.time()
                
                # get latest timetables
                try: new_timetables = await get_all_timetables()
                except asyncio.exceptions.TimeoutError: pass
                except TooManyRedirects:
                    logger.warning(f'Failed to update timetables, to many redirects')
                
                
                is_changed = False

                # small helper to send messages
                async def send_timetable(user:User, text: str, timetable:Timetable):
                    if timetable.images == []:
                        await pdfs_to_image(bot, [timetable])
                    try:
                        await bot.send_message(user.id,text)
                        await bot.send_media_group(user.id, [types.InputMediaDocument(media=i) for i in timetable.images])
                    except exceptions.TelegramForbiddenError: pass
                    except Exception as e:
                        await send_error_message(bot, e, 'error on sending timetable for '+user.get_nick())

                # cfg.timetables[-1].date = datetime.datetime(20,1,1)

                # detect changes
                for tt in new_timetables:
                    ott = next((i for i in cfg.timetables if i.name == tt.name), None)
                    if not ott or tt.date > ott.date or tt.text_content != ott.text_content:
                        is_changed = True
                
                if is_changed:
                    await pdfs_to_image(bot, [tt for tt in new_timetables if not tt.images]) # cache
                    
                    for tt in new_timetables: # parse
                        try:
                            await loop.run_in_executor(None, parse_schedule_from_pdf, tt)
                        except ConvertingError as e:
                            await bot.send_message(cfg.superuser, f'Failed to parse {tt.name}, {e}')    
                    find_cogroups_in_timetables(new_timetables)
                    
                    
                    cfg.teachers = parse_teachers_timetable(new_timetables)
                    
                    # Testing
                    # new_timetables[-1].groups['107в2'][0].lessons[1].number = '4'
                    # new_timetables[-1].groups['107в2'][0].lessons[0] = Lesson('','2','','','',[],'')
                    # new_timetables[-1].groups['107в2'][1].lessons.append(Lesson('пара пара пара пара пара пара','5','11111','2222','3333',[],''))
                    # new_timetables[-1].groups['107в2'][2].lessons[2] = Lesson('309 Разработка программных модулей Пауль С.А ','3','','','',[],'')
                    
                    # find difference... 
                    # diff: dict[str, dict[WeekDay, list[list[Lesson|None, Lesson|None, WeekDay|None]]]] = {}
                    # for tt in new_timetables:
                    #     ott = next((i for i in cfg.timetables if i.name == tt.name), None)
                    #     if not ott: continue
                    #     for gr in tt.groups:
                    #         ogrps = ott.groups.get(gr)
                    #         if not ogrps: continue
                    #         diff[gr] = {}
                    #         for wd in tt.groups[gr]:
                    #             t = []
                    #             owd = next((i for i in ogrps if i.weekday == wd.weekday), None)
                    #             if not owd: 
                    #                 t = [[None, l] for l in wd.lessons if l.content]
                    #             else:
                    #                 for l in wd.lessons:
                    #                     if not l.content: continue
                    #                     ol = next((i for i in owd.lessons if i.number == l.number and i.content ), None)
                    #                     if not ol: t.append([None, l])
                    #                     elif l.canceled and not ol.canceled: t.append([l, None])
                    #                     elif l.content != ol.content: t.append([ol, l])
                                        
                    #                 for ol in owd.lessons:
                    #                     if not ol.content: continue
                    #                     if not next((i for i in wd.lessons if i.number == ol.number and i.content ), None): t.append([ol, None])
                                    
                    #             if t: diff[gr][wd] = t
                            
                    #         for wd in diff[gr]:
                    #             for df in diff[gr][wd]:
                    #                 if df[0] is not None: continue
                    #                 for j_wd, j_df in diff[gr].items():
                    #                     for d in j_df:
                    #                         if d[1] is not None: continue
                    #                         if df[1].content.replace(df[1].classroom, '') == d[0].content.replace(d[0].classroom, ''):   
                    #                             df[0] = d[0]
                    #                             df.append(j_wd)
                    #                             j_df.remove(d)
                    # find difference...
                    diff: dict[str, dict[WeekDay, list[Diff]]] = {}
                    for tt in new_timetables:
                        ott = next((i for i in cfg.timetables if i.name == tt.name), None)
                        if not ott: continue

                        for gr in tt.groups:
                            ogrps = ott.groups.get(gr)
                            if not ogrps: continue
                            diff[gr] = {}

                            for wd in tt.groups[gr]:
                                diffs = []
                                owd = next((i for i in ogrps if i.weekday == wd.weekday), None)
                                if not owd:
                                    diffs = [Diff(None, l) for l in wd.lessons if l.content]
                                else:
                                    for l in wd.lessons:
                                        if not l.content: continue

                                        ol = next((i for i in owd.lessons if i.number == l.number and i.content), None)
                                        
                                        if not ol: diffs.append(Diff(None, l))
                                        elif l.canceled and not ol.canceled: diffs.append(Diff(l, None))
                                        elif l.content != ol.content: diffs.append(Diff(ol, l))

                                    for ol in owd.lessons:
                                        if not ol.content: continue
                                        if not next((i for i in wd.lessons if i.number == ol.number and i.content), None):
                                            diffs.append(Diff(ol, None))
                                
                                if diffs: diff[gr][wd] = diffs

                            for wd in diff[gr]:
                                for df in diff[gr][wd]:
                                    if df.type != DiffType.NEW: continue
                                    for j_wd in diff[gr]:
                                        for d in diff[gr][j_wd]:
                                            if df.type != DiffType.CANCELED: continue
                                            if df.new.content.replace(df.new.classroom, '') == d.old.content.replace(d.old.classroom, ''):
                                                df.old = d.old
                                                df.new_day = j_wd
                                                diff[gr][j_wd].remove(d)
                            # Сравниваем и ищем совпадения между группами уроков
                            # for wd, diffs in diff[gr].items():
                            #     for df in diffs:
                            #         if df.old is not None: continue

                            #         for j_wd, j_diffs in diff[gr].items():
                            #             for d in j_diffs:
                            #                 if d.new is not None: continue

                            #                 if df.new.content.replace(df.new.classroom, '') == d.old.content.replace(d.old.classroom, ''):
                            #                     df.old = d.old
                            #                     df.new_day = j_wd
                            #                     j_diffs.remove(d)
                    
                    # send to all users
                    for user in users:
                        if not user.timetable: continue
                        if user.timetable in cfg.teachers: # TODO changes
                            await bot.send_message(user.id, f'(β) Вышло расписание для {user.timetable}\n\n' +'\n'.join([await wd.print(bot, for_teacher=True) for wd in cfg.teachers[user.timetable]]))
                            continue
                        ntt = next((i for i in new_timetables if i.name == user.timetable or user.timetable in i.groups), None)
                        if ntt:
                            if user.timetable == ntt.name: # общая pdf ка
                                changes = {gr: sum([len(diff[gr][wd]) for wd in diff[gr]]) for gr in diff if gr in ntt.groups}
                                changes = {gr: changes[gr] for gr in changes if changes[gr]}
                                await send_timetable(user, f'Новое расписание для {ntt.as_str}\n\n(β)' + ('Изменения не найдены'
                                    if not changes else f'Найдены изменения для {",".join(f"{k}: {v}шт" for k, v in changes.items())}' + '\n\nЧтобы бот показывал детально показывал что куда перенесли, поставь в профиле расписание по конкретной группе'), ntt)
                            else: # отдельная группа
                                await send_timetable(user, f'(β) Новое расписание для {user.timetable}\n\n'+'\n'.join([await wd.print(bot) for wd in ntt.groups[user.timetable]]), ntt)
                                if not diff[user.timetable]: 
                                    await bot.send_message(user.id, '(β) Изменений не найдены')
                                elif len(diff[user.timetable]) > 20:
                                    await bot.send_message(user.id, f'(β) {len(diff[user.timetable])} изменений, расписания слишком сильно отличается')
                                else:
                                    s = '(β) Найдены изменения:\n'
                                    for wd in diff[user.timetable]:
                                        s+=weekdays[wd.weekday].title()+' '+wd.date+'\n'
                                        for df in diff[user.timetable][wd]:
                                            s+=await df.print(bot)+'\n'
                                        s+='\n'
                                    await bot.send_message(user.id, s)
                    
                    cfg.timetables = new_timetables
                
                # helper to parse all data from nsu / per user
                async def check_user(user: User, aiohttp_session: aiohttp.ClientSession):
                    try:
                        if user.cookie:
                            student = Student(user.cookie, session=aiohttp_session)
                        else: 
                            try: student = await Student.auth(user.login, decrypt(user.password))
                            except LoginFailedException: 
                                user.login = None
                                user.password = None
                                await bot.send_message(user.id, 'Не удалось войти в аккаунт, учётная запись была отвязана\nЕсли ты хочешь дальше пользоваться системой оценок попробуй привязать аккаунт заново')
                                await session.commit()
                                return 
                            user.cookie = student.cookie
                            await session.commit()

                        try:
                            old = cfg.subjects.get(user.id) or []
                            # visit latest_marks page only if no links cached already
                            try:
                                new = [await student.subject_detail(i.link) for i in (old or await student.latest_marks())]
                            except DataMissingException: return
                            except ForbidenException:
                                user.login = user.password = user.cookie = user.fio = None
                                await session.commit()
                                await bot.send_message(user.id, 'NSU Cab не даёт доступ к оценкам на вашем аккаунте, аккаунт отвязан. Зайдите самостоятельно на сайт и проверьте работоспасобность аккаунта. Если после перепревязки ошибка повторится, сообщите мне')
                                return
                                
                            # find new marks
                            for old_subj in old:
                                for new_subj in new:
                                    if old_subj.link == new_subj.link:
                                        for nm in new_subj.marks:
                                            flag = True
                                            for om in old_subj.marks:
                                                if om.date == nm.date:
                                                    flag = False
                                                    break
                                            if flag:
                                                try:
                                                    await bot.send_message(user.id, f'Новая оценка для {new_subj.name} за {nm.date}{f"({nm.type})" if nm.type else ""}: {mark(nm.mark, user.marks_row, True, False)} {"Н" if nm.is_absent else ""}\n{f"Тема: {nm.theme}" if nm.theme else ""}',
                                                                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Все оценки по '+new_subj.name, switch_inline_query_current_chat='!s'+base64.b64encode(new_subj.link.replace(link_base,'').encode()).decode())]]))
                                                except aiogram.exceptions.TelegramForbiddenError: pass
                                                except Exception as e:
                                                    await send_error_message(bot, e, 'error on sending mark')
                            cfg.subjects[user.id] = new
                        except WrongCookieException:
                            await bot.send_message(cfg.superuser, 'Куки не прошла для '+user.get_nick())
                            user.cookie = None
                            await session.commit()
                            await check_user(user, aiohttp_session)
                        # await s.close()
                    except Exception as e:
                        await send_error_message(bot, e, 'Error updating marks for '+user.get_nick())
                
                # trigger every hour
                if loop_counter>=59:
                    loop_counter = 0
                    logger.info(f'Start marks parsing')
                    async with aiohttp.ClientSession(NSU_ENDPOINT, headers=header_generator(country='ru')) as aiohttp_session:
                        await asyncio.gather(*[check_user(user, aiohttp_session) for user in users if user.login])
                    logger.info(f'End marks parsing')
                else: loop_counter += 1
                    
                logger.info(f'Loop processed: {time.time()-tm}')    
            
        except Exception as e:
            await send_error_message(bot, e, 'Error in main loop on iteration, skipping to next')
        await asyncio.sleep(60)
         
        
    