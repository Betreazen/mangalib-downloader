//! Константы движка — порт `mangalib_dl/config.py` (значения 1:1, паритет).

pub const USER_AGENT: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 \
                              (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36";

pub const MAX_CONCURRENT_DOWNLOADS: usize = 3; // одновременных загрузок страниц
pub const API_RATE_RPS: f64 = 3.0; // запросов/сек к API
pub const IMAGE_RATE_RPS: f64 = 5.0; // запросов/сек к CDN картинок
pub const REQUEST_TIMEOUT_SECS: f64 = 30.0; // сек на запрос
pub const MAX_RETRIES: u32 = 4; // попыток на один запрос
pub const RETRY_BACKOFF: f64 = 1.6; // множитель экспоненциальной паузы
pub const RETRY_STATUS: [u16; 5] = [429, 500, 502, 503, 504]; // что повторяем
pub const MAX_RETRY_AFTER: f64 = 120.0; // потолок ожидания по Retry-After, сек
pub const CONVERT_QUALITY: u8 = 92; // качество JPEG при конвертации
