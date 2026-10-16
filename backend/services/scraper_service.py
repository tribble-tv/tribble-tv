import re
import time

REDECANAIS_BASE = "https://redecanais.ph"

CATEGORY_URLS = {
    "homepage": REDECANAIS_BASE + "/",
    "filmes": REDECANAIS_BASE + "/?cat=filmes",
    "series": REDECANAIS_BASE + "/?cat=series",
    "canais": REDECANAIS_BASE + "/?cat=canais",
    "animes": REDECANAIS_BASE + "/?cat=animes",
    "infantil": REDECANAIS_BASE + "/?cat=infantil",
}

_ASSISTIR_RE = re.compile(r'/assistir/([^/?#"\'>\s]+)', re.IGNORECASE)
_CANAL_RE = re.compile(r'[?&]canal=([^&"\'#\s]+)', re.IGNORECASE)


class ScraperError(RuntimeError):
    pass


def _extract_slug(href: str) -> str | None:
    if not href:
        return None
    m = _ASSISTIR_RE.search(href)
    if m:
        return m.group(1)
    m = _CANAL_RE.search(href)
    if m:
        return m.group(1)
    return None


def _build_embed(slug: str) -> str:
    return f"https://redecanaistv.ph/player3/ch.php?canal={slug}"


def _extract_all_from_html(html: str, seen: set, results: list) -> None:
    """Fallback regex: extrai slugs /assistir/<slug> do HTML bruto."""
    slugs = _ASSISTIR_RE.findall(html)
    for slug in slugs:
        if slug in seen:
            continue
        seen.add(slug)
        title = slug.replace("-", " ").title()
        results.append({
            "title": title,
            "embed_url": _build_embed(slug),
            "canal_id": slug,
            "thumb_url": None,
        })


def _collect_links(page, seen: set, results: list) -> int:
    """Coleta links /assistir/ do DOM. Retorna quantidade adicionada."""
    added = 0

    selectors = [
        "div.items-row a[href*='/assistir/']",
        "div.cat-list a[href*='/assistir/']",
        "div#content a[href*='/assistir/']",
        "div.blog a[href*='/assistir/']",
        "article a[href*='/assistir/']",
        "a[href*='/assistir/']",
    ]

    links = []
    for sel in selectors:
        links = page.query_selector_all(sel)
        if links:
            break

    for link in links:
        href = link.get_attribute("href") or ""
        slug = _extract_slug(href)
        if not slug or slug in seen:
            continue
        seen.add(slug)

        title = ""
        for _ in range(4):
            try:
                title_el = link.query_selector(
                    "h2, h3, h4, .article-title, .page-header, "
                    "[class*='title'], [class*='name'], [itemprop='name']"
                )
                if title_el:
                    title = (title_el.inner_text() or "").strip()
                    if title:
                        break
            except Exception:
                pass

        if not title:
            title = (link.inner_text() or "").strip()
        if not title:
            title = slug.replace("-", " ").title()

        thumb = None
        try:
            img = link.query_selector("img")
            if img:
                thumb = (
                    img.get_attribute("src")
                    or img.get_attribute("data-src")
                    or img.get_attribute("data-lazy-src")
                )
        except Exception:
            pass

        results.append({
            "title": title,
            "embed_url": _build_embed(slug),
            "canal_id": slug,
            "thumb_url": thumb,
        })
        added += 1

    return added


def _wait_cloudflare(page, timeout: int = 30) -> bool:
    """Aguarda o Cloudflare challenge resolver. Retorna True se passou."""
    for _ in range(timeout):
        title = page.title().lower()
        if "momento" not in title and "moment" not in title and "cloudflare" not in title:
            return True
        time.sleep(1)
    return False


def scrape_category(category: str, max_pages: int = 5) -> list[dict]:
    """
    Faz scraping do redecanais.ph usando camoufox (Firefox antidetect).
    Contorna o Cloudflare Managed Challenge automaticamente.
    Retorna lista de dicts: {title, embed_url, canal_id, thumb_url}
    """
    try:
        from camoufox.sync_api import Camoufox
    except ImportError:
        raise ScraperError(
            "camoufox não está instalado. "
            "Execute: pip install 'camoufox[geoip]' && python -m camoufox fetch"
        )

    start_url = CATEGORY_URLS.get(category, CATEGORY_URLS["homepage"])
    results: list[dict] = []
    seen: set[str] = set()

    with Camoufox(headless=True, geoip=True, locale="pt-BR") as browser:
        page = browser.new_page()

        current_url = start_url
        page_num = 0

        while page_num < max_pages:
            try:
                page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                break

            passed = _wait_cloudflare(page, timeout=30)
            if not passed:
                raise ScraperError(
                    "Cloudflare não resolveu após 30s. "
                    "Tente novamente em alguns minutos."
                )

            time.sleep(2)

            added = _collect_links(page, seen, results)
            if added == 0:
                _extract_all_from_html(page.content(), seen, results)

            next_url = None
            for next_sel in [
                "a[rel='next']",
                "a.next",
                ".pagination a.next",
                "li.next a",
                "a[aria-label*='próxima']",
                "a[aria-label*='next']",
                ".paginacao a:last-child",
                "a.pagination-next",
            ]:
                el = page.query_selector(next_sel)
                if el:
                    href = el.get_attribute("href") or ""
                    if href and href not in (current_url, "#", ""):
                        next_url = href if href.startswith("http") else REDECANAIS_BASE + href
                        break

            if not next_url or next_url == current_url:
                m = re.search(r'[?&]start=(\d+)', current_url)
                limit_m = re.search(r'[?&]limit=(\d+)', current_url)
                limit = int(limit_m.group(1)) if limit_m else 10
                start = int(m.group(1)) + limit if m else limit
                sep = "&" if "?" in current_url else "?"
                next_url = f"{current_url}{sep}start={start}"

                if not page.query_selector(f"a[href*='start={start}']"):
                    break

            current_url = next_url
            page_num += 1

    return results


def import_results(results: list[dict], overwrite: bool = False) -> dict:
    """
    Persiste os resultados de scraping no banco de dados como vídeos embed.
    Retorna {created: N, skipped: N, updated: N}
    """
    from backend.extensions import db
    from backend.models import Video

    created = skipped = updated = 0

    for item in results:
        embed_url = item.get("embed_url", "").strip()
        title = item.get("title", "").strip()
        if not embed_url or not title:
            skipped += 1
            continue

        existing = Video.query.filter_by(source_url=embed_url, source_type="embed").first()
        if existing:
            if overwrite:
                existing.title = title
                updated += 1
            else:
                skipped += 1
            continue

        video = Video(
            title=title,
            source_url=embed_url,
            source_type="embed",
            external_provider="redecanais",
        )
        db.session.add(video)
        created += 1

    db.session.commit()
    return {"created": created, "skipped": skipped, "updated": updated}
