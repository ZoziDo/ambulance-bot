from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from models.models import Base
from config import DB_URL

# Создаём движок с защитой от разрыва соединений
engine = create_async_engine(
    DB_URL,
    echo=False,
    pool_pre_ping=True,        # Очень важно для стабильности
    pool_size=10,
    max_overflow=20,
)

# Создаём фабрику сессий
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)

async def init_db():
    """Инициализация базы данных + исправление последовательностей"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            print("✅ Таблицы успешно созданы / обновлены")

        # === ИСПРАВЛЕНИЕ ПОСЛЕДОВАТЕЛЬНОСТЕЙ ===
        async with AsyncSessionLocal() as session:
            # Для таблицы users
            await session.execute(text("""
                SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) + 1 FROM users), 1), false);
            """))
            # Для таблицы shifts
            await session.execute(text("""
                SELECT setval('shifts_id_seq', COALESCE((SELECT MAX(id) + 1 FROM shifts), 1), false);
            """))
            await session.commit()

        print("✅ Последовательности (sequences) успешно синхронизированы")

        # Проверяем таблицы
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public';"))
            tables = [row[0] for row in result.fetchall()]
            print(f"📋 Найденные таблицы: {tables}")

    except Exception as e:
        print(f"❌ Ошибка при инициализации базы: {e}")
        raise
