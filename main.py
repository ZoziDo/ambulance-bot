import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, ADMIN_IDS
from database import init_db
from handlers.user import user_router
from handlers.admin import admin_router
from keyboards.reply import main_menu

# Настройка логирования
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Подключаем роутеры
dp.include_router(user_router)
dp.include_router(admin_router)

async def main():
    await init_db()
    print("✅ База данных инициализирована")
    
    # Приветственное сообщение для админов при запуске
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "🚑 Бот путевых листов запущен успешно!")
        except:
            pass
    
    print("🚀 Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())