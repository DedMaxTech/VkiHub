from dataclasses import dataclass
import datetime
from aiogram import html
from aiogram.utils.deep_linking import create_start_link
import enum


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
    canceled: bool = False
    '''Спарсеная отмена'''
    half_lesson_detected: bool = False
    '''На этом номере пары найдены полупары'''
    
    async def print(self, bot=None, for_teacher = False):
        t=f"{self.text_number}: {'🚫' if self.canceled else ''}{self.content or html.italic('         пропуск ')}"
        if self.teacher: 
            if not for_teacher:
                t = t.replace(self.teacher, html.link(self.teacher, await create_start_link(bot, 't:'+self.teacher, True)) if bot else html.underline(self.teacher))
                if self.content and [gr for gr in self.co_groups if gr[:-1] != self.group[:-1]] and '🛏' not in self.content: 
                    t += f"(+ {await group_groups([gr for gr in self.co_groups if gr[:-1 if '🛏' not in self.content else -2] != self.group[:-1 if '🛏' not in self.content else -2]], bot)})"
            else: t = t.replace(self.teacher, await group_groups(self.co_groups, bot))
        
        if self.classroom: t = t.replace(self.classroom, html.underline(self.classroom))
        if self.canceled: t = html.strikethrough(t)
        if t[-1]=='.': t = t[:-1]
        if self.half_lesson_detected: t+=f'\n⚠️Обнаружена полупара, пожалуйста, перепроверьте расписание на {self.number.split(".")[0]} пару. {html.link("Почему так?", "https://github.com/DedMaxTech/VkiHub/issues/2")}'
        return t
    @property
    def text_number(self): #замена цифры на эмодзи
        if self.number[0].isdigit():
            return f'{"1️⃣,2️⃣,3️⃣,4️⃣,5️⃣".split(",")[int(self.number[0])-1]}{self.number[1:]}'
        else: return self.number
    
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
    REPLACED = '🟡Перенос'
    MOVED = '🔵Замена'
    
    
@dataclass
class Diff:
    old: Lesson = None
    new: Lesson = None
    new_day: 'WeekDay' = None
    

    
    def print(self):
        
        # match self.type:
        #     case DiffType.CANCELED: 
        #         return ''
        #     case DiffType.NEW: 
        #         self.new.print()
        #     case DiffType.REPLACED: 
        #         self.old.print() + '\n' + self.new.print()
        #     case DiffType.MOVED: 
        #         self.new_day.print()
        if self.type == DiffType.CANCELED: return ''
        if self.type == DiffType.NEW: return self.new.print()
        if self.type == DiffType.REPLACED: return self.old.print() + '\n' + self.new.print()
        if self.type == DiffType.MOVED: return self.new_day.print()
    
    @property
    def type(self):
        match (self.old, self.new, self.new_day):
            case (_,None, None): return DiffType.CANCELED
            case (None,_, None): return DiffType.NEW
            case (_,_, None): return DiffType.REPLACED
            case (_,_,_): return DiffType.MOVED

@dataclass()
class WeekDay:
    '''Пары сгруппированные по дню недели'''
    
    weekday:int
    '''Индекс дня недели'''
    date:str
    '''дата в формате 01.01.20, может быть пустой (часто)'''
    lessons: list[Lesson]
    '''Уроки в этот день'''
    
    async def print(self, bot=None, for_teacher = False):
        s=weekdays[self.weekday].title()+' '+self.date+'\n'
        # s += '\n'.join([await i.print(bot, for_teacher) for i in self.lessons])
        for i in self.lessons: 
            cur_num_lessons = [x for x in self.lessons if x.content and x.number[0] == i.number[0]]
            if len(cur_num_lessons) > 1:
                index = cur_num_lessons.index(i)
                if index==0: s+='┏'
                elif index == len(cur_num_lessons)-1: s+='┗'
                else: s+='┣'
            s += await i.print(bot, for_teacher) + '\n'
        if not self.lessons: s+='Пары не найдены'
        return s + '\n'
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
    