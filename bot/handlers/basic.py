import json
import random
from aiogram import Router, html
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram import types , flags, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.chat_action import ChatActionSender

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from fuzzywuzzy import process, fuzz
import emoji

from db.models import User
from messages.basic import *
from config import cfg
from modules.nsu_cab import *
from modules.timetable import normalize_group_name
from handlers.timetable import timetable_handler, timetable_diff_handler

router = Router()


@router.message(CommandStart(deep_link=True,deep_link_encoded=True)) # deep links
async def handler(message: types.Message, user: User, session: AsyncSession, command: CommandObject, state: FSMContext):
    await message.delete()
    if command.args == 'support':
        await message.answer(f"Если тебе нравится бот и ты хочешь поддержать разработку то можешь скинуть копеечку на:\nСбер {html.spoiler('5469020015860902')}\nИли напиши в лс @dedmaxtech")
    if command.args == 'rules':
        await message.answer(legal_notice)
    if command.args.startswith('t:'):
        await timetable_handler(message, user, session)
    if command.args.startswith('d:'):
        await timetable_diff_handler(message, user, session)
        
@router.message(CommandStart())
async def cmd_start(msg: types.Message, session: AsyncSession, user:User, state: FSMContext):
    await msg.answer(start_message, reply_markup=build_timetable_markup(user))
    if not user.login:
        await state.set_state(ProfileStates.setup_nsu)
        await msg.answer(f'Хочешь сразу привязать аккаунт нгу для уведомлений об оценках?\nДанные для аккаунта должны дать в колледже\n\nЕсли что вдруг, то ты потом всегда можешь привязать и отвязать свой аккаунт', 
                        reply_markup=Rkb([[RM_YES, RM_NO_ACCOUNT]]))
    else:
        await setup_nsu(msg, session, user, state)

@router.message(ProfileStates.setup_nsu)
async def setup_nsu(msg: types.Message, session: AsyncSession, user:User, state: FSMContext):
    if msg.text == RM_YES:
        await msg.answer(f'Введи свой логин для аккаунта нгу\n\nВводя свои данные, я принимаю {html.link("условия обработки данных", await create_start_link(msg.bot, "rules", True))}', reply_markup=Rkb([[RM_CANCEL]], "i.ivanov", False))
        return await state.set_state(ProfileStates.set_login)
    
    if not user.timetable:
        await msg.answer(f'Хочешь настроить свою группу? Благодоря этому бот будет присылать тебе новые расписание как только оно выйдет и показывать изменения',
                        reply_markup=Rkb([[RM_YES, RM_SKIP_GROUP]]))
        return await state.set_state(ProfileStates.setup_group)
    
    if msg.text == RM_NO_ACCOUNT:
        await setup_group(msg, session, user, state)
        

@router.message(ProfileStates.setup_group)
async def setup_group(msg: types.Message, session: AsyncSession, user:User, state: FSMContext):
    if msg.text == RM_YES:
        await msg.answer('Напиши свою группу или фамилию, если вы преподователь. Если не знаешь группу, можешь пока что выбрать общее расписание на поток', reply_markup=build_timetable_markup(user, [RM_CANCEL]))
        return await state.set_state(ProfileStates.set_group)
    await state.clear()
    await msg.answer('Хорошо, если что то ты всегда можешь настроить всё в своём /profile\nТакже не забудь прочитать /help', reply_markup=build_timetable_markup(user))

@router.message(Command("help"))
@flags.command('Памагити/ЧаВо')
async def cmd_start(msg: types.Message, session: AsyncSession, user:User):
    await msg.answer(help_message+f'PS: скинуть на покушать можно {html.link("сюда", await create_start_link(msg.bot, "support", True))}')


####### Profile #######
@router.message(Command("profile"))
@flags.command('Мой профиль и настройки')
async def profile(msg: types.Message, session: AsyncSession, user:User):
    if isinstance(msg, types.CallbackQuery): msg = msg.message
    txt, rm = bulid_profile_keyboard(user)
    if isinstance(msg, types.CallbackQuery): await msg.edit_text(txt, reply_markup=rm)
    else: await msg.answer(txt, reply_markup=rm)

@router.message(F.text == RM_CANCEL)
async def cmd_help(msg: types.Message, user:User, state: FSMContext):
    await state.clear()
    await msg.answer("Отменено", reply_markup=build_timetable_markup(user))

####### Timetable config #######
@router.callback_query(F.data == CD_SET_GROUP)
async def update(cb: types.CallbackQuery, user:User, state: FSMContext):
    await cb.answer()
    await cb.message.answer('Выберите расписание которое будет вам приходить, можешь выбрать расписание снизу, ну или написать свою группу или фамилию, если вы преподователь', reply_markup=build_timetable_markup(user, [RM_CANCEL]))
    await state.set_state(ProfileStates.set_group)
    
@router.message(ProfileStates.set_group, F.text)
async def newchat(msg: types.Message, session: AsyncSession, user:User,state: FSMContext):
    q = msg.text.replace('⭐️', '').replace('🕓','')
    normalized_q = normalize_group_name(q)
    tt = None
    if q in cfg.timetables: tt = q
    elif q and (q[0].isdigit() or (q[0] in 'Вв' and len(q) > 1 and q[1].isdigit())) and (gr := next((gr for gr in cfg.groups if gr.startswith(normalized_q)), None)): tt = gr
    elif q and (t:= next((t for t in cfg.teachers if q.lower() in t.lower()), None)): tt = t
    if not tt:
        return await msg.answer('Не найдено, выбери снизу или напишу свою группу', reply_markup=build_timetable_markup(user, [RM_CANCEL]))
    
    user.timetable = tt
    await session.commit()
    
    await state.clear()
    await msg.answer('Расписание установлено: ' + tt)
    await profile(msg, session, user)

@router.callback_query(F.data == CD_CLEAR_GROUP)
async def update(cb: types.CallbackQuery,session: AsyncSession,state: FSMContext, user:User):
    user.timetable = None
    await session.commit()
    await cb.answer('Рассылка отменена!', show_alert=True)
    txt, rm = bulid_profile_keyboard(user)
    await cb.message.edit_text(txt, reply_markup=rm)


@router.callback_query(F.data == CD_SET_ABBREVIATIONS)
async def cd_abbreviations(cb: types.CallbackQuery,session: AsyncSession,state: FSMContext, user:User):
    await cb.answer()
    await cb.message.answer(abbreviation_message, reply_markup=Rkb([[RM_CANCEL], [RM_ABBR_FULL], [RM_ABBR_SHORT], ['{}']], '{"a":"b"} или a=b', False))
    await state.set_state(ProfileStates.set_abbreviations)
    if user.abbrevioations:
        await cb.message.answer(f'Ваши текущие сокращения: {html.pre(json.dumps(user.abbrevioations, ensure_ascii=False, indent=0))}')

@router.message(ProfileStates.set_abbreviations, F.text)
async def set_abbreviations(msg: types.Message, session: AsyncSession, user:User,state: FSMContext):
    if msg.text == RM_ABBR_FULL: abbr = None
    elif msg.text == RM_ABBR_SHORT: abbr = base_abbreviation
    
    elif msg.text[0] == '{':
        try: 
            abbr = json.loads(msg.text)
            for k,v in abbr.items():
                if not type(v) == str: return await msg.answer(f'Значение для "{k}" должно быть строкой')
        except Exception: return await msg.answer('Ошибка при парсинге json, проверьте что все строки корректны, все значения в " а не в \' и что в послнедней строке нет запятой')
    elif '=' in msg.text:
        abbr = {}
        for i in msg.text.split('\n'):
            if len(i.split('=')) != 2: return await msg.answer(f'Проверьте равно в строке "{i}"')
            k,v = i.split('=')
            abbr[k] = v
    else: return await msg.answer('Не понимаю какой формат ввода, посмотри примеры')
    
    user.abbrevioations = abbr
    await session.commit()
    await state.clear()
    await msg.answer('Сокращения сохранены', reply_markup=build_timetable_markup(user))
    await profile(msg, session, user)

####### NSU config #######
@router.callback_query(F.data == CD_LINK_NSU)
async def cb_link_nsu(cb: types.CallbackQuery,session: AsyncSession,state: FSMContext, user:User):
    await cb.answer()
    await cb.message.answer(f'Введи свой логин для аккаунта нгу\n\nВводя свои данные, я принимаю {html.link("условия обработки данных", await create_start_link(cb.bot, "rules", True))}', reply_markup=Rkb([[RM_CANCEL]], "i.ivanov", False))
    await state.set_state(ProfileStates.set_login)

@router.message(ProfileStates.set_login, F.text)
async def set_login(msg: types.Message, session: AsyncSession, user:User,state: FSMContext):
    await state.update_data(login=msg.text)
    await state.set_state(ProfileStates.set_password)
    await msg.answer('Введи НГУшный пароль (если такой стоит везде и боишься то смени на какой нибудь рандомный)', reply_markup=Rkb([[RM_CANCEL]], "qwerty"))


@router.message(ProfileStates.set_password, F.text)
async def set_password(msg: types.Message, session: AsyncSession, user:User,state: FSMContext):
    login, password = (await state.get_data())['login'], msg.text
    try:
        await msg.delete()
        await msg.answer(f'{login}: {html.spoiler(password)}\nПроверяю...', reply_markup=build_timetable_markup(user))
        async with ChatActionSender.typing(msg.from_user.id, bot=msg.bot):
            s = await Student.auth(login, password)
            p = await s.get_profile()
            p.group = p.group.translate(en_to_ru)
            if p.group[0] == 'в' and p.group[1].isdigit():
                p.group = p.group[1:]
            
            user.login = login
            user.password = encrypt(password)
            user.cookie = s.cookie
            user.fio = p.name
            await session.commit()
            
            m = await msg.answer(f'Аккаунт НГУ найден: {p.name}, {p.group}\n{html.italic("Первичная синхронизация...")}')
            try:
                a = await s.latest_marks()
                cfg.subjects[user.id] = [await s.subject_detail(i.link) for i in await s.latest_marks()] 
            except DataMissingException: pass
            await m.edit_text(f'Аккаунт НГУ привязан и синхронизирован: {p.name}\nКак только тебе поставят новую оценку бот тебе напишет')
            
            # TODO устанавливать группу только если она есть в текущих раписаниях, смотри код для колбека установки группы выше
            if not user.timetable:
                user.timetable = p.group
                await session.commit()
                await msg.answer(f'Также я установил тебе ежедневную рассылку расписания для группы {p.group}, её можно отключить в профиле')
            
            await s.close()
            
        if (c:=next((i for i in cfg.contacts if i.name == user.fio or i.name == user.google_fio), None)) and not user.is_visible:
            if user.username:
                await msg.answer(f'Я нашёл твой учебный google аккаунт: {c.email}, давай свяжем аккаунт нгу, google и телеграм, благодоря этому люди в общем поиске смогут найти твой телеграм, а это очень важно, часто найти контакты человека сложно\n\nЕсли понадобиться ты всегда сможешь скрыть свой телеграм из поиска в /profile', 
                                reply_markup=Rkb([[RM_YES, RM_NOT_LINK]], one_time=False))
                await msg.answer('Что такое общий поиск? Вот это🔽',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🔎Поиск студентов/преподователей', switch_inline_query_current_chat='')]]))
                return await state.set_state(ProfileStates.config_visible)
            await msg.answer(f'Я нашёл твой учебный google аккаунт: {c.email}, можно связать аккаунт нгу, google и телеграм для общего поиска, но к сожедению у тебя нет @юзернейма. Если можешь, установи в настрйоках телеграмма свой юзернейм и привяжи аккаунты в профиле')
                
    except LoginFailedException:
        await msg.answer('Не удалось войти, скорее всего неправильный логин/пароль, проверь данные и попробуй ещё раз', reply_markup=build_timetable_markup(user))
    except DataMissingException as e:
        await msg.answer(e.args[0]+', проверь на сайте, присутсвует ли это информация, если нет то попробуй позже, а если да то напиши мне', reply_markup=build_timetable_markup(user))
    except ForbidenException as e:
        await msg.answer('Не удалось войти, доступ запрещён. Попробуй зайти на сайт вручную, если доступ на сайте есть, а бот не даёт войти, напиши мне', reply_markup=build_timetable_markup(user))
    await state.clear()
    await profile(msg, session, user)


@router.message(ProfileStates.config_visible)
async def config_visible(msg: types.Message, session: AsyncSession, user:User,state: FSMContext):
    if msg.text == RM_YES:
        contact = next((i for i in cfg.contacts if i.name == user.fio or i.name == user.google_fio), None)
        if contact:
            contact.tg_username = user.username
            user.is_visible = True
            await session.commit()
            await msg.answer('Аккаунты успешно связаны, ищи себя через кнопку в профиле!', reply_markup=build_timetable_markup(user))
        else: await msg.answer('Ничего не нашел, видимо ошибка... Попробуй позже')
    else: await msg.answer('Жаль, так вкишники могли бы проще друг с другом связываться(', reply_markup=build_timetable_markup(user))
    await state.clear()
    await profile(msg, session, user)
    


@router.callback_query(F.data == CD_CHANGE_VISIBLE)
async def cb_clear(cb: types.CallbackQuery,session: AsyncSession,state: FSMContext, user:User):
    contact = next((i for i in cfg.contacts if i.name == user.fio or i.name == user.google_fio), None)
    if user.is_visible:
        user.is_visible = False
        contact.tg_username = None
        await session.commit()
        await cb.answer('Теперь тебя не видно в поиске, очень жаль, теперь вкишникам сложнее связываться(', show_alert=True)
    else:
        if not user.fio:
            return await cb.answer('Чтобы подтвердить свою личность, нужно сначала (пере)привязать свой аккаунт нгу', show_alert=True)
        if not user.username:
            return await cb.answer('Чтобы тебя было видно в поиске надо чтобы у тебя был @юзернейм, пожалуйста настрой его в аккаунте телеграма', show_alert=True)
        if not contact:
            return await cb.answer('Не могу найти твой гугл аккаунт, пожалуйста попробуй позже или обратись ко мне', show_alert=True)
        user.is_visible = True
        contact.tg_username = user.username
        await session.commit()
        await cb.answer(f'Теперь твой телеграм привязан к {contact.email} и его видно в общем поиске, так вкишникам будет проще находить друг друга, спасибо!', show_alert=True)
        
    txt, rm = bulid_profile_keyboard(user)
    await cb.message.edit_text(txt, reply_markup=rm)

@router.callback_query(F.data == CD_CLEAR_NSU)
async def cb_link_nsu(cb: types.CallbackQuery,session: AsyncSession,state: FSMContext, user:User):
    user.login = user.password = user.cookie = user.fio = None
    await session.commit()
    if user.id in cfg.subjects: del cfg.subjects[user.id]
    await cb.answer('Аккаунт НГУ отвязан', show_alert=True)
    txt, rm = bulid_profile_keyboard(user)
    await cb.message.edit_text(txt, reply_markup=rm)


####### Customization #######
@router.callback_query(F.data == CD_CURTOMIZE_MARKS)
async def cb_customize_marks(cb: types.CallbackQuery,session: AsyncSession,state: FSMContext, user:User):
    await cb.answer()
    await cb.message.answer('Напиши свой ряд кастомизации оценок, просто введи эмодзи через запятую без пробелов, которые будут соответсовавать оценкам "5,4,3,2,Н"\nИли выбери из предложенных', 
                            reply_markup=Rkb([['🟢,🟣,🟠,🔴,🚷','🟩,🟪,🟧,🟥,♿'], ['😍,😊,😭,🙊,🙈', '5️⃣,4️⃣,3️⃣,2️⃣,⚠️'], [RM_CANCEL]], "5,4,3,2,Н"))
    await state.set_state(ProfileStates.set_marks)

example_data = [Subject("Очень важный предмет", [Mark("","",False,i, "") for i in "5432Н5432Н5432Н"], "1"),
                Subject("Очень важный предмет 2", [Mark("","",False,"5", "")], "1"),
                Subject("Очень важный предмет 3", [Mark("","",False,i, "") for i in "25Н"], "1"),]
@router.message(ProfileStates.set_marks, F.text)
async def set_marks(msg: types.Message, session: AsyncSession, user:User,state: FSMContext):
    splited = msg.text.split(',')
    if len(splited) != 5:
        return await msg.answer('Введи ровно 5 эмодзи, по 1 на каждую оценку')
    if len(msg.text) > 32:
        return await msg.answer('Слишком длинные эмодзи, попробуй другие\nЕсли ты всё на самом деле написал всё корректно но бот выдал ошибку, напиши мне')
    for i in splited:
        if not emoji.is_emoji(i):
            return await msg.answer(f'"{i}" - не эмодзи, попробуй другие\nЕсли ты всё на самом деле написал всё корректно но бот выдал ошибку, напиши мне')
    await state.update_data(marks=msg.text)
    await msg.answer("К сожелению, на каждом устройстве отступы отображаются по разному, так что ты можешь настроить их под себя\n\nЛибо устнови отступы (отличаются от устройства к устройству), либо отправь эмодзи заполнитель (всегда выглядит одинакого)\n\nНастрой так, чтобы все предметы были на одном уровне",
                     reply_markup=indents_kb)
    await msg.answer("Выбери и я покажу как это будет выглядеть", reply_markup=build_marks_kb(example_data, msg.text+",➖"))
    await state.set_state(ProfileStates.set_indent)

@router.message(ProfileStates.set_indent, F.text)
async def set_indent(msg: types.Message, session: AsyncSession, user:User,state: FSMContext):
    data = await state.get_data()
    cur_indent = data.get('indent', '➖')
    marks_count = data.get('marks_count', 5)
    
    if msg.text == RM_M_OK:
        user.marks_row = data['marks']+','+(" "*cur_indent if isinstance(cur_indent, int) else cur_indent)
        user.marks_count = marks_count
        await session.commit()
        await state.clear()
        await msg.answer('Установлено \n'+user.repr_mark_row, reply_markup=build_timetable_markup(user))
        return await profile(msg, session, user)
    
    if msg.text == RM_M_LEFT:
        cur_indent = cur_indent-1 if isinstance(cur_indent, int) else 4
        if cur_indent < 0: return await msg.answer("Нельзя сделать меньше")
    elif msg.text == RM_M_RIGHT:
        cur_indent = cur_indent+1 if isinstance(cur_indent, int) else 6
        if cur_indent > 11: return await msg.answer("Нельзя сделать больше")
    elif msg.text == RM_M_NO_INDENT: cur_indent = 0
    elif msg.text == RM_M_COUNT_LEFT:
        marks_count = marks_count-1
        if marks_count < 0: return await msg.answer("Нельзя сделать меньше")
    elif msg.text == RM_M_COUNT_RIGHT:
        marks_count = marks_count+1
        if marks_count > 20: return await msg.answer("Не ну это перебор...")
    elif msg.text == RM_M_NO_MARKS: marks_count = 0
    elif msg.text == RM_M_ALL_MARKS: marks_count = 20
    elif msg.text == RM_M_ANDROID: cur_indent = 5
    elif msg.text == RM_M_IPHONE: 
        cur_indent = 6
        await msg.answer("Note: на айфоне отступы работают плохо, лучше используй эмодзи заполнитель, к примеру ➖")
    elif msg.text == RM_M_PC: cur_indent = 7
    elif emoji.is_emoji(msg.text): cur_indent = msg.text 
    else: return await msg.answer("Я тебя не понял, пришли эмодзи для заполнителя или выбери вариант из предложенных", reply_markup=indents_kb)
    
    
    await state.update_data(indent=cur_indent)
    await state.update_data(marks_count=marks_count)
    
    await msg.answer("Так нормально?", reply_markup=build_marks_kb(example_data, data['marks']+","+(" "*cur_indent if isinstance(cur_indent, int) else cur_indent), marks_count))
    
    
