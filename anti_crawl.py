"""
PCBuilder 反反爬增强模块
- 浏览器指纹随机化（WebGL/Canvas/Audio/navigator）
- 人类行为模拟（鼠标轨迹/滚动/打字/停留）
- 请求调度（泊松分布间隔/指数退避）
- 反爬检测（验证码/限流/登录失效）
- 搜索流程模拟（首页→搜索框逐字输入）
"""

import time
import random
import math
import re
from typing import Optional, Tuple
from playwright.sync_api import Page, BrowserContext


# ============================================================
# 1. 浏览器指纹注入
# ============================================================

STEALTH_JS = r"""
() => {
    // 1. 隐藏 webdriver 标志
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // 2. 伪装 chrome 对象
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: { isInstalled: false }
    };

    // 3. 伪装 permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );

    // 4. 伪装 plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5]
    });

    // 5. 伪装 languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['zh-CN', 'zh', 'en']
    });

    // 6. Canvas 指纹随机化
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {
        if (type === 'image/png') {
            const ctx = this.getContext('2d');
            const imageData = ctx.getImageData(0, 0, this.width, this.height);
            for (let i = 0; i < imageData.data.length; i += 4) {
                imageData.data[i] += Math.floor(Math.random() * 2);
            }
            ctx.putImageData(imageData, 0, 0);
        }
        return originalToDataURL.apply(this, arguments);
    };

    // 7. WebGL 指纹随机化
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.apply(this, arguments);
    };

    // 8. AudioContext 指纹随机化
    const originalOfflineContext = window.OfflineAudioContext;
    if (originalOfflineContext) {
        const proto = originalOfflineContext.prototype;
        const originalStartRendering = proto.startRendering;
        proto.startRendering = function() {
            return originalStartRendering.apply(this, arguments).then(buffer => {
                const channelData = buffer.getChannelData(0);
                for (let i = 0; i < channelData.length; i++) {
                    channelData[i] += (Math.random() - 0.5) * 0.0000001;
                }
                return buffer;
            });
        };
    }
}
"""


def inject_stealth(page: Page):
    """注入浏览器指纹伪装JS（在每个新页面加载后调用）"""
    try:
        page.add_init_script(STEALTH_JS)
    except Exception:
        pass


# ============================================================
# 2. 人类行为模拟
# ============================================================

def random_pause(min_sec: float = 1.0, max_sec: float = 3.0):
    """随机暂停（人类不会精确等待固定时间）"""
    time.sleep(random.uniform(min_sec, max_sec))


def poisson_pause(avg_sec: float = 2.0, max_sec: float = 8.0):
    """泊松分布暂停（更接近人类请求间隔，大部分短偶尔长）"""
    # 逆变换采样
    u = random.random()
    wait = -avg_sec * math.log(1 - u)
    wait = min(wait, max_sec)
    time.sleep(wait)


def human_scroll(page: Page, direction: str = "down", distance: int = None):
    """人类式滚动：变速、偶尔回滚、分段滚动"""
    if distance is None:
        distance = random.randint(300, 800)

    steps = random.randint(3, 6)
    step_size = distance // steps

    for i in range(steps):
        if direction == "down":
            page.evaluate(f"window.scrollBy(0, {step_size + random.randint(-50, 50)})")
        else:
            page.evaluate(f"window.scrollBy(0, -{step_size + random.randint(-50, 50)})")
        time.sleep(random.uniform(0.1, 0.4))

    # 10%概率回滚一点（人类习惯）
    if random.random() < 0.1:
        rollback = random.randint(50, 150)
        if direction == "down":
            page.evaluate(f"window.scrollBy(0, -{rollback})")
        else:
            page.evaluate(f"window.scrollBy(0, {rollback})")
        time.sleep(random.uniform(0.2, 0.5))


def human_scroll_to_load_all(page: Page, rounds: int = 5):
    """滚动加载全部商品（替代原来的匀速滚动）"""
    for i in range(rounds):
        human_scroll(page, "down", random.randint(400, 900))
        time.sleep(random.uniform(0.3, 0.8))

    # 滚回顶部（人类浏览完会回到顶部看筛选）
    time.sleep(random.uniform(0.5, 1.0))
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(random.uniform(0.3, 0.6))


def human_mouse_move(page: Page, x: int, y: int):
    """贝塞尔曲线鼠标移动（不是直线）"""
    start_x = random.randint(0, 800)
    start_y = random.randint(0, 600)
    cp1x = random.randint(0, 1200)
    cp1y = random.randint(0, 800)
    cp2x = random.randint(0, 1200)
    cp2y = random.randint(0, 800)

    js = f"""
    () => {{
        const startX = {start_x}, startY = {start_y};
        const cp1x = {cp1x}, cp1y = {cp1y};
        const cp2x = {cp2x}, cp2y = {cp2y};
        const endX = {x}, endY = {y};
        for (let t = 0; t <= 1; t += 0.05) {{
            const x = Math.pow(1-t,3)*startX + 3*Math.pow(1-t,2)*t*cp1x
                      + 3*(1-t)*t*t*cp2x + t*t*t*endX;
            const y = Math.pow(1-t,3)*startY + 3*Math.pow(1-t,2)*t*cp1y
                      + 3*(1-t)*t*t*cp2y + t*t*t*endY;
            window.scrollTo(x, y);
        }}
    }}
    """
    try:
        page.mouse.move(x, y, steps=random.randint(10, 25))
    except Exception:
        pass


def human_type(page: Page, selector: str, text: str):
    """人类式打字：逐字输入，随机间隔，偶尔删错重打"""
    try:
        page.click(selector)
        time.sleep(random.uniform(0.2, 0.5))

        for i, char in enumerate(text):
            page.keyboard.type(char, delay=random.randint(30, 120))

            # 5%概率"打错"——删一个字重打
            if random.random() < 0.05 and i > 0:
                page.keyboard.press("Backspace")
                time.sleep(random.uniform(0.1, 0.3))
                page.keyboard.type(char, delay=random.randint(50, 100))

        time.sleep(random.uniform(0.3, 0.8))
    except Exception:
        pass


def human_hover_random_card(page: Page):
    """随机悬停在一个商品卡片上（模拟用户查看）"""
    try:
        cards = page.query_selector_all('[class*="item"], [class*="product"], [class*="card"]')
        if cards:
            card = random.choice(cards[:20])
            box = card.bounding_box()
            if box:
                page.mouse.move(
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                    steps=random.randint(8, 20)
                )
                time.sleep(random.uniform(0.5, 1.5))
    except Exception:
        pass


# ============================================================
# 3. 搜索流程模拟（不直接跳URL，走首页→搜索框）
# ============================================================

def human_search(page: Page, keyword: str, base_url: str = "https://www.tmall.com"):
    """人类式搜索：先打开首页，在搜索框逐字输入，点搜索按钮"""
    try:
        page.goto(base_url, wait_until="domcontentloaded")
        time.sleep(random.uniform(2.0, 4.0))

        # 找搜索框
        search_selectors = [
            'input[name="q"]', '#mq', '.search-input input',
            'input[placeholder*="搜索"]', '#key',
        ]
        search_input = None
        for sel in search_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    search_input = el
                    break
            except Exception:
                continue

        if search_input:
            human_type(page, search_selectors[search_selectors.index(
                next(s for s in search_selectors if page.query_selector(s))
            )], keyword)

            # 点搜索按钮
            btn_selectors = [
                'button[type="submit"]', '.search-btn', '#search-btn',
                'button[class*="search"]', '.btn-search',
            ]
            for btn_sel in btn_selectors:
                try:
                    btn = page.query_selector(btn_sel)
                    if btn:
                        btn.click()
                        break
                except Exception:
                    continue
            else:
                # 没找到按钮就按回车
                page.keyboard.press("Enter")
        else:
            # 找不到搜索框就直接URL跳转（兜底）
            search_url = f"https://list.tmall.com/search_product.htm?q={keyword}&sort=d"
            page.goto(search_url, wait_until="domcontentloaded")

        time.sleep(random.uniform(3.0, 5.0))
        return True
    except Exception as e:
        # 失败兜底：直接URL
        search_url = f"https://list.tmall.com/search_product.htm?q={keyword}&sort=d"
        page.goto(search_url, wait_until="domcontentloaded")
        time.sleep(random.uniform(2.0, 3.0))
        return False


# ============================================================
# 4. 反爬检测与退避
# ============================================================

def detect_anti_bot(page: Page) -> Tuple[bool, str]:
    """检测是否触发反爬，返回(是否触发, 类型)"""
    try:
        page_text = page.evaluate("document.body.innerText") or ""
    except Exception:
        page_text = ""

    # 验证码
    captcha_keywords = ['滑块', '完成验证', '按住滑块', '拖动到最右边',
                        '安全验证', '人机验证', '拖动下方', 'captcha',
                        '请选择符合描述', '所有图片', '点击提交', '没有新图片']
    if any(kw in page_text for kw in captcha_keywords):
        return True, "captcha"

    # 限流
    rate_limit_keywords = ['访问太频繁', '稍后重试', '操作频繁', '请求过于频繁',
                           '系统繁忙', '请稍后再试', 'rate limit']
    if any(kw in page_text for kw in rate_limit_keywords):
        return True, "rate_limit"

    # 登录失效
    login_keywords = ['请登录', '登录后查看', '扫码登录', '账号登录', 'login']
    if any(kw in page_text for kw in login_keywords):
        # 检查是否真的没登录（有登录按钮且没有用户信息）
        try:
            if page.query_selector('.login-btn, #login, [class*="login"]'):
                return True, "login_expired"
        except Exception:
            pass

    # 验证码选择器
    captcha_selectors = ['#nc_1_n1z', '#nc_1_wrapper', '.nc-container',
                         '.baxia-wrapper', '.baxia-dialog', '#captcha',
                         '.captcha-container', '[id*="nc_"]']
    for sel in captcha_selectors:
        try:
            if page.locator(sel).count() > 0:
                return True, "captcha"
        except Exception:
            continue

    return False, ""


def exponential_backoff(attempt: int, base: float = 30.0, max_wait: float = 600.0):
    """指数退避：第1次等30秒，第2次等60秒，第3次等120秒..."""
    wait = min(base * (2 ** attempt), max_wait)
    wait += random.uniform(0, wait * 0.3)  # 加随机抖动
    print(f"  ⏳ 指数退避：等待 {wait:.0f} 秒后重试...")
    time.sleep(wait)


# ============================================================
# 5. 页面停留模拟（每个搜索结果页停留8-15秒）
# ============================================================

def human_page_stay(page: Page, min_sec: float = 8.0, max_sec: float = 15.0):
    """在搜索结果页模拟人类停留：滚动+悬停+偶尔返回"""
    stay_time = random.uniform(min_sec, max_sec)
    start = time.time()

    actions = 0
    while time.time() - start < stay_time:
        # 随机选择动作
        action = random.random()
        if action < 0.4:
            human_scroll(page, "down", random.randint(200, 600))
        elif action < 0.6:
            human_scroll(page, "up", random.randint(100, 300))
        elif action < 0.8:
            human_hover_random_card(page)
        else:
            time.sleep(random.uniform(1.0, 3.0))
        actions += 1

    # 滚回顶部
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(random.uniform(0.3, 0.6))


# ============================================================
# 6. 浏览器上下文配置（随机视口+UA）
# ============================================================

def get_random_viewport() -> dict:
    """随机视口大小（主流分辨率）"""
    viewports = [
        {"width": 1920, "height": 1080},
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
        {"width": 1536, "height": 864},
        {"width": 1280, "height": 720},
        {"width": 1600, "height": 900},
    ]
    return random.choice(viewports)


def get_random_ua() -> str:
    """随机User-Agent"""
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    ]
    return random.choice(uas)


def create_human_context(browser, state_file: str = None):
    """创建人类特征的浏览器上下文（随机UA+视口+时区+语言）"""
    context_kwargs = {
        "user_agent": get_random_ua(),
        "viewport": get_random_viewport(),
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "extra_http_headers": {
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        }
    }
    if state_file and __import__("os").path.exists(state_file):
        context_kwargs["storage_state"] = state_file

    context = browser.new_context(**context_kwargs)
    return context