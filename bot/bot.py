from aiogram import F, Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import logging, asyncio
from logging.handlers import RotatingFileHandler

from config import cfg
from middlewares import *
from handlers import admin, basic, marks, timetable
from utils import *
from modules import loop
from db.models import User

# Logging
logger = logging.getLogger('bot')
logger.setLevel(logging.DEBUG)
log_format=logging.Formatter('%(levelname)s:%(asctime)s:%(message)s')
sh = logging.StreamHandler()
rh = RotatingFileHandler(cfg.base_dir/"temp/bot.log", maxBytes=1000*1000, backupCount=1, encoding='utf-8')
sh.setLevel(logging.WARNING)
rh.setLevel(logging.DEBUG)
sh.setFormatter(log_format)
rh.setFormatter(log_format)
logger.addHandler(rh)
logger.addHandler(sh)
logging.getLogger('aiogram').setLevel(logging.WARNING)
logging.getLogger('camelot').setLevel(logging.WARNING)

# Sqlalchemy
engine = create_async_engine(url=cfg.db_url)
sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

# Aiogram
bot = Bot(token=cfg.bot_token,  default=DefaultBotProperties(parse_mode="HTML", link_preview_is_disabled=True))
dp = Dispatcher()

# Order is important
dp.update.middleware(DbSessionMiddleware(session_pool=sessionmaker))
dp.update.middleware(AuthMiddleware())
dp.update.middleware(LoggingMiddleware(logger=logger))
dp.update.middleware(BanMiddleware())
dp.update.middleware(NotificationMiddleware())
dp.message.middleware(StudentMiddleware())
dp.callback_query.middleware(StudentMiddleware())


async def main():
    dp.include_router(admin.router)
    dp.include_router(basic.router)
    dp.include_router(marks.router)
    dp.include_router(timetable.router)

    # Set default and admins commands
    default_commands=list(collect_commands(dp))
    await bot.set_my_commands(default_commands, scope=types.BotCommandScopeAllPrivateChats())
    admin_commands=list(collect_commands(dp, 'admin_command'))
    for i in cfg.admins: await bot.set_my_commands(admin_commands+default_commands, scope=types.BotCommandScopeChat(chat_id=i))

    # run background loop
    asyncio.run_coroutine_threadsafe(loop.loop(bot,sessionmaker),asyncio.get_event_loop())
    
    await bot.send_message(cfg.superuser,'Bot started', disable_notification=True)
    logger.info('Bot started')
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
