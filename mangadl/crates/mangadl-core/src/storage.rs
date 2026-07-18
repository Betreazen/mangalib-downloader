//! Абстракция выходного хранилища (ARCHITECTURE §11.1).
//! Ядро пишет только через этот трейт — на Android место `FsStorage`
//! займёт реализация поверх SAF (Фаза 7).

use std::path::PathBuf;

use async_trait::async_trait;

use crate::{error::SourceError, package};

#[async_trait]
pub trait OutputStorage: Send + Sync {
    async fn write_page(
        &self,
        chapter_dir: &str,
        name: &str,
        bytes: &[u8],
    ) -> Result<(), SourceError>;
    /// Собирает CBZ из картинок в `chapter_dir` в файл `out_name` (оба — от корня).
    async fn make_cbz(&self, chapter_dir: &str, out_name: &str) -> Result<(), SourceError>;
    /// Для skip-existing/докачки.
    fn exists(&self, chapter_dir: &str) -> bool;
}

/// Хранилище поверх обычной файловой системы (desktop и app-dir Android).
pub struct FsStorage {
    root: PathBuf,
}

impl FsStorage {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }
}

#[async_trait]
impl OutputStorage for FsStorage {
    async fn write_page(
        &self,
        chapter_dir: &str,
        name: &str,
        bytes: &[u8],
    ) -> Result<(), SourceError> {
        let dir = self.root.join(chapter_dir);
        tokio::fs::create_dir_all(&dir).await?;
        tokio::fs::write(dir.join(name), bytes).await?;
        Ok(())
    }

    async fn make_cbz(&self, chapter_dir: &str, out_name: &str) -> Result<(), SourceError> {
        let images = self.root.join(chapter_dir);
        let out = self.root.join(out_name);
        tokio::task::spawn_blocking(move || package::make_cbz(&images, &out).map(|_| ()))
            .await
            .map_err(|e| SourceError::Io(std::io::Error::other(e.to_string())))?
    }

    fn exists(&self, chapter_dir: &str) -> bool {
        self.root.join(chapter_dir).exists()
    }
}
