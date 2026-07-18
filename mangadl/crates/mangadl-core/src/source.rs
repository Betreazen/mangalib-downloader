//! Несущий контракт мультисорса — порт `mangalib_dl/sources/base.py` 1:1.
//! Это god-nodes графа: семантику полей и методов менять нельзя (ARCHITECTURE §2).

use std::collections::HashMap;

use async_trait::async_trait;
use serde::{Deserialize, Serialize};

use crate::error::SourceError;

/// Статус реализации источника: "verified" | "unverified" | "stub".
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SourceStatus {
    Verified,
    Unverified,
    Stub,
}

/// Найденный тайтл на конкретном сайте.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct SearchResult {
    pub source_id: String, // id источника из реестра ("remanga", ...)
    pub manga_id: String,  // внутренний id/slug тайтла на сайте
    pub title: String,
    #[serde(default)]
    pub alt_titles: Vec<String>,
    #[serde(default)]
    pub url: String, // страница тайтла в браузере
    #[serde(default)]
    pub cover: String,
    #[serde(default)]
    pub chapters_count: Option<u32>, // если сайт отдаёт сразу в поиске
    #[serde(default)]
    pub extra: serde_json::Value, // прочее для адаптера
}

impl SearchResult {
    /// Основное + альтернативные названия (для группировки в агрегаторе).
    pub fn all_titles(&self) -> impl Iterator<Item = &str> {
        std::iter::once(self.title.as_str()).chain(self.alt_titles.iter().map(String::as_str))
    }
}

/// Глава тайтла в терминах источника.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct ChapterInfo {
    pub chapter_id: String, // внутренний id (или "vol/num")
    #[serde(default)]
    pub volume: String,
    #[serde(default)]
    pub number: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub team: String, // команда перевода, если известна
    #[serde(default)]
    pub branch_id: Option<String>, // ветка перевода, если сайт их различает
}

impl ChapterInfo {
    /// Человекочитаемая метка — порт `ChapterInfo.label`.
    pub fn label(&self) -> String {
        let base = if self.volume.is_empty() {
            format!("Глава {}", self.number)
        } else {
            format!("Том {} Глава {}", self.volume, self.number)
        };
        if self.name.is_empty() {
            base
        } else {
            format!("{base} — {}", self.name)
        }
    }
}

/// Страница главы: абсолютный URL + заголовки для скачивания (напр. Referer).
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct PageInfo {
    pub index: u32,
    pub url: String,
    #[serde(default)]
    pub headers: HashMap<String, String>,
}

/// Абстрактный источник. Адаптеры задают id/name/base_url и три метода.
#[async_trait]
pub trait MangaSource: Send + Sync {
    fn id(&self) -> &'static str;
    fn name(&self) -> &'static str;
    fn base_url(&self) -> &'static str;
    /// false = только метаданные (Shikimori).
    fn can_download(&self) -> bool {
        true
    }
    fn status(&self) -> SourceStatus {
        SourceStatus::Verified
    }

    /// Поиск тайтлов по названию.
    async fn search(&self, query: &str, limit: usize) -> Result<Vec<SearchResult>, SourceError>;
    /// Полный список глав тайтла (все ветки перевода).
    async fn get_chapters(&self, manga_id: &str) -> Result<Vec<ChapterInfo>, SourceError>;
    /// Страницы конкретной главы (абсолютные URL картинок).
    async fn get_pages(
        &self,
        manga_id: &str,
        chapter: &ChapterInfo,
    ) -> Result<Vec<PageInfo>, SourceError>;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn label_with_volume_and_name() {
        let ch = ChapterInfo {
            chapter_id: "1".into(),
            volume: "1".into(),
            number: "2".into(),
            name: "Пролог".into(),
            ..Default::default()
        };
        assert_eq!(ch.label(), "Том 1 Глава 2 — Пролог");
    }

    #[test]
    fn label_without_volume() {
        let ch = ChapterInfo {
            chapter_id: "1".into(),
            number: "5".into(),
            ..Default::default()
        };
        assert_eq!(ch.label(), "Глава 5");
    }
}
