from aiogram.fsm.state import StatesGroup, State

class ShiftStates(StatesGroup):
    waiting_start_km = State()
    waiting_start_fuel = State()
    waiting_refuel = State()
    waiting_end_km = State()

class RegistrationStates(StatesGroup):
    waiting_full_name = State()
    waiting_car_number = State()

