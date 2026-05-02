import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL")
GROUP_ID = -1003845752683

# Защита от пустых значений
ADMIN_IDS = []
admin_str = os.getenv("ADMIN_IDS", "")
if admin_str:
    try:
        ADMIN_IDS = [int(x.strip()) for x in admin_str.split(",") if x.strip()]
    except:
        pass

# Проверка критических переменных
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен!")
if not DB_URL:
    raise ValueError("❌ DB_URL не установлен! Проверь Variables в Railway.")

print("✅ Config успешно загружен")
