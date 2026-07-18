//! HTTP-движок: общий клиент, rate-limit (governor), ретраи 429/5xx/Retry-After.
//! Порт `mangalib_dl/ratelimit.py` — поведение 1:1 (паритет-чеклист).

use std::collections::HashMap;
use std::num::NonZeroU32;
use std::time::Duration;

use governor::Quota;

use crate::{config, error::SourceError};

pub type Limiter = governor::DefaultDirectRateLimiter;

/// Токен-бакет: не более `rps` запросов в секунду (с burst = ceil(rps),
/// как capacity = max(1, rate) в Python RateLimiter).
pub fn rate_limiter(rps: f64) -> Limiter {
    let rps = rps.max(0.1);
    let period = Duration::from_secs_f64(1.0 / rps);
    let burst = NonZeroU32::new((rps.ceil() as u32).max(1)).expect("burst >= 1");
    Limiter::direct(
        Quota::with_period(period)
            .expect("period > 0")
            .allow_burst(burst),
    )
}

/// Параметры ретраев. Default = значения config.py (паритет);
/// в тестах подставляются маленькие паузы.
#[derive(Clone, Debug)]
pub struct RetryPolicy {
    pub max_retries: u32,
    pub backoff: f64,
    pub max_retry_after: f64,
}

impl Default for RetryPolicy {
    fn default() -> Self {
        Self {
            max_retries: config::MAX_RETRIES,
            backoff: config::RETRY_BACKOFF,
            max_retry_after: config::MAX_RETRY_AFTER,
        }
    }
}

/// Разбор заголовка Retry-After (секунды или HTTP-дата) — порт `parse_retry_after`.
pub fn parse_retry_after(value: Option<&str>, max: f64) -> Option<f64> {
    let v = value?.trim();
    if v.is_empty() {
        return None;
    }
    if v.bytes().all(|b| b.is_ascii_digit()) {
        return Some(v.parse::<f64>().unwrap_or(max).min(max));
    }
    let dt = chrono::DateTime::parse_from_rfc2822(v).ok()?;
    let delta = (dt.timestamp_millis() - chrono::Utc::now().timestamp_millis()) as f64 / 1000.0;
    Some(delta.clamp(0.0, max))
}

/// Общий клиент приложения (пул соединений, браузерный UA, редиректы).
pub fn default_client() -> Result<reqwest::Client, SourceError> {
    reqwest::Client::builder()
        .user_agent(config::USER_AGENT)
        .timeout(Duration::from_secs_f64(config::REQUEST_TIMEOUT_SECS))
        .build()
        .map_err(|e| SourceError::Http("client".into(), e.to_string()))
}

/// Запрос с уважением лимитов: токен-бакет, ретраи, 429/Retry-After.
/// Порт `request_with_retries` из ratelimit.py.
pub async fn request_with_retries(
    client: &reqwest::Client,
    method: reqwest::Method,
    url: &str,
    query: Option<&HashMap<String, String>>,
    headers: Option<&HashMap<String, String>>,
    limiter: Option<&Limiter>,
    policy: &RetryPolicy,
) -> Result<reqwest::Response, SourceError> {
    let mut last_err = String::new();
    for attempt in 0..policy.max_retries {
        if let Some(l) = limiter {
            l.until_ready().await;
        }
        let mut req = client.request(method.clone(), url);
        if let Some(q) = query {
            req = req.query(q);
        }
        if let Some(h) = headers {
            for (k, v) in h {
                req = req.header(k, v);
            }
        }
        match req.send().await {
            Ok(resp) => {
                let status = resp.status().as_u16();
                if config::RETRY_STATUS.contains(&status) {
                    let retry_after = parse_retry_after(
                        resp.headers()
                            .get("Retry-After")
                            .and_then(|v| v.to_str().ok()),
                        policy.max_retry_after,
                    );
                    // Если сервер не подсказал — экспоненциальная пауза;
                    // 429 без подсказки — подождём подольше (>= 5 сек, как в Python).
                    let mut wait =
                        retry_after.unwrap_or_else(|| policy.backoff.powi(attempt as i32));
                    if status == 429 && retry_after.is_none() {
                        wait = wait.max(5.0);
                    }
                    last_err = format!("HTTP {status}");
                    if attempt < policy.max_retries - 1 {
                        tracing::warn!(url, status, wait, attempt, "throttling, ждём и повторяем");
                        tokio::time::sleep(Duration::from_secs_f64(wait)).await;
                        continue;
                    }
                } else if resp.status().is_client_error() || resp.status().is_server_error() {
                    // Неретраябельный статус — сразу ошибка (как raise_for_status).
                    return Err(SourceError::Http(url.to_string(), format!("HTTP {status}")));
                } else {
                    return Ok(resp);
                }
            }
            Err(e) => {
                last_err = e.to_string();
                if attempt < policy.max_retries - 1 {
                    tokio::time::sleep(Duration::from_secs_f64(
                        policy.backoff.powi(attempt as i32),
                    ))
                    .await;
                }
            }
        }
    }
    Err(SourceError::Http(
        url.to_string(),
        format!(
            "Запрос не удался после {} попыток: {last_err}",
            policy.max_retries
        ),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retry_after_seconds() {
        assert_eq!(parse_retry_after(Some("7"), 120.0), Some(7.0));
    }

    #[test]
    fn retry_after_capped() {
        assert_eq!(parse_retry_after(Some("999"), 120.0), Some(120.0));
    }

    #[test]
    fn retry_after_http_date() {
        let future = (chrono::Utc::now() + chrono::Duration::seconds(30)).to_rfc2822();
        let parsed = parse_retry_after(Some(&future), 120.0).expect("дата разобрана");
        assert!((25.0..=31.0).contains(&parsed), "получили {parsed}");
    }

    #[test]
    fn retry_after_garbage_is_none() {
        assert_eq!(parse_retry_after(Some("soon"), 120.0), None);
        assert_eq!(parse_retry_after(None, 120.0), None);
    }
}
