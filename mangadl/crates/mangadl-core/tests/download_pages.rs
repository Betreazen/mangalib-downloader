//! AC-1: скачка страниц через OutputStorage — раскладка original/, детекция
//! формата, per-request заголовки (Referer), прогресс, CBZ.

use std::collections::HashMap;
use std::sync::Mutex;

use mangadl_core::download::{download_chapter_pages, DownloadOpts};
use mangadl_core::http::RetryPolicy;
use mangadl_core::source::PageInfo;
use mangadl_core::storage::{FsStorage, OutputStorage};
use wiremock::matchers::{header, method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

const PNG_BYTES: &[u8] = b"\x89PNG\r\n\x1a\n-fake-png-body";
const JPG_BYTES: &[u8] = b"\xff\xd8\xff\xe0-fake-jpg-body";

fn opts() -> DownloadOpts {
    DownloadOpts {
        concurrency: 2,
        rate_rps: 100.0,
        retry: RetryPolicy {
            max_retries: 2,
            backoff: 0.01,
            max_retry_after: 1.0,
        },
    }
}

#[tokio::test]
async fn downloads_pages_with_headers_and_packs_cbz() {
    let server = MockServer::start().await;
    // Страница 1 отдаётся только с проброшенным Referer (как CDN источников).
    Mock::given(method("GET"))
        .and(path("/p1"))
        .and(header("Referer", "https://example.site/"))
        .respond_with(ResponseTemplate::new(200).set_body_bytes(PNG_BYTES))
        .expect(1)
        .mount(&server)
        .await;
    Mock::given(method("GET"))
        .and(path("/p2"))
        .respond_with(ResponseTemplate::new(200).set_body_bytes(JPG_BYTES))
        .expect(1)
        .mount(&server)
        .await;

    let pages = vec![
        PageInfo {
            index: 1,
            url: format!("{}/p1", server.uri()),
            headers: HashMap::from([("Referer".to_string(), "https://example.site/".to_string())]),
        },
        PageInfo {
            index: 2,
            url: format!("{}/p2", server.uri()),
            headers: HashMap::new(),
        },
    ];

    let tmp = tempfile::tempdir().unwrap();
    let storage = FsStorage::new(tmp.path());
    let progress_log = Mutex::new(Vec::new());
    let progress = |done: usize, total: usize, _msg: &str| {
        progress_log.lock().unwrap().push((done, total));
    };

    let saved = download_chapter_pages(
        &reqwest::Client::new(),
        &pages,
        &storage,
        "Глава 1",
        &opts(),
        Some(&progress),
    )
    .await
    .expect("скачка успешна");

    assert_eq!(saved, 2);
    // Раскладка и расширения — по сигнатуре, как в Python (001.png, 002.jpg).
    assert!(tmp.path().join("Глава 1/original/001.png").exists());
    assert!(tmp.path().join("Глава 1/original/002.jpg").exists());
    assert!(storage.exists("Глава 1"));

    {
        let log = progress_log.lock().unwrap();
        assert_eq!(log.len(), 2);
        assert_eq!(log.last(), Some(&(2, 2)));
    }

    // CBZ из скачанного.
    storage
        .make_cbz("Глава 1/original", "Глава 1 [original].cbz")
        .await
        .expect("CBZ собран");
    let cbz = std::fs::File::open(tmp.path().join("Глава 1 [original].cbz")).unwrap();
    let mut archive = zip::ZipArchive::new(cbz).unwrap();
    let names: Vec<String> = (0..archive.len())
        .map(|i| archive.by_index(i).unwrap().name().to_string())
        .collect();
    assert_eq!(names, vec!["001.png", "002.jpg"]);
}

#[tokio::test]
async fn failed_page_fails_whole_download() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/ok"))
        .respond_with(ResponseTemplate::new(200).set_body_bytes(JPG_BYTES))
        .mount(&server)
        .await;
    Mock::given(method("GET"))
        .and(path("/broken"))
        .respond_with(ResponseTemplate::new(404))
        .mount(&server)
        .await;

    let pages = vec![
        PageInfo {
            index: 1,
            url: format!("{}/ok", server.uri()),
            headers: HashMap::new(),
        },
        PageInfo {
            index: 2,
            url: format!("{}/broken", server.uri()),
            headers: HashMap::new(),
        },
    ];

    let tmp = tempfile::tempdir().unwrap();
    let storage = FsStorage::new(tmp.path());
    let err = download_chapter_pages(
        &reqwest::Client::new(),
        &pages,
        &storage,
        "ch",
        &opts(),
        None,
    )
    .await
    .expect_err("битая страница роняет скачку, как asyncio.gather");
    assert!(err.to_string().contains("HTTP 404"), "{err}");
}
