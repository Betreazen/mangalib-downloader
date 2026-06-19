"""Глобальные константы и настройки для загрузчика MangaLib."""
from __future__ import annotations

# Базовый адрес публичного JSON API читалки MangaLib.
API_BASE = "https://api2.mangalib.me/api"

# site_id для самого MangaLib (в API это поле site_id[]=1).
SITE_ID = 1

# Браузерные заголовки. Токен авторизации НЕ обязателен для большинства
# тайтлов; для лицензированных/18+ его можно передать дополнительно.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://mangalib.me/",
    "Origin": "https://mangalib.me",
    "Site-Id": str(SITE_ID),
}

# Запасной список CDN-серверов картинок на случай, если /constants недоступен.
# Реальный актуальный список подтягивается из API при старте.
FALLBACK_IMAGE_SERVERS = [
    "https://img2.imglib.info",
    "https://img3.mixlib.me",
    "https://img4.imglib.info",
]

# --- Параметры скачивания (значения по умолчанию, мягкие к лимитам) ---
MAX_CONCURRENT_DOWNLOADS = 3      # одновременных загрузок страниц
API_RATE_RPS = 3.0               # запросов/сек к API (метаданные/страницы)
IMAGE_RATE_RPS = 5.0             # запросов/сек к CDN картинок
INTER_CHAPTER_DELAY = 1.5        # пауза между главами, сек
REQUEST_TIMEOUT = 30.0           # сек на запрос
MAX_RETRIES = 4                  # попыток на одну страницу/запрос
RETRY_BACKOFF = 1.6              # множитель экспоненциальной паузы
RETRY_STATUS = {429, 500, 502, 503, 504}  # коды, которые имеет смысл повторять
MAX_RETRY_AFTER = 120.0          # верхняя граница ожидания по Retry-After, сек

# Формат для конвертации AVIF -> привычный формат.
CONVERT_FORMAT = "JPEG"          # JPEG или PNG
CONVERT_QUALITY = 92             # для JPEG

# Метка для переводов без указанной команды.
UNSIGNED_LABEL = "Без указания команды"
