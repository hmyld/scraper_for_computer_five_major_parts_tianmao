import json
import os
import re
import time
import random
from playwright.sync_api import sync_playwright, Page

INPUT_FILE = "dictionary/hardware_base_mb.json"
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "mb_result.json")
STATE_FILE = "state.json"
MAX_PER_ITEM = 30
PAGES_PER_ITEM = 2

# ========== 主板品牌库 ==========
MB_BRANDS = {
    "华硕": ["华硕", "asus", "ROG", "猛禽", "TUF", "DUAL", "巨齿鲨", "PRIME", "大师", "吹雪", "M14H", "M15H"],
    "微星": ["微星", "msi", "魔龙", "万图师", "超龙", "MAG", "MPG", "MEG", "Bazooka", "MORTAR", "迫击炮", "战斧", "EDGE", "刀锋", "ACE", "战神", "UNIFY", "暗影"],
    "技嘉": ["技嘉", "gigabyte", "AORUS", "大雕", "小雕", "魔鹰", "雪鹰", "猎鹰", "GAMING", "AERO", "VISION", "设计师", "UD", "DS3H", "B550M", "ELITE"],
    "七彩虹": ["七彩虹", "colorful", "战斧", "火神", "水神", "iGame", "AD", "Ultra", "CVN", "巡洋舰", "战列舰", "航母"],
    "影驰": ["影驰", "galaxy", "galax", "星曜", "金属大师", "黑将", "骁将", "HOF", "名人堂"],
    "铭瑄": ["铭瑄", "maxsun", "终结者", "电竞之心", "瑷珈", "风", "BigMac", "挑战者", "MS-挑战者"],
    "映泰": ["映泰", "biostar", "RACING", "电竞", "HI-FI", "T-Series", "B550MH", "TB"],
    "华擎": ["华擎", "asrock", "幻影", "钢铁传奇", "挑战者", "Taichi", "Phantom", "钢铁", "Steel", "Pro4", "M-ITX", "ABM", "B550M"],
    "昂达": ["昂达", "onda", "神盾", "典范", "滚珠", "A520", "B550"],
    "梅捷": ["梅捷", "soyo", "狂龙", "焱龙", "战龙", "SY-"],
    "精英": ["精英", "ECS"],
    "双敏": ["双敏", "unika"],
    "斯巴达克": ["斯巴达克", "spark"],
    "富士康": ["富士康", "foxconn"],
    "捷波": ["捷波", "jetway"],
    "磐正": ["磐正", "epox", "supox"],
    "超微": ["超微", "supermicro", "X11", "X12", "X13", "H11", "H12", "H13"],
    "永擎": ["永擎", "asrock rack", "ASRock Rack", "EP2C", "X570D4U"],
    "泰安": ["泰安", "tyan", "S8030", "S8253"],
    "英特尔": ["英特尔", "intel", "DQ57", "DH67", "DB75", "BOXDH"],
    "戴尔": ["戴尔", "dell"],
    "惠普": ["惠普", "hp"],
    "联想": ["联想", "lenovo"],
    "盈通": ["盈通", "yeston", "花嫁", "樱瞳"],
    "蓝宝": ["蓝宝", "sapphire", "纯黑", "铂爵"],
    "讯景": ["讯景", "xfx"],
    "撼讯": ["撼讯", "powercolor"],
    "瀚铠": ["瀚铠", "合金"],
    "电竞叛客": ["电竞叛客", "axgaming"],
    "翔升": ["翔升", "asl"],
    "小影霸": ["小影霸", "hasee", "神舟"],
    "镭风": ["镭风", "colorfire"],
    "致铭": ["致铭", "cthimm"],
    "冠盟": ["冠盟", "gamen"],
    "顶星": ["顶星", "topstar"],
    "杰微": ["杰微", "jwele"],
    "科脑": ["科脑", "koloe"],
}


def extract_brand(title: str) -> str:
    title_lower = title.lower()
    for brand, keywords in MB_BRANDS.items():
        for kw in keywords:
            if kw.lower() in title_lower:
                return brand
    return "未知"


def build_mb_key(item: dict) -> str:
    return f"{item['chipset']}_{item['socket']}"


def build_search_word(item: dict) -> str:
    chipset = item["chipset"]
    socket = item["socket"]
    # 老型号加"拆机"，新型号直接搜
    old_chipsets = {"B75", "Z77", "B85", "Z87", "970", "990FX", "A68H", "A78M", "A88X",
                    "B350", "X370", "A320", "B450", "X470", "H310", "B360", "H370", "Z370",
                    "B365", "Z390", "H410", "H470", "B460", "Z490", "X299", "B75", "Z77"}
    if chipset in old_chipsets:
        return f"{chipset} 主板 {socket} 拆机 二手"
    return f"{chipset} 主板 {socket}"


def is_valid_listing(title: str, target_chipset: str) -> bool:
    title_upper = title.upper()
    # 必须含芯片组名称
    if target_chipset.upper() not in title_upper:
        return False
    # 必须含"主板"或相关词
    if not re.search(r'主板|mainboard|motherboard|母板', title, re.I):
        return False
    # 板U套装跳过
    if re.search(r'板U|套装|CPU.*主板|主板.*CPU|组合|套餐', title):
        return False
    # 标题出现2种以上芯片组 → 混卖
    chipset_pattern = r'\b([ABHZX]\d{2,3}[A-Z]?)\b'
    chipsets_found = re.findall(chipset_pattern, title_upper)
    if len(set(chipsets_found)) > 1:
        return False
    # 混卖关键词
    if re.search(r'多芯片组|多型号|可选|全系列|全系|拍下备注|多种规格', title):
        return False
    return True


def load_mb_list():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    mb_data = data["mb_chipset"]
    print(f"✅ 成功加载 {len(mb_data)} 种主板芯片组")
    return mb_data


def create_output_folder():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)


def save_results(all_results):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)


def extract_items_via_js(page: Page, keyword: str):
    """天猫版主板提取"""
    js_code = r"""
    (keyword) => {
        const results = [];
        const seen = new Set();

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

                // 关键词过滤（芯片组名称）
                if (keyword) {
                    const titleClean = title.replace(/[\s\-]/g, '').toLowerCase();
                    const kwClean = keyword.replace(/[\s\-]/g, '').toLowerCase();
                    if (!titleClean.includes(kwClean)) return null;
                }

                // 混卖过滤
                if (/板U|套装|CPU.*主板|主板.*CPU|组合|套餐|多芯片组|多型号|可选|全系列|全系|拍下备注/.test(title)) return null;

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

                if (title && price && parseFloat(price) > 0) {
                    return { title, price, shop, url: fullUrl, thumbnail: img };
                }
                return null;
            } catch(e) { return null; }
        }

        if (cards.length > 0) {
            for (const card of cards) {
                const item = extractFromCard(card);
                if (item) results.push(item);
            }
        } else {
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
                except:
                    pass
            if found:
                try:
                    page.screenshot(path="debug/mb_tmall_captcha.png")
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


def crawl_tmall_mb(page: Page, mb_item: dict):
    search_word = build_search_word(mb_item)
    mb_key = build_mb_key(mb_item)
    chipset = mb_item["chipset"]

    print(f"\n==== [天猫] {search_word} ====")

    all_items = []
    seen_urls = set()

    for page_num in range(PAGES_PER_ITEM):
        offset = page_num * 60
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

        items = extract_items_via_js(page, chipset)
        print(f"  第{page_num+1}页: {len(items)}条")

        for item in items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_items.append(item)

        if len(all_items) >= MAX_PER_ITEM:
            break

        time.sleep(random.uniform(1.5, 2.5))

    print(f"✅ 共{len(all_items)}条（去重后）")

    collected_items = []
    skipped = 0
    for item in all_items[:MAX_PER_ITEM]:
        title = item["title"]

        if not is_valid_listing(title, chipset):
            skipped += 1
            continue

        brand = extract_brand(title)
        product_info = {
            "mb_key": mb_key,
            "chipset": chipset,
            "socket": mb_item["socket"],
            "mem_type": mb_item["mem_type"],
            "pcie_ver": mb_item["pcie_ver"],
            "has_overclock": mb_item["has_overclock"],
            "brand": brand,
            "title": title,
            "price": item["price"],
            "shop": item["shop"],
            "url": item["url"],
            "thumbnail": item["thumbnail"],
            "source": "tmall",
        }
        collected_items.append(product_info)
        print(f"  -> [{brand}] ¥{item['price']} | {title[:45]}")

    if skipped > 0:
        print(f"  🚫 过滤混卖/不匹配: {skipped}条")

    return collected_items


def main():
    create_output_folder()
    mb_data = load_mb_list()
    # 测试：先跑前5个
    # mb_data = mb_data[:5]
    all_results = []

    crawled_keys = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            all_results = existing
            crawled_keys = set(d["mb_key"] for d in existing)
            print(f"📂 已有{len(existing)}条，已爬{len(crawled_keys)}种芯片组，跳过已爬")
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

        for idx, mb_item in enumerate(mb_data):
            mb_key = build_mb_key(mb_item)
            if mb_key in crawled_keys:
                print(f"\n⏭️  {mb_key} 已爬过，跳过")
                continue

            page = context.new_page()
            goods = crawl_tmall_mb(page, mb_item)
            all_results.extend(goods)
            page.close()

            save_results(all_results)
            print(f"✅ {mb_key}: {len(goods)}条 | 累计{len(all_results)}条 | 已保存")

            time.sleep(random.uniform(3.0, 5.0))

        browser.close()

    print(f"\n✅ 全部完成！共{len(all_results)}条，保存至 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()