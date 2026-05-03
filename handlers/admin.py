from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select, func, desc, delete, update   # ← добавь update
from datetime import date, timedelta
import pandas as pd
from datetime import datetime
from aiogram.types import FSInputFile
from aiogram.fsm.context import FSMContext

from database import AsyncSessionLocal
from models.models import User, Shift
from config import ADMIN_IDS

admin_router = Router()


# ==================== СПИСОК ВОДИТЕЛЕЙ ====================
@admin_router.message(F.text == "👷 Водители")
async def show_drivers(message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).order_by(User.full_name))
        users = result.scalars().all()

        if not users:
            await message.answer("Пока нет зарегистрированных водителей.")
            return

        text = "👷 <b>Водители парка:</b>\n\n"
        keyboard = []

        for u in users:
            status = "🚫" if u.banned else "✅" if u.approved else "⏳"
            text += f"{status} {u.full_name} — {u.car_number}\n"
            keyboard.append([InlineKeyboardButton(
                text=f"{status} {u.full_name[:30]}",
                callback_data=f"driver_{u.tg_id}"
            )])

        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


# ==================== КАРТОЧКА ВОДИТЕЛЯ ====================
@admin_router.callback_query(F.data.startswith("driver_"))
async def driver_detail(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[1])

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Пользователь не найден")
            return

        shifts_result = await session.execute(
            select(Shift)
            .where(Shift.user_id == tg_id)
            .order_by(Shift.date.desc())
            .limit(5)
        )
        shifts = shifts_result.scalars().all()

        text = f"""👤 <b>Карточка водителя</b>

Ф.И.О: <b>{user.full_name}</b>
Машина: <b>{user.car_number}</b>
Статус: {'✅ Одобрен' if user.approved else '⏳ Ожидает'} {'🚫 Забанен' if user.banned else ''}

📊 <b>Последние 5 смен:</b>\n"""

        for s in shifts:
            consumed_liters = round(s.calculated_consumption * s.distance / 100, 2) if s.distance else 0
            text += f"• {s.date.strftime('%d.%m.%Y')} | {s.distance} км | {consumed_liters} л | {s.calculated_consumption} л/100км\n"

        # Умная клавиатура
        kb_list = [
            [InlineKeyboardButton(text="📊 Статистика", callback_data=f"stat_{tg_id}")],
            [InlineKeyboardButton(text="📅 Смены за месяц", callback_data=f"month_shifts_{tg_id}")],
            [InlineKeyboardButton(text="📋 Все смены", callback_data=f"all_shifts_{tg_id}")],
        ]

        if user.banned:
            kb_list.append([InlineKeyboardButton(text="✅ Разбанить", callback_data=f"unban_{tg_id}")])
        else:
            kb_list.append([InlineKeyboardButton(text="🚫 Забанить", callback_data=f"ban_{tg_id}")])

        kb_list.append([InlineKeyboardButton(text="🗑 Удалить водителя", callback_data=f"delete_user_{tg_id}")])
        kb_list.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data="back_to_drivers")])

        kb = InlineKeyboardMarkup(inline_keyboard=kb_list)

        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

# ==================== ВСЕ СМЕНЫ ВОДИТЕЛЯ ====================
@admin_router.callback_query(F.data.startswith("all_shifts_"))
async def all_shifts(callback: CallbackQuery, state: FSMContext):
    tg_id = int(callback.data.split("_")[2])

    async with AsyncSessionLocal() as session:
        user_result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = user_result.scalar_one_or_none()

        if not user:
            await callback.answer("Пользователь не найден")
            return

        shifts_result = await session.execute(
            select(Shift).where(Shift.user_id == tg_id).order_by(Shift.date.desc(), Shift.id.desc())
        )
        shifts = shifts_result.scalars().all()

        if not shifts:
            await callback.message.edit_text("У этого водителя пока нет смен.")
            await callback.answer()
            return

        text = f"""📋 <b>Все смены — {user.full_name}</b>\n\n"""
        text += "Чтобы удалить смены — напишите их номера через запятую.\n"
        text += "Пример: 1, 3, 5\n\n"

        kb_buttons = []

        for i, s in enumerate(shifts, 1):
            consumed_liters = round(s.calculated_consumption * s.distance / 100, 2) if s.distance and s.calculated_consumption else 0
            
            text += (
                f"<b>{i}.</b> 📅 {s.date.strftime('%d.%m.%Y')}   🚗 - <b>{s.car_number or '—'}</b>\n"
                f"   {s.start_km} → {s.end_km} ({s.distance} км) | {consumed_liters} л\n"
                f"────────────────────\n\n"
            )

        kb_buttons.append([InlineKeyboardButton(text="🔙 Назад к карточке", callback_data=f"driver_{tg_id}")])

        kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await state.set_state("waiting_delete_shifts")   # специальное состояние
        await state.update_data(tg_id=tg_id, shifts=shifts)  # сохраняем список смен
        await callback.answer()


# ==================== СТАТИСТИКА ПАРКА ====================
@admin_router.message(F.text == "📈 Статистика парка")
async def park_statistics(message: Message):
    async with AsyncSessionLocal() as session:
        total_shifts = await session.scalar(select(func.count(Shift.id))) or 0
        total_distance = await session.scalar(select(func.sum(Shift.distance))) or 0

        total_consumed = round((total_distance / 100) * 17, 2) if total_distance > 0 else 0.0
        avg_park = 17.0

        # ТОП-7 по пробегу
        top = await session.execute(
            select(
                User.full_name,
                User.car_number,
                func.sum(Shift.distance).label("total_dist")
            )
            .join(Shift)
            .group_by(User.id, User.full_name, User.car_number)
            .having(func.sum(Shift.distance) > 0)
            .order_by(desc(func.sum(Shift.distance)))
            .limit(7)
        )
        top_list = top.all()

        text = f"""📈 <b>Общая статистика парка</b>

Всего смен: <b>{total_shifts}</b>
Общий пробег: <b>{total_distance}</b> км
Израсходовано по норме: <b>{total_consumed}</b> л
Средний расход по парку: <b>{avg_park}</b> л/100 км

🔥 <b>Топ-7 водителей по пробегу:</b>\n"""

        for i, (name, car, dist) in enumerate(top_list, 1):
            text += f"{i}. {name} — {car}\n   <b>{dist}</b> км\n"

        await message.answer(text)


# ==================== ЗАЯВКИ НА ДОСТУП ====================
@admin_router.message(F.text == "📨 Заявки на доступ")
async def show_requests(message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.approved == False, User.banned == False)
        )
        pending = result.scalars().all()

        if not pending:
            await message.answer("✅ Нет активных заявок.")
            return

        text = "📨 <b>Заявки на доступ:</b>\n\n"
        for u in pending:
            text += f"👤 {u.full_name}\n🚗 {u.car_number}\n🆔 <code>{u.tg_id}</code>\n\n"

        await message.answer(text)


# ==================== ЭКСПОРТ В EXCEL ====================
@admin_router.message(F.text == "📤 Экспорт в Excel")
async def export_to_excel(message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Shift, User.full_name, User.car_number)
            .join(User, Shift.user_id == User.tg_id)
            .order_by(Shift.date.desc())
        )
        data = result.all()

        if not data:
            await message.answer("Нет данных для экспорта.")
            return

        rows = []
        for shift, full_name, car_number in data:
            consumed_liters = round(shift.calculated_consumption * shift.distance / 100, 2) if shift.distance and shift.calculated_consumption else 0
            rows.append({
                "Дата": shift.date.strftime("%d.%m.%Y"),
                "Водитель": full_name or "Не указано",
                "Машина": car_number or "Не указано",
                "Начальный км": shift.start_km,
                "Конечный км": shift.end_km,
                "Пробег (км)": shift.distance,
                "Израсходовано (л)": consumed_liters,
                "Расход (л/100км)": shift.calculated_consumption,
                "Заправлено (л)": shift.refueled_liters,
            })

        df = pd.DataFrame(rows)

        # Создаём файл
        filename = f"статистика_парка_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx"
        df.to_excel(filename, index=False)

        # Отправляем файл
        try:
            await message.answer_document(
                FSInputFile(filename),
                caption=f"📤 Статистика парка\nДата выгрузки: {datetime.now().strftime('%d.%m.%Y %H:%M')}\nВсего записей: {len(rows)}"
            )
            print(f"✅ Файл {filename} успешно отправлен")
        except Exception as e:
            await message.answer(f"❌ Ошибка при отправке файла: {e}")
            print(f"Ошибка отправки файла: {e}")

# ==================== СТАТИСТИКА ОДНОГО ВОДИТЕЛЯ ====================
@admin_router.callback_query(F.data.startswith("stat_"))
async def driver_stat(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[1])

    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.tg_id == tg_id))
        user = user.scalar_one_or_none()

        if not user:
            await callback.answer("Пользователь не найден")
            return

        # Статистика водителя
        total_distance = await session.scalar(select(func.sum(Shift.distance)).where(Shift.user_id == tg_id)) or 0
        total_shifts = await session.scalar(select(func.count(Shift.id)).where(Shift.user_id == tg_id)) or 0

        consumed_result = await session.execute(
            select(func.sum(Shift.calculated_consumption * Shift.distance / 100.0))
            .where(Shift.user_id == tg_id)
        )
        total_consumed = consumed_result.scalar() or 0.0

        avg = round((total_consumed / total_distance * 100), 2) if total_distance > 0 else 17.0

        text = f"""📊 <b>Статистика водителя</b>

{user.full_name}
Машина: {user.car_number}

Всего смен: <b>{total_shifts}</b>
Общий пробег: <b>{total_distance}</b> км
Израсходовано по норме: <b>{total_consumed:.2f}</b> л
Средний расход: <b>{avg}</b> л/100 км"""

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к карточке", callback_data=f"driver_{tg_id}")]
        ])

        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()


# ==================== СМЕНЫ ЗА ТЕКУЩИЙ МЕСЯЦ ====================
@admin_router.callback_query(F.data.startswith("month_shifts_"))
async def month_shifts(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[2])
    current_month = date.today().replace(day=1)

    async with AsyncSessionLocal() as session:
        # Получаем информацию о пользователе
        user_result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = user_result.scalar_one_or_none()

        if not user:
            await callback.message.edit_text("Пользователь не найден.")
            await callback.answer()
            return

        # Получаем смены
        shifts_result = await session.execute(
            select(Shift)
            .where(Shift.user_id == tg_id, Shift.date >= current_month)
            .order_by(Shift.date.desc())
        )
        shifts = shifts_result.scalars().all()

        if not shifts:
            await callback.message.edit_text(f"У водителя {user.full_name} в текущем месяце смен нет.")
            await callback.answer()
            return

        text = f"""📅 <b>Смены за текущий месяц</b> — {user.full_name}\n\n"""

        for s in shifts:
            consumed_liters = round(s.calculated_consumption * s.distance / 100, 2) if s.distance and s.calculated_consumption else 0
            
            text += (
                f"📅 {s.date.strftime('%d.%m.%Y')}   🚗 - <b>{s.car_number or '—'}</b>\n"
                f"{s.start_km} → {s.end_km} ({s.distance} км)\n"
                f"Израсходовано: <b>{consumed_liters}</b> л\n"
                f"────────────────────\n\n"
            )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к карточке", callback_data=f"driver_{tg_id}")]
        ])

        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

# ==================== НАЗАД К СПИСКУ ВОДИТЕЛЕЙ ====================
@admin_router.callback_query(F.data == "back_to_drivers")
async def back_to_drivers(callback: CallbackQuery):
    try:
        # Удаляем текущее сообщение с карточкой водителя
        await callback.message.delete()
    except:
        pass  # если не удалось удалить — не критично

    # Отправляем новое сообщение со списком водителей
    await show_drivers(callback.message)
    
    await callback.answer()              

# ==================== ОБРАБОТКА УДАЛЕНИЯ СМЕН ====================
@admin_router.message(F.text.regexp(r"^\d+(,\s*\d+)*$"))
async def process_delete_shifts(message: Message, state: FSMContext):
    data = await state.get_data()
    tg_id = data.get("tg_id")
    shifts_list = data.get("shifts")

    if not tg_id or not shifts_list:
        await message.answer("Сессия устарела. Откройте «Все смены» заново.")
        await state.clear()
        return

    try:
        indices = [int(x.strip()) for x in message.text.split(",")]
    except ValueError:
        await message.answer("❌ Неверный формат. Введите номера смен через запятую.\nПример: 1, 3")
        return

    deleted_count = 0
    async with AsyncSessionLocal() as session:
        for idx in indices:
            if 1 <= idx <= len(shifts_list):
                shift_to_delete = shifts_list[idx - 1]
                await session.delete(shift_to_delete)
                deleted_count += 1

        await session.commit()

    await message.answer(f"✅ Успешно удалено {deleted_count} смен.")

    await state.clear()

    # Обновляем список смен у админа
    await reopen_all_shifts(message, tg_id)

    # Уведомляем водителя, что смена была удалена
    try:
        await message.bot.send_message(
            tg_id,
            "🗑 Механик удалил одну или несколько ваших смен."
        )
    except:
        pass  # если водитель заблокировал бота — не страшно


# ==================== ПОВТОРНОЕ ОТКРЫТИЕ СПИСКА СМЕН ====================
async def reopen_all_shifts(message: Message, tg_id: int):
    async with AsyncSessionLocal() as session:
        user_result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = user_result.scalar_one_or_none()

        if not user:
            await message.answer("Пользователь не найден.")
            return

        shifts_result = await session.execute(
            select(Shift)
            .where(Shift.user_id == tg_id)
            .order_by(Shift.date.desc(), Shift.id.desc())
        )
        shifts = shifts_result.scalars().all()

        if not shifts:
            await message.answer("У этого водителя больше нет смен.")
            return

        text = f"""📋 <b>Все смены — {user.full_name}</b>\n\n"""
        text += "Чтобы удалить смены — напишите их номера через запятую.\nПример: 1, 3\n\n"

        for i, s in enumerate(shifts, 1):
            consumed_liters = round(s.calculated_consumption * s.distance / 100, 2) if s.distance and s.calculated_consumption else 0
            text += (
                f"<b>{i}.</b> 📅 {s.date.strftime('%d.%m.%Y')}   🚗 <b>{s.car_number or '—'}</b>\n"
                f"   {s.start_km} → {s.end_km} ({s.distance} км) | {consumed_liters} л\n"
                f"────────────────────\n\n"
            )

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад к карточке", callback_data=f"driver_{tg_id}")
        ]])

        await message.answer(text, reply_markup=kb, parse_mode="HTML")

# Вспомогательная функция — переоткрывает список всех смен после удаления
async def all_shifts_after_delete(message: Message, tg_id: int):
    # Создаём фейковый callback
    fake_callback = CallbackQuery(
        id="fake",
        from_user=message.from_user,
        message=message,
        data=f"all_shifts_{tg_id}",
        chat_instance="fake",
        bot=message.bot
    )
    
    # Вызываем all_shifts с нужными параметрами
    await all_shifts(fake_callback, FSMContext(None, None, None))  # передаём пустой state

# ==================== МЕНЮ ДЕЙСТВИЙ С ВОДИТЕЛЕМ ====================
@admin_router.callback_query(F.data.startswith("actions_"))
async def user_actions_menu(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[1])

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Пользователь не найден")
            return

        text = f"""🔧 <b>Действия с водителем</b>

👤 {user.full_name}
🚗 {user.car_number}

Выберите действие:"""

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚫 Забанить", callback_data=f"ban_{tg_id}")],
            [InlineKeyboardButton(text="✅ Разбанить", callback_data=f"unban_{tg_id}")],
            [InlineKeyboardButton(text="🗑 Удалить водителя", callback_data=f"delete_user_{tg_id}")],
            [InlineKeyboardButton(text="🔙 Назад к карточке", callback_data=f"driver_{tg_id}")]
        ])

        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

# ==================== РАЗБАНИТЬ ВОДИТЕЛЯ ====================
@admin_router.callback_query(F.data.startswith("unban_"))
async def unban_user(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[1])

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User)
            .where(User.tg_id == tg_id)
            .values(banned=False, approved=True)
        )
        await session.commit()

    # Только обновляем текст карточки
    await callback.message.edit_text("✅ Водитель разбанен.")
    await callback.answer("Разбанен", show_alert=True)

    # Уведомляем самого водителя
    try:
        await callback.bot.send_message(
            tg_id, 
            "🎉 Вы были разблокированы!\nТеперь можете пользоваться ботом."
        )
    except:
        pass
