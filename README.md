# Benji Habbo Retros Hack v2.0

Многофункциональный инструмент для анализа безопасности и тестирования Habbo ретро отелей. Разработан в образовательных целях для изучения уязвимостей веб-приложений.

> **ВНИМАНИЕ**: Данный инструмент предназначен только для образовательных целей и тестирования собственных систем. Несанкционированное использование против сторонних ресурсов незаконно.

## 📋 Содержание

- [Возможности](#-возможности)
- [Установка](#-установка)
- [Использование](#-использование)
- [Модули](#-модули)
- [Структура проекта](#-структура-проекта)
- [Требования](#-требования)
- [Лицензия](#-лицензия)

## 🚀 Возможности

### 🌐 Cloudflare Bypass / Real IP Resolver
- DNS анализ и поиск реального IP сервера
- SSL Certificate Transparency логи (crt.sh)
- Поиск поддоменов
- Анализ HTTP заголовков (CF-Ray, X-Forwarded-For и др.)
- История DNS записей (SecurityTrails, VirusTotal)
- Сканирование открытых портов

### 🔑 Admin Account Extraction
- Сканирование админ-панелей (200+ путей)
- Брутфорс учётных данных (100+ комбинаций)
- Поиск конфигурационных файлов
- Тестирование SQL-инъекций
- Извлечение CMS credentials

### 💥 Hotel Client Crash / DoS
- WebSocket флуд
- TCP Connection Flood
- Large Packet Attack (до 1MB)
- HTTP GET/POST флуд
- Slowloris атака
- Packet of Death

### 📦 In-Client Rank/Currency Manipulation
- Перехват WebSocket трафика
- Изменение ранга пользователя
- Модификация валюты (кредиты, пиксели, алмазы)
- Инъекция модифицированных пакетов
- Поддержка различных CMS систем

### 🖥️ UI Dashboard
- Тёмная тема
- Многофункциональный интерфейс с вкладками
- Цветное логирование
- Сохранение результатов
- Статус-бар с информацией о модулях

## 📦 Установка

### Требования
- Python 3.8 или выше
- pip (менеджер пакетов Python)

### Шаги установки

1. Клонируйте или скачайте репозиторий:
```bash
cd BenjiHabboHack
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Запустите приложение:
```bash
python main.py
```

Или с указанием URL:
```bash
python main.py http://example.com
```

## 🎮 Использование

### Графический интерфейс

1. Введите URL целевого отеля в верхней панели
2. Перейдите на нужную вкладку
3. Настройте параметры
4. Нажмите "Запустить"

### Командная строка

Каждый модуль можно использовать отдельно:

```python
# Cloudflare Bypass
from modules.cloudflare_bypass import CloudflareBypass
cf = CloudflareBypass("http://example.com")
results = cf.run()

# Admin Extraction
from modules.admin_extractor import AdminExtractor
adm = AdminExtractor("http://example.com")
results = adm.run()

# Client Crash
from modules.client_crasher import ClientCrasher
crash = ClientCrasher("http://example.com")
stats = crash.run(attack_type="http_flood", duration=60)

# Packet Manipulation
from modules.packet_manipulator import PacketManipulator
pkt = PacketManipulator("http://example.com")
results = pkt.run_full_manipulation()
```

## 🧩 Модули

### Cloudflare Bypass (`modules/cloudflare_bypass.py`)
- `CloudflareBypass` - основной класс для обхода Cloudflare
- Методы: DNS анализ, SSL CT, поддомены, заголовки, история DNS, порты
- Результат: реальный IP сервера

### Admin Extractor (`modules/admin_extractor.py`)
- `AdminExtractor` - класс для поиска админ-панелей
- 200+ путей админ-панелей
- 100+ комбинаций учётных данных
- SQL-инъекции и поиск конфигов

### Client Crasher (`modules/client_crasher.py`)
- `ClientCrasher` - класс для DoS атак
- 6 типов атак
- Настраиваемая интенсивность (1-10)
- Многопоточность

### Packet Manipulator (`modules/packet_manipulator.py`)
- `PacketManipulator` - класс для манипуляции пакетами
- Перехват WebSocket
- Модификация ранга/валюты
- Поддержка 8 CMS систем

### Утилиты

#### Network Utils (`utils/network_utils.py`)
- DNS разрешение
- HTTP заголовки
- SSL сертификаты
- Сканирование портов
- Проверка Cloudflare

#### Log Utils (`utils/log_utils.py`)
- Цветное логирование
- Поддержка GUI
- Уровни: DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL
- Сохранение в файл

## 📁 Структура проекта

```
BenjiHabboHack/
├── main.py                      # Главный модуль с GUI
├── requirements.txt             # Зависимости
├── README.md                    # Документация
├── modules/
│   ├── cloudflare_bypass.py     # Обход Cloudflare
│   ├── admin_extractor.py       # Извлечение админов
│   ├── client_crasher.py        # DoS атаки
│   └── packet_manipulator.py    # Манипуляция пакетами
└── utils/
    ├── network_utils.py         # Сетевые утилиты
    └── log_utils.py             # Утилиты логирования
```

## 🔧 Требования

### Обязательные
- Python 3.8+
- requests
- dnspython

### Опциональные
- websocket-client (для WebSocket атак)
- beautifulsoup4 (для парсинга HTML)
- aiohttp (для асинхронных запросов)
- colorama (цветной вывод)
- pyOpenSSL (SSL/TLS)

## ⚠️ Отказ от ответственности

Данный инструмент предоставляется исключительно в образовательных целях. Автор не несёт ответственности за любое незаконное использование данного программного обеспечения. Используйте только на собственных системах или с явного разрешения владельца.

## 📄 Лицензия

MIT License

Copyright (c) 2024 Benji

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
