import json
import os
import re
import time
import random
from playwright.sync_api import sync_playwright, Page

INPUT_FILE = "dictionary/hardware_base_storage.json"
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "disk_result.json")
STATE_FILE = "state.json"
MAX_PER_ITEM = 30
PAGES_PER_ITEM = 2

# ========== 存储品牌库 ==========
DISK_BRANDS = {
    "西部数据": ["西部数据", "wd", "Western Digital", "西数", "蓝盘", "黑盘", "红盘", "紫盘", "金盘", "SN570", "SN770", "SN850"],
    "希捷": ["希捷", "seagate", "酷鱼", "酷狼", "酷鹰", "BarraCuda", "IronWolf", "SkyHawk", "FireCuda", "希捷酷鱼"],
    "东芝": ["东芝", "toshiba", "P300", "MG08", "MG09", "DT01", "DT02"],
    "日立": ["日立", "hitachi", "HGST", "昱科"],
    "三星": ["三星", "samsung", "980", "990", "970", "870", "860", "EVO", "PRO", "QVO", "PM9A1", "PM981"],
    "铠侠": ["铠侠", "kioxia", "原东芝", "RC20", "RD20", "SE10", "CD6", "CM6"],
    "致态": ["致态", "zhitai", "长江存储", "TiPlus", "TiPro", "Ti600", "Ti7000", "TiPlus7100"],
    "英睿达": ["英睿达", "crucial", "镁光", "P3", "P5", "P5Plus", "BX500", "MX500", "T500"],
    "金士顿": ["金士顿", "kingston", "NV2", "KC3000", "A400", "UV500", "FURY"],
    "威刚": ["威刚", "adata", "XPG", "S11", "S50", "GAMMIX", "翼龙", "龙耀", "SP580", "SU650"],
    "七彩虹": ["七彩虹", "colorful", "CN600", "CN700", "战戟", "战斧"],
    "影驰": ["影驰", "galaxy", "星曜", "金属大师", "黑将", "擎"],
    "铭瑄": ["铭瑄", "maxsun", "终结者", "电竞之心", "复仇者"],
    "朗科": ["朗科", "netac", "绝影", "超光"],
    "光威": ["光威", "gloway", "弈Pro", "弈系列", "天策", "神武", "骁将"],
    "阿斯加特": ["阿斯加特", "asgard", "弗雷", "洛基", "女武神", "瓦尔基里", "AN2", "AN3"],
    "金百达": ["金百达", "kingbank", "银爵", "黑爵", "刃", "KP230", "KP260"],
    "海康威视": ["海康威视", "hikvision", "C2000", "C3000", "C4000"],
    "大华": ["大华", "dahua", "C900", "C970", "T70"],
    "联想": ["联想", "lenovo", "SL700", "拯救者"],
    "惠普": ["惠普", "hp", "EX900", "EX950", "FX900"],
    "戴尔": ["戴尔", "dell"],
    "闪迪": ["闪迪", "sandisk", "至尊高速", "至尊极速", "Ultra", "Extreme"],
    "英特尔": ["英特尔", "intel", "660P", "670P", "760P", "D3-S4510"],
    "浦科特": ["浦科特", "plextor", "M10P", "M9P", "M8V"],
    "建兴": ["建兴", "liteon", "LITE-ON", "CA1", "CA3", "CV8"],
    "创见": ["创见", "transcend", "MTE", "TS"],
    "宇瞻": ["宇瞻", "apacer", "黑豹", "暗黑", "AS2280"],
    "十铨": ["十铨", "team", "火神", "冥神", "Delta", "T-Force", "暗夜", "MP34"],
    "海盗船": ["海盗船", "corsair", "MP600", "MP510", "Force", "复仇者"],
    "芝奇": ["芝奇", "g.skill", "gskill", "幻锋戟", "皇家戟", "Trident", "Ripjaws"],
    "雷克沙": ["雷克沙", "lexar", "NM620", "NM710", "NM790", "SL500"],
    "爱国者": ["爱国者", "aigo", "P3000", "P5000", "P7000"],
    "台电": ["台电", "teclast", "腾龙", "疾影", "NP900"],
    "群联": ["群联", "phison"],
    "慧荣": ["慧荣", "silicon motion"],
    "联想": ["联想", "lenovo"],
}


def extract_brand(title: str) -> str:
    title_lower = title.lower()
    for brand, keywords in DISK_BRANDS.items():
        for kw in keywords:
            if kw.lower() in title_lower:
                return brand
    return "未知"


def format_capacity(cap_gb: float) -> str:
    """1000GB→1TB, 500GB→500G, 80GB→80G"""
    if cap_gb >= 1000 and cap_gb % 1000 == 0:
        return f"{cap_gb // 1000}TB"
    return f"{int(cap_gb)}G"


def build_storage_key(item: dict) -> str:
    ff = item["form_factor"].replace('"', '').replace(' ', '_').replace('.', '')
    iface = item["interface"].replace(' ', '_')
    pcie = item.get("pcie_version") or "any"
    cap = item["capacity_gb"]
    return f"{ff}_{iface}_pcie{pcie}_{cap}G"


def build_search_word(item: dict) -> str:
    ff = item["form_factor"]
    cap_str = format_capacity(item["capacity_gb"])
    is_ssd = item["is_ssd"]
    pcie = item.get("pcie_version")

    if "3.5" in ff and not is_ssd:
        return f"3.5寸 机械硬盘 {cap_str} SATA 台式机 监控"
    elif "2.5" in ff and not is_ssd:
        return f"2.5寸 笔记本硬盘 {cap_str} SATA"
    elif "2.5" in ff and is_ssd:
        return f"2.5寸 SATA SSD {cap_str} 固态硬盘"
    elif "M.2" in ff and "SATA" in ff:
        return f"M.2 2280 SATA SSD {cap_str} 固态硬盘"
    elif "M.2" in ff and "NVMe" in ff:
        pcie_str = f"PCIe{pcie}" if pcie else ""
        return f"M.2 NVMe {pcie_str} {cap_str} SSD 固态硬盘".strip()
    return f"{ff} {cap_str} 硬盘"


def extract_capacity_from_title(title: str) -> float:
    """从标题提取容量(GB)，兼容1TB/1000G/1T等写法"""
    title_upper = title.upper()
    # TB
    m = re.search(r'(\d+(?:\.\d+)?)\s*TB?', title_upper)
    if m:
        return float(m.group(1)) * 1000
    # GB
    m = re.search(r'(\d+)\s*G[B]?', title_upper)
    if m:
        return float(m.group(1))
    return 0


def is_valid_listing(title: str, target_cap: float) -> bool:
    title_upper = title.upper()
    # 必须含容量
    title_cap = extract_capacity_from_title(title)
    if title_cap <= 0:
        return False
    if abs(title_cap - target_cap) > 1:
        return False
    # 标题出现2种以上容量 → 混卖
    caps_tb = re.findall(r'(\d+(?:\.\d+)?)\s*TB?', title_upper)
    caps_gb = re.findall(r'(\d+)\s*G[B]?', title_upper)
    all_caps = set()
    for c in caps_tb:
        all_caps.add(float(c) * 1000)
    for c in caps_gb:
        all_caps.add(float(c))
    if len(all_caps) > 1:
        return False
    # 混卖关键词
    if re.search(r'多容量|多规格|可选|全系列|全系|拍下备注|多种容量|大容量|套餐|组合', title):
        return False
    return True


def load_storage_list():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    storage_data = data["storage_spec"]
    print(f"✅ 成功加载 {len(storage_data)} 种存储规格")
    return storage_data


def create_output_folder():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)


def save_results(all_results):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)


def extract_items_via_js(page: Page, keyword: str):
    """天猫版存储提取"""
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

                // 关键词过滤（容量）
                if (keyword) {
                    const titleClean = title.replace(/[\s\-]/g, '').toLowerCase();
                    const kwClean = keyword.replace(/[\s\-]/g, '').toLowerCase();
                    if (!titleClean.includes(kwClean)) return null;
                }

                // 混卖过滤
                if (/多容量|多规格|可选|全系列|全系|拍下备注|多种容量|套餐|组合/.test(title)) return null;

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
                    page.screenshot(path="debug/disk_tmall_captcha.png")
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


def crawl_tmall_disk(page: Page, storage_item: dict):
    search_word = build_search_word(storage_item)
    storage_key = build_storage_key(storage_item)
    target_cap = storage_item["capacity_gb"]
    cap_str = format_capacity(target_cap)

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

        items = extract_items_via_js(page, cap_str)
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

        if not is_valid_listing(title, target_cap):
            skipped += 1
            continue

        brand = extract_brand(title)
        product_info = {
            "storage_key": storage_key,
            "form_factor": storage_item["form_factor"],
            "interface": storage_item["interface"],
            "pcie_version": storage_item.get("pcie_version"),
            "capacity_gb": target_cap,
            "is_ssd": storage_item["is_ssd"],
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
    storage_data = load_storage_list()
    # 测试：先跑前5个
    # storage_data = storage_data[:5]
    all_results = []

    crawled_keys = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            all_results = existing
            crawled_keys = set(d["storage_key"] for d in existing)
            print(f"📂 已有{len(existing)}条，已爬{len(crawled_keys)}种规格，跳过已爬")
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

        for idx, storage_item in enumerate(storage_data):
            storage_key = build_storage_key(storage_item)
            if storage_key in crawled_keys:
                print(f"\n⏭️  {storage_key} 已爬过，跳过")
                continue

            page = context.new_page()
            goods = crawl_tmall_disk(page, storage_item)
            all_results.extend(goods)
            page.close()

            save_results(all_results)
            print(f"✅ {storage_key}: {len(goods)}条 | 累计{len(all_results)}条 | 已保存")

            time.sleep(random.uniform(3.0, 5.0))

        browser.close()

    print(f"\n✅ 全部完成！共{len(all_results)}条，保存至 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()