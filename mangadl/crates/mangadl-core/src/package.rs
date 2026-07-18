//! Упаковка в CBZ + безопасные имена файлов — порт `mangalib_dl/packager.py`.

use std::fs::File;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use zip::{write::SimpleFileOptions, CompressionMethod, ZipWriter};

use crate::error::SourceError;

const MAX_NAME_LEN: usize = 150;
const IMAGE_EXTS: [&str; 6] = ["jpg", "jpeg", "png", "webp", "avif", "gif"];

/// Делает строку безопасной для имени файла/папки в Windows (порт `safe_name`).
pub fn safe_name(name: &str) -> String {
    let replaced: String = name
        .chars()
        .map(|c| match c {
            '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*' => '_',
            c if (c as u32) < 0x20 => '_',
            c => c,
        })
        .collect();
    let trimmed = replaced.trim_matches([' ', '.']);
    let collapsed = trimmed.split_whitespace().collect::<Vec<_>>().join(" ");
    let cut: String = collapsed.chars().take(MAX_NAME_LEN).collect();
    if cut.is_empty() {
        "untitled".into()
    } else {
        cut
    }
}

/// Собирает CBZ из всех картинок в папке (по алфавиту имён), без сжатия
/// (ZIP_STORED — картинки уже сжаты). Порт `make_cbz`.
pub fn make_cbz(images_dir: &Path, cbz_path: &Path) -> Result<PathBuf, SourceError> {
    let mut images: Vec<PathBuf> = std::fs::read_dir(images_dir)?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| {
            p.is_file()
                && p.extension()
                    .and_then(|e| e.to_str())
                    .is_some_and(|e| IMAGE_EXTS.contains(&e.to_ascii_lowercase().as_str()))
        })
        .collect();
    images.sort();

    if let Some(parent) = cbz_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut zf = ZipWriter::new(File::create(cbz_path)?);
    let opts = SimpleFileOptions::default().compression_method(CompressionMethod::Stored);
    for img in &images {
        let name = img
            .file_name()
            .expect("файл из read_dir имеет имя")
            .to_string_lossy();
        zf.start_file(name.as_ref(), opts)
            .map_err(|e| SourceError::Io(std::io::Error::other(e.to_string())))?;
        let mut buf = Vec::new();
        File::open(img)?.read_to_end(&mut buf)?;
        zf.write_all(&buf)?;
    }
    zf.finish()
        .map_err(|e| SourceError::Io(std::io::Error::other(e.to_string())))?;
    Ok(cbz_path.to_path_buf())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_name_replaces_invalid_chars() {
        assert_eq!(safe_name("a<b>c:d\"e/f\\g|h?i*j"), "a_b_c_d_e_f_g_h_i_j");
    }

    #[test]
    fn safe_name_trims_and_collapses() {
        assert_eq!(safe_name("  Том 1.  "), "Том 1");
        assert_eq!(safe_name("a\t b\n c"), "a_ b_ c"); // управляющие → '_'
        assert_eq!(safe_name("a    b"), "a b");
    }

    #[test]
    fn safe_name_empty_is_untitled() {
        assert_eq!(safe_name("..."), "untitled");
        assert_eq!(safe_name(""), "untitled");
    }

    #[test]
    fn safe_name_truncates() {
        assert_eq!(safe_name(&"я".repeat(500)).chars().count(), 150);
    }

    #[test]
    fn cbz_contains_sorted_images_only() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("002.png"), b"png2").unwrap();
        std::fs::write(dir.path().join("001.jpg"), b"jpg1").unwrap();
        std::fs::write(dir.path().join("notes.txt"), b"skip me").unwrap();

        let cbz = dir.path().join("out/ch.cbz");
        make_cbz(dir.path(), &cbz).unwrap();

        let mut archive = zip::ZipArchive::new(File::open(&cbz).unwrap()).unwrap();
        let names: Vec<String> = (0..archive.len())
            .map(|i| archive.by_index(i).unwrap().name().to_string())
            .collect();
        assert_eq!(names, vec!["001.jpg", "002.png"]);
    }
}
