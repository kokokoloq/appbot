import feedparser
from telegram import Bot
import html
import asyncio
from dateutil import parser as date_parser
from telegram.error import RetryAfter
from html import escape, unescape
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

DAYS_LIMIT = 1  # Максимальный возраст новости в днях

TELEGRAM_BOT_TOKEN = '6862103484:AAHgDBh5JDD8OS_QcnXpjgHrz1Zl8Ga5BMk'
TELEGRAM_CHAT_ID = '-1002076321726'
RSS_URLS = [
    "http://lenta.ru/rss",
    "http://www.gazeta.ru/export/rss/first.xml",
    "https://tass.ru/rss/v2.xml",
    "https://ria.ru/export/rss2/index.xml",
    "https://www.kommersant.ru/RSS/news.xml",
    "https://1prime.ru/rss",
    "http://www.aif.ru/rss/all.php",
    "http://russian.rt.com/rss/",
    "http://www.rg.ru/xml/index.xml",
    "http://www.ixbt.com/export/news.rss",
    "http://www.dp.ru/exportnews.xml",
    "http://www.banki.ru/xml/news.rss",
    "http://news.rambler.ru/rss/world/",
    "http://www.fontanka.ru/fontanka.rss",
    "http://www.bfm.ru/news.rss?rubric=19",
    "https://smotrim.ru/vesti?u=rss",
    "https://kp.ru/rss/allsections.xml",
    "https://ura.news/rss",
    "http://regnum.ru/rss/main",
    "http://www.ng.ru/rss",
    "http://www.cbr.ru/rss/RssNews",
    "http://www.mk.ru/rss/news/index.xml",
    "http://www.3dnews.ru/digital/rss/",
]

SEARCH_KEYWORDS = ["сбер", "gigachat", "сбербанк", "сбер","Sberindex", "Сбер индекс",
                   "Сбериндекс", "сбермобаил", "греф сбербанк", "sbrf", "домклик", "герман греф" "греф", "Gref sberbank", "sber",  "sberbank", "сбербанк", "Sber index",  "SberCIB"]
CHECK_INTERVAL_SECONDS = 25
DATABASE_FILE = 'processed_links.db'

async def send_telegram_message(message):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='HTML', disable_web_page_preview=True)
    except RetryAfter as e:
        logging.warning(f"Got RetryAfter exception. Retrying after {e.retry_after} seconds.")
        await asyncio.sleep(e.retry_after)
        await send_telegram_message(message)  # Повторная попытка отправки
    except Exception as e:
        logging.error(f"Error sending message: {e}")

def create_database():
    connection = sqlite3.connect(DATABASE_FILE)
    cursor = connection.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS processed_links (link TEXT PRIMARY KEY)')
    connection.commit()
    connection.close()

def is_link_processed(link):
    connection = sqlite3.connect(DATABASE_FILE)
    cursor = connection.cursor()
    cursor.execute('SELECT link FROM processed_links WHERE link = ?', (link,))
    result = cursor.fetchone()
    connection.close()
    return bool(result)

def mark_link_as_processed(link):
    connection = sqlite3.connect(DATABASE_FILE)
    cursor = connection.cursor()
    cursor.execute('INSERT INTO processed_links (link) VALUES (?)', (link,))
    connection.commit()
    connection.close()

async def parse_rss(feed_url):
    try:
        feed = feedparser.parse(feed_url)

        if not feed.entries:
            
            return

        current_time = datetime.now(timezone.utc)  # Учтем часовой пояс UTC

        for entry in feed.entries:
            # Получение даты публикации новости
            published_date = entry.get('published', 'N/A')
            if published_date == 'N/A':
                continue

            # Парсинг даты и времени публикации
            parsed_date = date_parser.parse(published_date).replace(tzinfo=timezone.utc)

            # Проверка, не старше ли новость, чем DAYS_LIMIT дней
            if current_time - parsed_date > timedelta(days=DAYS_LIMIT):
                continue

            link = entry.get('link', 'N/A')

            if is_link_processed(link):
                continue

            mark_link_as_processed(link)

            title = entry.get('title', 'N/A').capitalize()
            summary = entry.get('content', [{'value': entry.get('summary_detail', {}).get('value', 'N/A')}])[0].get('value', 'N/A')

            highlighted_summary = highlight_keywords(summary)

            # Используйте html.unescape() перед отправкой в телеграм
            highlighted_summary = unescape(highlighted_summary)

            if any(keyword.lower() in title.lower() or keyword.lower() in summary.lower() for keyword in SEARCH_KEYWORDS):
                entry_message = (
                    f"\n\n<b>{title}</b>\n"
                    f"{parse_publish_date(entry.get('published', 'N/A'))}\n"
                    f"{escape_special_characters(link)}\n"
                    f"{highlighted_summary}"
                )

                await send_telegram_message(entry_message)

    except Exception as e:
        logging.error(f"Error parsing RSS: {e}")
        await send_telegram_message(f"Error: {escape_special_characters(str(e))}")

def highlight_keywords(text):
    for keyword in SEARCH_KEYWORDS:
        # Используем HTML-тег <strong> для выделения ключевых слов
        text = text.replace(keyword, f"<strong>{keyword}</strong>")
    return text

def escape_special_characters(text):
    # Экранируем специальные символы для HTML
    return html.escape(text)

def parse_publish_date(date_string):
    try:
        parsed_date = date_parser.parse(date_string)
        # Преобразование в строку без указания часового пояса
        return parsed_date.strftime('%d.%m.%Y %H:%M')
    except ValueError:
        return 'N/A'

async def main():
    create_database()
    while True:
        for rss_url in RSS_URLS:
            await parse_rss(rss_url)
        
        try:
            # Задержка перед следующей проверкой
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        except RetryAfter as e:
            logging.warning(f"Got RetryAfter exception. Retrying after {e.retry_after} seconds.")
            await asyncio.sleep(e.retry_after)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
