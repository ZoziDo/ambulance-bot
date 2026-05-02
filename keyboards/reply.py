from aiogram.utils.keyboard import ReplyKeyboardBuilder


def main_menu():
    """Главное меню водителя с цветными кнопками"""
    builder = ReplyKeyboardBuilder()

    # Первая строка
    builder.button(text="🚑 Начать смену", button_color="positive")   # Зелёная
    builder.button(text="🏁 Завершить смену", button_color="negative") # Красная

    builder.row()

    # Вторая строка
    builder.button(text="⛽ Заправка", button_color="primary")        # Синяя
    builder.button(text="📖 Моя история", button_color="primary")

    builder.row()

    # Третья строка
    builder.button(text="📊 Статистика", button_color="primary")
    builder.button(text="⚙️ Настройки", button_color="secondary")    # Серая

    builder.adjust(2, 2, 2)   # 2 | 2 | 2 кнопки

    return builder.as_markup(
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )


def admin_menu():
    """Меню администратора"""
    builder = ReplyKeyboardBuilder()

    builder.button(text="👷 Водители")
    builder.button(text="📈 Статистика парка")

    builder.row()

    builder.button(text="📨 Заявки на доступ")
    builder.button(text="📤 Экспорт в Excel")

    builder.adjust(2, 2)

    return builder.as_markup(
        resize_keyboard=True,
        input_field_placeholder="Админ-панель"
    )