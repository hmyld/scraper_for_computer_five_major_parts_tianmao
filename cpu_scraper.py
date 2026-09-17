import json
import os
import re
import time
import random
from playwright.sync_api import sync_playwright, Page

INPUT_FILE = "dictionary/hardware_base_cpu.json"
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "cpu_result.json")
STATE_FILE = "state.json"
MAX_PER_CHIP = 30
PAGES_PER_CHIP = 2


def load_cpu_list():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    cpu_data = data["cpu_chip"]
    print(f"✅ 成功加载 {len(cpu_data)} 颗CPU")
    return cpu_data


def create_output_folder():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)


def save_results(all_results):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)


def extract_core_keyword(chip_model: str) -> str:
    kw = chip_model.strip()
    prefixes = ['Athlon', '速龙', 'Ryzen', '锐龙', 'Intel', '酷睿', 'Core',
                'Pentium', '奔腾', 'Celeron', '赛扬', 'FX', 'Xeon', '至强',
                'Sempron', '闪龙', 'Opteron', '皓龙', 'AMD', '英特尔']
    for p in prefixes:
        kw = kw.replace(p, '')
    kw = kw.strip()
    parts = kw.split()
    if len(parts) > 1 and re.match(r'^(R[3579]|i[3579]|E[35])$', parts[0], re.I):
        kw = parts[1]
    kw = kw.replace('-', ' ')
    parts = kw.split()
    if len(parts) > 1 and re.match(r'^(R[3579]|i[3579]|E[35])$', parts[0], re.I):
        kw = parts[1]
    return kw.strip()


def extract_items_via_js(page: Page, keyword: str):
    """天猫版CPU提取：优先天猫卡片，兜底a标签通用提取"""
    js_code = r"""
    (keyword) => {
        const results = [];
        const seen = new Set();

        // 天猫商品卡片常见选择器
        const cardSelectors = [
            '.product-iWrap', '.item', '.product', '.J_TItems .item',
            '[data-item-id]', '.item-wrap', '.goods-item'
        ];

        let cards = [];
        for (const sel of cardSelectors) {
            const found = document.querySelectorAll(sel);
            if (found.length > 0) {
                cards = Array.from(found);
                break;
            }
        }

        // 提取单个商品的通用逻辑
        function extractFromCard(card) {
            try {
                const linkEl = card.querySelector('a[href]');
                if (!linkEl) return null;
                const url = linkEl.getAttribute('href') || '';
                if (!url.includes('tmall.com') && !url.includes('taobao.com')) return null;
                if (url.includes('shop.') || url.includes('store.') ||
                    url.includes('/search') || url.includes('/list') ||
                    url.includes('login.')) return null;
                const fullUrl = url.startsWith('//') ? 'https:' + url : url;
                if (seen.has(fullUrl)) return null;
                seen.add(fullUrl);

                let title = linkEl.getAttribute('title') || (linkEl.innerText || '').trim();
                if (!title || title.length < 5) {
                    const titleEl = card.querySelector('.productTitle, .product-title, [class*="title"]');
                    if (titleEl) title = (titleEl.innerText || '').trim();
                }
                if (!title || title.length < 8) return null;

                // 关键词过滤
                if (keyword) {
                    const titleClean = title.replace(/[\s\-]/g, '').toLowerCase();
                    const kwClean = keyword.replace(/[\s\-]/g, '').toLowerCase();
                    if (!titleClean.includes(kwClean)) return null;
                }

                // 混卖过滤
                if (/大全|套餐|套装|板U|组合|全家桶|合集|全系|多型号/.test(title)) return null;

                // 价格
                let price = '';
                const priceEls = card.querySelectorAll('.productPrice, .product-price, [class*="price"], [class*="Price"], em');
                for (const el of priceEls) {
                    const t = (el.innerText || '').trim();
                    const m = t.match(/¥?\s*([\d,]+(?:\.\d+)?)/);
                    if (m) { price = m[1].replace(/,/g, ''); break; }
                }
                if (!price) {
                    const m = (card.innerText || '').match(/¥\s*([\d,]+(?:\.\d+)?)/);
                    if (m) price = m[1].replace(/,/g, '');
                }

                // 店铺
                let shop = '';
                const shopEls = card.querySelectorAll('.productShop-name, .productShop, [class*="shop"], [class*="Shop"], [class*="seller"]');
                for (const el of shopEls) {
                    const t = (el.innerText || '').trim();
                    if (t && t.length < 40 && !t.includes('¥')) { shop = t.replace(/\n/g, ' '); break; }
                }

                // 图片
                let img = '';
                const imgEl = card.querySelector('img');
                if (imgEl) {
                    img = imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || '';
                    if (img.startsWith('//')) img = 'https:' + img;
                }

                const modelCount = (title.match(/[A-Z]?\d{3,4}[A-Z]{0,3}/g) || []).length;
                if (title && price && parseFloat(price) > 0) {
                    return { title, price, shop, url: fullUrl, thumbnail: img, modelCount };
                }
                return null;
            } catch(e) { return null; }
        }

        if (cards.length > 0) {
            // 用卡片提取
            for (const card of cards) {
                const item = extractFromCard(card);
                if (item) results.push(item);
            }
        } else {
            // 兜底：a标签通用提取
            const allLinks = document.querySelectorAll('a[href]');
            for (const a of allLinks) {
                const href = a.getAttribute('href') || '';
                const title = a.getAttribute('title') || (a.innerText || '').trim();
                if (title.length < 8) continue;
                if (!href.includes('tmall.com') && !href.includes('taobao.com')) continue;
                if (href.includes('shop.') || href.includes('store.') ||
                    href.includes('/search') || href.includes('/list') ||
                    href.includes('login.')) continue;

                let card = a;
                for (let i = 0; i < 10; i++) {
                    if (!card.parentElement) break;
                    card = card.parentElement;
                    if ((card.innerText || '').includes('¥')) break;
                }
                const item = extractFromCard(card);
                if (item) results.push(item);
            }
        }
        return results;
    }
    """
    return page.evaluate(js_code, keyword)


def scroll_page_to_load_all(page: Page):
    for i in range(5):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(random.uniform(0.4, 0.8))
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(0.5)


def _check_captcha(page: Page):
    for attempt in range(3):
        try:
            time.sleep(1.0)
            captcha_selectors = [
                '#nc_1_n1z', '#nc_1_wrapper', '#nc_1__scale_text',
                '.nc-container', '.nc_scale', '.nc-lang-cnt',
                '#captcha', '.captcha-container', '.baxia-wrapper',
                '.risk-warning', '.baxia-dialog', '[id*="nc_"]',
                '#login-form', '.login-box',
            ]
            found = False
            for sel in captcha_selectors:
                try:
                    if page.locator(sel).count() > 0:
                        found = True
                        print(f"  🔍 命中验证码选择器: {sel}")
                        break
                except:
                    continue
            if not found:
                try:
                    page_text = page.evaluate("document.body.innerText")
                    if any(kw in page_text for kw in [
                        '滑块', '完成验证', '按住滑块', '拖动到最右边',
                        '安全验证', '人机验证', '拖动下方',
                        '请选择符合描述', '所有图片', '点击提交',
                        '没有新图片', '符合描述的', '验证', 'captcha',
                        '请登录', '登录后查看',
                    ]):
                        found = True
                        print("  🔍 命中验证码/登录文本")
                except:
                    pass
            if found:
                try:
                    page.screenshot(path="debug/cpu_tmall_captcha.png")
                except:
                    pass
                print("\n" + "=" * 60)
                print("⚠️  检测到验证码/登录！请在浏览器手动完成")
                print("   完成后回到终端按 Enter 继续...")
                print("=" * 60)
                input()
                time.sleep(2)
                try:
                    page.reload()
                    time.sleep(2)
                except:
                    pass
                return
        except Exception as e:
            print(f"  验证码检测异常: {e}")


def crawl_tmall_cpu(page: Page, chip_model: str):
    search_word = f"{chip_model} CPU 处理器"
    core_kw = extract_core_keyword(chip_model)
    print(f"\n==== [天猫] {search_word} ====")

    all_items = []
    seen_urls = set()

    for page_num in range(PAGES_PER_CHIP):
        offset = page_num * 60  # 天猫每页约60条
        search_url = f"https://list.tmall.com/search_product.htm?q={search_word}&sort=d&s={offset}"

        try:
            page.goto(search_url, wait_until="domcontentloaded")
            time.sleep(random.uniform(3.0, 4.0))
        except Exception as e:
            print(f"  第{page_num+1}页加载失败: {e}")
            continue

        _check_captcha(page)
        scroll_page_to_load_all(page)
        _check_captcha(page)

        items = extract_items_via_js(page, core_kw)
        print(f"  第{page_num+1}页: {len(items)}条")

        for item in items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_items.append(item)

        if len(all_items) >= MAX_PER_CHIP:
            break

        time.sleep(random.uniform(1.5, 2.5))

    all_items.sort(key=lambda x: x.get("modelCount", 99))
    print(f"✅ 共{len(all_items)}条（去重后），单型号优先排序")

    collected_items = []
    for item in all_items[:MAX_PER_CHIP]:
        product_info = {
            "chip_model": chip_model,
            "title": item["title"],
            "price": item["price"],
            "shop": item["shop"],
            "url": item["url"],
            "thumbnail": item["thumbnail"],
            "source": "tmall",
        }
        collected_items.append(product_info)
        print(f"  -> ¥{item['price']} | {item['title'][:45]}")

    return collected_items


def main():
    create_output_folder()
    cpu_data = load_cpu_list()
    # 测试：先跑前5个
    # cpu_data = cpu_data[:5]
    all_results = []

    crawled_models = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            all_results = existing
            crawled_models = set(d["chip_model"] for d in existing)
            print(f"📂 已有{len(existing)}条，已爬{len(crawled_models)}个CPU，跳过已爬")
        except:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ]
        )
        if os.path.exists(STATE_FILE):
            context = browser.new_context(storage_state=STATE_FILE)
            print("✅ 加载登录状态")
        else:
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.tmall.com")
            input("扫码登录天猫后按Enter...")
            context.storage_state(path=STATE_FILE)

        for idx, cpu_item in enumerate(cpu_data):
            chip_model = cpu_item["chip_model"]
            if chip_model in crawled_models:
                print(f"\n⏭️  {chip_model} 已爬过，跳过")
                continue

            page = context.new_page()
            goods = crawl_tmall_cpu(page, chip_model)
            all_results.extend(goods)
            page.close()

            save_results(all_results)
            print(f"✅ {chip_model}: {len(goods)}条 | 累计{len(all_results)}条 | 已保存")

            time.sleep(random.uniform(3.0, 5.0))

        browser.close()

    print(f"\n✅ 全部完成！共{len(all_results)}条，保存至 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()