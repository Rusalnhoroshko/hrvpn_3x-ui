# payment.py
import aiosqlite
import os
import decimal
import hashlib
import hmac
from aiohttp import web
from dotenv import load_dotenv
from loguru import logger
from urllib.parse import urlencode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from db import DB_FILE
from telegram_bot import bot, generate_nickname
from vpn_manager import x3

load_dotenv()

logger.add("logs_payments.log", mode='w', level="DEBUG")

YOOMONEY_SECRET = os.getenv('YOOMONEY_SECRET')
YOOMONEY_WALLET = os.getenv('YOOMONEY_WALLET')
NOTIFICATION_URL = os.getenv('NOTIFICATION_URL')


def generate_payment_link(amount, label, description):
    params = {
        'receiver': YOOMONEY_WALLET,  # Ваш идентификатор кошелька ЮMoney
        'quickpay-form': 'shop',
        'targets': description,
        'paymentType': 'AC',  # Способ оплаты: банковская карта
        'sum': amount,
        'label': label,  # Уникальный идентификатор платежа
        # 'successURL': SUCCESS_URL,  # URL для перенаправления после оплаты
        'formcomment': description,
        'short-dest': description,
        'comment': description,
        'need-fio': 'false',
        'need-email': 'false',
        'need-phone': 'false',
        'need-address': 'false',
        'notificationURL': NOTIFICATION_URL  # URL для уведомлений от ЮMoney
    }
    payment_link = f"https://yoomoney.ru/quickpay/confirm.xml?{urlencode(params)}"
    return payment_link


async def yoomoney_notification(request):
    data = await request.post()
    logger.info(f"Получено уведомление от ЮMoney: {data}")

    # Получаем параметры из уведомления
    notification_type = data.get('notification_type', '')
    operation_id = data.get('operation_id', '')
    amount = data.get('amount', '')
    currency = data.get('currency', '')
    datetime_str = data.get('datetime', '')
    sender = data.get('sender', '')
    codepro = data.get('codepro', '')
    label = data.get('label', '')
    sha1_hash = data.get('sha1_hash', '')
    withdraw_amount_str = data.get('withdraw_amount', '').replace(',', '.').strip()

    # Строка для проверки подписи
    params_list = [
        notification_type,
        operation_id,
        amount,
        currency,
        datetime_str,
        sender,
        codepro,
        YOOMONEY_SECRET,
        label
    ]
    params = '&'.join(params_list)

    # Проверяем подпись
    hash_digest = hashlib.sha1(params.encode('utf-8')).hexdigest()
    if not hmac.compare_digest(hash_digest, sha1_hash):
        logger.error("Неверная подпись в уведомлении от ЮMoney")
        return web.Response(text='Invalid signature')

    # Проверяем, не была ли уже обработана эта транзакция
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('''
            SELECT COUNT(*) FROM purchase_history WHERE operation_id = ?
        ''', (operation_id,))
        row = await cursor.fetchone()
        if row[0] > 0:
            logger.info(f"Уведомление с operation_id {operation_id} уже обработано.")
            return web.Response(text='OK')  # Возвращаем OK, чтобы ЮMoney не отправлял повторные уведомления

    # Подпись верна, обрабатываем платеж
    if not label:
        logger.error("Отсутствует label в уведомлении")
        return web.Response(text='Invalid label')

    # Преобразуем withdraw_amount_str в Decimal
    try:
        paid_amount = decimal.Decimal(withdraw_amount_str)
        paid_amount = paid_amount.quantize(decimal.Decimal('1.00'))  # Округляем до 2 знаков
    except decimal.InvalidOperation:
        logger.error(f"Некорректная сумма withdraw_amount: {withdraw_amount_str}")
        return web.Response(text='Invalid withdraw_amount')

    logger.info(f"paid_amount: {paid_amount}")

    # Обновляем amount_mapping с использованием Decimal
    amount_mapping = {
        decimal.Decimal('5.00'): 5,
        decimal.Decimal('200.00'): 30,
        decimal.Decimal('500.00'): 90,
        decimal.Decimal('1000.00'): 180
    }

    matching_amount = None
    for amt in amount_mapping:
        difference = abs(paid_amount - amt)
        logger.info(f"Сравнение paid_amount: {paid_amount} и amt: {amt}, разница: {difference}")
        if difference <= decimal.Decimal('0.01'):
            matching_amount = amt
            break

    logger.info(f"matching_amount: {matching_amount}")


    if not matching_amount:
        logger.error(f"Не удалось найти соответствие для paid_amount: {paid_amount}")
        if label.startswith('renew_') or label.startswith('new_subscribe_'):
            parts = label.split('_')
            if len(parts) >= 2:
                user_id_str = parts[1]
                if user_id_str.isdigit():
                    user_id = int(user_id_str)
                    await bot.send_message(user_id, "Получена неверная сумма оплаты.")
        return web.Response(text='Invalid amount')

    # Округляем сумму до ближайшего значения в amount_mapping
    expected_period = amount_mapping[matching_amount]

    if label.startswith('renew_key_'):
        parts = label.split('_')
        if len(parts) != 4:
            logger.error(f"Некорректный формат label для продления: {label}")
            return web.Response(text='Invalid label format for renew')

        user_id_str = parts[2]
        if not user_id_str.isdigit():
            logger.error(f"Некорректный user_id в label: {label}")
            return web.Response(text='Invalid user ID in label')

        user_id = int(user_id_str)
        booster_key = x3.renew_subscribe(day=expected_period, tg_id=user_id)
        if booster_key:
            await bot.send_message(user_id, f"Оплата получена! Ваша подписка продлена на {expected_period} дней.")
            return web.Response(text='OK')
        else:
            await bot.send_message(user_id, "Ошибка при обновлении ключа.")
            return web.Response(text='Error creating VPN key')
    else:
        parts = label.split('_')
        if len(parts) != 2:
            logger.error(f"Некорректный формат label для новой подписки: {label}")
            return web.Response(text='Invalid label format for new subscription')

        user_id_str = parts[0]
        if not user_id_str.isdigit():
            logger.error(f"Некорректный user_id в label: {label}")
            return web.Response(text='Invalid user ID in label')

        user_id = int(user_id_str)
        random_nickname = generate_nickname()
        user_name = f"{user_id}-{random_nickname}"

        # Создаем клиента и получаем ссылку
        booster_key = x3.add_client(day=expected_period, tg_id=user_id, user_id=user_name)
        if booster_key:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Инструкция", callback_data="instruction")]
                ]
            )
            await bot.send_message(user_id, f"Оплата получена!")
            await bot.send_message(user_id,
                                   f"Ваш ключ для HRVPN:<pre>{booster_key}</pre>"
                                   f"Просто коснитесь 👆 и ключ сам скопируеться в буффер обмена",
                                  parse_mode="HTML", reply_markup=keyboard)
            return web.Response(text='OK')
        else:
            await bot.send_message(user_id, "Ошибка при создании ключа.")
            return web.Response(text='Error creating VPN key')
