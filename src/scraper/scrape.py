"""
src/scraper/scrape.py
Скрапинг liturgical texts с azbyka.ru (ЦСЯ и греческий).
Один класс, оба языка — URL-структура идентична.
"""
import httpx
import time
import pathlib
import logging
import argparse
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

load_dotenv()
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE = os.getenv("AZBYKA_BASE_URL", "https://azbyka.ru")
DELAY = float(os.getenv("SCRAPER_DELAY_SEC", "1.5"))

BOOKS: dict[str, tuple[str, str, range | None]] = {
    # key: (lang, url_pattern, pages)
    # pages=None → автоопределение по 404
    "oktoih_cu":  ("cu",  "/otechnik/Pravoslavnoe_Bogosluzhenie/oktoih/{n}",                   range(1, 35)),
    "oktoih_grc": ("grc", "/otechnik/greek/oktoih-na-grecheskom-jazyke/{n}",                   range(1, 20)),
    "mineja_jan_cu":  ("cu",  "/otechnik/Pravoslavnoe_Bogosluzhenie/mineya-yanvar/{n}",         range(1, 50)),
    "mineja_jan_grc": ("grc", "/otechnik/greek/mineja-yanvar-na-grecheskom-jazyke/{n}",         range(1, 50)),
    "mineja_feb_cu":  ("cu",  "/otechnik/Pravoslavnoe_Bogosluzhenie/mineya-fevral/{n}",         range(1, 50)),
    "mineja_feb_grc": ("grc", "/otechnik/greek/mineja-fevral-na-grecheskom-jazyke/{n}",         range(1, 50)),
    "triodion_cu":    ("cu",  "/otechnik/Pravoslavnoe_Bogosluzhenie/triod-postnaya/{n}",        range(1, 80)),
    "pentecostarion_cu": ("cu", "/otechnik/Pravoslavnoe_Bogosluzhenie/triod-tsvetnaya/{n}",     range(1, 60)),
}

CONTENT_SELECTORS = [
    ".book-body-content",
    ".book-content",
    "article.book",
    ".otechnik-content",
    "div[itemprop='articleBody']",
]


def extract_content(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for sel in CONTENT_SELECTORS:
        node = soup.select_one(sel)
        if node:
            return node.get_text("\n", strip=True)
    # Последний резерв — весь body
    body = soup.find("body")
    return body.get_text("\n", strip=True) if body else None


def scrape_book(book_key: str, out_dir: pathlib.Path, force: bool = False):
    if book_key not in BOOKS:
        raise ValueError(f"Unknown book key: {book_key}. Available: {list(BOOKS)}")

    lang, pattern, pages = BOOKS[book_key]
    book_out = out_dir / book_key
    book_out.mkdir(parents=True, exist_ok=True)

    log.info(f"Scraping {book_key} ({lang}) → {book_out}")

    with httpx.Client(timeout=20, follow_redirects=True,
                      headers={"User-Agent": "HymnographyResearch/1.0 (academic)"}) as client:
        for n in pages:
            out_file = book_out / f"{n:04d}.txt"
            if out_file.exists() and not force:
                log.debug(f"  Skip {n} (cached)")
                continue

            url = BASE + pattern.format(n=n)
            try:
                r = client.get(url)
            except httpx.RequestError as e:
                log.warning(f"  Request error on page {n}: {e}")
                time.sleep(DELAY * 2)
                continue

            if r.status_code == 404:
                log.info(f"  Page {n}: 404, stopping")
                break
            if r.status_code != 200:
                log.warning(f"  Page {n}: HTTP {r.status_code}")
                time.sleep(DELAY)
                continue

            text = extract_content(r.text)
            if not text or len(text) < 100:
                log.warning(f"  Page {n}: no content extracted")
                time.sleep(DELAY)
                continue

            out_file.write_text(text, encoding="utf-8")
            log.info(f"  Page {n}: {len(text):,} chars → {out_file.name}")
            time.sleep(DELAY)

    log.info(f"Done: {book_key}")


def main():
    parser = argparse.ArgumentParser(description="Scrape azbyka.ru liturgical texts")
    parser.add_argument("--book", action="append", required=True,
                        help="Book key(s) to scrape. Repeat for multiple.")
    parser.add_argument("--out", default="data/raw", help="Output directory")
    parser.add_argument("--force", action="store_true", help="Re-scrape even if cached")
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out)
    for book_key in args.book:
        scrape_book(book_key, out_dir, force=args.force)


if __name__ == "__main__":
    main()
