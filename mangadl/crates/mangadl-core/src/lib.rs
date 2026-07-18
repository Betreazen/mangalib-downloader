//! mangadl-core — ядро мультисорс-загрузчика (порт `mangalib_dl/sources/`).
//! Фаза 1: контракт (source, error) + движок (http, convert, package, storage,
//! download). Реестр/агрегатор/источники — Фазы 2–3 по TZ.md.

pub mod config;
pub mod convert;
pub mod download;
pub mod error;
pub mod http;
pub mod package;
pub mod source;
pub mod storage;

pub use error::SourceError;
pub use source::{ChapterInfo, MangaSource, PageInfo, SearchResult, SourceStatus};
pub use storage::{FsStorage, OutputStorage};
