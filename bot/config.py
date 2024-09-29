import os, pathlib
from modules.types import *
from dotenv import load_dotenv

load_dotenv(override=True)

class Settings():
    bot_token = os.getenv('BOT_TOKEN')
    superuser= int(os.getenv('BOT_SUPERUSER'))
    admins = [int(val) for val in os.getenv('BOT_ADMINS').split(',')]
    db_url = os.getenv('DB_URL')
    base_dir=dir = pathlib.Path(__file__).parent.parent
    allow_eval = int(os.getenv('BOT_ALLOW_EVAL') or '0')
    temp_group = int(os.getenv('TEMP_GROUP') or os.getenv('BOT_SUPERUSER'))
    encyption_key = os.getenv('ENCRYPTION_KEY').encode()
    
    
    # globals
    timetables: list[Timetable] = []
    '''all timetables from ci.nsu.ru, with parsed data'''
    contacts: list[Contact] = []
    '''contact from google directory'''
    subjects: dict[int, list[Subject]] = {}
    '''cached marks from cab.nsu.ru per user id'''
    teachers : dict[str, list['WeekDay']] = {}
    '''timetable for teachers (same as for groups in timetables)'''
    classrooms : dict[str, list['WeekDay']] = {}
    '''timetable for classrooms (same as for groups in timetables)'''
    last_timetable_update: datetime.datetime | None = None
    

try: cfg = Settings()
except Exception as e: raise Exception(f'Error creating config from .env file or ENV_VAR: {e.__class__.__name__} - {e}')