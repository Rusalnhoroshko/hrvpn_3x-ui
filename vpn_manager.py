# vpn_manager.py
import os
import json
import uuid
import requests
from datetime import datetime, timezone
from loguru import logger
from dotenv import load_dotenv


load_dotenv()

BASE_PATH = os.getenv("BASE_PATH")
LOGIN = os.getenv("LOGIN")
PASSWORD = os.getenv("PASSWORD")
HOST = os.getenv("HOST")

logger.add("logs_manager.log", mode='w', level="DEBUG")


class X3:
    def __init__(self, login, password, host):
        self.login = login
        self.password = password
        self.host = host
        self.cookies = {}
        self.ses = requests.Session()
        self.login_panel()
    
    def get_inbounds(self):
        headers = {"Accept": "application/json"}
        response = self.ses.get(f"{self.host}{BASE_PATH}/panel/api/inbounds/list",
                                headers=headers, cookies=self.cookies, verify=True)

        if response.status_code == 200:
            try:
                inbounds = response.json().get('obj', [])
                return inbounds
            except json.JSONDecodeError:
                logger.error(f"Ошибка декодирования JSON: {response.text}")
                return []
        else:
            logger.error(f"Ошибка получения инбаундов. Статус: {response.status_code}, Ответ: {response.text}")
            return []

    # Метод для авторизации
    def login_panel(self):
        data = {
            "username": self.login,
            "password": self.password
        }
        response = self.ses.post(f"{self.host}{BASE_PATH}/login", data=data, verify=True)
        if response.status_code == 200 and response.json().get("success"):
            self.cookies = response.cookies
            logger.info("Успешный вход в систему!")
        else:
            raise ConnectionError("Ошибка входа. Проверьте логин и пароль.")

    # Метод добавления клиента
    def add_client(self, day, tg_id, user_id):
        epoch = datetime.fromtimestamp(0, timezone.utc)
        x_time = int((datetime.now(timezone.utc) - epoch).total_seconds() * 1000.0)
        x_time += 86400000 * day

        inbounds = self.get_inbounds()
        if not inbounds:
            logger.error("Нет доступных инбаундов для добавления клиента.")
            return None

        inbound_id = inbounds[0]["id"]

        headers = {"Accept": "application/json"}
        data1 = {
            "id": inbound_id,
            "settings": json.dumps({
                "clients": [
                    {
                        "id": str(uuid.uuid1()),
                        "alterId": 90,
                        "email": user_id,
                        "limitIp": 3,
                        "totalGB": 0,
                        "expiryTime": x_time,
                        "flow": 'xtls-rprx-vision',
                        "enable": True,
                        "tgId": tg_id,
                        "subId": ""
                    }
                ]
            })
        }

        response = self.ses.post(
            f"{self.host}{BASE_PATH}/panel/api/inbounds/addClient",
            headers=headers,
            json=data1,
            cookies=self.cookies,
            verify=True
        )

        logger.debug(f"Ответ сервера при добавлении клиента: {response.json()}")

        if response.status_code == 200 and response.json().get("success"):
            client_link = self.find_client_by_tg_id(tg_id)
            if client_link:
                logger.info(f"Ссылка для клиента с tg_id {tg_id} отправлена")
                return client_link
            else:
                logger.error(f"Клиент с tg_id {tg_id} не найден после добавления.")
                return None
        else:
            logger.error(f"Ошибка добавления клиента: {response.json()}")
            return None

    # Метод обновления подписки
    def renew_subscribe(self, day, tg_id):
        inbounds = self.get_inbounds()

        for item in inbounds:
            try:
                settings = json.loads(item["settings"])

                for client in settings["clients"]:
                    if client.get("tgId") == tg_id:
                        # Получаем текущее время истечения срока
                        current_expiry_time = client["expiryTime"]
                        client_id = client["id"]

                        # Вычисляем новое время истечения срока, добавляя дополнительные дни
                        new_expiry_time = current_expiry_time + day * 86400000

                        # Обновляем время истечения срока
                        client["expiryTime"] = new_expiry_time

                        # Подготавливаем данные для отправки на сервер
                        headers = {"Accept": "application/json"}
                        data = {
                            "id": item["id"],
                            "client_id": client_id,
                            "settings": json.dumps({
                                "clients": [
                                    {
                                        "id": client_id,
                                        "tgId": tg_id,
                                        "expiryTime": new_expiry_time,
                                        "email": client["email"],
                                        "enable": client.get("enable", True),
                                        "totalGB": client.get("totalGB", 0),
                                        "reset": client.get("reset", 0),
                                        "limitIp": client.get("limitIp", 3),
                                        "flow": client.get("flow", "")
                                    }
                                ]
                            })
                        }

                        response = self.ses.post(
                            f"{self.host}{BASE_PATH}/panel/api/inbounds/updateClient/{client_id}",
                            headers=headers,
                            json=data,
                            cookies=self.cookies,
                            verify=True
                        )

                        if response.status_code == 200 and response.json().get("success"):
                            logger.info(f"Время истечения срока действия клиента с tg_id {tg_id} успешно обновлено.")
                            return True
                        else:
                            logger.error(client_id)
                            logger.error(f"Ошибка обновления клиента с tg_id {tg_id}: {response.json()}")
                            return False
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка декодирования JSON для item: {item}. Ошибка: {e}")
            except Exception as e:
                logger.error(f"Ошибка при обновлении времени истечения для клиента с tg_id {tg_id}: {e}")

        logger.debug(f"Клиент с tg_id {tg_id} не найден для обновления.")
        return False

    # Метод для поиска клиента по tg_id
    def find_client_by_tg_id(self, tg_id):
        inbounds = self.get_inbounds()

        for item in inbounds:
            try:
                settings = json.loads(item["settings"])

                # Ищем клиента по tg_id
                for client in settings["clients"]:
                    if client.get("tgId") == tg_id:
                        # Формируем ссылку для клиента
                        client_id = client["id"]
                        email = client["email"]
                        host = self.host.replace("https://", "")
                        port = item["port"]
                        flow = client["flow"]

                        # Safeguard: Ensure streamSettings is a dict
                        stream_settings = json.loads(item["streamSettings"])\
                            if isinstance(item["streamSettings"], str)\
                            else item["streamSettings"]
                        security = stream_settings.get("security", "")

                        # Ensure realitySettings is properly parsed
                        reality_settings = json.loads(stream_settings["realitySettings"])\
                            if isinstance(stream_settings["realitySettings"], str)\
                            else stream_settings["realitySettings"]
                        public_key = reality_settings.get("settings", {}).get("publicKey")
                        server_name = reality_settings.get("serverNames", [""])[0]
                        short_id = reality_settings.get("shortIds", [""])[0]


                        # Correctly format the client link
                        client_link = (f"vless://{client_id}@{host}:{port}?type=tcp&security={security}&pbk={public_key}"
                                       f"&fp=chrome&sni={server_name}&sid={short_id}&flow={flow}#hrvpn-{email}")

                        # Log the correct VLESS link
                        logger.info(f"Найдена ссылка для клиента: {tg_id}")
                        return client_link  # Возвращаем ссылку клиента

            except json.JSONDecodeError as e:
                logger.error(f"Ошибка декодирования JSON для item: {item}. Ошибка: {e}")
            except Exception as e:
                logger.error(f"Ошибка при обработке клиента с tg_id {tg_id}: {e}")

        logger.debug(f"Клиент с tg_id {tg_id} не найден.")
        return None

    # Метод удаления клиента
    def delete_client(self, tg_id):
        inbounds = self.get_inbounds()
        inbound_id = inbounds[0]['id']
        for item in inbounds:
            try:
                settings = json.loads(item["settings"])
                for client in settings["clients"]:
                    if client.get("tgId") == tg_id:
                        client_id = client["id"]
                        response = self.ses.post(
                            f"{self.host}{BASE_PATH}/panel/api/inbounds/{inbound_id}/delClient/{client_id}",
                            headers={"Accept": "application/json"},
                            cookies=self.cookies,
                            verify=True
                        )
                        if response.status_code == 200 and response.json().get("success"):
                            logger.info(f"Ключ клиента с tg_id {tg_id} успешно удален.")
                            return True
                        else:
                            logger.error(client_id)
                            logger.error(f"Ошибка удаления ключа клиента с tg_id {tg_id}: {response.json()}")
                            return False
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка декодирования JSON для item: {item}. Ошибка: {e}")
            except Exception as e:
                logger.error(f"Ошибка при удалении ключа для клиента с tg_id {tg_id}: {e}")

        logger.debug(f"Клиент с tg_id {tg_id} не найден для удаления.")
        return False

    # Метод для поиска даты окончания подписки по tg_id
    def find_expirytime_by_tg_id(self, tg_id):
        inbounds = self.get_inbounds()

        for item in inbounds:
            try:
                settings = json.loads(item["settings"])

                # Ищем клиента по tg_id
                for client in settings["clients"]:
                    if client.get("tgId") == tg_id:
                        time_left = client["expiryTime"]
                        return time_left

            except Exception as e:
                logger.error(f"Ошибка при обработке клиента с tg_id {tg_id}: {e}")

        logger.debug(f"Клиент с tg_id {tg_id} не найден.")
        return None


# Инициализация X3 с использованием ваших данных
x3 = X3(
    login=LOGIN,
    password=PASSWORD,
    host=HOST
)