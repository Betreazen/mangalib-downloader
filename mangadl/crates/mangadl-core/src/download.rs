//! Параллельное скачивание страниц по абсолютным URL — порт
//! `mangalib_dl/sources/download.py` (мультисорс-путь). Пишет через `OutputStorage`.

use std::sync::atomic::{AtomicUsize, Ordering};

use tokio::sync::Semaphore;

use crate::{
    config,
    convert::detect_ext,
    error::SourceError,
    http::{self, rate_limiter, RetryPolicy},
    package::safe_name,
    source::{ChapterInfo, PageInfo},
    storage::OutputStorage,
};

/// (done, total, message) — как ProgressCb в Python.
pub type ProgressFn<'a> = dyn Fn(usize, usize, &str) + Send + Sync + 'a;

#[derive(Clone, Debug)]
pub struct DownloadOpts {
    pub concurrency: usize,
    pub rate_rps: f64,
    pub retry: RetryPolicy,
}

impl Default for DownloadOpts {
    fn default() -> Self {
        Self {
            concurrency: config::MAX_CONCURRENT_DOWNLOADS,
            rate_rps: config::IMAGE_RATE_RPS,
            retry: RetryPolicy::default(),
        }
    }
}

/// Качает страницы в `chapter_dir/original`. Возвращает число обработанных.
pub async fn download_chapter_pages(
    client: &reqwest::Client,
    pages: &[PageInfo],
    storage: &dyn OutputStorage,
    chapter_dir: &str,
    opts: &DownloadOpts,
    progress: Option<&ProgressFn<'_>>,
) -> Result<usize, SourceError> {
    let original_dir = format!("{chapter_dir}/original");
    let limiter = rate_limiter(opts.rate_rps);
    let sem = Semaphore::new(opts.concurrency.max(1));
    let total = pages.len();
    let done = AtomicUsize::new(0);

    let results = futures::future::join_all(pages.iter().map(|p| {
        let (original_dir, limiter, sem, done) = (&original_dir, &limiter, &sem, &done);
        async move {
            let _permit = sem.acquire().await.expect("семафор не закрывается");
            let headers = (!p.headers.is_empty()).then_some(&p.headers);
            let resp = http::request_with_retries(
                client,
                reqwest::Method::GET,
                &p.url,
                None,
                headers,
                Some(limiter),
                &opts.retry,
            )
            .await?;
            let data = resp
                .bytes()
                .await
                .map_err(|e| SourceError::Http(p.url.clone(), e.to_string()))?;
            if !data.is_empty() {
                let ext = detect_ext(&data);
                storage
                    .write_page(original_dir, &format!("{:03}.{ext}", p.index), &data)
                    .await?;
            }
            let n = done.fetch_add(1, Ordering::Relaxed) + 1;
            if let Some(cb) = progress {
                cb(n, total, &format!("Страница {n}/{total}"));
            }
            Ok::<(), SourceError>(())
        }
    }))
    .await;

    // Как asyncio.gather: первая ошибка прерывает результат целиком.
    for r in results {
        r?;
    }
    Ok(done.load(Ordering::Relaxed))
}

/// Имя папки главы — порт `chapter_dirname`.
pub fn chapter_dirname(ch: &ChapterInfo) -> String {
    safe_name(&ch.label())
}
