# StreamTail 🚀

![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-green.svg)
![License](https://img.shields.io/badge/license-Apache%202.0-lightgrey.svg)

**StreamTail** — асинхронный менеджер для стримеров. Управляет статусом, названием
и категорией трансляции одновременно на всех платформах в один клик.

## 📦 Установка

```bash
git clone <repo>
cd streamtail
pip install -r requirements.txt
cp config/app.yaml config/app.yaml   # уже есть
# Заполни токены в config/app.yaml
python main.py
```

## ⚙️ Настройка

Отредактируй `config/app.yaml`:

| Ключ | Описание |
|------|----------|
| `app.check_interval` | Интервал опроса платформ (секунды) |
| `platforms.<name>.enabled` | Включить/выключить платформу |
| `favorites.games` | Быстрый список игр в выпадающем меню |

## 🎮 Поддерживаемые платформы

| Платформа | Статус | set_title | set_game |
|-----------|--------|-----------|----------|
| Twitch    | ✅     | ✅        | ✅       |
| YouTube   | ✅     | ✅        | ⚠️ только ID |
| VK Live   | ✅     | ✅        | ✅       |
| Kick      | ✅     | ✅ (token) | ✅ (token) |

## 🛠 Архитектура

```
app/
├── core/           # EventBus, Scheduler, PluginManager, IoC-контейнер
├── platforms/      # Плагины платформ (Twitch, YouTube, VK, Kick)
├── plugins/        # Базовый класс BasePlugin
├── services/       # StreamService, GameService, NotificationService
├── ui/
│   ├── desktop/    # Tkinter GUI (async-tkinter-loop)
│   └── web/        # TODO: FastAPI (Фаза 3)
└── utils/          # Config, Logger
```

**Ключевые решения:**
- `EventBus` — wildcard-подписки, sync/async колбэки на одном потоке (thread-safe для Tkinter)
- Карточки платформ строятся динамически после события `plugins.loaded`
- Массовое обновление всех платформ через `asyncio.gather` (параллельно)
- Вкладка «Лог событий» с цветовой подсветкой онлайн/оффлайн переходов

## 🗺 Roadmap

- **Фаза 2 (текущая):** Kick, EventLog, динамические карточки
- **Фаза 3:** FastAPI web-интерфейс, CLI (Typer), трей-иконка, OAuth-помощник
