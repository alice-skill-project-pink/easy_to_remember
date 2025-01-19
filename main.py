import os
import mysql.connector
from fuzzywuzzy import fuzz
import logging

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

# Конфигурация базы данных из переменных окружения
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "test_db")

# ======================== DB CONNECTION MODULE ========================
def get_mysql_connection():
    """
    Устанавливает соединение с базой данных MySQL.
    
    Возвращает объект соединения, который используется для выполнения SQL-запросов.

    Returns:
        connection (mysql.connector.connection.MySQLConnection): Объект соединения с MySQL.
    """
    try:
        connection = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        return connection
    except mysql.connector.Error as err:
        logger.error(f"Ошибка подключения к MySQL: {err}")
        raise

# ======================== DB MODELS MODULE ========================
def ensure_table_exists():
    """
    Проверяет существование таблицы texts в базе данных и создаёт её, если она отсутствует.

    Создаёт таблицу texts, если её нет. Таблица содержит два столбца: session_id и original_text.
    """
    query = """
    CREATE TABLE IF NOT EXISTS texts (
        session_id VARCHAR(255) PRIMARY KEY,
        original_text TEXT NOT NULL
    );
    """
    execute_query(query)

def save_original_text(session_id, text):
    """
    Сохраняет оригинальный текст в таблице для указанного session_id.

    Если текст уже существует, он обновляется.

    Args:
        session_id (str): Идентификатор сессии пользователя.
        text (str): Оригинальный текст, который нужно сохранить.
    """
    query = """
    INSERT INTO texts (session_id, original_text) 
    VALUES (%s, %s) 
    ON DUPLICATE KEY UPDATE original_text = %s;
    """
    execute_query(query, (session_id, text, text))

def get_original_text(session_id):
    """
    Извлекает оригинальный текст для указанного session_id.

    Args:
        session_id (str): Идентификатор сессии пользователя.

    Returns:
        str: Оригинальный текст, если он найден, иначе None.
    """
    query = "SELECT original_text FROM texts WHERE session_id = %s"
    result = execute_query(query, (session_id,), fetchone=True)
    return result[0] if result else None

def delete_original_text(session_id):
    """
    Удаляет оригинальный текст для указанного session_id.

    Args:
        session_id (str): Идентификатор сессии пользователя.
    """
    query = "DELETE FROM texts WHERE session_id = %s"
    execute_query(query, (session_id,))

def execute_query(query, params=None, fetchone=False):
    """
    Выполняет SQL-запрос с параметрами.

    Args:
        query (str): SQL-запрос.
        params (tuple, optional): Параметры для запроса (по умолчанию None).
        fetchone (bool, optional): Если True, возвращается только одна строка результата (по умолчанию False).

    Returns:
        tuple: Результат запроса, если fetchone=True, иначе None.
    """
    with get_mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            if fetchone:
                return cursor.fetchone()
            connection.commit()

# ======================== TEXT PROCESSING MODULE ========================
def clean_text(text):
    """
    Очищает текст от пунктуации, лишних пробелов и приводит его к нижнему регистру.

    Args:
        text (str): Текст, который нужно очистить.

    Returns:
        str: Очищенный текст.
    """
    return " ".join(''.join(e for e in text.lower() if e.isalnum() or e.isspace()).split())

# ======================== LOGIC MODULE ========================
def calculate_similarity(original, user_text):
    """
    Рассчитывает процент сходства между двумя текстами с использованием библиотеки fuzzywuzzy.

    Сравнение выполняется на основе очищенных версий обоих текстов (пунктуация и регистр игнорируются).

    Args:
        original (str): Оригинальный текст.
        user_text (str): Текст, который пользователь попытался запомнить.

    Returns:
        int: Процент сходства между очищенными текстами.
    """
    cleaned_original = clean_text(original)
    cleaned_user_text = clean_text(user_text)
    return fuzz.ratio(cleaned_original, cleaned_user_text)

# ======================== SKILL HANDLER ========================
def create_response(text, buttons=None, session_id=None, user_id=None):
    """
    Формирует структуру ответа для навыка Алиса.

    Args:
        text (str): Текст ответа.
        buttons (list, optional): Список кнопок для ответа (по умолчанию None).
        session_id (str, optional): Идентификатор сессии пользователя (по умолчанию None).
        user_id (str, optional): Идентификатор пользователя (по умолчанию None).

    Returns:
        dict: Ответ, который будет отправлен пользователю в формате JSON.
    """
    return {
        "response": {
            "text": text,
            "buttons": buttons or [],
            "end_session": False
        },
        "session": {
            "session_id": session_id,
            "user_id": user_id,
            "new": True
        },
        "version": "1.0"
    }

def handler(event, context):
    """
    Обрабатывает входящие события от пользователя и формирует ответы.

    Логика обработки:
    - Приветствие нового пользователя.
    - Сохранение оригинального текста.
    - Сравнение текста пользователя с оригиналом.
    - Отправка результата пользователю.

    Args:
        event (dict): Событие от Алисы с данными запроса.
        context (dict): Контекст запроса (не используется в текущей реализации).

    Returns:
        dict: Ответ для отправки пользователю.
    """
    try:
        user_message = event['request']['original_utterance']
        session_id = event['session']['session_id']
        user_id = event['session']['user_id']

        logger.info(f"Обработка сообщения от пользователя {user_id}, сессия {session_id}: {user_message}")

        # Убедиться, что таблица существует
        ensure_table_exists()

        # Приветствие нового пользователя
        if event['session']['new']:
            return create_response("Здравствуйте, введите текст, который хотите выучить.",
                                   [{"title": "Сбросить", "hide": True}],
                                   session_id, user_id)

        # Обработка кнопки "Сбросить"
        if user_message.lower() == "сбросить":
            delete_original_text(session_id)
            return create_response("Текст был удалён. Введите новый текст.",
                                   [{"title": "Сбросить", "hide": True}],
                                   session_id, user_id)

        # Проверка наличия оригинального текста
        original_text = get_original_text(session_id)

        if not original_text:
            save_original_text(session_id, user_message)
            return create_response("Оригинальный текст сохранён. Теперь расскажите его, как вы запомнили.",
                                   [{"title": "Сбросить", "hide": True}],
                                   session_id, user_id)

        # Если оригинальный текст уже есть, обработка пользовательского ввода
        similarity = calculate_similarity(original_text, user_message)

        response_text = (
            f"Процент совпадения: {similarity}%\n\n"
            f"Оригинал текста: {original_text}\n\n"
            f"Ваш текст: {user_message}"
        )

        return create_response(response_text, [{"title": "Сбросить", "hide": True}], session_id, user_id)

    except Exception as e:
        logger.error(f"Ошибка при обработке запроса: {e}")
        return create_response("Произошла ошибка. Попробуйте снова.", [{"title": "Сбросить", "hide": True}], session_id, user_id)
