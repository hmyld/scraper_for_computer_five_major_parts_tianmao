"""
PCBuilder 五大件价格采集总调度器
- 并行爬取 CPU/GPU/内存/硬盘/主板（天猫版）
- 错峰启动 + 随机延迟 反爬
- 每个品类爬完自动清洗
- 日志统一记录
- 支持单品类重跑 / 全部重跑
"""

import os
import sys
import json
import time
import random
import logging
import subprocess
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# ========== 基础配置 ==========
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DICT_DIR = BASE_DIR / "dictionary"

MAX_CONCURRENT = 2          # 同时跑几个爬虫（2-3个比较稳，5个容易风控+内存爆）
STAGGER_SECONDS = 45        # 错峰启动间隔（秒），避免同时请求被封
RETRY_TIMES = 1             # 失败重试次数
SCRAPE_TIMEOUT = 7200       # 单个爬虫超时（秒），2小时
CLEAN_TIMEOUT = 600         # 单个清洗超时（秒）

# ========== 五大件任务配置 ==========
TASKS = [
    {
        "name": "CPU",
        "scraper": "cpu_scraper.py",
        "cleaner": "cpu_cleaner.py",
        "raw_file": "data/cpu_result.json",
        "cleaned_file": "data/cpu_result_cleaned.json",
        "summary_file": "data/cpu_price_summary.json",
        "dict_file": "dictionary/hardware_base_cpu.json",
    },
    {
        "name": "GPU",
        "scraper": "gpu_scraper.py",
        "cleaner": "gpu_cleaner.py",
        "raw_file": "data/gpu_result.json",
        "cleaned_file": "data/gpu_result_cleaned.json",
        "summary_file": "data/gpu_price_summary.json",
        "dict_file": "dictionary/hardware_base_gpu.json",
    },
    {
        "name": "内存",
        "scraper": "ram_scraper.py",
        "cleaner": "ram_cleaner.py",
        "raw_file": "data/mem_result.json",
        "cleaned_file": "data/mem_result_cleaned.json",
        "summary_file": "data/mem_price_summary.json",
        "dict_file": "dictionary/hardware_base_ram.json",
    },
    {
        "name": "硬盘",
        "scraper": "sto_scraper.py",
        "cleaner": "sto_cleaner.py",
        "raw_file": "data/sto_result.json",
        "cleaned_file": "data/sto_result_cleaned.json",
        "summary_file": "data/sto_price_summary.json",
        "dict_file": "dictionary/hardware_base_sto.json",
    },
    {
        "name": "主板",
        "scraper": "mb_scraper.py",
        "cleaner": "mb_cleaner.py",
        "raw_file": "data/mb_result.json",
        "cleaned_file": "data/mb_result_cleaned.json",
        "summary_file": "data/mb_price_summary.json",
        "dict_file": "dictionary/hardware_base_mb.json",
    },
]


# ========== 日志配置 ==========
def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"run_all_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ]
    )
    return log_file


# ========== 反爬配置 ==========
def get_anti_crawl_env(task_name: str) -> dict:
    """为每个子进程注入反爬环境变量"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    # 每个品类用不同的随机延迟范围，降低行为一致性
    delay_ranges = {
        "CPU": (2.0, 4.0),
        "GPU": (3.0, 5.0),
        "内存": (2.5, 4.5),
        "硬盘": (2.0, 3.5),
        "主板": (3.0, 5.0),
    }
    min_d, max_d = delay_ranges.get(task_name, (2.0, 4.0))
    env["SCRAPE_MIN_DELAY"] = str(min_d)
    env["SCRAPE_MAX_DELAY"] = str(max_d)

    # 随机User-Agent（子进程读取后注入浏览器）
    ua_pool = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]
    env["SCRAPE_UA"] = random.choice(ua_pool)

    # 代理配置（如果有代理池，在这里设置）
    # env["HTTP_PROXY"] = "http://your-proxy:port"
    # env["HTTPS_PROXY"] = "http://your-proxy:port"

    return env


# ========== 执行单个任务 ==========
def run_task(task: dict) -> dict:
    """执行单个品类：爬虫 → 清洗，返回结果状态"""
    name = task["name"]
    scraper = BASE_DIR / task["scraper"]
    cleaner = BASE_DIR / task["cleaner"]
    raw_file = BASE_DIR / task["raw_file"]
    summary_file = BASE_DIR / task["summary_file"]

    result = {
        "name": name,
        "scrape_status": "pending",
        "clean_status": "pending",
        "raw_count": 0,
        "cleaned_count": 0,
        "error": None,
        "start_time": datetime.now().isoformat(),
    }

    # ---- 1. 执行爬虫 ----
    for attempt in range(RETRY_TIMES + 1):
        try:
            logging.info(f"[{name}] 爬虫开始 (第{attempt+1}次尝试)")
            env = get_anti_crawl_env(name)

            proc = subprocess.run(
                [sys.executable, str(scraper)],
                cwd=str(BASE_DIR),
                env=env,
                capture_output=True,
                text=True,
                timeout=SCRAPE_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )

            # 写爬虫日志
            scraper_log = LOG_DIR / f"{name}_scraper.log"
            with open(scraper_log, "w", encoding="utf-8") as f:
                f.write("=== STDOUT ===\n")
                f.write(proc.stdout or "")
                f.write("\n=== STDERR ===\n")
                f.write(proc.stderr or "")

            if proc.returncode != 0:
                raise RuntimeError(f"爬虫退出码 {proc.returncode}，详见 {scraper_log}")

            # 统计原始数据量
            if raw_file.exists():
                with open(raw_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                result["raw_count"] = len(raw_data)

            result["scrape_status"] = "success"
            logging.info(f"[{name}] 爬虫完成，原始数据 {result['raw_count']} 条")
            break

        except subprocess.TimeoutExpired:
            logging.error(f"[{name}] 爬虫超时（>{SCRAPE_TIMEOUT}秒）")
            result["error"] = f"爬虫超时"
            if attempt < RETRY_TIMES:
                logging.info(f"[{name}] 等待30秒后重试...")
                time.sleep(30)
        except Exception as e:
            logging.error(f"[{name}] 爬虫失败: {e}")
            result["error"] = str(e)
            if attempt < RETRY_TIMES:
                logging.info(f"[{name}] 等待30秒后重试...")
                time.sleep(30)
    else:
        result["scrape_status"] = "failed"

    # 爬虫失败则跳过清洗
    if result["scrape_status"] != "success":
        result["end_time"] = datetime.now().isoformat()
        return result

    # ---- 2. 执行清洗 ----
    try:
        logging.info(f"[{name}] 清洗开始")
        proc = subprocess.run(
            [sys.executable, str(cleaner)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=CLEAN_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )

        cleaner_log = LOG_DIR / f"{name}_cleaner.log"
        with open(cleaner_log, "w", encoding="utf-8") as f:
            f.write("=== STDOUT ===\n")
            f.write(proc.stdout or "")
            f.write("\n=== STDERR ===\n")
            f.write(proc.stderr or "")

        if proc.returncode != 0:
            raise RuntimeError(f"清洗退出码 {proc.returncode}，详见 {cleaner_log}")

        # 统计清洗后数据量
        cleaned_file = BASE_DIR / task["cleaned_file"]
        if cleaned_file.exists():
            with open(cleaned_file, "r", encoding="utf-8") as f:
                cleaned_data = json.load(f)
            result["cleaned_count"] = len(cleaned_data)

        result["clean_status"] = "success"
        logging.info(f"[{name}] 清洗完成，保留 {result['cleaned_count']} 条")

    except Exception as e:
        logging.error(f"[{name}] 清洗失败: {e}")
        result["clean_status"] = "failed"
        result["error"] = str(e)

    result["end_time"] = datetime.now().isoformat()
    return result


# ========== 主流程 ==========
def main():
    log_file = setup_logging()
    DATA_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    # 解析命令行参数：python run_all.py [CPU,GPU] 或 python run_all.py --all
    selected = None
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg not in ("--all", "all", "-a"):
            selected = [s.strip().upper() for s in sys.argv[1].split(",")]
            # 中文名称映射
            name_map = {"CPU": "CPU", "GPU": "GPU", "内存": "内存", "RAM": "内存",
                        "硬盘": "硬盘", "STO": "硬盘", "DISK": "硬盘", "主板": "主板", "MB": "主板"}
            selected = [name_map.get(s, s) for s in selected]

    tasks = TASKS
    if selected:
        tasks = [t for t in TASKS if t["name"] in selected]
        if not tasks:
            logging.error(f"未找到指定品类: {selected}")
            sys.exit(1)

    logging.info("=" * 60)
    logging.info("PCBuilder 五大件价格采集启动")
    logging.info(f"并发数: {MAX_CONCURRENT} | 错峰间隔: {STAGGER_SECONDS}秒")
    logging.info(f"待采集品类: {[t['name'] for t in tasks]}")
    logging.info(f"日志文件: {log_file}")
    logging.info("=" * 60)

    # 检查文件是否存在
    for task in tasks:
        scraper = BASE_DIR / task["scraper"]
        cleaner = BASE_DIR / task["cleaner"]
        if not scraper.exists():
            logging.error(f"[{task['name']}] 爬虫文件不存在: {scraper}")
        if not cleaner.exists():
            logging.error(f"[{task['name']}] 清洗文件不存在: {cleaner}")

    # 并行执行（错峰启动）
    results = []
    with ProcessPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {}
        for i, task in enumerate(tasks):
            if i > 0:
                logging.info(f"等待 {STAGGER_SECONDS} 秒后启动下一个（错峰反爬）...")
                time.sleep(STAGGER_SECONDS)
            future = executor.submit(run_task, task)
            futures[future] = task["name"]
            logging.info(f"[{task['name']}] 已提交到进程池")

        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                results.append(result)
                status = "✅" if result["scrape_status"] == "success" and result["clean_status"] == "success" else "❌"
                logging.info(f"{status} [{name}] 爬虫:{result['scrape_status']} 清洗:{result['clean_status']} "
                             f"原始:{result['raw_count']}条 清洗后:{result['cleaned_count']}条")
            except Exception as e:
                logging.error(f"❌ [{name}] 进程异常: {e}")
                results.append({"name": name, "scrape_status": "failed", "error": str(e)})

    # 汇总报告
    logging.info("\n" + "=" * 60)
    logging.info("📊 采集汇总报告")
    logging.info("=" * 60)
    logging.info(f"{'品类':<6} {'爬虫':<8} {'清洗':<8} {'原始':>6} {'清洗后':>6} {'状态'}")
    logging.info("-" * 55)

    success_count = 0
    for r in sorted(results, key=lambda x: x["name"]):
        ok = r["scrape_status"] == "success" and r["clean_status"] == "success"
        if ok:
            success_count += 1
        status_icon = "✅" if ok else "❌"
        logging.info(f"{r['name']:<6} {r['scrape_status']:<8} {r['clean_status']:<8} "
                     f"{r.get('raw_count', 0):>6} {r.get('cleaned_count', 0):>6} {status_icon}")
        if r.get("error"):
            logging.info(f"       错误: {r['error']}")

    logging.info("-" * 55)
    logging.info(f"完成: {success_count}/{len(results)} 个品类")
    logging.info(f"日志目录: {LOG_DIR}")
    logging.info("=" * 60)

    # 保存汇总结果
    report_file = LOG_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logging.info(f"汇总报告: {report_file}")


if __name__ == "__main__":
    main()