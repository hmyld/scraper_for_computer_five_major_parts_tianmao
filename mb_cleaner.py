import json
import os
import numpy as np
from collections import defaultdict

INPUT_FILE = "data/mb_result.json"
CLEANED_FILE = "data/mb_result_cleaned.json"
SUMMARY_FILE = "data/mb_price_summary.json"

MAX_PRICE = 20000  # 服务器主板可能贵
MIN_SAMPLE = 3


def mad_based_clean(prices, threshold=3.0):
    if len(prices) < 4:
        return prices, []
    prices = np.array(prices, dtype=float)
    median = np.median(prices)
    mad = np.median(np.abs(prices - median))
    robust_std = mad * 1.4826
    if robust_std == 0:
        return prices.tolist(), []
    lower = median - threshold * robust_std
    upper = median + threshold * robust_std
    mask = (prices >= lower) & (prices <= upper)
    return prices[mask].tolist(), prices[~mask].tolist()


def find_optimal_sigma(prices):
    best_sigma = 2.0
    best_cv = float('inf')
    best_kept = prices
    for sigma in [1.5, 2.0, 2.5, 3.0]:
        kept, _ = mad_based_clean(prices, threshold=sigma)
        if len(kept) < max(3, len(prices) * 0.3):
            continue
        arr = np.array(kept)
        mean = np.mean(arr)
        std = np.std(arr)
        if mean > 0:
            cv = std / mean
            if cv < best_cv:
                best_cv = cv
                best_sigma = sigma
                best_kept = kept
    return best_kept, best_sigma


def calc_stats(kept_prices):
    kp = sorted(kept_prices)
    if not kp:
        return None
    arr = np.array(kp)
    median = float(np.median(arr))
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    q25 = float(np.percentile(arr, 25))
    q75 = float(np.percentile(arr, 75))
    recommend = round(min(median, mean), 1)
    return {
        "min_price": kp[0],
        "max_price": kp[-1],
        "median_price": round(median, 1),
        "avg_price": round(mean, 1),
        "std_price": round(std, 1),
        "q25_price": round(q25, 1),
        "q75_price": round(q75, 1),
        "price_range": [round(q25, 1), round(q75, 1)],
        "recommend_price": recommend,
    }


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ 找不到 {INPUT_FILE}")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"📊 原始数据: {len(data)} 条")

    filtered_data = []
    removed_high = 0
    for d in data:
        try:
            price = float(d.get("price", 0))
            if price <= 0 or price > MAX_PRICE:
                removed_high += 1
                continue
            filtered_data.append(d)
        except:
            removed_high += 1
            continue
    print(f"🚫 价格异常过滤: 删除 {removed_high} 条（≤0或>¥{MAX_PRICE}）")
    data = filtered_data

    groups = defaultdict(list)
    mb_all_prices = defaultdict(list)
    for d in data:
        try:
            price = float(d.get("price", 0))
            if price > 0:
                key = (d["mb_key"], d.get("brand", "未知"))
                groups[key].append(d)
                mb_all_prices[d["mb_key"]].append(price)
        except:
            continue

    cleaned_data = []
    summary = defaultdict(dict)

    print(f"\n{'芯片组':<18} {'品牌':<8} {'原始':>4} {'删除':>4} {'保留':>4} {'σ':>4} {'最低':>7} {'中位':>7} {'均值':>7} {'最高':>7} {'推荐价':>8}")
    print("-" * 100)

    for (mb_key, brand), items in sorted(groups.items()):
        prices = [float(i["price"]) for i in items]
        kept_prices, best_sigma = find_optimal_sigma(prices)

        kept_set = set(kept_prices)
        price_count = defaultdict(int)
        for p in kept_prices:
            price_count[p] += 1
        kept_items = []
        for item in items:
            p = float(item["price"])
            if price_count[p] > 0:
                kept_items.append(item)
                price_count[p] -= 1

        removed_count = len(items) - len(kept_items)
        cleaned_data.extend(kept_items)

        total = len(mb_all_prices[mb_key])
        is_low_sample = total < MIN_SAMPLE

        brand_stats = calc_stats(kept_prices)
        if brand_stats:
            median = brand_stats["median_price"]
            mean = brand_stats["avg_price"]
            min_p = brand_stats["min_price"]
            max_p = brand_stats["max_price"]
            if is_low_sample:
                recommend = None
                recommend_str = "⚠️不足"
            else:
                recommend = brand_stats["recommend_price"]
                recommend_str = f"¥{recommend:>6.0f}"
        else:
            median = mean = min_p = max_p = 0
            recommend = None
            recommend_str = "⚠️不足"

        summary[mb_key][brand] = {
            "mb_total_sample": total,
            "brand_sample_count": len(kept_items),
            "removed_count": removed_count,
            "optimal_sigma": best_sigma,
            "min_price": min_p,
            "max_price": max_p,
            "median_price": median,
            "avg_price": mean,
            "recommend_price": recommend,
            "data_quality": "low_sample" if is_low_sample else "ok"
        }

        print(f"{mb_key:<18} {brand:<8} {len(items):>4} {removed_count:>4} {len(kept_items):>4} "
              f"{best_sigma:>4.1f} "
              f"{min_p:>7.0f} "
              f"{median:>7.0f} "
              f"{mean:>7.0f} "
              f"{max_p:>7.0f} "
              f"{recommend_str:>8}")

    # 芯片组整体汇总
    print(f"\n{'='*70}")
    print(f"📊 主板芯片组整体价格（不区分品牌）")
    print(f"{'='*70}")
    print(f"{'芯片组':<18} {'样本':>4} {'最低':>7} {'25%':>7} {'中位':>7} {'均值':>7} {'75%':>7} {'最高':>7} {'推荐':>7}")
    print("-" * 85)

    mb_summary = {}
    for mb_key in sorted(mb_all_prices.keys()):
        all_prices = mb_all_prices[mb_key]
        kept, sigma = find_optimal_sigma(all_prices)
        stats = calc_stats(kept)
        total = len(all_prices)
        is_low = total < MIN_SAMPLE

        if stats and not is_low:
            rec = stats["recommend_price"]
            rec_str = f"{rec:>7.0f}"
        else:
            rec = None
            rec_str = "⚠️不足"

        mb_summary[mb_key] = {
            "total_sample": total,
            "cleaned_sample": len(kept),
            "optimal_sigma": sigma,
            "min_price": stats["min_price"] if stats else 0,
            "q25_price": stats["q25_price"] if stats else 0,
            "median_price": stats["median_price"] if stats else 0,
            "avg_price": stats["avg_price"] if stats else 0,
            "q75_price": stats["q75_price"] if stats else 0,
            "max_price": stats["max_price"] if stats else 0,
            "price_range": stats["price_range"] if stats else [0, 0],
            "recommend_price": rec,
            "data_quality": "low_sample" if is_low else "ok"
        }

        print(f"{mb_key:<18} {total:>4} "
              f"{stats['min_price'] if stats else 0:>7.0f} "
              f"{stats['q25_price'] if stats else 0:>7.0f} "
              f"{stats['median_price'] if stats else 0:>7.0f} "
              f"{stats['avg_price'] if stats else 0:>7.0f} "
              f"{stats['q75_price'] if stats else 0:>7.0f} "
              f"{stats['max_price'] if stats else 0:>7.0f} "
              f"{rec_str:>7}")

    final_output = {}
    for mb_key in sorted(mb_summary.keys()):
        final_output[mb_key] = {
            "mb_summary": mb_summary[mb_key],
            "brands": summary[mb_key]
        }

    with open(CLEANED_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)

    low_sample_count = sum(1 for v in mb_all_prices.values() if len(v) < MIN_SAMPLE)

    print(f"\n✅ 清洗完成")
    print(f"   原始: {len(data) + removed_high}条")
    print(f"   价格异常删除: {removed_high}条")
    print(f"   统计异常删除: {len(data) - len(cleaned_data)}条")
    print(f"   最终保留: {len(cleaned_data)}条")
    print(f"   覆盖芯片组: {len(mb_summary)} 种")
    print(f"   ⚠️ 样本不足: {low_sample_count} 种（总样本<{MIN_SAMPLE}条）")
    print(f"   清洗后数据: {CLEANED_FILE}")
    print(f"   价格统计: {SUMMARY_FILE}")


if __name__ == "__main__":
    main()