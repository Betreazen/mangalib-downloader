//! Ошибки источников — порт Python-иерархии
//! (`SourceError`/`AuthRequiredError` из base.py + `Locked`/`Unreleased` из api.py).

/// Единая ошибка источника. Первый `String` — имя источника (или URL/контекст).
#[derive(thiserror::Error, Debug)]
pub enum SourceError {
    #[error("{0}: сеть/HTTP: {1}")]
    Http(String, String),
    #[error("{0}: разбор ответа: {1}")]
    Parse(String, String),
    #[error("{0}: требуется авторизация")]
    AuthRequired(String),
    #[error("{0}: платная глава")]
    Locked(String),
    #[error("{0}: ещё не вышла")]
    Unreleased(String),
    #[error("{0}: не реализовано ({1})")]
    NotImplemented(String, String),
    // В Python I/O-ошибки летят как OSError; в Rust делаем их явным вариантом.
    #[error("ввод-вывод: {0}")]
    Io(#[from] std::io::Error),
}
