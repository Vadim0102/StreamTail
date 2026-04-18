# StreamTail 🚀

![Version](https://img.shields.io/badge/version-idk-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-green.svg)
![License](https://img.shields.io/badge/license-Apache%202.0-lightgrey.svg)

**StreamTail** — это асинхронный менеджер для стримеров, позволяющий управлять статусом, названием и категорией трансляции одновременно на всех платформах в один клик.

## 📦 Установка
1. Клонируйте репозиторий.
2. Установите зависимости: `pip install -r requirements.txt`
3. Настройте `config/app.yaml` (добавьте свои токены).
4. Запустите приложение: `python main.py`

## 🛠 Архитектура
- **Core:** Асинхронное ядро с EventBus.
- **Plugins:** Модульная система платформ (Twitch, YouTube, VK).
- **UI:** Tkinter + asyncio (через `async-tkinter-loop`).
