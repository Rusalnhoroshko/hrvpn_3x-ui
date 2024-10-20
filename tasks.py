# tasks.py
import json
import os
import secrets
import string
import aiosqlite
import asyncio
from urllib.parse import urlencode
from loguru import logger
from dotenv import load_dotenv
from datetime import datetime, timezone
from vpn_manager import x3

logger.add("logs_tasks.log", mode='w', level="INFO")

load_dotenv()

YOOMONEY_SECRET = os.getenv('YOOMONEY_SECRET')
YOOMONEY_WALLET = os.getenv('YOOMONEY_WALLET')
NOTIFICATION_URL = os.getenv('NOTIFICATION_URL')


def generate_nickname(length=8):
    characters = string.ascii_lowercase + string.digits
    nickname = ''.join(secrets.choice(characters) for _ in range(length))
    return nickname


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


async def check_expirytime(tg_id):
    time_left = x3.find_expirytime_by_tg_id(tg_id=tg_id)
    expirytime = datetime.fromtimestamp(time_left / 1000, tz=timezone.utc)
    time_left = expirytime - datetime.now(timezone.utc)
    total_seconds_left = time_left.total_seconds()
    return int(total_seconds_left)


async def add_new_user_in_db(tg_id):
    # проверяет, пользовался ли клиент ботом, если нет то добавляет в db
    pass


async def add_test_usage_status_in_db(tg_id):
    # добавляет в db клиента при использовании тестового периода
    pass


async def check_test_usage_status_in_db(tg_id):
    # проверяет, пользовался ли клиент тестовым периодом, если да то возвращает True
    pass


async def check_subscribes_expirity():
    # с определенным интервалом проверяет срок действия подписок x3.get_inbounds() и присылает уведомления о сроках
    # уведомления об окончания подписки(5 дней,1 день, срок истек)
    from telegram_bot import bot
    while True:
        inbounds = x3.get_inbounds()
        for item in inbounds:
            try:
                settings = json.loads((item["settings"]))
                for client in settings['clients']:
                    tg_id = client.get("tgId")

                    total_seconds_left = await check_expirytime(tg_id)
                    days_left = int(total_seconds_left // 86400)
                    print(days_left)


                    if 86400 < total_seconds_left <= 87000:
                        await bot.send_message(str(tg_id), f"До окончания подписки осталось {days_left} день")
                        logger.info(f"Срок действия подписки {days_left} дней для {tg_id}")
                    elif total_seconds_left <= 0:
                        await bot.send_message(str(tg_id), "Срок действия подписки истек\n"
                                                           "Ключ удалён")
                        logger.info(f"Срок действия подписки истек для {tg_id}, Ключ удалён")
                        x3.delete_client(tg_id)

            except Exception as e:
                logger.error(f"Fail to check_subscribes_expirity {e}")
        await asyncio.sleep(600)