from sqlalchemy import Column, Integer, BigInteger, DateTime, String, Boolean
from sqlalchemy.orm import declarative_base
import datetime
from transliterate import translit

BaseModel = declarative_base()


class User(BaseModel):
    __tablename__ = "User"

    id = Column(BigInteger, primary_key=True, unique=True, autoincrement=False)
    '''Telegram id'''
    username = Column(String(32), nullable=True)
    '''Telegram username'''
    first_name = Column(String(64), nullable=True)
    '''Telegram first name'''
    last_name = Column(String(64), nullable=True)
    '''Telegram last name'''
    
    created = Column(DateTime, default=datetime.datetime.now)
    '''Timestamp when user was created'''
    updated = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
    '''Timestamp of last update'''
    
    banned = Column(DateTime, default=datetime.datetime.now)
    '''End of user ban time'''

    notification_chat = Column(BigInteger, nullable=True)
    '''delayed message from chat (usual superuser)'''
    notification_msg = Column(Integer, nullable=True)
    '''delayed message id in chat'''
    
    timetable = Column(String(64), nullable=True)
    '''Configured timetable (1 спо / 101а1 / Пипич)'''
    login = Column(String(32), nullable=True)
    '''nsu.cab login'''
    password = Column(String(128), nullable=True)
    '''nsu.cab encrypted password'''
    cookie = Column(String(64), nullable=True)
    '''Cached nsu.cab cookie'''
    marks_row = Column(String(32), default='🟢,🟣,🟠,🔴,🚷,     ')
    '''Customized icons for marks'''
    fio = Column(String(32), nullable=True)
    '''Cached fio from nsu.cab profile for linking'''
    is_visible = Column(Boolean, default=False)
    '''Is user visible in global search'''
    
    last_timetable = Column(String(64), nullable=True)
    '''Last timetable used by user'''
    

    @property
    def repr_mark_row(self):
        s = self.marks_row.split(',')
        return f'5={s[0]}, 4={s[1]}, 3={s[2]}, 2={s[3]}, Н={s[4]}'
    
    @property
    def google_fio(self):
        if not self.fio: return None
        f,i,o = translit(self.fio, reversed=True).split()
        return f+i[0]+o[0]
    
    def is_banned(self):
        res = (self.banned-datetime.datetime.now()).total_seconds()
        return res if res>0 else 0
    
    def get_nick(self):
        return f'{self.id}@{self.username or ""}, {self.first_name} {self.last_name or ""}'.replace('  ', ' ')
    
    def details(self):
        return self.get_nick() + f'\ncrtd: {self.created.strftime("%d.%m.%Y %H:%M:%S")}, updt: {self.updated.strftime("%d.%m.%Y %H:%M:%S")}, banned: {self.banned.strftime("%d.%m.%Y %H:%M:%S")}'

    def __str__(self):
        # generate from model fields
        return f"<User {''.join([f'{k}: {v},' for k, v in self.__dict__.items() if not k.startswith('_')])}>"

