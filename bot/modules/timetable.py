import asyncio
import io
import os
import re, datetime
import time
import aiofiles
import aiohttp
from bs4 import BeautifulSoup as BS
from config import cfg
import pymupdf
from aiogram import types
from googleapiclient.discovery import build
from urllib.parse import unquote
import camelot,  re
from typing import Callable

from utils import *
from .types import *

class ConversionBackend(object): # кастомный бекенд для камелота, ускоряет работу раза в 3
    def convert(self, pdf_path, png_path):
        pymupdf.Document(pdf_path)[0].get_pixmap(dpi=120).save(png_path)


aliases_table = {
    'семинар': '🚌',
    'лекция дистанционно': '🛏Дист..',
    'дистанционная лекция': '🛏Дист.',
    'дистанционно лекция': '🛏Дист.',
    'ауд.': '',
    'произв.пр.': '🛠Пр.',
    'произ. практ.': '🛠Пр.',
    'практическое занятие': '🛠Пр.',
    'уч. практика': '🛠Пр.',
    'Уч. Пр.': '🛠Пр.',
    'Произв. пр.': '🛠Пр.',
    'лаб.': '🔬',
    'отмена': '',
    
    
    # 'Системное программирование':'Сис. прогр.',
    # 'Разработка веб-ПРИЛОЖЕНИЙ': 'Веб прогр.',
    # 'Технология разработки программного обеспечения': 'ТРИЗ',
    # 'Инструментальные средства разработки ПО': 'ИСРПО',
    # 'Инструментальные средства разработки программного обеспечения': 'ИСРПО',
    # 'Техническое документоведение в профессиональной деятельности': 'Тех. документоведение',
    # 'Физическая культура': 'Физ-ра',
    # 'Поддержка и тестирование программных модулей':'Тестирование модулей',
    # 'Иностранный язык в профессиональной деятельности': 'Англ. язык',
    # 'Иностранный язык в проф.деятельности': 'Англ. язык',
    # 'Экономика отрасли': 'Экономика',
    # 'Мененджмент в профессиональной деятельности': 'Мененджмент',
    # 'Математическое моделирование': 'Мат. модел.',
    # 'Основы философии': 'Философия',
    # 'Основы безопасности и защиты Родины': 'ОБЖ',
    # 'Прикладная': 'Прикладная',
    # 'ИСТОРИЯ': 'История',
    # 'МАТЕМАТИКА': 'Математика',
    # 'ФИЗИКА': 'Физика',
    # 'ЛИТЕРАТУРА': 'Литература',
    # 'ХИМИЯ': 'Химия',
    # 'БИОЛОГИЯ': 'Биология',
    # 'ГЕОГРАФИЯ': 'География',
    # 'ИНФОРМАТИКА': 'Информатика',
    # 'Компьютерные сети': 'Комп. сети',
    # 'Операционные системы и среды': 'Опер. системы',
    # 'Информационные. Технологии': 'Инф. технологии',
    # 'Безопасность жизнедеятельности': 'БЖ',
    # 'Элементы высшей математики': 'Вышмат',
    # 'Информационные технологии': 'Инф. технологии',
    # 'Архитектура аппаратных средств': 'Аппар. средства',
    # 'Архитектура аппаратн. средств': 'Аппар. средства',
    # 'Основы алгоритм. И программ.': 'Алгоритмизация',
    # 'Основы алгоритмизации и программирования': 'Алгоритмизация',
    # 'Разработка программных модулей': 'Прог. модули',
    # 'Правовое обеспечение проф.деятельности': 'Право',
    # 'ПМ.04. Сопровождение и обслуживание ПО комп. сист.': 'Комп. сист.',
    # 'ПМ.11. Разработка, администрирование и защита БД': 'Разработка БД',
    # 'Технология разработки и защиты бд': 'Разработка БД',
    # 'СТАНДАРТИЗАЦИЯ, Сертификация и техническое документоведение': 'Тех документоведение',
    
    # 'Микропроцессорные системы': 'Микропроцессоры',
    # 'ПМ.01.01. Проектирование цифровых устройств': 'Цифровые устройства',
    # 'Проектирование цифровых устройств': 'Цифровые устройства',
    # 'Настройка программного обеспечения сетевых устройств': 'Сетевые устройства',
    # 'Установка активных сетевых устройств': 'Сетевые устройства',
    # 'Дискретная математика': 'Математика',
    # 'ПМ.03.Техническое обслуживание и ремонт компьютерных систем и комплексов': 'Ремонт систем',
    # 'Техническое обслуживание и ремонт компьютерных систем и комплексов': 'Ремонт систем',
    # 'Программирование мобильных устройств': 'Мобильные устройства',
    # 'преподаватель':'',
    # 'Обеспечение качества функционирования компьютерных систем':'Качество систем',
}
def parse_schedule_from_pdf(timetable:Timetable):
    '''Парсинг расписания из pdf'''
    # я уже не помню как тут всё работает.....
    tm = time.perf_counter()
    # !! часто нужно калибровать числовые параметры (тестовым путём), тк меняют толщину и расположение линий в расписании
    tables = camelot.read_pdf(str(cfg.base_dir/'temp/pdf_files'/(timetable.name+'.pdf')), pages='all',copy_text=['h', 'v'],  line_scale=53, joint_tol=12, line_tol=12   , backend=ConversionBackend())
    schedule:dict[str, dict[str, WeekDay]] = {}
    for table in tables:
        data: list[list[str]] = table.df.values.tolist()
        if 'время' in data[0]: continue # таблица первого сентября
        # if len(data[0][2:])!=len(set(data[0][2:])): # Если ты не понимаешь почему эта ошибка, открывай дебаг вью камелота, скорее кривое расписание и нужно менять line_scale выше
        #     raise ConvertingError('Дубликаты в заголовке')
        if not(data[0][1] == '' or '№' in data[0][1]):
            for i in data:
                i.insert(1, '')
                
        for i in range(2, len(data[0])):
            if i >= len(data[0]): break
            if data[0][i-1] == data[0][i]:
                # удаляем столбец
                i=i
                for j in range(0,len(data)):
                    data[j].pop(i)
                    # data[j] = data[j][:i] + data[j][i+1:]
        
        try:
            data[1][1] = data[1][1].split()[-1]
        except IndexError: raise ConvertingError(f'IndexError in data[1][1]')
        week_dates = {} # ищем и удаляем даты с раписания
        last_day = None # для фикса ситуации когда у ряда нет дня недели/цифры пары
        last_number = 0 # для фикса при отсутсвии номеров пар
        for i in range(1, len(data)):
            if not data[i][0] and not data[i][1] and last_day and any(data[i][j] for j in range(2, len(data[i]))):
                data[i][0] = last_day 
                data[i][1] = str(int(data[i-1][1])+1) # TODO: писать не цифру а "вне пар" (сейчас числа используются для всего)
            if data[i][0]:
                if last_day != data[i][0]: last_number = 0
                last_day = data[i][0]
            for j in range(2, len(data[i])):
                t = re.findall(r'\b\d{2}\.\d{2}\.\d{2}(?:\d{2})?\b', data[i][j])
                if t:
                    week_dates[data[i][0]] = t[0]
                    data[i][j]=''
            if not data[i][1]:
                last_number += 1
                data[i][1] = str(last_number)
            if i>1 and data[i][1]==data[i-1][1] and data[i][0]==data[i-1][0]:
                data[i][1] += '.5' # для второй полупары добавляем половинку, просто чтобы люди не запутались

        # тут уже тупо распихиваем готовую инфу и форматируем текст
        for i in range(1, len(data)):
            row = data[i]
            for j in range(2, len(row)):
                if row[1].endswith('.5') and data[i][j] == data[i-1][j]: continue
                cont = reduce(lambda x,y: repl(x,y, aliases_table[y]), aliases_table, delete_spaces(row[j].replace('\n', ' '))).strip()
                cont = re.sub(r'(\b[A-ZА-ЯЁ]{3,}\b(?:\s+\b[A-ZА-ЯЁ]+\b)+)', lambda x: x.group(0).capitalize(), cont)
                
                teacher = re.findall(r'\b[А-ЯЁ][а-яё]*\s[А-ЯЁ]\.\s?[А-ЯЁ]\.?\b',cont) #\b[А-ЯЁ][а-яё]+\s[А-ЯЁ]\.[А-ЯЁ]\.
                classroom = re.findall(r'\b\d{3}[a-zа-яё]?\b',cont)
                schedule.setdefault(data[0][j], {})
                schedule[data[0][j]].setdefault(row[0], WeekDay(weekday=weekdays.index(row[0].title()),date=week_dates.get(row[0], ''),lessons=[]))
                schedule[data[0][j]][row[0]].lessons.append(
                    Lesson(
                        content=cont,
                        number=row[1],
                        group=data[0][j],
                        teacher=teacher[0] if teacher else '',
                        classroom=classroom[0] if classroom else '',
                        co_groups=[data[0][x] for x in range(2, len(row)) if row[j]==row[x]], # and  j!=x and data[0][j][:-1]!=data[0][x][:-1] (не считать подгруппы)
                        canceled='отмена' in row[j].lower(), 
                        raw=row[j],
                        half_lesson_detected='.5' in row[1] or '.5' in data[min(i+1, len(data)-1)][1]
                    ))

    for gr in schedule: # удаляем пустые пары в конце
        for wd in schedule[gr]:
            i = schedule[gr][wd]
            t = []
            flag = False
            for x in reversed(i.lessons):
                if flag or x.content:
                    t.append(x)
                    flag = True
            i.lessons = list(reversed(t))
    
    logger.debug(f'Parsing time for {timetable.name}: {time.perf_counter()-tm:.2f}')
    timetable.groups = {gr: list(wd.values()) for gr, wd in schedule.items()}

def find_cogroups_in_timetables(timetables:list[Timetable]):
    for tt in timetables:
        for gr in tt.groups:
            for wd in tt.groups[gr]:
                for l in wd.lessons:
                    for tt2 in timetables:
                        for gr2 in tt2.groups:
                            for wd2 in tt2.groups[gr2]:
                                if wd2.weekday != wd.weekday: continue
                                for l2 in wd2.lessons:
                                    if l.content and l.number == l2.number and l.content == l2.content and l2.group not in l.co_groups:
                                        l.co_groups.append(l2.group)
                                        l2.co_groups.append(l.group)

def by_teacher(lesson: Lesson): return lesson.teacher
def by_classroom(lesson: Lesson): return lesson.classroom
def group_timetable_by(timetables:list[Timetable], f:Callable[[Lesson], str]):
    '''Группирует расписание по ключу из распарсеного расписания студентов'''
    r: dict[str, list['WeekDay']] = {}
    for tt in timetables:
        for gr in tt.groups:
            for wd in tt.groups[gr]:
                for l in wd.lessons:
                    if f(l):
                        r.setdefault(f(l), [])
                        d = next((i for i in r[f(l)] if i.weekday==wd.weekday), None)
                        if d is None:
                            d = WeekDay(weekday=wd.weekday, date=wd.date, lessons=[])
                            r[f(l)].append(d)
                        if not next((i for i in d.lessons if i.number==l.number and i.content==l.content), None):
                            d.lessons.append(l)
    r2 = {}
    for pr in sorted(r):
        for wd in sorted(r[pr], key=lambda x: x.weekday):
            t = {float(i.number) for i in wd.lessons}
            for i in range(1,int(max(t))):
                if i not in t:
                    wd.lessons.append(Lesson('',str(i), '', '', '', [], ''))
            wd.lessons.sort(key=lambda x: x.number)
            r2.setdefault(pr, []).append(wd)  
    return r2


# def find_timetable_diff(new: dict[str, list['WeekDay']], old: dict[str, list['WeekDay']] = None):
#     if old is None: return
    
#     for gr in new:
#         ogrps = old.get(gr)
#         if not ogrps: continue
#         diff: dict[WeekDay, list[Diff]] = {}

#         for wd in new[gr]:
#             diffs = []
#             owd = next((i for i in ogrps if i.weekday == wd.weekday), None)
#             if not owd:
#                 diffs = [Diff(None, l) for l in wd.lessons if l.content]
#             else:
#                 for l in wd.lessons:
#                     if not l.content: continue

#                     ol = next((i for i in owd.lessons if i.number == l.number and i.content), None)
                    
#                     if not ol: diffs.append(Diff(None, l))
#                     elif l.canceled and not ol.canceled: diffs.append(Diff(l, None))
#                     elif l.content != ol.content: diffs.append(Diff(ol, l))

#                 for ol in owd.lessons:
#                     if not ol.content: continue
#                     if not next((i for i in wd.lessons if i.number == ol.number and i.content), None):
#                         diffs.append(Diff(ol, None))
            
#             if diffs: diff[wd] = diffs

#         for wd in diff:
#             for df in diff[wd]:
#                 if df.type != DiffType.NEW: continue
#                 for j_wd in diff:
#                     for d in diff[j_wd]:
#                         if df.type != DiffType.CANCELED: continue
#                         if df.new.content.replace(df.new.classroom, '') == d.old.content.replace(d.old.classroom, ''):
#                             df.old = d.old
#                             df.new_day = j_wd
#                             diff[j_wd].remove(d)
#             wd.diffs = diff[wd]
def find_timetable_diff(new: dict[str, list['WeekDay']], old: dict[str, list['WeekDay']] = None):
    if old is None: return
    
    for gr in new:
        ogrps = old.get(gr)
        if not ogrps: continue
        diff: dict[WeekDay, list[Diff]] = {}

        for wd in new[gr]:
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
            
            if diffs: diff[wd] = diffs

        for wd in diff:
            for df in diff[wd]:
                if df.type != DiffType.NEW: continue
                for j_wd in diff:
                    for d in diff[j_wd]:
                        if df.type != DiffType.CANCELED: continue
                        if df.new.content.replace(df.new.classroom, '') == d.old.content.replace(d.old.classroom, ''):
                            df.old = d.old
                            df.new_day = j_wd
                            diff[j_wd].remove(d)
            wd.diffs = diff[wd]

shorter_table = {
    '.pdf': '',
    '\n': '',
    'Расписание': '',
    'студентов': '',
    'преподователей': '',
    'курса': 'курс',
    'специальности ': '',
    'специальностей ': '',
    '09.02.07': 'прога',
    '09.02.01': 'железо',
    '09.02.08': '', # TODO придумать название для этого направления
    '01.02.08': '', # TODO придумать название для этого направления
    'и': '',
    ' класса': 'клс.',
    'после ': '',
    'на': '',
    'Информационные системы и программирование': 'прога',
    'Компьютерные системы и комплексы': 'железо',
}
from functools import reduce
async def get_all_timetables()-> list[Timetable]:
    '''скачивает все pdf ки с сайта'''
    if not os.path.exists(cfg.base_dir / 'temp/pdf_files'): os.makedirs(cfg.base_dir / 'temp/pdf_files')
    for i in os.listdir(cfg.base_dir/'temp/pdf_files/'): os.remove(cfg.base_dir/'temp/pdf_files'/i)
    result = []
    async with aiohttp.ClientSession(trust_env=True) as sesion:
        async with sesion.get('https://ci.nsu.ru/education/schedule/', timeout=aiohttp.ClientTimeout(10)) as resp:
            with open(cfg.base_dir/'temp/pagecopy.html', 'w') as file:
                file.write(await resp.text())
            soup = BS(await resp.text(), 'html.parser')
            items = soup.find_all('a', class_='file-link')
            for i in items:
                link = unquote(i.get('href').replace('\n','').strip())
                if 'Основное' in link: continue
                date = re.findall(r'\d\d.\d\d.\d\d', link)[-1] or ''
                tt = Timetable(
                    name=delete_spaces(reduce(lambda x,y: x.replace(y, shorter_table[y]), shorter_table, link.split('/')[-1].replace(date,''))).strip(),
                    # name=link.split('/')[-1].translate(shorter_table).replace(date,'').strip(),
                    # name=link.split('/')[-1].replace('.pdf','').replace('\n','').replace('Расписание','').replace('студентов','').replace('преподователей','').replace('курса','курс').replace('специальности ','').replace('09.02.07','программирование').replace('09.02.01','железо').replace(' класса','клс.').replace('после ','').replace('на','').replace('Информационные системы и программирование','программирование').replace('Компьютерные системы и комплексы','железо').replace(date,'').replace('  ', ' ').strip(),
                    link=link,
                    date=datetime.datetime(year=int(date.split('.')[2]),month=int(date.split('.')[1]),day=int(date.split('.')[0])),
                    images=[], groups={})
                for i in result:
                    if i.name == tt.name:
                        result.remove(i)
                result.append(tt)
                async with sesion.get('https://ci.nsu.ru'+tt.link if not tt.link.startswith('https://') else tt.link, allow_redirects=True) as r:
                    async with aiofiles.open(cfg.base_dir/'temp/pdf_files'/(tt.name+'.pdf'), 'wb') as file:
                        await file.write(await r.read())
                    doc = pymupdf.Document(cfg.base_dir/'temp/pdf_files'/(tt.name+'.pdf'))
                    for page in doc:
                        tt.text_content += page.get_text()
    # DELETE ME
    # result += [Timetable('1 спо TEST', '', datetime.datetime(2022, 3, 10), [], {'2401в2':[]})]
    return sorted(result, key=lambda x: x.name)


async def pdfs_to_image(bot, tts):
    '''рендерит и кэширует фотки расписания в тг'''
    if not os.path.exists(cfg.base_dir / 'temp/images'): os.makedirs(cfg.base_dir / 'temp/images')
    for i in os.listdir(cfg.base_dir/'temp/images'): os.remove(cfg.base_dir/'temp/images'/i)
    for tt in tts:
        for page in pymupdf.Document(cfg.base_dir/'temp/pdf_files'/(tt.name+'.pdf')):
            img = page.get_pixmap(dpi=100).tobytes()
            msg = await bot.send_document(cfg.temp_group if cfg.temp_group else cfg.superuser, types.BufferedInputFile(img, filename=tt.name+'.png'),disable_notification=True)
            tt.images.append(msg.document.file_id)

def get_contacts(creds) -> list[Contact]:
    '''Скачивает контакты с кабинета сотрудника вки'''
    service = build('people', 'v1', credentials=creds)
    data = []
    token = None
    while True:
        results = service.people().listDirectoryPeople(
            readMask='names,emailAddresses,phoneNumbers,photos,organizations',
            sources = ['DIRECTORY_SOURCE_TYPE_DOMAIN_CONTACT', 'DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE'],
            pageSize=1000,
            pageToken=token
        ).execute()
        
        for person in results.get('people', []):
            names = person.get('names', [])
            emails = person.get('emailAddresses', [])
            photos = person.get('photos', [])
            orgs = person.get('organizations', [])
            
            title = (orgs[0].get('title') if orgs else None) or (orgs[0].get('department') if orgs else None) or ''
            is_student = bool(re.match(r'^\d{3,4}[a-z]{1,2}\d$', title))
            
            if is_student:
                title = title.translate(en_to_ru)
            
            c = Contact(
                name=names[0].get('displayName') if names else 'No Name',
                email=emails[0].get('value') if emails else 'No Email',
                photo=photos[0].get('url') if photos else None,
                title=title,
                is_student=is_student
            )
            if 'Unknown' in c.name or c.name.startswith('sum'): continue
            data.append(c)
            
        token = results.get('nextPageToken')
        if not token: break
    return data


