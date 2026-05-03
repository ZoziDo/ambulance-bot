from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from datetime import date, timedelta   # ← Добавь timedelta сюда, если ещё нет

from keyboards.reply import main_menu, admin_menu
from config import ADMIN_IDS, GROUP_ID
from database import AsyncSessionLocal
from models.models import User, Shift
from sqlalchemy import select, update, func
from states import ShiftStates, RegistrationStates
from calculations import calculate_shift

user_router = Router()
user_router.active_shifts = {}


# ====================== ПРОВЕРКА БАНА ======================
async def is_banned(user_id: int, message: Message) -> bool:
    """Возвращает True, если пользователь забанен"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == user_id))
        user = result.scalar_one_or_none()
        if user and user.banned:
            await message.answer("⛔ Ваш доступ к боту был отклонён навсегда.\n\nОбратитесь к механику.")
            return True
    return False


@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    if await is_banned(message.from_user.id, message):
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == message.from_user.id))
        user = result.scalar_one_or_none()

        if user and user.approved and user.full_name and user.car_number:
            if message.from_user.id in ADMIN_IDS or user.role == "admin":
                await message.answer("👷 <b>Админ-панель</b>\nДобро пожаловать!", reply_markup=admin_menu())
            else:
                await message.answer("🚑 <b>Бот путевых листов скорой</b>\nДобро пожаловать!", reply_markup=main_menu())
            return

        # Регистрация
        if not user:
            user = User(tg_id=message.from_user.id, approved=False, banned=False, role="driver")
            session.add(user)
            await session.commit()

        if not user.full_name or not user.car_number:
            await state.set_state(RegistrationStates.waiting_full_name)
            await message.answer("👤 Введите ваше Ф.И.О полностью:")
            return

        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Я водитель скорой", callback_data="send_request")]])
        await message.answer("✅ Данные сохранены.\nНажмите кнопку для отправки заявки:", reply_markup=kb)


# ====================== РЕГИСТРАЦИЯ ======================
@user_router.message(RegistrationStates.waiting_full_name)
async def process_full_name(message: Message, state: FSMContext):
    if await is_banned(message.from_user.id, message):
        await state.clear()
        return
   
    full_name = message.text.strip()
    if len(full_name) < 5:
        await message.answer("❌ Пожалуйста, введите Ф.И.О полностью (минимум 5 символов):")
        return

    await state.update_data(full_name=full_name)
    await state.set_state(RegistrationStates.waiting_car_number)
    await message.answer("🚗 Введите номер машины:\nПример: Н337НН142 или А721АА142")


@user_router.message(RegistrationStates.waiting_car_number)
async def process_car_number(message: Message, state: FSMContext):
    if await is_banned(message.from_user.id, message):
        await state.clear()
        return

    car_number = message.text.strip().upper()

    if len(car_number) < 4:
        await message.answer("❌ Номер машины слишком короткий. Введите корректный номер:")
        return

    data = await state.get_data()
    full_name = data.get('full_name')

    if not full_name:
        await message.answer("⚠️ Ошибка. Начните регистрацию заново.")
        await state.clear()
        await state.set_state(RegistrationStates.waiting_full_name)
        await message.answer("👤 Введите ваше Ф.И.О полностью:")
        return

    # Сохранение
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User)
            .where(User.tg_id == message.from_user.id)
            .values(full_name=full_name, car_number=car_number)
        )
        await session.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я водитель скорой", callback_data="send_request")]
    ])

    await message.answer(
        f"✅ Регистрация завершена!\n\n"
        f"👤 Ф.И.О: {full_name}\n"
        f"🚗 Машина: {car_number}\n\n"
        "Нажмите кнопку ниже, чтобы отправить заявку на доступ:",
        reply_markup=kb
    )
    await state.clear()

# ====================== ЗАЯВКА ======================
@user_router.callback_query(F.data == "send_request")
async def send_access_request(callback: CallbackQuery):
    if await is_banned(callback.from_user.id, callback.message):
        return
    await callback.answer()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == callback.from_user.id))
        user = result.scalar_one_or_none()

        if not user or not user.full_name or not user.car_number:
            await callback.message.edit_text("❌ Сначала заполните Ф.И.О и номер машины.")
            return

        text = f"""🔔 <b>Новая заявка на доступ</b>

👤 Ф.И.О: {user.full_name}
🚗 Машина: {user.car_number}
🆔 ID: <code>{user.tg_id}</code>
📛 @{callback.from_user.username or 'нет'}"""

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{user.tg_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{user.tg_id}"),
            InlineKeyboardButton(text="🚫 Забанить", callback_data=f"ban_{user.tg_id}")
        ]])

        try:
            await callback.bot.send_message(GROUP_ID, text, reply_markup=kb, parse_mode="HTML")
            await callback.message.edit_text("✅ Заявка отправлена в группу!\nОжидайте решения.")
        except:
            await callback.message.edit_text("❌ Не удалось отправить заявку.")


# ====================== АДМИН ДЕЙСТВИЯ ======================
@user_router.callback_query(F.data.startswith("approve_"))
async def approve_user(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        await session.execute(update(User).where(User.tg_id == tg_id).values(approved=True, banned=False))
        await session.commit()

    await callback.message.edit_text("✅ Пользователь одобрен!")
    await callback.bot.send_message(tg_id, "🎉 Доступ одобрен!\nНажмите /start")
    await callback.answer()


@user_router.callback_query(F.data.startswith("reject_"))
async def reject_user(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        await session.execute(update(User).where(User.tg_id == tg_id).values(approved=False))
        await session.commit()

    await callback.message.edit_text("❌ Доступ отклонён.")
    await callback.bot.send_message(tg_id, "⛔ Доступ к боту отклонён.")
    await callback.answer()


@user_router.callback_query(F.data.startswith("ban_"))
async def ban_user(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        await session.execute(update(User).where(User.tg_id == tg_id).values(banned=True, approved=False))
        await session.commit()

    await callback.message.edit_text("🚫 Пользователь забанен.")
    await callback.bot.send_message(tg_id, "⛔ Ваш доступ к боту был отклонён навсегда.")
    await callback.answer()


# ====================== ОСНОВНЫЕ ФУНКЦИИ С ЗАЩИТОЙ ======================

@user_router.message(F.text == "🚑 Начать смену")
async def start_shift(message: Message, state: FSMContext):
    if await is_banned(message.from_user.id, message):
        return

    user_id = message.from_user.id
    today = date.today()

    async with AsyncSessionLocal() as session:
        # Защита: проверяем, есть ли уже открытая смена сегодня
        existing = await session.execute(
            select(Shift).where(
                Shift.user_id == user_id,
                Shift.date == today,
                Shift.end_km.is_(None)  # смена не завершена
            )
        )
        if existing.scalar_one_or_none():
            await message.answer("❌ У вас уже открыта смена на сегодня!")
            return

    await message.answer("📍 Введите начальный километраж:")
    await state.set_state(ShiftStates.waiting_start_km)


@user_router.message(F.text == "⛽ Заправка")
async def refuel(message: Message, state: FSMContext):
    if await is_banned(message.from_user.id, message):
        return

    user_id = message.from_user.id

    if user_id not in user_router.active_shifts:
        await message.answer("❌ Сначала начните смену!")
        return

    await message.answer("⛽ Сколько литров вы заправили?")
    await state.set_state(ShiftStates.waiting_refuel)


@user_router.message(F.text == "🏁 Завершить смену")
async def end_shift(message: Message, state: FSMContext):
    if await is_banned(message.from_user.id, message):
        return

    user_id = message.from_user.id

    if user_id not in user_router.active_shifts:
        await message.answer("❌ Сначала начните смену!")
        return

    await message.answer("📍 Введите конечный километраж:")
    await state.set_state(ShiftStates.waiting_end_km)


@user_router.message(F.text == "🏁 Завершить смену")
async def end_shift(message: Message, state: FSMContext):
    if await is_banned(message.from_user.id, message):
        return
    user_id = message.from_user.id
    if user_id not in user_router.active_shifts:
        await message.answer("❌ Сначала начните смену!")
        return
    await message.answer("📍 Введите конечный километраж:")
    await state.set_state(ShiftStates.waiting_end_km)


# ==================== МОЯ ИСТОРИЯ ====================
@user_router.message(F.text == "📖 Моя история")
async def my_history(message: Message):
    if await is_banned(message.from_user.id, message):
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сегодня", callback_data="history_today")],
        [InlineKeyboardButton(text="За 7 дней", callback_data="history_7days")],
        [InlineKeyboardButton(text="За 30 дней", callback_data="history_30days")],
        [InlineKeyboardButton(text="Текущий месяц", callback_data="history_month")],
        [InlineKeyboardButton(text="Все смены", callback_data="history_all")]
    ])

    await message.answer("📖 Выберите период для просмотра истории:", reply_markup=kb)


# ==================== ОБРАБОТЧИКИ СОСТОЯНИЙ (оставляем как были) ====================
@user_router.message(ShiftStates.waiting_start_km)
async def process_start_km(message: Message, state: FSMContext):
    try:
        km = int(message.text.strip())
        await state.update_data(start_km=km)
        await message.answer("⛽ Введите литры в баке при выезде:")
        await state.set_state(ShiftStates.waiting_start_fuel)
    except ValueError:
        await message.answer("❌ Введите число")


@user_router.message(ShiftStates.waiting_start_fuel)
async def process_start_fuel(message: Message, state: FSMContext):
    try:
        start_fuel = float(message.text.replace(',', '.').strip())
        data = await state.get_data()
        user_id = message.from_user.id

        user_router.active_shifts[user_id] = {
            "user_id": user_id,
            "start_km": data['start_km'],
            "start_fuel": start_fuel,
            "refueled_total": 0.0,
            "date": date.today()
        }

        await message.answer(
            f"✅ <b>Смена начата!</b>\n\n"
            f"Начальный км: <b>{data['start_km']}</b>\n"
            f"Топливо при выезде: <b>{start_fuel}</b> л\n\n"
            f"⛽ Когда заправитесь — нажмите кнопку «Заправка»",
            reply_markup=main_menu()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число")


@user_router.message(ShiftStates.waiting_refuel)
async def process_refuel(message: Message, state: FSMContext):
    try:
        liters = float(message.text.replace(',', '.').strip())
        user_id = message.from_user.id
        user_router.active_shifts[user_id]["refueled_total"] += liters

        await message.answer(f"✅ +{liters} л зафиксировано.\nВсего заправлено: {user_router.active_shifts[user_id]['refueled_total']} л")
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число")


@user_router.message(ShiftStates.waiting_end_km)
async def process_end_km(message: Message, state: FSMContext):
    try:
        end_km = int(message.text.strip())
        user_id = message.from_user.id
        shift = user_router.active_shifts.get(user_id)

        if not shift:
            await message.answer("❌ Активная смена не найдена")
            await state.clear()
            return

        distance, consumed, consumption_per_100, remaining, need_to_refuel = calculate_shift(
            shift["start_km"], end_km, shift["start_fuel"], shift["refueled_total"]
        )

        result_text = f"""✅ <b>Смена завершена!</b>

Пройдено: <b>{distance}</b> км
Израсходовано по норме: <b>{consumed}</b> л
Расход по норме: <b>{consumption_per_100}</b> л/100 км

Остаток в баке ≈ <b>{remaining}</b> л
Нужно заправить до полного: <b>{need_to_refuel}</b> л"""

        # Сохранение в базу данных
        async with AsyncSessionLocal() as session:
            # Получаем текущий номер машины водителя на момент завершения смены
            user_result = await session.execute(
                select(User.car_number).where(User.tg_id == user_id)
            )
            current_car_number = user_result.scalar()

            new_shift = Shift(
                user_id=user_id,
                date=shift["date"],
                start_km=shift["start_km"],
                start_fuel=shift["start_fuel"],
                end_km=end_km,
                end_fuel=remaining,
                refueled_liters=shift["refueled_total"],
                calculated_consumption=consumption_per_100,
                distance=distance,
                consumed_liters=consumed,
                car_number=current_car_number,        # ← Сохраняем номер машины на момент смены
            )
            session.add(new_shift)
            await session.commit()

        # Показываем результат ОДИН РАЗ
        await message.answer(result_text, reply_markup=main_menu())

        # Удаляем активную смену
        if user_id in user_router.active_shifts:
            del user_router.active_shifts[user_id]

        await state.clear()

    except ValueError:
        await message.answer("❌ Введите число")
    except Exception as e:
        await message.answer("❌ Ошибка при сохранении смены")
        print("Ошибка:", e)
        await state.clear()

# ==================== ОБРАБОТЧИК ИСТОРИИ ====================
@user_router.callback_query(F.data.startswith("history_"))
async def history_callback(callback: CallbackQuery):
    period = callback.data.split("_")[1]
    user_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
        query = select(Shift).where(Shift.user_id == user_id)

        if period == "today":
            query = query.where(Shift.date == date.today())
            period_text = "Сегодня"
        elif period == "7days":
            since = date.today() - timedelta(days=7)
            query = query.where(Shift.date >= since)
            period_text = "За последние 7 дней"
        elif period == "30days":
            since = date.today() - timedelta(days=30)
            query = query.where(Shift.date >= since)
            period_text = "За последние 30 дней"
        else:
            period_text = "За всё время"

        result = await session.execute(query.order_by(Shift.date.desc()))
        shifts = result.scalars().all()

        if not shifts:
            await callback.message.edit_text(f"📖 В периоде «{period_text}» смен не найдено.")
            await callback.answer()
            return

        total_distance = sum(s.distance or 0 for s in shifts)
        total_consumed = 0.0
        for s in shifts:
            if s.distance and s.calculated_consumption:
                total_consumed += (s.calculated_consumption * s.distance / 100)

        count = len(shifts)
        avg_consumption = round(total_consumed / total_distance * 100, 2) if total_distance > 0 else 17.0

        text = f"""📖 <b>История — {period_text}</b>

Всего смен: <b>{count}</b>
Пройдено: <b>{total_distance}</b> км
Израсходовано по норме: <b>{total_consumed:.2f}</b> л
Средний расход: <b>{avg_consumption}</b> л/100 км

📋 Смены:\n\n"""

        for s in shifts[:12]:
            consumed_liters = round(s.calculated_consumption * s.distance / 100, 2) if s.distance and s.calculated_consumption else 0
            
            text += (
                f"📅 {s.date.strftime('%d.%m.%Y')}   🚗 - <b>{s.car_number or '—'}</b>\n"
                f"{s.start_km} → {s.end_km} км ({s.distance} км)\n"
                f"Израсходовано: <b>{consumed_liters}</b> л\n"
                f"Расход: <b>{s.calculated_consumption}</b> л/100 км\n"
                f"────────────────────\n\n"
            )

        await callback.message.edit_text(text)
        await callback.answer()

# ==================== ЛИЧНАЯ СТАТИСТИКА ВОДИТЕЛЯ ====================
@user_router.message(F.text == "📊 Статистика")
async def driver_statistics(message: Message):
    if await is_banned(message.from_user.id, message):
        return

    user_id = message.from_user.id

    try:
        async with AsyncSessionLocal() as session:
            # Общие данные за всё время
            total_shifts = await session.scalar(
                select(func.count(Shift.id)).where(Shift.user_id == user_id)
            ) or 0

            total_distance = await session.scalar(
                select(func.sum(Shift.distance)).where(Shift.user_id == user_id)
            ) or 0

            # Суммарное израсходованное топливо
            consumed_result = await session.execute(
                select(func.sum(Shift.calculated_consumption * Shift.distance / 100))
                .where(Shift.user_id == user_id)
            )
            total_consumed = consumed_result.scalar() or 0.0

            avg_consumption = round((total_consumed / total_distance * 100), 2) if total_distance > 0 else 17.0

            # За последние 30 дней
            since_30 = date.today() - timedelta(days=30)
            distance_30 = await session.scalar(
                select(func.sum(Shift.distance)).where(Shift.user_id == user_id, Shift.date >= since_30)
            ) or 0

            text = f"""📊 <b>Ваша личная статистика</b>

📅 За всё время:
• Смен: <b>{total_shifts}</b>
• Пробег: <b>{total_distance}</b> км
• Израсходовано по норме: <b>{total_consumed:.2f}</b> л
• Средний расход: <b>{avg_consumption}</b> л/100 км

📅 За последние 30 дней:
• Пробег: <b>{distance_30}</b> км

🔍 <b>Рекомендация:</b>
Если ваш средний расход сильно выше 17 л/100 км — обратите внимание на стиль вождения и техническое состояние машины."""

            await message.answer(text)

    except Exception as e:
        print(f"Ошибка в driver_statistics: {e}")
        await message.answer("❌ Произошла ошибка при загрузке статистики.\nПопробуйте позже.")

@user_router.callback_query(F.data == "history_month")
async def history_current_month(callback: CallbackQuery):
    user_id = callback.from_user.id
    current_month = date.today().replace(day=1)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Shift)
            .where(Shift.user_id == user_id, Shift.date >= current_month)
            .order_by(Shift.date.desc())
        )
        shifts = result.scalars().all()

        period_text = f"Текущий месяц ({current_month.strftime('%m.%Y')})"

        if not shifts:
            await callback.message.edit_text(f"📖 В {period_text} смен не найдено.")
            await callback.answer()
            return

        total_distance = sum(s.distance or 0 for s in shifts)
        total_consumed = 0.0
        for s in shifts:
            if s.distance and s.calculated_consumption:
                total_consumed += round(s.calculated_consumption * s.distance / 100, 2)

        count = len(shifts)
        avg = round((total_consumed / total_distance * 100), 2) if total_distance > 0 else 17.0

        text = f"""📖 <b>История — {period_text}</b>

Всего смен: <b>{count}</b>
Пройдено: <b>{total_distance}</b> км
Израсходовано по норме: <b>{total_consumed:.2f}</b> л
Средний расход: <b>{avg}</b> л/100 км

📋 Смены:\n\n"""

        for s in shifts[:15]:
            consumed_liters = round(s.calculated_consumption * s.distance / 100, 2) if s.distance and s.calculated_consumption else 0
            
            text += (
                f"📅 {s.date.strftime('%d.%m.%Y')}   🚗 - <b>{s.car_number or '—'}</b>\n"
                f"{s.start_km} → {s.end_km} ({s.distance} км)\n"
                f"Израсходовано: <b>{consumed_liters}</b> л\n"
                f"Расход: <b>{s.calculated_consumption}</b> л/100 км\n"
                f"────────────────────\n\n"
            )

        await callback.message.edit_text(text)
        await callback.answer()

# ==================== НАСТРОЙКИ ====================
@user_router.message(F.text == "⚙️ Настройки")
async def settings_menu(message: Message):
    if await is_banned(message.from_user.id, message):
        return

    text = (
        "⚙️ <b>Настройки профиля</b>\n\n"
        "Здесь вы можете изменить данные своего профиля.\n"
        "Сейчас доступно:\n"
        "• Изменить номер машины"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Изменить номер машины", callback_data="change_car_number")]
    ])

    await message.answer(text, reply_markup=kb)


@user_router.callback_query(F.data == "change_car_number")
async def start_change_car_number(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🚗 Введите новый номер машины:\n"
        "Пример: А123АА142 или Н377НН77",
        reply_markup=None
    )
    await state.set_state(RegistrationStates.waiting_car_number)  # можно использовать существующий state
    await callback.answer()


@user_router.message(RegistrationStates.waiting_car_number)
async def process_new_car_number(message: Message, state: FSMContext):
    if await is_banned(message.from_user.id, message):
        await state.clear()
        return

    new_car_number = message.text.strip().upper()

    if len(new_car_number) < 3:
        await message.answer("❌ Номер машины слишком короткий. Попробуйте ещё раз.")
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.tg_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if user:
            user.car_number = new_car_number
            await session.commit()

            await message.answer(
                f"✅ Номер машины успешно обновлён!\n\n"
                f"Новый номер: <b>{new_car_number}</b>",
                reply_markup=main_menu()
            )
        else:
            await message.answer("❌ Профиль не найден.")

    await state.clear()                        
