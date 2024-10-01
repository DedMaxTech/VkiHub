from dataclasses import dataclass, field
import datetime
import re
from aiogram import html
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
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, Timetable): return self.name == other.name
        else: return other == self.name
    
    @property
    def as_str(self):
        return f'{self.name} от {self.date.strftime("%d.%m.%Y")}'
    
    def __str__(self) -> str:
        return f"<Timetable {self.name} for {self.date}>"

base_abbreviation = {
    "ауд.": "",
    "отмена": "",
    "преподаватель":"",
    "семинар": "🚌",
    "лекция дистанционно": "🛏",
    "дистанционная лекция": "🛏",
    "дистанционно лекция": "🛏",
    "произв.пр.": "🛠",
    "произ. практ.": "🛠",
    "практическое занятие": "🛠",
    "уч. практика": "🛠",
    "Уч. Пр.": "🛠",
    "Произв. пр.": "🛠",
    "лаб.": "🔬",
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
    
    "Системное программирование":"Сист. прогр.",
    "Разработка веб-ПРИЛОЖЕНИЙ": "Веб",
    "Технология разработки программного обеспечения": "ТРИЗ",
    "Инструментальные средства разработки ПО": "ИСРПО",
    "Инструментальные средства разработки программного обеспечения": "ИСРПО",
    "Техническое документоведение в профессиональной деятельности": "Документоведение",
    "Физическая культура": "Физкультура",
    "Поддержка и тестирование программных модулей":"Тестирование",
    "Иностранный язык в профессиональной деятельности": "Английский",
    "Иностранный язык в проф.деятельности": "Английский",
    "Экономика отрасли": "Экономика",
    "Мененджмент в профессиональной деятельности": "Мененджмент",
    "Математическое моделирование": "Мат. модел.",
    "Основы философии": "Философия",
    "Основы безопасности и защиты Родины": "ОБЖ",
    "Компьютерные сети": "Комп. сети",
    "Операционные системы и среды": "Опер. системы",
    "Информационные. Технологии": "Инф. тех.",
    "Безопасность жизнедеятельности": "БЖ",
    "Элементы высшей математики": "Вышмат",
    "Информационные технологии": "Инф. тех.",
    "Архитектура аппаратных средств": "Аппар. средства",
    "Архитектура аппаратн. средств": "Аппар. средства",
    "Основы алгоритм. И программ.": "Алгоритмизация",
    "Основы алгоритмизации и программирования": "Алгоритмизация",
    "Разработка программных модулей": "Прог. модули",
    "Правовое обеспечение проф.деятельности": "Право",
    "ПМ.04. Сопровождение и обслуживание ПО комп. сист.": "Комп. сист.",
    "ПМ.11. Разработка, администрирование и защита БД": "Разработка БД",
    "Технология разработки и защиты бд": "Разработка БД",
    "СТАНДАРТИЗАЦИЯ, Сертификация и техническое документоведение": "Документоведение",
    
    "Микропроцессорные системы": "Микропроцессоры",
    "ПМ.01.01. Проектирование цифровых устройств": "Цифровые устройства",
    "Проектирование цифровых устройств": "Цифровые устройства",
    "Настройка программного обеспечения сетевых устройств": "Сетевые устройства",
    "Установка активных сетевых устройств": "Сетевые устройства",
    "Дискретная математика": "Математика",
    "ПМ.03.Техническое обслуживание и ремонт компьютерных систем и комплексов": "Ремонт систем",
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
            else: t = t.replace(self.teacher, html.link(self.teacher, await create_start_link(bot, 't:'+self.teacher, True)) if bot else self.teacher)
            
            if hide_my_group:
                if self.other_cogroups and 'дистанц' not in self.content.lower(): t+=f' (+ {await group_groups(self.other_cogroups, bot)})'
            else: t += (' ' if hide_teacher else '| ') + await group_groups(self.co_groups, bot)   
        
        
        if self.classroom: t = t.replace(self.classroom, html.underline(html.link(self.classroom, await create_start_link(bot, 't:'+self.classroom, True)) if bot else self.classroom))
        if self.canceled: t = html.strikethrough(t)
        if t[-1]=='.': t = t[:-1]
        if self.half_lesson_detected: t+=f'\n⚠️Полупара, перепроверьте расписание на {self.number.split(".")[0]} пару. {html.link("Почему так?", "https://github.com/DedMaxTech/VkiHub/issues/2")}'
        if user:
            for k, v in (default_abbreviation if user.abbrevioations is None else user.abbrevioations).items():
                t = re.sub(k, v, t, flags=re.IGNORECASE)
        return t.strip()
    @property
    def text_number(self): #замена цифры на эмодзи
        if self.number[0].isdigit():
            return f'{"1️⃣,2️⃣,3️⃣,4️⃣,5️⃣".split(",")[int(self.number[0])-1]}{self.number[1:]}'
        else: return self.number
    
    @property
    def other_cogroups(self): # todo refactor
        return [gr for gr in self.co_groups if gr[:-1 if 'дистанц' not in self.content.lower() else -2] != self.group[:-1 if 'дистанц' not in self.content.lower() else -2]]

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



class DiffType(enum.Enum):
    CANCELED = '🔴Отмена'
    NEW = '🟢Новая'
    REPLACED = '🔵Замена'
    MOVED = '🟡Перенос'
    
    
@dataclass
class Diff:
    old: Lesson = None
    new: Lesson = None
    new_day: 'WeekDay' = None
    
    async def print(self, bot, user: User=None, hide_teacher = False, hide_my_group = True):
        if self.type == DiffType.CANCELED: return f"{self.type.value}: {await self.old.print(bot, user, hide_teacher, hide_my_group)}"
        if self.type == DiffType.NEW: return f"{self.type.value}: {await self.new.print(bot, user, hide_teacher, hide_my_group)}"
        if self.type == DiffType.REPLACED: return f"{self.type.value}: {await self.old.print(bot, user, hide_teacher, hide_my_group)}\nна {await self.new.print(bot, user, hide_teacher, hide_my_group)}"
        if self.type == DiffType.MOVED: 
            s = f"{self.type.value}: {await self.old.print(bot, user, hide_teacher, hide_my_group)}"
            if self.old.weekday.weekday != self.new_day.weekday or self.old.number !=self.new.number: s += f"\nна {html.underline(weekdays[self.new_day.weekday])} {self.new_day.date} {self.new.text_number} парой"
            if self.old.classroom != self.new.classroom: s += f"\nв кабинет {self.new.classroom}"
            return s
    
    @property
    def type(self) -> DiffType:
        match (self.old, self.new, self.new_day):
            case (_,None, None): return DiffType.CANCELED
            case (None,_, None): return DiffType.NEW
            case (_,_, None): return DiffType.REPLACED
            case (_,_,_): return DiffType.MOVED
    
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
        if not self.lessons: s+='Пары не найдены'
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
    match mark, are_absent:
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
    