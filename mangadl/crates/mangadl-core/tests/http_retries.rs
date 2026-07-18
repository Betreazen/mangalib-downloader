//! AC-1: поведение ретраев и token-bucket как в Python (TESTING §5, mock-сервер).

use std::time::{Duration, Instant};

use mangadl_core::http::{rate_limiter, request_with_retries, RetryPolicy};
use reqwest::Method;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

fn fast_policy() -> RetryPolicy {
    RetryPolicy {
        max_retries: 4,
        backoff: 0.05,
        max_retry_after: 120.0,
    }
}

fn client() -> reqwest::Client {
    reqwest::Client::new()
}

#[tokio::test]
async fn respects_retry_after_on_429() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/api"))
        .respond_with(ResponseTemplate::new(429).insert_header("Retry-After", "1"))
        .up_to_n_times(1)
        .mount(&server)
        .await;
    Mock::given(method("GET"))
        .and(path("/api"))
        .respond_with(ResponseTemplate::new(200).set_body_string("ok"))
        .mount(&server)
        .await;

    let start = Instant::now();
    let resp = request_with_retries(
        &client(),
        Method::GET,
        &format!("{}/api", server.uri()),
        None,
        None,
        None,
        &fast_policy(),
    )
    .await
    .expect("после паузы запрос успешен");
    assert_eq!(resp.status().as_u16(), 200);
    assert!(
        start.elapsed() >= Duration::from_millis(950),
        "клиент обязан выждать Retry-After: 1, прошло {:?}",
        start.elapsed()
    );
}

#[tokio::test]
async fn retries_5xx_with_backoff_then_succeeds() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/flaky"))
        .respond_with(ResponseTemplate::new(500))
        .up_to_n_times(2)
        .mount(&server)
        .await;
    Mock::given(method("GET"))
        .and(path("/flaky"))
        .respond_with(ResponseTemplate::new(200).set_body_string("ok"))
        .expect(1)
        .mount(&server)
        .await;

    let resp = request_with_retries(
        &client(),
        Method::GET,
        &format!("{}/flaky", server.uri()),
        None,
        None,
        None,
        &fast_policy(),
    )
    .await
    .expect("две 500 пережиты ретраями");
    assert_eq!(resp.status().as_u16(), 200);
}

#[tokio::test]
async fn gives_up_after_max_retries() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/dead"))
        .respond_with(ResponseTemplate::new(503))
        .expect(2) // ровно max_retries запросов, не больше
        .mount(&server)
        .await;

    let policy = RetryPolicy {
        max_retries: 2,
        backoff: 0.01,
        max_retry_after: 120.0,
    };
    let err = request_with_retries(
        &client(),
        Method::GET,
        &format!("{}/dead", server.uri()),
        None,
        None,
        None,
        &policy,
    )
    .await
    .expect_err("после max_retries — ошибка");
    assert!(err.to_string().contains("после 2 попыток"), "{err}");
}

#[tokio::test]
async fn no_retry_on_404() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/missing"))
        .respond_with(ResponseTemplate::new(404))
        .expect(1) // ретраев быть не должно
        .mount(&server)
        .await;

    let err = request_with_retries(
        &client(),
        Method::GET,
        &format!("{}/missing", server.uri()),
        None,
        None,
        None,
        &fast_policy(),
    )
    .await
    .expect_err("404 — сразу ошибка");
    assert!(err.to_string().contains("HTTP 404"), "{err}");
}

#[tokio::test]
async fn token_bucket_does_not_exceed_rps() {
    // burst = 40 уходит мгновенно, остальные 20 — не быстрее 40 rps => >= 0.5 c.
    let limiter = rate_limiter(40.0);
    let start = Instant::now();
    for _ in 0..60 {
        limiter.until_ready().await;
    }
    let elapsed = start.elapsed();
    assert!(
        elapsed >= Duration::from_millis(450),
        "60 запросов при 40 rps (burst 40) не могут пройти за {elapsed:?}"
    );
}
