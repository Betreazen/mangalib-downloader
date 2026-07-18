//! Детекция формата по сигнатуре + конвертация в JPEG.
//! Порт `_detect_ext` из downloader.py; AVIF-декод — за фичей `avif` (Фаза 1b).

use std::io::Cursor;

use image::codecs::jpeg::JpegEncoder;

use crate::error::SourceError;

/// Определяет реальное расширение по magic-байтам (порт `_detect_ext`).
pub fn detect_ext(data: &[u8]) -> &'static str {
    if data.len() >= 3 && data[..3] == [0xff, 0xd8, 0xff] {
        return "jpg";
    }
    if data.len() >= 8 && data[..8] == *b"\x89PNG\r\n\x1a\n" {
        return "png";
    }
    if data.len() >= 12 && data[..4] == *b"RIFF" && data[8..12] == *b"WEBP" {
        return "webp";
    }
    if data.len() >= 12
        && data[4..8] == *b"ftyp"
        && (&data[8..12] == b"avif" || &data[8..12] == b"avis")
    {
        return "avif";
    }
    if data.len() >= 6 && (data[..6] == *b"GIF87a" || data[..6] == *b"GIF89a") {
        return "gif";
    }
    "bin"
}

/// Декодирует картинку (PNG/WebP/GIF/…; AVIF — при фиче `avif`) и кодирует в JPEG.
pub fn to_jpeg(data: &[u8], quality: u8) -> Result<Vec<u8>, SourceError> {
    let img = image::load_from_memory(data)
        .map_err(|e| SourceError::Parse("convert".into(), e.to_string()))?;
    let mut out = Cursor::new(Vec::new());
    img.to_rgb8()
        .write_with_encoder(JpegEncoder::new_with_quality(&mut out, quality))
        .map_err(|e| SourceError::Parse("convert".into(), e.to_string()))?;
    Ok(out.into_inner())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config;

    #[test]
    fn detects_magic_bytes() {
        assert_eq!(detect_ext(&[0xff, 0xd8, 0xff, 0x00]), "jpg");
        assert_eq!(detect_ext(b"\x89PNG\r\n\x1a\n...."), "png");
        assert_eq!(detect_ext(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "webp");
        assert_eq!(detect_ext(b"\x00\x00\x00\x1cftypavif...."), "avif");
        assert_eq!(detect_ext(b"\x00\x00\x00\x1cftypavis...."), "avif");
        assert_eq!(detect_ext(b"GIF87a......"), "gif");
        assert_eq!(detect_ext(b"GIF89a......"), "gif");
        assert_eq!(detect_ext(b"hello"), "bin");
        assert_eq!(detect_ext(b""), "bin");
        assert_eq!(detect_ext(b"\xff\xd8"), "bin"); // короткий буфер не роняет
    }

    fn sample_image() -> image::DynamicImage {
        image::DynamicImage::ImageRgb8(image::RgbImage::from_pixel(4, 4, image::Rgb([200, 10, 10])))
    }

    #[test]
    fn png_converts_to_valid_jpeg() {
        let mut png = Cursor::new(Vec::new());
        sample_image()
            .write_to(&mut png, image::ImageFormat::Png)
            .unwrap();
        let jpg = to_jpeg(png.get_ref(), config::CONVERT_QUALITY).unwrap();
        assert_eq!(detect_ext(&jpg), "jpg");
        image::load_from_memory(&jpg).expect("валидный JPEG");
    }

    #[test]
    fn webp_converts_to_valid_jpeg() {
        let mut webp = Cursor::new(Vec::new());
        sample_image()
            .write_to(&mut webp, image::ImageFormat::WebP)
            .unwrap();
        assert_eq!(detect_ext(webp.get_ref()), "webp");
        let jpg = to_jpeg(webp.get_ref(), config::CONVERT_QUALITY).unwrap();
        assert_eq!(detect_ext(&jpg), "jpg");
    }

    // AC-1: AVIF→JPEG — гоняется при включённой фиче `avif` (dav1d на desktop).
    #[cfg(feature = "avif")]
    #[test]
    fn avif_converts_to_valid_jpeg() {
        let mut avif = Cursor::new(Vec::new());
        sample_image()
            .write_to(&mut avif, image::ImageFormat::Avif)
            .unwrap();
        assert_eq!(detect_ext(avif.get_ref()), "avif");
        let jpg = to_jpeg(avif.get_ref(), config::CONVERT_QUALITY).unwrap();
        assert_eq!(detect_ext(&jpg), "jpg");
        image::load_from_memory(&jpg).expect("валидный JPEG");
    }

    #[test]
    fn broken_data_is_parse_error() {
        let err = to_jpeg(b"not an image", 92).unwrap_err();
        assert!(matches!(err, SourceError::Parse(..)));
    }
}
