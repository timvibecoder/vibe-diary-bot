# Дневник вайба (Telegram Bot)

Telegram бот для отслеживания "вайба" с системой достижений и социальными механиками.

## Возможности

- 📈 Отслеживание личного вайба
- 🏆 Система достижений
- 💝 Передача вайба другим пользователям
- 📊 Уровни и прогресс
- 📝 Заметки к изменениям
- 🎁 Ежедневные бонусы
- 📈 Топ пользователей

## Команды

- `/start` - начать использование бота
- `/plusvibe [число]` - повысить вайб
- `/minusvibe [число]` - понизить вайб
- `/myvibe` - проверить текущий вайб
- `/topvibe` - показать топ пользователей
- `/history` - история изменений
- `/levels` - информация об уровнях
- `/transfer` - передать вайб другому пользователю
- `/achievements` - просмотр достижений
- `/daily` - получить ежедневный бонус

## Установка

1. Клонируйте репозиторий
2. Установите зависимости: `pip install -r requirements.txt`
3. Создайте файл `.env` и добавьте токен бота:
   ```
   TELEGRAM_TOKEN=ваш_токен_бота
   ```
4. Запустите бота: `python3 bot.py`

## Развертывание

Бот готов к развертыванию на Railway.app:
1. Подключите этот репозиторий к Railway
2. Добавьте переменную окружения `TELEGRAM_TOKEN`
3. Railway автоматически развернет и запустит бота

## Лицензия

MIT 