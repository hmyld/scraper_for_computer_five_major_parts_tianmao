import json
import os
import re
import time
import random
from playwright.sync_api import sync_playwright, Page

INPUT_FILE = "dictionary/hardware_base_ram.json"
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "mem_result.json")
STATE_FILE = "state.json"
MAX_PER_MEM = 30
PAGES_PER_MEM = 2

# ========== 内存品牌库 ==========
MEM_BRANDS = {
    "金士顿": ["金士顿", "kingston", "FURY", "骇客", "Beast", "野兽", "Impact"],
    "威刚": ["威刚", "adata", "XPG", "万紫千红", "游戏威龙", "龙耀", "Dazzle"],
    "芝奇": ["芝奇", "g.skill", "gskill", "幻锋戟", "皇家戟", "焰光戟", "Trident", "Ripjaws", "钢牙"],
    "海盗船": ["海盗船", "corsair", "复仇者", "Vengeance", "统治者", "Dominator", "LPX"],
    "英睿达": ["英睿达", "crucial", "铂胜", "Ballistix", "Pro"],
    "三星": ["三星", "samsung", "原厂"],
    "海力士": ["海力士", "hynix", "SK海力士", "skhynix"],
    "镁光": ["镁光", "micron", "Crucial"],
    "十铨": ["十铨", "team", "火神", "冥神", "Delta", "T-Force", "暗夜"],
    "光威": ["光威", "gloway", "弈Pro", "天策", "弈系列", "神武"],
    "阿斯加特": ["阿斯加特", "asgard", "弗雷", "洛基", "女武神", "瓦尔基里"],
    "科赋": ["科赋", "klevv", "炎龙", "雷霆", "Bolt", "CRAS"],
    "宇瞻": ["宇瞻", "apacer", "黑豹", "暗黑", "NOX"],
    "金泰克": ["金泰克", "kimtigo", "贪狼星", "速虎"],
    "影驰": ["影驰", "galaxy", "星曜", "金属大师", "GAMER"],
    "七彩虹": ["七彩虹", "colorful", "战斧", "火神", "iGame"],
    "铭瑄": ["铭瑄", "maxsun", "终结者"],
    "朗科": ["朗科", "netac", "绝影"],
    "金百达": ["金百达", "kingbank", "银爵", "黑爵", "刃"],
    "联想": ["联想", "lenovo", "记忆科技", "ramaxel"],
    "戴尔": ["戴尔", "dell"],
    "惠普": ["惠普", "hp"],
    "南亚": ["南亚", "nanya"],
    "尔必达": ["尔必达", "elpida"],
    "奇梦达": ["奇梦达", "qimonda"],
}


def extract_brand(title: str) -> str:
    title_lower = title.lower()
    for brand, keywords in MEM_BRANDS.items():
        for kw in keywords:
            if kw.lower() in title_lower:
                return brand
    return "未知"


def format_capacity(cap_gb: float) -> str:
    """0.25→256M, 0.5→512M, 1→1G, 16→16G"""
    if cap_gb < 1:
        return f"{int(cap_gb * 1024)}M"
    return f"{int(cap_gb)}G"


def build_mem_key(mem_item: dict) -> str:
    return f"{mem_item['mem_type']}_{mem_item['speed_mhz']}_{mem_item['capacity_gb']}G"


def build_search_word(mem_item: dict) -> str:
    mem_type = mem_item["mem_type"]
    speed = mem_item["speed_mhz"]
    cap_str = format_capacity(mem_item["capacity_gb"])
    ecc = "ECC" if mem_item["is_ecc"] else ""
    # 老内存(DDR1/DDR2)加"台式机"过滤笔记本
    if mem_type.startswith("DDR1") or mem_type.startswith("DDR2"):
        return f"{mem_type} {speed} {cap_str} {ecc} 内存条 台式机 拆机".strip()
    return f"{mem_type} {speed} {cap_str} {ecc} 内存条 台式机".strip()


def detect_kit(title: str) -> tuple:
    """
    检测是否套条，返回 (is_kit, stick_count)
    如 16G*2 → (True, 2), 8Gx4 → (True, 4)
    """
    title_clean = title.upper().replace("×", "X").replace("＊", "*")
    # 匹配 16G*2 / 8GX2 / 2*16G / 4X8G
    m = re.search(r'(\d+)\s*G\s*[*X]\s*(\d+)', title_clean)
    if m:
        cap, cnt = int(m.group(1)), int(m.group(2))
        if cnt <= 8 and cap > 0:
            return True, cnt
    m = re.search(r'(\d+)\s*[*X]\s*(\d+)\s*G', title_clean)
    if m:
        cnt, cap = int(m.group(1)), int(m.group(2))
        if cnt <= 8 and cap > 0:
            return True, cnt
    # 关键词检测
    if re.search(r'套条|套装|双通道|双条|两根|2条|二条|4条|四条', title):
        if re.search(r'4条|四条|4根|四根', title):
            return True, 4
        return True, 2
    return False, 1


def extract_capacity_from_title(title: str) -> float:
    """从标题提取单根容量(GB)，套条取单根"""
    title_clean = title.upper()
    # 先匹配套条 16G*2 → 单根16G
    m = re.search(r'(\d+)\s*G\s*[*X×]\s*\d+', title_clean)
    if m:
        return float(m.group(1))
    m = re.search(r'\d+\s*[*X×]\s*(\d+)\s*G', title_clean)
    if m:
        return float(m.group(1))
    # 普通 16G / 16GB
    m = re.search(r'(\d+)\s*G[B]?', title_clean)
    if m:
        return float(m.group(1))
    # MB
    m = re.search(r'(\d+)\s*M[B]?', title_clean)
    if m:
        return float(m.group(1)) / 1024
    return 0


def load_mem_list():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    mem_data = data["mem_spec"]
    print(f"✅ 成功加载 {len(mem_data)} 种内存规格")
    return mem_data


def create_output_folder():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)


def save_results(all_results):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)


def extract_items_via_js(page: Page, keyword: str):
    js_code = r"""
    (keyword) => {
        const results = [];
        const seen = new Set();
        const allLinks = document.querySelectorAll('a[href]');
        const productLinks = [];
        for (const a of allLinks) {
            const href = a.getAttribute('href') || '';
            const title = a.getAttribute('title') || (a.innerText || '').trim();
            if (title.length < 8) continue;
            if (!href.includes('taobao.com') && !href.includes('tmall.com')) continue;
            if (href.includes('shop.taobao.com') || href.includes('store.taobao.com') ||
                href.includes('/search') || href.includes('/list') ||
                href.includes('tmall.com/shop') || href.includes('login.taobao.com')) continue;
            productLinks.push(a);
        }
        for (const link of productLinks) {
            try {
                let card = link;
                for (let i = 0; i < 10; i++) {
                    if (!card.parentElement) break;
                    card = card.parentElement;
                    if ((card.innerText || '').includes('¥')) break;
                }
                const url = link.getAttribute('href');
                const fullUrl = url.startsWith('//') ? 'https:' + url : url;
                if (seen.has(fullUrl)) continue;
                seen.add(fullUrl);
                let title = link.getAttribute('title');
                if (!title || title.length < 5) title = (link.innerText || '').trim();
                if (!title || title.length < 8) continue;

                // 关键词过滤（型号+频率）
                if (keyword) {
                    const titleClean = title.replace(/[\s\-]/g, '').toLowerCase();
                    const kwClean = keyword.replace(/[\s\-]/g, '').toLowerCase();
                    if (!titleClean.includes(kwClean)) continue;
                }

                // 混卖过滤
                if (/大全|套餐|套装|板U|组合|全家桶|合集|全系|多型号|CPU/.test(title)) continue;

                // 价格
                let price = '';
                const priceEls = card.querySelectorAll('[class*="price"], [class*="Price"]');
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
                const shopEls = card.querySelectorAll('[class*="shop"], [class*="Shop"], [class*="seller"]');
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
                    results.push({ title, price, shop, url: fullUrl, thumbnail: img });
                }
            } catch(e) { continue; }
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
                    ]):
                        found = True
                except:
                    pass
            if found:
                try:
                    page.screenshot(path="debug/mem_captcha.png")
                except:
                    pass
                print("\n" + "=" * 60)
                print("⚠️  检测到验证码！请在浏览器手动完成验证")
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


def crawl_taobao_mem(page: Page, mem_item: dict):
    search_word = build_search_word(mem_item)
    mem_key = build_mem_key(mem_item)
    target_cap = mem_item["capacity_gb"]
    print(f"\n==== {search_word} ====")

    all_items = []
    seen_urls = set()

    for page_num in range(PAGES_PER_MEM):
        offset = page_num * 44
        search_url = f"https://s.taobao.com/search?q={search_word}&sort=sale-desc&s={offset}"

        try:
            page.goto(search_url, wait_until="domcontentloaded")
            time.sleep(random.uniform(2.0, 3.0))
        except Exception as e:
            print(f"  第{page_num+1}页加载失败: {e}")
            continue

        _check_captcha(page)
        scroll_page_to_load_all(page)
        _check_captcha(page)

        # 关键词用频率（如3200），避免DDR4重复
        keyword = str(mem_item["speed_mhz"])
        items = extract_items_via_js(page, keyword)
        print(f"  第{page_num+1}页: {len(items)}条")

        for item in items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_items.append(item)

        if len(all_items) >= MAX_PER_MEM:
            break

        time.sleep(random.uniform(1.0, 2.0))

    print(f"✅ 共{len(all_items)}条（去重后）")

    collected_items = []
    for item in all_items[:MAX_PER_MEM]:
        title = item["title"]
        brand = extract_brand(title)
        is_kit, stick_count = detect_kit(title)
        title_cap = extract_capacity_from_title(title)
        total_price = float(item["price"])

        # 套条 → 计算单根价格
        if is_kit and stick_count > 1:
            unit_price = round(total_price / stick_count, 2)
        else:
            unit_price = total_price

        # 容量不匹配的跳过（搜16G出来8G的）
        if title_cap > 0 and abs(title_cap - target_cap) > 0.01:
            # 但套条总容量可能是2倍，单根容量应该匹配
            continue

        product_info = {
            "mem_key": mem_key,
            "mem_type": mem_item["mem_type"],
            "speed_mhz": mem_item["speed_mhz"],
            "capacity_gb": mem_item["capacity_gb"],
            "is_ecc": mem_item["is_ecc"],
            "brand": brand,
            "title": title,
            "total_price": total_price,
            "unit_price": unit_price,
            "is_kit": is_kit,
            "stick_count": stick_count,
            "shop": item["shop"],
            "url": item["url"],
            "thumbnail": item["thumbnail"],
        }
        collected_items.append(product_info)
        kit_tag = f"[套条{stick_count}根]" if is_kit else "[单根]"
        print(f"  -> {kit_tag} [{brand}] 单根¥{unit_price} | {title[:40]}")

    return collected_items


def main():
    create_output_folder()
    mem_data = load_mem_list()
    # 测试：先跑前5个
    # mem_data = mem_data[:5]
    all_results = []

    crawled_keys = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            all_results = existing
            crawled_keys = set(d["mem_key"] for d in existing)
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
            page.goto("https://taobao.com")
            input("扫码登录后按Enter...")
            context.storage_state(path=STATE_FILE)

        for idx, mem_item in enumerate(mem_data):
            mem_key = build_mem_key(mem_item)
            if mem_key in crawled_keys:
                print(f"\n⏭️  {mem_key} 已爬过，跳过")
                continue

            page = context.new_page()
            goods = crawl_taobao_mem(page, mem_item)
            all_results.extend(goods)
            page.close()

            save_results(all_results)
            print(f"✅ {mem_key}: {len(goods)}条 | 累计{len(all_results)}条 | 已保存")

            time.sleep(random.uniform(3.0, 5.0))

        browser.close()

    print(f"\n✅ 全部完成！共{len(all_results)}条，保存至 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()