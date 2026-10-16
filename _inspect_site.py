from playwright.sync_api import sync_playwright
import time, json

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width":1280,"height":900},
        locale="pt-BR",
        extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"},
    )
    page = ctx.new_page()
    page.add_init_script("""
        Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
        window.chrome = {runtime:{}};
        Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
        Object.defineProperty(navigator,'languages',{get:()=>['pt-BR','pt','en-US']});
    """)

    page.goto("https://redecanais.ph/", wait_until="domcontentloaded", timeout=30000)

    # Aguarda Cloudflare resolver (pode levar até 15s)
    for i in range(15):
        title = page.title()
        print(f"  [{i}s] title: {title}", flush=True)
        if "moment" not in title.lower() and "cloudflare" not in title.lower():
            break
        time.sleep(1)

    time.sleep(3)
    print(f"URL final: {page.url}")
    print(f"Titulo final: {page.title()}")

    # Salva HTML bruto para analise
    html = page.content()
    with open("/tmp/_site_dump.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML salvo ({len(html)} bytes)")
    # Imprime trecho relevante
    print("=== HTML SNIPPET ===")
    print(html[:3000])

    result = page.evaluate("""() => {
        const info = {};
        info.title = document.title;
        info.body_class = document.body.className.substring(0, 120);
        info.url = location.href;

        // Links /assistir/
        const links = [...document.querySelectorAll('a[href*="/assistir/"]')];
        info.assistir_count = links.length;
        info.sample_links = links.slice(0, 8).map(a => ({
            href: a.href,
            text: a.innerText.trim().substring(0, 80),
            parent_tag: a.parentElement ? a.parentElement.tagName : null,
            parent_class: a.parentElement ? a.parentElement.className.substring(0, 100) : null,
            gp_tag: a.parentElement && a.parentElement.parentElement ? a.parentElement.parentElement.tagName : null,
            gp_class: a.parentElement && a.parentElement.parentElement ? a.parentElement.parentElement.className.substring(0, 100) : null
        }));

        // Seletores candidatos para cards
        const candidates = [
            "div.items-row", "div.cat-list", "div.blog", "div#content",
            "div.catItemView", "ul.latestnews-items", ".latestnews-item",
            "div.nspWrap", "article", ".item-page", ".blog-items",
            "div.items-leading", "div.item", ".catItem", "div.catItems",
            "div.K2ItemsBlock", "div.newsflash-items", "div#sp-component"
        ];
        info.candidates = {};
        candidates.forEach(sel => {
            info.candidates[sel] = document.querySelectorAll(sel).length;
        });

        // Estrutura do #content
        const content = document.querySelector("#content, #sp-component, main, .site-content");
        info.content_tag = content ? content.tagName : null;
        info.content_id = content ? content.id : null;
        info.content_class = content ? content.className.substring(0, 120) : null;
        info.content_children = content ? [...content.children].slice(0,5).map(c => c.tagName + "." + c.className.substring(0,60)) : [];

        // Paginacao
        const pageLinks = [...document.querySelectorAll("a")].filter(a => /start=|page=|pag=/i.test(a.href || ""));
        info.pagination_samples = pageLinks.slice(0, 5).map(a => ({ href: a.href, text: a.innerText.trim() }));

        // Títulos próximos aos links /assistir/
        if (links.length > 0) {
            const firstLink = links[0];
            const container = firstLink.closest("div, article, li");
            if (container) {
                info.first_card_html = container.innerHTML.substring(0, 500);
            }
        }

        return info;
    }""")

    print(json.dumps(result, indent=2, ensure_ascii=False))
    browser.close()
