# Photo Master - AI Photo Face Sorter

Приложение для автоматической сортировки фотографий по лицам с использованием компьютерного зрения.

## 🚀 Быстрый запуск (Windows)

### Первый запуск:
```cmd
start.bat
```

### Повторные запуски:
```cmd
run.bat
```

## 📋 Что делает приложение

- 🔍 **Сканирование папок** с фотографиями
- 👤 **Распознавание лиц** на изображениях
- 📊 **Кластеризация** фотографий по людям
- 📁 **Автоматическая сортировка** в папки по людям
- 🖥️ **Веб-интерфейс** для управления процессом

## 🛠️ Технологии

- **Backend**: Python + FastAPI + InsightFace + OpenCV
- **Frontend**: React + TypeScript + Vite + shadcn/ui
- **AI**: InsightFace для распознавания лиц
- **База данных**: SQLite (через SQLAlchemy)

## 📦 Установка

### Автоматическая (Windows):
1. Скачайте проект с GitHub
2. Запустите `start.bat`
3. Откройте http://localhost:5173

### Ручная установка:

#### Backend:
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
# или source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

#### Frontend:
```bash
cd frontend
npm install
```

## 🚀 Запуск

### Backend:
```bash
cd backend
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Frontend:
```bash
cd frontend
npm run dev
```

## 📱 Использование

1. Откройте http://localhost:5173 в браузере
2. Выберите корневую папку для сканирования
3. Добавьте папки в очередь обработки
4. Нажмите "Обработать" для запуска анализа
5. Просмотрите результаты кластеризации

## 🔧 Системные требования

- **Python 3.9+**
- **Node.js 18+**
- **Windows/Linux/Mac**
- **4GB+ RAM** (рекомендуется 8GB+)
- **GPU** (опционально, ускоряет обработку)

## 📁 Структура проекта

```
Photo_master/
├── backend/           # Python FastAPI сервер
│   ├── api/          # API endpoints
│   ├── core/         # Логика обработки изображений
│   ├── models/       # Pydantic модели
│   └── utils/        # Вспомогательные функции
├── frontend/         # React приложение
│   ├── src/
│   │   ├── components/  # React компоненты
│   │   ├── pages/       # Страницы приложения
│   │   └── lib/         # Утилиты и API клиент
│   └── public/      # Статические файлы
├── start.bat         # Полная установка (Windows)
├── run.bat           # Быстрый запуск (Windows)
└── README_Windows.md # Подробная инструкция для Windows
```

## 🐛 Устранение неполадок

### Ошибки запуска:
- Убедитесь что Python и Node.js установлены
- Проверьте что порты 8000 и 5173 свободны
- Попробуйте перезапустить batch файлы

### Проблемы с производительностью:
- Добавьте больше RAM
- Используйте GPU если доступна
- Обрабатывайте меньшие папки

### Ошибки распознавания:
- Проверьте качество фотографий
- Убедитесь что лица хорошо видны
- Попробуйте разные углы освещения

## 📄 Лицензия

MIT License

## 🤝 Вклад в проект

1. Fork репозиторий
2. Создайте feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit изменения (`git commit -m 'Add some AmazingFeature'`)
4. Push в branch (`git push origin feature/AmazingFeature`)
5. Откройте Pull Request

## 📞 Контакты

Если возникли вопросы или проблемы:
1. Проверьте [Issues](https://github.com/RockInMyHead/Photo_master/issues)
2. Создайте новый Issue с подробным описанием проблемы
3. Укажите версию Python, Node.js и ОС
