from dataclasses import dataclass, field
import datetime
import difflib
from functools import lru_cache
import re
from typing import Any
from aiogram import html
from aiogram import types, Bot
from aiogram.utils.deep_linking import create_start_link
import enum
from db.models import User

@dataclass
class Timetable:
    '''"Временное" расписание с сайта'''
    
    name:str
    '''Отформатированное и укороченое название с сайта'''
    link:str
    '''Ссылка на пдф'''
    date: datetime.datetime
    '''Запарсеная дата'''
    images: list[str]
    '''Список кэшированых айдишников изображений'''
    groups: dict[str, list['WeekDay']]
    '''Запарсеное расписание по группам'''
    text_content:str = ''
    '''Депрекейтед, использовалось как аналог хэша для сравнения изменений'''
    notes: str = ''
    '''Доп инфа по расписанию, обычно о ошибках парсинга'''
    
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, Timetable): return self.name == other.name
        else: return other == self.name
    
    @property
    def as_str(self):
        return f'{self.name} от {self.date.strftime("%d.%m.%Y")}'
    
    def __str__(self) -> str:
        return f"<Timetable {self.name} for {self.date}>"


@dataclass(frozen=True)
class ApiTimeSlot:
    id: int | None
    begin: str
    end: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ApiTimeSlot':
        return cls(
            id=data.get('id'),
            begin=data.get('begin') or '',
            end=data.get('end') or '',
        )


@dataclass(frozen=True)
class ApiLessonInfo:
    id: int | None
    name: str
    type: int | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ApiLessonInfo':
        return cls(
            id=data.get('id'),
            name=data.get('name') or '',
            type=data.get('type'),
        )


@dataclass(frozen=True)
class ApiNamedEntity:
    id: int | None
    name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> 'ApiNamedEntity | None':
        if not data:
            return None
        return cls(
            id=data.get('id'),
            name=data.get('name') or '',
        )


@dataclass(frozen=True)
class ApiSchoolClass:
    id: int | None
    name: str
    parallel: int | None
    subgroup: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ApiSchoolClass':
        return cls(
            id=data.get('id'),
            name=data.get('name') or '',
            parallel=data.get('parallel'),
            subgroup=data.get('subgroup'),
        )


@dataclass(frozen=True)
class ApiScheduleEntry:
    id: int | None
    weekday: int
    time: ApiTimeSlot
    lesson: ApiLessonInfo
    classroom: ApiNamedEntity | None
    teacher: ApiNamedEntity | None
    school_classes: list[ApiSchoolClass]
    parity: int | None
    show_for_current_week: bool
    parity_label: str | None
    parity_type: str | int | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ApiScheduleEntry':
        return cls(
            id=data.get('id'),
            weekday=data.get('weekday') or 0,
            time=ApiTimeSlot.from_dict(data.get('time') or {}),
            lesson=ApiLessonInfo.from_dict(data.get('lesson') or {}),
            classroom=ApiNamedEntity.from_dict(data.get('classroom')),
            teacher=ApiNamedEntity.from_dict(data.get('teacher')),
            school_classes=[ApiSchoolClass.from_dict(i) for i in (data.get('schoolClasses') or [])],
            parity=data.get('parity'),
            show_for_current_week=bool(data.get('show_for_current_week', True)),
            parity_label=data.get('parity_label'),
            parity_type=data.get('parity_type'),
        )


base_abbreviation = {
    r"\bауд..": "",
    "отмена": "",
    "преподаватель":"",
    "семинар": "🚌",
    "лекция дистанционно": "🛏",
    "дист.. лекция": "🛏",
    "дистанционно": "🛏",
    "лекция": "📖",
    "произ..пр..": "🛠",
    "практ..занят..": "🛠",
    "Уч..Пр..": "🛠",
    r"КП\.": "🛠",
    "Читальный зал": "Чит. зал",
    r"\bлаб..": "🔬",
    "  ": " ",
}
default_abbreviation = {
    **base_abbreviation,
    "История": "История",
    "Математика": "Математика",
    "Физика": "Физика",
    "Литература": "Литература",
    "Химия": "Химия",
    "Биология": "Биология",
    "География": "География",
    "Прикладная": "Прикладная",
    "Информатика": "Информатика",
    "Обществознание": "Обществознание",
    "Робототехника": "Робототехника",
    
    r"ПМ(\.\d\d){1,2}\.?\s?": "",
    "Системное программирование":"Сист. прогр.",
    "Разработка веб-ПРИЛОЖЕНИЙ": "Веб",
    "Технология разработки п..о..": "ТРПО",
    "Инструментальные средства разработки ПО": "ИСРПО",
    "Инструментальные средства разработки программного обеспечения": "ИСРПО",
    "Техническое документоведение в профессиональной деятельности": "Документоведение",
    "СТАНДАРТИЗАЦИЯ, Сертификация и техническое документоведение": "Документоведение",
    "Физическая культура": "Физкультура",
    "Поддержка и тестирование программных модулей":"Тестирование",
    "Иностранный язык в проф..деятельности": "Английский",
    "Англ..язык в проф..деятельности": "Английский",
    "Экономика отрасли": "Экономика",
    "Менеджмент в профессиональной деятельности": "Мененджмент",
    "Мененджмент в профессиональной деятельности": "Мененджмент",
    "Математическое моделирование": "Мат. модел.",
    "Основы философии": "Философия",
    "Основы безопасности и защиты Родины": "ОБЖ",
    "Основы безопасности жизнедеятельности": "ОБЖ",
    "Компьютерные сети": "Комп. сети",
    "Операционные системы и среды": "Опер. системы",
    "Информ..технологии": "Инф. тех.",
    "Безопасность жизнедеятельности": "БЖ",
    "Элементы высшей математики": "Вышмат",
    "Архитектура аппаратн..средств": "Аппар. средства",
    "Основы алгоритм..И программ..": "Алгоритмизация",
    "Основы алгоритмизации и программирования": "Алгоритмизация",
    "Разработка программных модулей": "Прог. модули",
    "Правовое обеспечение проф..деятельности": "Право",
    "Сопровождение и обслуживание П..О.. к..с..": "Обслуживание ПО",
    "Разработка, администрирование и защита БД": "Разработка БД",
    "Технология разработки и защиты б..д..": "Разработка БД",
    "Микропроцессорные системы": "Микропроцессоры",
    "Проектирование цифровых устройств": "Цифровые устройства",
    "Настройка программного обеспечения сетевых устройств": "Сетевые устройства",
    "Установка активных сетевых устройств": "Сетевые устройства",
    "Дискретная математика": "Математика",
    "Техническое обслуживание и ремонт компьютерных систем и комплексов": "Ремонт систем",
    "Программирование мобильных устройств": "Мобильные устройства",
    "Обеспечение качества функционирования компьютерных систем":"Качество систем"
}
@dataclass
class Lesson:
    '''Ячейка-урок с парса пдфки'''
    
    content: str
    '''Отформатированное название'''
    number: str
    '''Номер пары (может быть .5)'''
    group: str
    '''К какой группе относиться (используется для упрощения сортировок)'''
    teacher: str | None
    '''Спарсеный учитель'''
    classroom: str | None
    '''Спарсеная аудитория'''
    co_groups: list[str]
    '''Группы, у который стоит точно такая же пара'''
    conflict_groups: list[str]
    '''Группы, у который пара в этом же кабинете'''
    raw: str
    '''Оригинальный контент ячейки (по приколу)'''
    weekday: 'WeekDay'
    '''День недели пары'''
    canceled: bool = False
    '''Спарсеная отмена'''
    half_lesson_detected: bool = False
    '''На этом номере пары найдены полупары'''
    
    async def print(self, bot=None, user: User=None, hide_teacher = False, hide_my_group = True):
        t=f"{self.text_number}: {'🚫' if self.canceled else ''}{self.content or html.italic('       пропуск ')}"
        
        if self.content:
            if hide_teacher: t = t.replace(self.teacher, '')
            else: t = t.replace(self.teacher, html.link(self.teacher, await create_start_link(bot, 't:'+self.teacher, True)) if bot and self.teacher else self.teacher)
            
            if hide_my_group:
                if self.other_cogroups and not self.is_distant and len(self.other_cogroups)<6: t+=f' (+ {await group_groups(self.other_cogroups, bot)})'
            else: t += (' ' if hide_teacher else '| ') + await group_groups(self.co_groups, bot)   
            
            if not (hide_my_group or hide_teacher):
                t = t.replace(self.classroom, '')
            # elif self.conflict_groups and self.classroom and not self.is_distant: # TODO better conflict display
            #     t += f' (⚠️ {await group_groups(self.conflict_groups, bot)})'
        
        
        if self.classroom: t = t.replace(self.classroom, html.underline(html.link(self.classroom, await create_start_link(bot, 't:'+self.classroom, True)) if bot else self.classroom))
        if self.canceled: t = html.strikethrough(t)
        if t[-1]=='.': t = t[:-1]
        # if self.half_lesson_detected: t+=html.link("\n⚠️Полупара", "https://github.com/DedMaxTech/VkiHub/issues/2")
        if user:
            for k, v in (default_abbreviation if user.abbrevioations is None else user.abbrevioations).items():
                pattern = k.replace('..', r'\w*\.?\s*')
                if pattern.endswith(r'\s*'): pattern = pattern[:-3]
                t = re.sub(pattern, v, t, flags=re.IGNORECASE)
        return t.strip()
    
    @property
    def text_number(self): #замена цифры на эмодзи
        if self.number and self.number[0].isdigit():
            number_emoji = "1️⃣,2️⃣,3️⃣,4️⃣,5️⃣".split(",")
            index = int(self.number[0]) - 1
            if 0 <= index < len(number_emoji):
                return f'{number_emoji[index]}{self.number[1:]}'
        return self.number
    
    @property
    def minimal(self):
        return self.content.replace(self.classroom, '').replace(self.teacher, '')
    
    @property
    def other_cogroups(self): # todo refactor
        return [gr for gr in self.co_groups if gr[:-1 if not self.is_distant else -2] != self.group[:-1 if not self.is_distant else -2]]
    
    @property
    def is_distant(self):
        return 'дистанц' in self.content.lower()
    
    @staticmethod
    async def link(text: str, bot: Bot):
        return html.link(text, await create_start_link(bot, 't:'+text, True))

weekdays = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
async def group_groups(groups: list[str],bot=None):
    '''Сгруппировать подгруппы в группы...'''
    res = ''
    groups = groups.copy()
    groups.sort()
    while groups:
        t = groups[0]
        res += html.link(t, await create_start_link(bot, 't:'+t, True)) if bot else t
        if t[-1]!='2' and t[:-1]+'2' in groups: 
            groups.remove(t[:-1]+'2')
            res += '/' + (html.link(t[-2]+'2',await create_start_link(bot, 't:'+t[:-1]+'2', True)) if bot else t[-2]+'2')
        groups.remove(t)
        res += ', '
    return res[:-2]

def find_string_diff(old_text, new_text, max_length=10):
    f = lambda x: f'"{x}"' if len(x) < 2 else x
    diffs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_text, new_text).get_opcodes():
        if tag != 'equal':
            old_sub = old_text[i1:i2]
            new_sub = new_text[j1:j2]
            if len(old_sub) > max_length or len(new_sub) > max_length: return
            diffs.append((old_sub, new_sub, tag,i1, i2, j1, j2))
    
    if len(diffs) == 1:
        old_sub, new_sub, tag,i1, i2, j1, j2 = diffs[0]
        # old_text = old_text[:i1] + f'({f(old_sub)} → {f(new_sub)})' + old_text[i2:]
        # for 
            # old_text = old_text.replace(old_sub, f'({old_sub or quotes} → {new_sub or quotes})')
        return f'{f(old_sub)} → {f(new_sub)}' 

class DiffType(enum.Enum):
    CANCELED = '🔴Отмена'
    NEW = '🟢Новая'
    REPLACED = '🔵Замена'
    MOVED = '🟡Перенос'
    
    
@dataclass
class Diff:
    old: Lesson = None
    new: Lesson = None
    moved: bool = False
    
    async def print(self, bot, user: User=None, hide_teacher = False, hide_my_group = True):
        if self.type == DiffType.CANCELED: return f"{self.type.value}: {await self.old.print(bot, user, hide_teacher, hide_my_group)}"
        if self.type == DiffType.NEW: return f"{self.type.value}: {await self.new.print(bot, user, hide_teacher, hide_my_group)}"
        if self.type == DiffType.REPLACED: 
            # diff find here
            return f"{self.type.value}: {await self.old.print(bot, user, hide_teacher, hide_my_group)}\nна {await self.new.print(bot, user, hide_teacher, hide_my_group)}"
        if self.type == DiffType.MOVED: 
            s = f"{self.type.value}: {await self.old.print(bot, user, hide_teacher, hide_my_group)}"
            # if self.old.number !=self.new.number or self.old.weekday.weekday != self.new.weekday.weekday: 
            #     if self.old.weekday.weekday == self.new.weekday.weekday: s += f"\nна {self.new.text_number} пару"
            #     else: s += f"\nна {html.underline(weekdays[self.new.weekday.weekday])} {self.new.weekday.date} {self.new.text_number} парой"
            if self.old.weekday.weekday != self.new.weekday.weekday: 
                s += f"\nна {html.underline(weekdays[self.new.weekday.weekday])} {self.new.weekday.date} {self.new.text_number} парой"
            else:
                if self.old.number !=self.new.number: s += f"\nна {self.new.text_number} пару"
            if self.old.classroom != self.new.classroom: s += f"\nв кабинет {await Lesson.link(self.new.classroom, bot)}"
            if self.old.teacher != self.new.teacher: s += f"\nк {await Lesson.link(self.new.teacher, bot)}"
            if d:=find_string_diff(self.old.minimal, self.new.minimal): s += f"\nизменено: {d}"
            return s
    
    @property
    def type(self) -> DiffType:
        if not self.new: return DiffType.CANCELED
        if not self.old: return DiffType.NEW
        if not self.moved: return DiffType.REPLACED
        return DiffType.MOVED
    
    @staticmethod
    async def link(text: str, bot: Bot):
        return html.link(text, await create_start_link(bot, 'd:'+text, True))
    
    @staticmethod
    def changes(num:int):
        if num == 1: return 'изменение'
        if 1 < num < 5: return 'изменения'
        return 'изменений'

@dataclass()
class WeekDay:
    '''Пары сгруппированные по дню недели'''
    
    weekday:int
    '''Индекс дня недели'''
    date:str
    '''дата в формате 01.01.20, может быть пустой (часто)'''
    lessons: list[Lesson]
    '''Уроки в этот день'''
    diffs: list[Diff] = field(default_factory=list)
    '''Изменения в расписании на этот день'''
    
    async def print(self, bot=None, user: User=None, hide_teacher = False, hide_my_group = True):
        s=html.bold(weekdays[self.weekday].title())+' '+html.underline(self.date)+'\n'
        # s += '\n'.join([await i.print(bot, for_teacher) for i in self.lessons])
        for i in self.lessons: 
            cur_num_lessons = [x for x in self.lessons if x.content and x.number[0] == i.number[0]]
            if len(cur_num_lessons) > 1:
                index = cur_num_lessons.index(i)
                if index==0: s+='┏'
                elif index == len(cur_num_lessons)-1: s+='┗'
                else: s+='┣'
            s += await i.print(bot, user, hide_teacher, hide_my_group) + '\n'
            if i in cur_num_lessons and cur_num_lessons.index(i) == len(cur_num_lessons)-1 and any(x.half_lesson_detected for x in cur_num_lessons): 
                s += html.link("⚠️Полупара\n", "https://github.com/DedMaxTech/VkiHub/issues/2")
        if not self.lessons: s+='Пары не найдены\n'
        return s

    async def print_diffs(self, bot=None, user: User=None, hide_teacher = False, hide_my_group = True):
        return html.bold(weekdays[self.weekday].title())+' '+html.underline(self.date)+'\n'+'\n\n'.join([await i.print(bot, user, hide_teacher, hide_my_group) for i in self.diffs])
    def __hash__(self):
        return hash((self.weekday, self.date))

class ConvertingError(Exception):
    pass

@dataclass
class Contact:
    '''Контакт с гугл кабинета'''
    
    name: str
    '''Имя, обычно Фамилия Имя Отчество'''
    email: str
    '''Имеил'''
    photo: str
    '''Ссылка на аватарку, может быть пустой'''
    title: str
    '''Должность, у студней это группа, у преподов кафедра или должность'''
    is_student: bool
    '''тру если должность это группа'''
    tg_username: str|None = None
    '''Ник в телеграмме'''
    def str(self):
        tg_part = f"Tg: @{self.tg_username}" if self.tg_username else ""
        email_part = f"\n{self.email}" if self.email else ""
        return f"{self.name}\n{tg_part}{email_part}\n{self.title}"

def mark(m, marks_row='🟢,🟣,🟠,🔴,🚷', add_mark=False, compress=True, format=' {v}'):
    '''Преобразовать оценку'''
    marks_row = marks_row.split(',')
    match m:
        case '5': v = marks_row[0]
        case '4': v = marks_row[1]
        case '3': v = marks_row[2]
        case '2': v = marks_row[3]
        case '1': v = '⚠️'
        case 'Н': v = marks_row[4]
        case '': v = ''
        case _: v = format.format(v=m).title()
    if add_mark and m in '5432Н' and v not in '5️⃣4️⃣3️⃣2️⃣': v= m+v
    if compress: v = v.replace('Зачтено', 'Зач')
    return v

def get_thumb(mark, are_absent):
    '''Получить иконку оценки'''
    # TODO - перенести в локальный аплоад
    match mark[:1], are_absent:
        case '2', False: return 'https://i.imgur.com/a3u0JJl.png'
        case '2', True: return 'https://i.imgur.com/qxSw0pc.png'
        case '3', False: return 'https://i.imgur.com/pmrmKN3.png'
        case '3', True: return 'https://i.imgur.com/73O5Ths.png'
        case '4', False: return 'https://i.imgur.com/Y5cc17d.png'
        case '4', True: return 'https://i.imgur.com/WI9abmH.png'
        case '5', False: return 'https://i.imgur.com/AR8bEkf.png'
        case '5', True: return 'https://i.imgur.com/jIRavUB.png'
        case 'Н', False: return 'https://i.imgur.com/Uc2w2Nb.png'
        case 'Н', True: return 'https://i.imgur.com/Uc2w2Nb.png'
        case '', True: return 'https://i.imgur.com/Uc2w2Nb.png'
        case _, False: return 'https://i.imgur.com/0o6eY5C.png'
        case _, True: return 'https://i.imgur.com/RAiChwL.png'
        

@dataclass
class Mark:
    '''Оценка с кабинета нгу'''
    
    date: str
    '''Дата, обычно в формате 01.01.24'''
    type: str
    '''Тип оценки, обычно пустой, но может быть КН и тд'''
    is_absent: bool
    '''Стоит ли Нка'''
    mark: str
    '''Оценка, может быть число, число с +/-, зачёт, долг и тд'''
    theme: str
    '''Тема урока'''
    
    @property
    def are_empty(self):
        return not(self.is_absent or self.mark)
    
    def __eq__(self, value: object) -> bool:
        if isinstance(value, Mark): return self.date == value.mark
        else: return value == self.date
    
    def __str__(self): # {f"({self.type})" if self.type else ""}
        return f'{self.date}: {"🚷" if self.is_absent else ""}{mark(self.mark)} {self.theme}' 

@dataclass
class Subject:
    '''Предмет с оценками с кабинета нгу'''
    
    name: str
    '''Название предмета'''
    marks: list[Mark]
    '''Все оценки'''
    link: str
    '''Ссылка на страницу с оценками'''
    
    @property
    def marks_str(self):
        # return ''.join([mark(m.mark) for m in self.marks])
        return ''.join([mark(self.marks[i].mark) if i < len(self.marks) else ' '*7  for i in range(5)])
        
    

@dataclass
class Profile:
    '''Личный профиль с кабинета нгу'''
    
    name: str
    '''Имя, обычно Фамилия Имя Отчество'''
    group: str
    '''Группа'''
    image: str
    '''Ссылка на аватарку. Note: получить доступ к аве можно только с авторизированного запроса'''
    
@dataclass
class Order:
    '''Приказ с кабинета нгу'''
    
    title: str
    '''Название'''
    body: str
    '''Тело приказа'''
    
