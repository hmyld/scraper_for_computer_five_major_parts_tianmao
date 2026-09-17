import json
import os
import re
import time
import random
from playwright.sync_api import sync_playwright, Page

INPUT_FILE = "dictionary/hardware_base_mem.json"
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
    # 天猫搜索词简洁一点，太多限定词反而搜不到
    return f"{mem_type} {speed} {cap_str} {ecc} 内存条".strip()


def detect_kit(title: str) -> tuple:
    title_clean = title.upper().replace("×", "X").replace("＊", "*")
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
    if re.search(r'套条|套装|双通道|双条|两根|2条|二条|4条|四条', title):
        if re.search(r'4条|四条|4根|四根', title):
            return True, 4
        return True, 2
    return False, 1


def extract_capacity_from_title(title: str) -> float:
    title_clean = title.upper()
    m = re.search(r'(\d+)\s*G\s*[*X×]\s*\d+', title_clean)
    if m:
        return float(m.group(1))
    m = re.search(r'\d+\s*[*X×]\s*(\d+)\s*G', title_clean)
    if m:
        return float(m.group(1))
    m = re.search(r'(\d+)\s*G[B]?', title_clean)
    if m:
        return float(m.group(1))
    m = re.search(r'(\d+)\s*M[B]?', title_clean)
    if m:
        return float(m.group(1)) / 1024
    return 0


def is_valid_listing(title: str, target_type: str, target_speed: int, target_cap: float) -> bool:
    title_upper = title.upper()
    ddr_type = target_type.split()[0]
    if ddr_type not in title_upper:
        return False
    if str(target_speed) not in title:
        return False
    cap_str = format_capacity(target_cap)
    cap_gb = cap_str.replace("M", "MB") if "M" in cap_str else cap_str.replace("G", "GB")
    if cap_str not in title_upper and cap_gb not in title_upper:
        return False
    caps = re.findall(r'(\d+)\s*G[B]?', title, re.I)
    if len(set(c.upper().strip() for c in caps)) > 1:
        return False
    speeds = re.findall(r'(\d{3,4})\s*MHz?', title, re.I)
    if len(set(speeds)) > 1:
        return False
    if re.search(r'多容量|多频率|可选|全系列|全系|拍下备注|多种规格|规格齐全|多规格', title):
        return False
    return True


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


def extract_items_via_js(page: Page, keyword: str, ddr_type: str):
    """天猫版：遍历商品卡片提取，兼容天猫DOM结构"""
    speed_kw, cap_kw = keyword.split(" ", 1)
    js_code = r"""
    ({speed_kw, cap_kw, ddr_type}) => {
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

        // 兜底：如果没找到卡片，用a标签通用提取
        if (cards.length === 0) {
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

                const fullUrl = href.startsWith('//') ? 'https:' + href : href;
                if (seen.has(fullUrl)) continue;
                seen.add(fullUrl);

                const titleUpper = title.toUpperCase();
                if (!titleUpper.includes(ddr_type)) continue;
                if (!title.includes(speed_kw)) continue;
                if (!titleUpper.includes(cap_kw) && !titleUpper.includes(cap_kw.replace('G','GB')) && !titleUpper.includes(cap_kw.replace('M','MB'))) continue;

                const capMatches = title.match(/\d+\s*G[B]?/gi);
                if (capMatches) {
                    const uniqueCaps = new Set(capMatches.map(s => s.toUpperCase().replace(/\s/g,'')));
                    if (uniqueCaps.size > 1) continue;
                }
                const speedMatches = title.match(/\d{3,4}\s*MHz?/gi);
                if (speedMatches && new Set(speedMatches).size > 1) continue;
                if (/多容量|多频率|可选|全系列|全系|拍下备注|多种规格|规格齐全|多规格/.test(title)) continue;
                if (/套条|套装|双通道/.test(title)) {
                    if (!/\d+\s*G\s*[*xX×]\s*\d+/.test(title) && !/\d+\s*[*xX×]\s*\d+\s*G/.test(title)) continue;
                }

                let price = '';
                const priceEls = card.querySelectorAll('[class*="price"], [class*="Price"], em');
                for (const el of priceEls) {
                    const t = (el.innerText || '').trim();
                    const m = t.match(/¥?\s*([\d,]+(?:\.\d+)?)/);
                    if (m) { price = m[1].replace(/,/g, ''); break; }
                }
                if (!price) {
                    const m = (card.innerText || '').match(/¥\s*([\d,]+(?:\.\d+)?)/);
                    if (m) price = m[1].replace(/,/g, '');
                }

                let shop = '';
                const shopEls = card.querySelectorAll('[class*="shop"], [class*="Shop"], [class*="seller"], .productShop-name');
                for (const el of shopEls) {
                    const t = (el.innerText || '').trim();
                    if (t && t.length < 40 && !t.includes('¥')) { shop = t.replace(/\n/g, ' '); break; }
                }

                let img = '';
                const imgEl = card.querySelector('img');
                if (imgEl) {
                    img = imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || '';
                    if (img.startsWith('//')) img = 'https:' + img;
                }

                if (title && price && parseFloat(price) > 0) {
                    results.push({ title, price, shop, url: fullUrl, thumbnail: img });
                }
            }
            return results;
        }

        // 用卡片提取
        for (const card of cards) {
            try {
                const linkEl = card.querySelector('a[href]');
                if (!linkEl) continue;
                const url = linkEl.getAttribute('href') || '';
                if (!url.includes('tmall.com') && !url.includes('taobao.com')) continue;
                const fullUrl = url.startsWith('//') ? 'https:' + url : url;
                if (seen.has(fullUrl)) continue;
                seen.add(fullUrl);

                let title = linkEl.getAttribute('title') || (linkEl.innerText || '').trim();
                if (!title || title.length < 5) {
                    const titleEl = card.querySelector('.productTitle, .product-title, [class*="title"]');
                    if (titleEl) title = (titleEl.innerText || '').trim();
                }
                if (!title || title.length < 8) continue;

                const titleUpper = title.toUpperCase();
                if (!titleUpper.includes(ddr_type)) continue;
                if (!title.includes(speed_kw)) continue;
                if (!titleUpper.includes(cap_kw) && !titleUpper.includes(cap_kw.replace('G','GB')) && !titleUpper.includes(cap_kw.replace('M','MB'))) continue;

                const capMatches = title.match(/\d+\s*G[B]?/gi);
                if (capMatches) {
                    const uniqueCaps = new Set(capMatches.map(s => s.toUpperCase().replace(/\s/g,'')));
                    if (uniqueCaps.size > 1) continue;
                }
                const speedMatches = title.match(/\d{3,4}\s*MHz?/gi);
                if (speedMatches && new Set(speedMatches).size > 1) continue;
                if (/多容量|多频率|可选|全系列|全系|拍下备注|多种规格|规格齐全|多规格/.test(title)) continue;
                if (/套条|套装|双通道/.test(title)) {
                    if (!/\d+\s*G\s*[*xX×]\s*\d+/.test(title) && !/\d+\s*[*xX×]\s*\d+\s*G/.test(title)) continue;
                }

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

                let shop = '';
                const shopEls = card.querySelectorAll('.productShop-name, .productShop, [class*="shop"], [class*="Shop"]');
                for (const el of shopEls) {
                    const t = (el.innerText || '').trim();
                    if (t && t.length < 40 && !t.includes('¥')) { shop = t.replace(/\n/g, ' '); break; }
                }

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
    return page.evaluate(js_code, {"speed_kw": speed_kw, "cap_kw": cap_kw, "ddr_type": ddr_type})


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
                    page.screenshot(path="debug/mem_tmall_captcha.png")
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


def crawl_tmall_mem(page: Page, mem_item: dict):
    search_word = build_search_word(mem_item)
    mem_key = build_mem_key(mem_item)
    target_cap = mem_item["capacity_gb"]
    target_type = mem_item["mem_type"]
    target_speed = mem_item["speed_mhz"]
    ddr_type = target_type.split()[0]

    cap_str = format_capacity(target_cap)
    keyword = f"{target_speed} {cap_str}"

    print(f"\n==== [天猫] {search_word} ====")

    all_items = []
    seen_urls = set()

    for page_num in range(PAGES_PER_MEM):
        offset = page_num * 60  # 天猫每页约60条
        # 天猫搜索URL
        search_url = f"https://list.tmall.com/search_product.htm?q={search_word}&sort=d&s={offset}"

        try:
            page.goto(search_url, wait_until="domcontentloaded")
            time.sleep(random.uniform(3.0, 4.0))  # 天猫加载慢一点
        except Exception as e:
            print(f"  第{page_num+1}页加载失败: {e}")
            continue

        _check_captcha(page)
        scroll_page_to_load_all(page)
        _check_captcha(page)

        items = extract_items_via_js(page, keyword, ddr_type)
        print(f"  第{page_num+1}页: {len(items)}条")

        for item in items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_items.append(item)

        if len(all_items) >= MAX_PER_MEM:
            break

        time.sleep(random.uniform(1.5, 2.5))

    print(f"✅ 共{len(all_items)}条（去重后）")

    collected_items = []
    skipped_mixed = 0

    for item in all_items[:MAX_PER_MEM]:
        title = item["title"]

        if not is_valid_listing(title, target_type, target_speed, target_cap):
            skipped_mixed += 1
            continue

        brand = extract_brand(title)
        is_kit, stick_count = detect_kit(title)
        title_cap = extract_capacity_from_title(title)
        total_price = float(item["price"])

        if title_cap <= 0 or abs(title_cap - target_cap) > 0.01:
            skipped_mixed += 1
            continue

        if is_kit and stick_count > 1:
            unit_price = round(total_price / stick_count, 2)
        else:
            unit_price = total_price

        product_info = {
            "mem_key": mem_key,
            "mem_type": target_type,
            "speed_mhz": target_speed,
            "capacity_gb": target_cap,
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
            "source": "tmall",
        }
        collected_items.append(product_info)
        kit_tag = f"[套条{stick_count}根]" if is_kit else "[单根]"
        print(f"  -> {kit_tag} [{brand}] 单根¥{unit_price} | {title[:40]}")

    if skipped_mixed > 0:
        print(f"  🚫 过滤混卖/不匹配: {skipped_mixed}条")

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
            page.goto("https://www.tmall.com")
            input("扫码登录天猫后按Enter...")
            context.storage_state(path=STATE_FILE)

        for idx, mem_item in enumerate(mem_data):
            mem_key = build_mem_key(mem_item)
            if mem_key in crawled_keys:
                print(f"\n⏭️  {mem_key} 已爬过，跳过")
                continue

            page = context.new_page()
            goods = crawl_tmall_mem(page, mem_item)
            all_results.extend(goods)
            page.close()

            save_results(all_results)
            print(f"✅ {mem_key}: {len(goods)}条 | 累计{len(all_results)}条 | 已保存")

            time.sleep(random.uniform(4.0, 6.0))

        browser.close()

    print(f"\n✅ 全部完成！共{len(all_results)}条，保存至 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()