import re
from aiogram import Bot, Router, types
from cryptography.fernet import Fernet

import os,sys,traceback,logging
from config import cfg

logger = logging.getLogger('bot')

def chunk_text(text:str, num=4095) -> list[str]: 
    '''разделить текст по символам, часто нужно для разделения сообщений'''
    return [text[i:i+num] for i in range(0,len(text),num)]

# kinda deprecated
def remove_none(obj):
    t = type(obj)
    if issubclass(t, (tuple, list, set)): obj = t(remove_none(a) for a in obj)
    elif issubclass(t, dict): obj = {k: remove_none(v) for k, v in obj.items() if k is not None and v is not None}
    return obj

# рекурсивный сбор комманд с роутеров
def  collect_commands(router: Router, flag_name="command"):
    for handler in router.message.handlers:
        if flag_name not in handler.flags or "commands" not in handler.flags: continue
        yield types.BotCommand(command=handler.flags["commands"][0].commands[0], description=handler.flags[flag_name])
    for sub_router in router.sub_routers:
        yield from collect_commands(sub_router, flag_name)

async def reload_bot(bot:Bot=None):
    if bot: await bot.send_message(cfg.superuser, 'Restarting bot...')
    os.execv(sys.executable, [sys.executable] + sys.argv)

# тупой аналог json вывода словаря, old
def inspect_dict(data:dict,deep=0):
    if not isinstance(data, (dict, list)): return str(data)
    if isinstance(data, list): 
        return f'['+',\n'.join([inspect_dict(i, deep+1) for i in data])+']\n'
    return '{'+f',\n{"    "*deep}'.join([f'{k}: {inspect_dict(v,deep+1)}' for k,v in data.items()  if v is not None])+'}'


def delete_spaces(s:str) -> str:
    '''delete double spaces'''
    return re.sub(' +', ' ', s)

def repl(text, old, new=''):
    '''replace/delete case independed'''
    return re.sub(old, new, text, flags=re.IGNORECASE)

# def reduce(function, iterable, initializer=None):
    
#     it = iter(iterable)
#     if initializer is None:
#         value = next(it)
#     else:
#         value = initializer
#     for element in it:
#         value = function(value, element)
#     return value

async def send_error_message(bot:Bot,error: Exception, info: str|dict):
    '''отправка сообщений об ошибке, `info` - тг апдейт или кастомное сообщение'''
    text = f'ERROR: {error.__class__.__name__} - {error}\n'
    text +='INFO:\n' + (info if isinstance(info,str) else inspect_dict(info)) 
    text +=f'\nTRACEBACK: {traceback.format_exc()}'.replace(str(cfg.base_dir),''). replace('File ','').replace(', line ',':').replace(r'\venv\lib\site-packages','').replace('Traceback (most recent call last):','')
    logger.exception('error handle')
    try: 
        for s in chunk_text(text): await bot.send_message(cfg.superuser, s)
    except Exception as e:
        try: await bot.send_message(id, f'Error proccesing error...: {e}\nOriginal error: {error}') 
        except Exception as e2: print(f'Error proccesing error error: {e2},{e}\nOriginal error: {error}')
        
def Rkb(btns: list[list[str]], placeholder: str=None, one_time=True, persistent=False) -> types.ReplyKeyboardMarkup:
    """Alias for simple text keyboard"""
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=v) for v in row] for row in btns],
        resize_keyboard=True,
        one_time_keyboard=one_time,
        is_persistent=persistent,
        input_field_placeholder=placeholder
    )

# to encript/decript nsu cab password
def encrypt(message: str) -> str:
    return Fernet(cfg.encyption_key).encrypt(message.encode()).decode()

def decrypt(token: str,) -> str:
    return Fernet(cfg.encyption_key).decrypt(token.encode()).decode()

en_to_ru = str.maketrans({'a': 'а','b': 'б', 'v': 'в', 'g': 'г', 'd': 'д', 'e': 'е', 'j': 'ж', 'z': 'з', 
                        'i': 'и', 'к':'к', 'l':'л', 'm':'м', 'n':'н', 'o':'о', 'p':'п', 's':'с'})