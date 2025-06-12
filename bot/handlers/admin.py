import datetime
import subprocess
from types import CoroutineType
import aiogram
from aiogram import Router, Bot, html
from aiogram.filters import Command
from aiogram import types , flags, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.chat_action import ChatActionSender

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

import asyncio, traceback,logging

from db.models import User
from messages.admin import *
from config import cfg
from utils import send_error_message, reload_bot, Rkb

router = Router()
router.message.filter(F.from_user.id.in_(cfg.admins))

logger = logging.getLogger('bot')



@router.message(Command('admin'))
@flags.admin_command('Main admin panel')
async def admin(msg: types.Message):
    text, markup = get_admin_panel()
    await msg.answer(text, reply_markup=markup)

################ Token ################
@router.message(F.document & F.document.file_name == 'auth_token.json')
async def cancel(msg: types.Message,state: FSMContext):
    await msg.reply('Apply new token?', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Apply and restart', callback_data='token_confirm')]]))
    
@router.callback_query(F.data=='token_confirm')
async def token_cb(cb: types.CallbackQuery, state: FSMContext, bot:Bot):
    await bot.download(cb.message.reply_to_message.document, cfg.base_dir/'temp/auth_token.json')
    await cb.answer()
    await reload_bot(bot)

async def send_to_user(msg:types.Message,user:User):
    try: await msg.copy_to(user.id)
    except aiogram.exceptions.TelegramForbiddenError as e: await msg.answer(f'User {user.get_nick()}, {e}')

################ Cancel ################
@router.message(F.text==RM_CANCEL)
async def cancel(msg: types.Message,state: FSMContext):
    await state.clear()
    await msg.answer('Canceled👍')

################ Make post ################
@router.callback_query(F.data==CD_MAKE_POST)
async def make_post_cb(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.make_post_delay)
    await cb.message.answer("Send message now or as notification when user will use bot?", reply_markup=Rkb([[RM_SEND_NOW, RM_SEND_LATER, RM_CANCEL]]))
    await cb.answer()

@router.message(F.text, AdminStates.make_post_delay)
async def make_post(msg: types.Message, session: AsyncSession,state: FSMContext, bot:Bot):
    if msg.text not in (RM_SEND_NOW, RM_SEND_LATER): return await msg.answer('Select from keyboard', reply_markup=Rkb([[RM_SEND_NOW, RM_SEND_LATER, RM_CANCEL]]))
    await state.update_data(send_now = msg.text == RM_SEND_NOW)
    await msg.answer('Write a text that will be sent to all users, text markup (bold, monospace etc) will be saved', reply_markup=cancel_markup)
    await state.set_state(AdminStates.make_post)
    
@router.message(AdminStates.make_post)
async def make_post(msg: types.Message, session: AsyncSession,state: FSMContext, bot:Bot):
    if (await state.get_data())['send_now']:
        async with ChatActionSender.typing(msg.chat.id, bot):
            await asyncio.gather(*[send_to_user(msg,user) for user in (await session.execute(select(User))).scalars().all()])
        await msg.answer('Complite!')
    else:
        await session.execute(update(User).values(notification_chat=msg.chat.id,notification_msg=msg.message_id))
        await msg.answer('Message scheduled')
    await state.clear()


################ Write PM ####################
@router.callback_query(F.data==CD_WRITE_PM)
async def write_pm_cb(cb: types.CallbackQuery,state: FSMContext):
    await state.set_state(AdminStates.write_pm_delay)
    await cb.message.answer("Send message now or as notification when user will use bot?", reply_markup=Rkb([[RM_SEND_NOW, RM_SEND_LATER, RM_CANCEL]]))
    await cb.answer()
    

@router.message(F.text, AdminStates.write_pm_delay)
async def make_post(msg: types.Message, session: AsyncSession,state: FSMContext, bot:Bot):
    if msg.text not in (RM_SEND_NOW, RM_SEND_LATER): return await msg.answer('Select from keyboard', reply_markup=Rkb([[RM_SEND_NOW, RM_SEND_LATER, RM_CANCEL]]))
    await state.update_data(send_now = msg.text == RM_SEND_NOW)
    await state.set_state(AdminStates.select_pm_users)
    await state.update_data(users=[])
    await msg.answer('Send me users ids, one per message', reply_markup=Rkb([[RM_CONFIRM, RM_CANCEL]]))
    await msg.answer('You can search users by button below',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Search users', switch_inline_query_current_chat='!user')]]))

@router.message(AdminStates.select_pm_users, F.text==RM_CONFIRM)
async def write_pm_text(msg: types.Message,state: FSMContext):
    await state.set_state(AdminStates.write_pm)
    await msg.answer('Write a text that will be sent, text markup (bold, monospace etc) will be saved\nList of users:\n'+'\n'.join([i.get_nick() for i in (await state.get_data())['users']]), reply_markup=cancel_markup)

@router.message(AdminStates.select_pm_users, F.text)
async def write_pm_select_ids(msg: types.Message, session: AsyncSession,state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer('This is not user id')
    user = (await session.execute(select(User).filter(User.id==int(msg.text)))).scalar()
    if user is None: return await msg.answer('User not found')
    await state.update_data(users=(await state.get_data())['users']+[user])
    await msg.answer('User added: '+user.get_nick())

@router.message(AdminStates.write_pm, F.text | F.photo | F.animation | F.video)
async def write_pm(msg: types.Message,session: AsyncSession,state: FSMContext):
    if (await state.get_data())['send_now']:
        async with ChatActionSender.typing(msg.chat.id, msg.bot):
            await asyncio.gather(*[send_to_user(msg,user) for user in (await state.get_data())['users']])
        await msg.answer('Complite!')
    else :
        await session.execute(update(User).where(User.id.in_([i.id for i in (await state.get_data())['users']]))
                              .values(notification_chat=msg.chat.id,notification_msg=msg.message_id))
        await msg.answer('Message scheduled')
    await state.clear()

################ Update ####################
@router.callback_query(F.data==CD_UPDATE)
async def update_cb(cb: types.CallbackQuery ):
    await cb.answer()
    async with ChatActionSender.upload_document(cb.from_user.id, bot=cb.bot):
        try: 
            logging.info('Bot update called')
            text = html.code(subprocess.check_output(['git','pull'], cwd=cfg.base_dir, text=True))
            if text != 'Already up to date.': text += '\nReload bot to apply changes'
        except subprocess.CalledProcessError as e: 
            text = 'Unexpected error, check console'
        await cb.message.answer(text)
       
################ Command ####################
@router.callback_query(F.data==CD_COMMAND_PROMPT)
async def command_cb(cb: types.CallbackQuery,state: FSMContext):
    if cfg.allow_eval==0: return await cb.answer('Eval not allowed in config file',show_alert=True)
    if cfg.allow_eval==1 and cb.from_user.id != cfg.superuser: return await cb.answer('Only allowed to superuser',show_alert=True)
    await state.set_state(AdminStates.command)
    await cb.message.answer('Enter expression(s) to execute, like in async func body, view values via return\nYOU MUST KNOW WHAT YOU ARE DOING')
    await cb.answer()

@router.message(AdminStates.command, F.text)
async def command(msg: types.Message, session: AsyncSession, state: FSMContext):
    try: 
        exec(f"async def func():\n    " + msg.text.replace("\n", "\n    "), {**(globals().copy()), **(locals().copy())}, locals())
        res = await locals()["func"]()
    except Exception as e: res = traceback.format_exc()
    
    logger.warning(f'Command executed, = {msg.text}, result={res}')
    await msg.answer(html.code(html.quote(str(res))),parse_mode='HTML')
    await state.clear()
    
################ Shell ####################
@router.callback_query(F.data==CD_SHELL)
async def command_cb(cb: types.CallbackQuery,state: FSMContext):
    if cfg.allow_eval==0: return await cb.answer('Eval not allowed in config file',show_alert=True)
    if cfg.allow_eval==1 and cb.from_user.id != cfg.superuser: return await cb.answer('Only allowed to superuser',show_alert=True)
    await state.set_state(AdminStates.shell)
    await cb.message.answer('Enter terminal commands\nYOU MUST KNOW WHAT YOU ARE DOING')
    await cb.answer()

@router.message(AdminStates.shell, F.text)
async def command(msg: types.Message, session: AsyncSession, state: FSMContext):
    try: 
        result = subprocess.run(msg.text, shell=True, capture_output=True, text=True)
        res = f'Return code:{result.returncode}\n{"Error" if result.stderr else "Output"}: {html.code(html.quote(result.stdout or result.stderr))}'
    except Exception as e: res = traceback.format_exc()
    
    logger.warning(f'Command executed, = {msg.text}, result={res}')
    await msg.answer(res,parse_mode='HTML')
    await state.clear()

################ Reload ####################
@router.callback_query(F.data==CD_RELOAD_BOT)
async def reload_cb(cb: types.CallbackQuery, bot:Bot):
    await cb.answer()
    logger.info('Bot reloaded by user='+str(cb.from_user.id))
    await reload_bot(bot)

################ Ban ####################
@router.callback_query(F.data==CD_BAN)
async def ban_cb(cb: types.CallbackQuery ,state: FSMContext):
    await cb.answer()
    await state.set_state(AdminStates.ban_select)
    await cb.message.answer('Send me user id, you can find by "List users" command', reply_markup=cancel_markup)
    
@router.message(AdminStates.ban_select, F.text)
async def ban_select(msg: types.Message, session: AsyncSession,state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer('This is not user id')
    user = (await session.execute(select(User).filter(User.id==int(msg.text)))).scalar()
    if user is None: return await msg.answer('User not found')
    await state.update_data(user_id=user.id)
    await state.set_state(AdminStates.ban_time)
    await msg.answer('User added: '+user.get_nick()+f'\nEnter seconds for ban, you can enter in format like {html.code("60*60*24*7")} (a week)\nSend 0 to unban')

@router.message(AdminStates.ban_time, F.text)
async def ban_time(msg: types.Message, state: FSMContext):
    try: 
        secs=1
        for i in msg.text.replace(' ','').split('*'): secs*=int(i)
    except ValueError: return await msg.answer('Wrong format')
    await state.set_state(AdminStates.ban_reason)
    await state.update_data(secs=secs)
    await msg.answer('Send ban reason message or use Skip', reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='➡️Skip'),KeyboardButton(text='❌Cancel')]], resize_keyboard=True, one_time_keyboard=True))

@router.message(AdminStates.ban_reason, F.text)
async def ban(msg: types.Message, session: AsyncSession,state: FSMContext, bot:Bot):
    data=await state.get_data()
    secs=data['secs']
    
    user = User(id=data['user_id'],banned=datetime.datetime.now()+datetime.timedelta(seconds=secs))
    await session.merge(user)
    await session.commit()
    
    await state.clear()
    await bot.send_message(user.id,('You banned until '+user.banned.strftime('%d.%m.%y %H:%M:%S') if secs else 'You ve been unbanned')+ 
                                   ('\nReason: '+msg.text if msg.text!='➡️Skip' else ''))
    logger.warning(f'User banned {user.id} for {secs} seconds,{user.banned}, reason:{msg.text}')
    await msg.answer('Success')


################ Logs ####################
@router.callback_query(F.data==CD_LOGS)
async def log_cb(cb: types.CallbackQuery ,state: FSMContext):
    await cb.answer()
    log = cfg.base_dir/'temp/bot.log'
    if log.is_file(): 
        await cb.message.answer_document(types.FSInputFile(log))
        await cb.message.answer('Last lines of file:\n\n'+log.read_text()[-3000:])


################ Id ####################
@router.message(F.text, F.via_bot, F.via_bot.id == int(cfg.bot_token.split(':')[0]))
async def unban_cb(msg: types.Message, session: AsyncSession,state: FSMContext):
    if not msg.text.isdigit(): return
    u = await session.get(User, int(msg.text))
    if u: await msg.answer(u.details(), parse_mode=None)
    

################ List users ################
@router.inline_query(F.query.startswith('!user'))
async def inline_list_users(inline_query: types.InlineQuery, session: AsyncSession):
    offs = int(inline_query.offset) if inline_query.offset else 0
    users = (await session.execute(select(User))).scalars().all()
    res = [types.InlineQueryResultArticle(
        id=str(user.id),title=user.get_nick(),thumb_height=0,thumb_width=0,
        input_message_content=types.InputTextMessageContent(message_text=str(user.id)),
        description=user.details()
    ) for user in users  if not inline_query.query[6:] or inline_query.query.lower()[6:] in user.details().lower()][offs:offs+50]
    await inline_query.answer(results=res,next_offset=str(offs+50 if len(res)>0 else None), is_personal=True,cache_time=1, switch_pm_text='List of users', switch_pm_parameter='awesome')
    
@router.errors()
async def error_handle(err: types.ErrorEvent, bot:Bot):
    await send_error_message(bot, err.exception, err.update.dict())
