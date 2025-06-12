import time
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardButton, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State

import psutil

CD_MAKE_POST = 'post'
CD_WRITE_PM = 'pm'
CD_RELOAD_BOT = 'reload'
CD_COMMAND_PROMPT = 'cmd'
CD_UPDATE = 'update'
CD_LOGS = 'logs'
CD_BAN = 'ban'
CD_SHELL = 'shell'

RM_CANCEL = '❌Cancel'
RM_CONFIRM = '✅Confirm'

RM_SEND_NOW = 'Now'
RM_SEND_LATER = 'As notification'

cancel_markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='❌Cancel')]], resize_keyboard=True,one_time_keyboard=True)

class AdminStates(StatesGroup):
    make_post_delay=State()
    make_post=State()
    select_pm_users=State()
    write_pm_delay=State()
    write_pm=State()
    command=State()
    shell=State()
    ban_time=State()
    ban_select=State()
    ban_reason=State()


def get_admin_panel():
    mem, disk = psutil.virtual_memory(), psutil.disk_usage('/')
    temp = hasattr(psutil, 'sensors_temperatures')
    if temp: temp=psutil.sensors_temperatures()
    m = f"""CPU: {psutil.cpu_percent()}%  {round(temp['cpu_thermal_zone'][0].current,1) if temp else 'ND'}°  {psutil.cpu_freq().current}MHz
RAM: {mem.percent}%  {round(temp['ddr_thermal_zone'][0].current,1) if temp else 'ND'}°  {int(mem.used/1024/1024)}Mb/{int(mem.total/1024/1024)}Mb
DISK: {disk.percent}%  {disk.used/1024/1024/1024:.1f}Gb/{disk.total/1024/1024:.1f}Gb
\nUptime: {(time.time()-psutil.boot_time())/3600/24:.1f} days"""

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text='📝Make post', callback_data=CD_MAKE_POST),
           InlineKeyboardButton(text='✉️Write PM', callback_data=CD_WRITE_PM))
    kb.row(InlineKeyboardButton(text='🔄Reload', callback_data=CD_RELOAD_BOT),
           InlineKeyboardButton(text='📥Update', callback_data=CD_UPDATE))
    kb.row(InlineKeyboardButton(text='🛠Eval', callback_data=CD_COMMAND_PROMPT),
           InlineKeyboardButton(text='🗒Logs', callback_data=CD_LOGS))
    kb.row(InlineKeyboardButton(text='🚫Ban', callback_data=CD_BAN),
           InlineKeyboardButton(text='⌨️Shell', callback_data=CD_SHELL))
    kb.row(InlineKeyboardButton(text='👥List users', switch_inline_query_current_chat='!user'))
    return m, kb.as_markup()

