# flask_app.py
from flask import Flask, Blueprint, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
import asyncio
import logging
import os
import nest_asyncio

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin.login'
nest_asyncio.apply()

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
USER_NAME = os.getenv('USER_NAME')
USER_PASSWORD = os.getenv('USER_PASSWORD')

from telegram_bot import bot
from vpn_manager import create_vpn_key_with_name
from db import (
    get_all_users,
    get_all_subscriptions,
    save_subscription,
    delete_subscription_async,
    update_subscription_async,
    get_subscription_expiry_async
)

class User(UserMixin):
    def __init__(self, id):
        self.id = id


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == USER_NAME and password == USER_PASSWORD:
            user = User(id=1)
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for(
                'admin.subscriptions_page'))  # Редирект либо на нужную страницу, либо на subscriptions
        else:
            flash('Invalid credentials')
            return redirect(url_for('admin.login'))
    return render_template('login.html')


@admin_bp.route('/broadcast', methods=['GET', 'POST'])
@login_required
def broadcast_message():
    if request.method == 'POST':
        message = request.form['message']

        # Получаем всех пользователей из таблицы users
        users = asyncio.run(get_all_users())

        # Рассылаем сообщение каждому пользователю
        for user in users:
            run_async_task(send_message_to_user(user['user_id'], message))

        flash('Сообщение отправлено всем пользователям.')
        return redirect(url_for('admin.broadcast_message'))

    return render_template('broadcast.html')


# Форма для отправки сообщения
@admin_bp.route('/send_message', methods=['GET', 'POST'])
@login_required
def send_message():
    if request.method == 'POST':
        chat_id = request.form['chat_id']
        message_text = request.form['message']

        asyncio.run(send_message_to_user(chat_id, message_text))
        flash(f"Сообщение отправлено пользователю {chat_id}")
        return redirect(url_for('admin.send_message'))

    return render_template('send_message.html')


# Выход
@admin_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('admin.login'))


async def send_message_to_user(chat_id, text):
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        logging.info(f"Сообщение отправлено пользователю {chat_id}: {text}")
    except Exception as e:
        logging.error(f"Ошибка при отправке сообщения пользователю {chat_id}: {e}")


def run_async_task(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Event loop is closed")

        if loop.is_running():
            loop.create_task(coro)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        new_loop.run_until_complete(coro)
        new_loop.close()


@admin_bp.route('/subscriptions')
@login_required
def subscriptions_page():
    subscriptions = asyncio.run(get_all_subscriptions())
    return render_template('index.html', subscriptions=subscriptions)

@admin_bp.route('/delete/<int:sub_id>', methods=['POST'])
@login_required
def delete_subscription_route(sub_id):
    asyncio.run(delete_subscription_async(sub_id))
    flash(f'Subscription {sub_id} deleted')
    return redirect(url_for('admin.subscriptions_page'))

@admin_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_key():
    if request.method == 'POST':
        user_id = request.form['user_id']
        duration_days = int(request.form['duration'])
        key_data = asyncio.run(create_vpn_key_with_name(user_id))
        if key_data:
            asyncio.run(save_subscription(user_id, key_data, duration_days))
            flash(f"Key for user {user_id} created")
        else:
            flash("Error creating key")
        return redirect(url_for('admin.subscriptions_page'))
    return render_template('new_key.html')

@admin_bp.route('/edit/<int:sub_id>', methods=['GET', 'POST'])
@login_required
def edit_subscription(sub_id):
    if request.method == 'POST':
        new_expires_at = request.form['expires_at']
        asyncio.run(update_subscription_async(sub_id, new_expires_at))
        flash(f'Subscription {sub_id} updated')
        return redirect(url_for('admin.subscriptions_page'))
    else:
        expires_at = asyncio.run(get_subscription_expiry_async(sub_id))
        return render_template('edit.html', sub_id=sub_id, expires_at=expires_at)

app.register_blueprint(admin_bp)

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

if __name__ == '__main__':
    app.run(debug=True)
