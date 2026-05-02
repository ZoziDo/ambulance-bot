def calculate_shift(start_km: int, end_km: int, start_fuel: float, total_refueled: float):
    """
    Реальный расчёт расхода на основе пройденного расстояния и заправок
    """
    distance = end_km - start_km
    if distance <= 0:
        return 0, 0.0, 17.0, start_fuel, round(80 - start_fuel, 2)

    # Израсходовано по норме (для справки)
    consumed_by_norm = round((distance / 100) * 17, 2)

    # Фактический расход мы считаем как норму, но сохраняем для будущего
    # (пока оставляем 17, но в статистике будем считать по distance)
    consumption_per_100 = 17.0

    remaining = round(start_fuel + total_refueled - consumed_by_norm, 2)
    if remaining < 0:
        remaining = 0.0

    need_to_refuel = round(80.0 - remaining, 2)

    return distance, consumed_by_norm, consumption_per_100, remaining, need_to_refuel