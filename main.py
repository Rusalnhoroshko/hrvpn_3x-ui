# main.py
import asyncio
from aiohttp import web
from db import init_db
from telegram_bot import bot, dp
from payments import yoomoney_notification
from tasks import check_subscribes_expirity


app = web.Application()
app.router.add_post('/yoomoney_notification', yoomoney_notification)


async def main():
    await init_db()
    asyncio.create_task(check_subscribes_expirity())
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '127.0.0.1', 8080)
    await site.start()

    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
