import json
import os
import re
import base64
import aiofiles
from itertools import zip_longest
from aiogram import Router, html
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardButton, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.deep_linking import create_start_link

import aiohttp
from bs4 import BeautifulSoup as bs
from config import cfg
from db.models import User
from modules.types import *
from utils import *


start_message = f'''Привет, чтобы посмотреть расписание нажимай на кнопки ниже, напишу свою группу или начни писать фамилию преподователя

Все настройки в твоём /profile
Обязательно почитай /help, там много полезной информации
А ещё лучше подпишись на @vki_hub_bot_news, чтобы быть вкурсе обновлений

{html.bold('MAINTAINER WANTED:')} боту нужен новый главный разработчик, обязательно {html.link('загляни на github', 'https://github.com/DedMaxTech/VkiHub')}

PS: а ещё есть {html.link("бот", 'https://t.me/vki_dating_bot')} для знакомства вкишников...
'''
help_message = f'''Это бот-помошник для вкишника, он покажет тебе твоё расписсание и оценки, но, что самое важное, пришлёт тебе всё новое как только обновится


Команды:
/profile - Твой профиль и настройки, тут ты можешь:
* Настроить, какое расписание тебе каждый день будет присылать бот
* Привязать и настроить аккаунт НГУ для оценок (подробнее ниже)
* Искать всех студентов и преподователей колледжа, по ФИО, группе или должности

/marks - Смотреть свой дневник
* Изначально необходимо привязать свой личный кабинет НГУ через логин и пароль (приходится так, тк сам по себе кабинет часто выкидывает)
* При вызове команды ты видишь свои последние 5 оценок (кстати, включая Нки, в отличии от сайта)
* Если нажать на предмет, оценки вместе с темами подробно откроются в инлайн режиме (но по приколу можешь использовать метод просмотр через сообщения ввиде меню)
* В профиле ты можешгь настроить иконки для отображения оценок, у каждого свои вкусы

Сокращения в расписании:
🚌 - Семинар
🛏 - Дистант
🛠 - Практика
🔬 - Лабараторная
{html.underline('Аудитория')}
{html.link('Группа/Преподователь', 'https://rb.gy/oogygp')}
(+ {html.link('грп1', 'https://rb.gy/oogygp')}, {html.link('грп2', 'https://rb.gy/oogygp')}) - группы, с которыми совместная пара
{html.strikethrough('🚫Отмена пары')}

Не хочешь сидеть на дистанте? Используй {html.link('расширение для Mts Link', 'https://github.com/DedMaxTech/MtsLinkFixer')}

/schedule - Просто статичное расписание звоноков, можно припинить к верху

/help - Это сообщение

Если ты знаешь как улучшить бота или хочешь ознакомиться с кодом, вот его {html.link('github', 'https://github.com/DedMaxTech/VkiHub')}
Также для информации об обновлениях крайне советую подписаться на @vki_hub_bot_news

По всем репортам, вопросам и предложениям пишите мне или в этот канал

{html.italic(f'by @dedmaxtech & {html.link("contributors", "https://github.com/DedMaxTech/VkiHub/graphs/contributors")}')}
'''

legal_notice = """Ваши данные (логин и пароль) будут храниться в базе данных бота и использоваться исключительно для авторизации и получения информации с cab.nsu.ru
Пароль хранится в зашифрованном виде

Информация с cab.nsu.ru (оценки, приказы и тд.) храняться только в виде кэша в оперативной памяти бота, и доступ к ним имеете только вы через команды бота

Вы можете безвозвратно стереть свои данные (логин,пароль) из бд бота, нажав на кнопку "Отвязать аккаунт" в своём профиле(/profile)
"""

example = {
    "физкультура": "домой",
    "Безопасность жиннедеятельности": "БЖ",
    "кабинет": "каб",
}

enter = '\n'
abbreviation_message = f"""
Ты можешь настроить свой список сокращений которые будут применяться в расписании
{html.blockquote('Зачем?')}
Благодаря этому  названия предметов адекватнее и само расписание визуально меньше (в идеале в одну стоку)

Пожалуйста, отправь json словарь со строками или слова разделенные = (примеры ниже), или выбери пресет
{html.pre(json.dumps(example, ensure_ascii=False, indent=0))}
или
{html.pre(enter.join([k+'='+v for k,v in example.items()]))}

Чтобы не писать полный словарь с нуля, можешь использовать словарь сокращений по умолчанию
{html.pre(json.dumps(default_abbreviation, ensure_ascii=False, indent=0))}
Если установить словарь по умолчанию, он будет автоматически обновляться и исправляться разработчиком

{html.blockquote('Почему есть строки по типу Математика=Математика?')}
Строки на замену не зависят от регистра, и это позволяет починить СтРоКи НАПИСАНЫЕ очеНЬ интересным способом

В ключах для замены можно писать {html.link('регулярные выражения', 'https://docs.python.org/3/library/re.html')}. Также по умолчаюнию ".." означает незаконченое слово

Полностью отключать сокращения не стоит
"""

rings_tt = """Расписание звонков: <code>
1п:  9:00-9:45  |  9:50-10:35
2п: 10:45-11:30 | 11:35-12:20
         обед 40 мин
3п: 13:00-13:45 | 13:50-14:35
4п: 14:45-15:30 | 15:35-16:20
5п: 16:30-17:15 | 17:20-18:05
</code>"""


RM_CANCEL = '❌Отменить'

RM_M_OK = '✅Мне всё нравится'
RM_M_LEFT = '⏪Уменьшить отступ'
RM_M_RIGHT = 'Увеличить отступ⏩'
RM_M_ANDROID = '📱Для андроида'
RM_M_IPHONE = '☎️Для айфона'
RM_M_PC = '🖥Для ПК'

RM_YES = '✅Да'
RM_NO_ACCOUNT = 'У меня нет аккаунта('
RM_SKIP_GROUP = 'Настрою позже'
RM_NOT_LINK = 'Не связывать (не рекомендуется)'

RM_ABBR_SHORT = 'Основные, без сокращений предметов'
RM_ABBR_FULL = 'По умолчанию (основное и предметы)'

indents_kb = Rkb([[RM_M_OK,RM_CANCEL], [RM_M_LEFT, RM_M_RIGHT], [RM_M_ANDROID, RM_M_IPHONE,RM_M_PC], ['⚫️', '⬛',  '➖', '⏹']], "Эмодзи...", False)

CD_SET_GROUP = 'set_group'
CD_CLEAR_GROUP = 'unset_group'
CD_LINK_NSU = 'link_nsu'
CD_CHANGE_VISIBLE = 'change_visible'
CD_CLEAR_NSU = 'clear_nsu'
CD_MARKS = 'marks'
CD_MARKS_V2 = 'marksv2'
CD_CURTOMIZE_MARKS = 'customize_marks'
CD_SET_ABBREVIATIONS = 'set_abbreviations'


class ProfileStates(StatesGroup):
    setup_nsu=State()
    setup_group=State()
    set_group=State()
    set_login=State()
    set_password=State()
    config_visible=State()
    set_marks=State()
    set_indent=State()
    set_abbreviations=State()
    
class SubjectDetail(CallbackData, prefix="subject"):
    link: str


def build_timetable_markup(user: User, add_buttons: list[str] = None):
    grp = {}
    if not add_buttons: add_buttons = []
    
    for tt in cfg.timetables:
        grp.setdefault(tt.name[0], []).append(KeyboardButton(text=tt.name))
    # btns = [g[i:i+2] for g in grp.values() for i in range(0, len(g), 2) ]
    btns = [g for g in grp.values() ]
    
    if user.timetable: add_buttons.append('⭐️'+user.timetable)
    if user.last_timetable and user.timetable != user.last_timetable: add_buttons.append('🕓'+user.last_timetable)
    if add_buttons: btns.insert(0, [KeyboardButton(text=i) for i in add_buttons])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True, one_time_keyboard=False, input_field_placeholder='2301а1 / Пипич')

link_base = '/vkistudent/journal/detail/'

def build_marks_kb(marks: list[Subject],  marks_row, use_callbacks = False, add_buttons: list[list[InlineKeyboardButton]] = []):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text = ''.join([(mark(mk.mark, marks_row, format='{v},') or marks_row.split(',')[-2])
                            if mk else fill
                            for mk, fill in zip_longest(i.marks[-5:], [marks_row.split(',')[-1]]*5)])\
                    +i.name + "‎  "*30+'.' , 
            switch_inline_query_current_chat='!s'+base64.b64encode(i.link.replace(link_base,'').encode()).decode() if not use_callbacks else None,
            callback_data=SubjectDetail(link=i.link.replace(link_base,'')).pack() if use_callbacks else None
        )]
        for i in marks
    ]+add_buttons)
    

def bulid_profile_keyboard(user: User):
    txt = (f'Рассылка расписания: {user.timetable}' if user.timetable else 'Вы не выбрали расписание для рассылки')+'\n'+\
            (f'Аккаунт НГУ: {user.login}\nИконки оценок: {user.marks_row}' if user.login else 'Аккаунт НГУ не привязан')+'\n'+\
            (f'{len(user.abbrevioations)} сокращений' if user.abbrevioations is not None else 'Сокращения расписания по умолчанию')+\
            '\n\nНовости бота: @vki_hub_bot_news'
    im = InlineKeyboardBuilder()
    
    if user.timetable:
        im.row(InlineKeyboardButton(text='⚙️Сменить расписание', callback_data=CD_SET_GROUP),
               InlineKeyboardButton(text='⛔️Отменить рассылку', callback_data=CD_CLEAR_GROUP))
    else:
        im.row(InlineKeyboardButton(text= '⚙️Установить рассылку', callback_data=CD_SET_GROUP))
    
    im.row(InlineKeyboardButton(text= '📒Настроить сокращения', callback_data=CD_SET_ABBREVIATIONS))
        
    
    if user.login and user.password:
        im.row(InlineKeyboardButton(text='🧮Мои оценки', callback_data=CD_MARKS_V2),
               InlineKeyboardButton(text='📑Мои документы', switch_inline_query_current_chat="Мои приказы"))        
        im.row(InlineKeyboardButton(text='🪄Настроить иконки', callback_data=CD_CURTOMIZE_MARKS), 
               InlineKeyboardButton(text='⛔️Отвязать аккаунт', callback_data=CD_CLEAR_NSU))
        im.row(InlineKeyboardButton(text='✨Привязать телеграм к поиску' if not user.is_visible else '📵Отвязать мой тг', callback_data=CD_CHANGE_VISIBLE))
    else:
        im.row(InlineKeyboardButton(text= '🔗Привязать аккаунт НГУ', callback_data=CD_LINK_NSU))
        
    im.row(InlineKeyboardButton(text='🔎Поиск студентов/преподователей', switch_inline_query_current_chat=''))
    return txt, im.as_markup()