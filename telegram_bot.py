# telegram_bot.py
import aiosqlite
import os
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger
from aiogram import types, F
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from vpn_manager import x3
from db import add_user, DB_FILE
from tasks import (check_expirytime,
                   generate_nickname,
                   generate_payment_link)


load_dotenv()

logger.add("logs_bot.log", mode='w', level="DEBUG")

API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    await add_user(user_id)  # Добавляем пользователя в базу данных, если он новый
    # Проверяем, использовал ли пользователь тестовую подписку
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('SELECT COUNT(*) FROM test_usage WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        has_used_test = row[0] > 0

    keyboard_buttons = [
        [InlineKeyboardButton(text="Мои ключи", callback_data="my_keys")],
        [InlineKeyboardButton(text="Купить ключ", callback_data="new_key")],
        [InlineKeyboardButton(text="Инструкция", callback_data="instruction")],
    ]

    # Вставляем кнопку "Тест на день" только если тест не был использован
    if not has_used_test:
        keyboard_buttons.insert(1, [InlineKeyboardButton(text="Тест HRVPN на 1 день", callback_data="test_period")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer("Выберите действие:", reply_markup=keyboard)


# Обработка нажатий кнопок
@dp.callback_query(F.data == "my_keys")
async def handle_my_keys(callback: types.CallbackQuery):
    await callback.answer("Вы выбрали 'Мои ключи'.")
    tg_id = callback.from_user.id
    booster_key = x3.find_client_by_tg_id(tg_id=tg_id)
    if booster_key:
        await callback.message.answer(f"Ваш ключ для HRVPN:<pre>{booster_key}</pre>"
                                      f"Просто коснитесь 👆 и ключ сам скопируеться в буффер обмена",
                                  parse_mode="HTML")
        total_seconds_left = await check_expirytime(tg_id)
        if total_seconds_left > 86400:
            days_left = (total_seconds_left // 86400)
            await bot.send_message(tg_id, f"До окончания подписки осталось {days_left} дней")
        elif 3600 < total_seconds_left <= 86400:
            hours_left = (total_seconds_left // 3600)
            await bot.send_message(tg_id, f"До окончания подписки осталось менее {hours_left} часов")
        elif 0 < total_seconds_left <= 3600:
            minutes_left = (total_seconds_left // 60)
            await bot.send_message(tg_id, f"До окончания подписки осталось менее {minutes_left} минут")
        else:
            await bot.send_message(tg_id, "Срок действия подписки истек")

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Продлить подписку", callback_data="renew_key")]]
        )
        await callback.message.answer("Чтобы продлить подписку нажмите кнопку",
                                        reply_markup=keyboard)
    else:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Купить ключ", callback_data="new_key")]]
        )
        await callback.message.answer("У Вас нет ключей. Можно приобрести нажав кнопку",
                                      reply_markup=keyboard)


@dp.callback_query(F.data == "new_key")
async def handle_new_key(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    check_key = x3.find_client_by_tg_id(tg_id=tg_id)
    if check_key:
        await callback.message.answer(f"У Вас уже есть ключ:<pre>{check_key}</pre>", parse_mode='HTML')
        await check_expirytime(tg_id)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Продлить подписку", callback_data="renew_key")]])
        await callback.message.answer("Чтобы продлить подписку нажмите кнопку",
                                      reply_markup=keyboard)
    else:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="30 дней - 200 рублей", callback_data="new_key_30")],
                [InlineKeyboardButton(
                    text="90 дней - 500 рублей", callback_data="new_key_90")],
                [InlineKeyboardButton(
                    text="180 дней - 1000 рублей", callback_data="new_key_180")],
            ]
        )
        await callback.message.answer("Выберите период подписки для нового ключа:", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("new_key_"))
async def handle_new_subscription(callback: types.CallbackQuery):
    period = int(callback.data.split("_")[2])
    amount_mapping = {30: 5, 90: 500, 180: 1000}
    amount = amount_mapping.get(period)

    if not amount:
        await callback.message.answer("Некорректный выбор периода подписки.")
        return

    user_id = callback.from_user.id
    payment_label = f"{user_id}_{int(datetime.now().timestamp())}"
    payment_link = generate_payment_link(amount, payment_label, f"Подписка на {period} дней")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Оплатить {amount} рублей", url=payment_link)]
    ])
    await callback.message.answer(
        f"Для оплаты подписки на {period} дней нажмите кнопку ниже:",reply_markup=keyboard)


@dp.callback_query(F.data == "renew_key")
async def handle_renew_key(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    check_key = x3.find_client_by_tg_id(tg_id=tg_id)
    if check_key:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="30 дней - 200 рублей", callback_data="renew_key_30")],
                [InlineKeyboardButton(
                    text="90 дней - 500 рублей", callback_data="renew_key_90")],
                [InlineKeyboardButton(
                    text="180 дней - 1000 рублей", callback_data="renew_key_180")],
            ]
        )
        await callback.message.answer("Выберите период продления:", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("renew_key_"))
async def handle_renew_subscription(callback: types.CallbackQuery):
    period = int(callback.data.split("_")[2])
    amount_mapping = {30: 5, 90: 500, 180: 1000}
    amount = amount_mapping.get(period)

    if not amount:
        await callback.message.answer("Некорректный выбор периода подписки.")
        return

    user_id = callback.from_user.id
    payment_label = f"renew_key_{user_id}_{int(datetime.now().timestamp())}"
    payment_link = generate_payment_link(amount, payment_label, f"Продление подписки на {period} дней")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Оплатить {amount} рублей", url=payment_link)]
    ])
    await callback.message.answer(
        f"Для продления подписки на {period} дней нажмите кнопку ниже:",reply_markup=keyboard)


@dp.callback_query(F.data == "instruction")
async def handle_instruction(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    x3.get_inbounds()





@dp.callback_query(F.data == "test_period")
async def handle_test_period(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    random_nickname = generate_nickname()
    user_id = f"{tg_id}-{random_nickname}"

    check_key = x3.find_client_by_tg_id(tg_id=tg_id)
    if check_key:
        await callback.message.answer(f"У Вас уже есть ключ:<pre>{check_key}</pre>", parse_mode='HTML')
        await check_expirytime(tg_id)

    elif not check_key:
        booster_key = x3.add_client(day=1, tg_id=tg_id, user_id=user_id)
        if booster_key:
            await callback.message.answer(f"Ваш ключ для HRVPN:<pre>{booster_key}</pre>"
                                          f"Просто коснитесь 👆 и ключ сам скопируеться в буффер обмена",
                                      parse_mode="HTML")
    else:
        await callback.answer("Ошибка при создании клиента или получении ссылки. Попробуйте позже.")


@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer("Список доступных команд:\n/start - Начать\n/help - Помощь\n")

