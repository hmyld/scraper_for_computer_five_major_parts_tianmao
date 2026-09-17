import json
import os
import numpy as np
from collections import defaultdict

INPUT_FILE = "data/cpu_result.json"
CLEANED_FILE = "data/cpu_result_cleaned.json"
SUMMARY_FILE = "data/cpu_price_summary.json"


def mad_based_clean(prices, threshold=3.0):
    """
    基于MAD（中位数绝对偏差）的稳健异常值剔除
    比均值+标准差更抗混卖起售价的干扰
    """
    if len(prices) < 4:
        return prices, []

    prices = np.array(prices, dtype=float)
    median = np.median(prices)
    mad = np.median(np.abs(prices - median))
    robust_std = mad * 1.4826  # MAD转标准差的系数

    if robust_std == 0:
        return prices.tolist(), []

    # 保留中位数 ± threshold * 稳健标准差 范围内的
    lower = median - threshold * robust_std
    upper = median + threshold * robust_std
    mask = (prices >= lower) & (prices <= upper)

    kept = prices[mask].tolist()
    removed = prices[~mask].tolist()
    return kept, removed


def iterative_sigma_clean(prices, sigma=2.0, max_iter=5):
    """
    迭代σ清洗：反复剔除超出均值±σ的，直到收敛
    """
    if len(prices) < 4:
        return prices, []

    prices = list(prices)
    all_removed = []

    for _ in range(max_iter):
        if len(prices) < 4:
            break
        arr = np.array(prices, dtype=float)
        mean = np.mean(arr)
        std = np.std(arr)
        if std == 0:
            break
        lower = mean - sigma * std
        upper = mean + sigma * std
        new_prices = [p for p in prices if lower <= p <= upper]
        removed = [p for p in prices if p < lower or p > upper]
        if not removed:
            break
        all_removed.extend(removed)
        prices = new_prices

    return prices, all_removed


def find_optimal_sigma(prices):
    """
    自动寻找最优σ倍数：使清洗后方差最小（数据最集中），且保留足够样本
    """
    best_sigma = 2.0
    best_cv = float('inf')  # 变异系数 = 标准差/均值
    best_kept = prices

    for sigma in [1.5, 2.0, 2.5, 3.0]:
        kept, _ = mad_based_clean(prices, threshold=sigma)
        if len(kept) < max(3, len(prices) * 0.3):
            continue  # 删太多了，跳过
        arr = np.array(kept)
        mean = np.mean(arr)
        std = np.std(arr)
        if mean > 0:
            cv = std / mean  # 变异系数，越小越集中
            if cv < best_cv:
                best_cv = cv
                best_sigma = sigma
                best_kept = kept

    return best_kept, best_sigma


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ 找不到 {INPUT_FILE}")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"📊 原始数据: {len(data)} 条")

    groups = defaultdict(list)
    for d in data:
        try:
            price = float(d.get("price", 0))
            if price > 0:
                groups[d["chip_model"]].append(d)
        except:
            continue

    cleaned_data = []
    summary = []

    print(f"\n{'型号':<20} {'原始':>4} {'删除':>4} {'保留':>4} {'σ倍数':>5} {'最低':>7} {'中位':>7} {'均值':>7} {'最高':>7} {'推荐价':>7}")
    print("-" * 95)

    for model in sorted(groups.keys()):
        items = groups[model]
        prices = [float(i["price"]) for i in items]

        # 方差最优：自动选最优σ倍数
        kept_prices, best_sigma = find_optimal_sigma(prices)

        # 保留对应的数据条目
        kept_set = set(kept_prices)
        kept_items = [i for i in items if float(i["price"]) in kept_set]
        # 处理重复价格
        kept_items = []
        price_count = defaultdict(int)
        for p in kept_prices:
            price_count[p] += 1
        for item in items:
            p = float(item["price"])
            if price_count[p] > 0:
                kept_items.append(item)
                price_count[p] -= 1

        removed_count = len(items) - len(kept_items)
        cleaned_data.extend(kept_items)

        # 统计
        kp = sorted(kept_prices)
        if kp:
            median = float(np.median(kp))
            mean = float(np.mean(kp))
            std = float(np.std(kp))
            recommend = min(median, mean)
        else:
            median = mean = std = recommend = 0

        summary.append({
            "chip_model": model,
            "sample_count": len(kept_items),
            "removed_count": removed_count,
            "optimal_sigma": best_sigma,
            "min_price": kp[0] if kp else 0,
            "max_price": kp[-1] if kp else 0,
            "median_price": round(median, 1),
            "avg_price": round(mean, 1),
            "std_price": round(std, 1),
            "recommend_price": round(recommend, 1)
        })

        print(f"{model:<20} {len(items):>4} {removed_count:>4} {len(kept_items):>4} "
              f"{best_sigma:>5.1f} "
              f"{kp[0] if kp else 0:>7.0f} "
              f"{median:>7.0f} "
              f"{mean:>7.0f} "
              f"{kp[-1] if kp else 0:>7.0f} "
              f"{recommend:>7.0f}")

    # 保存
    with open(CLEANED_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    total_removed = len(data) - len(cleaned_data)
    print(f"\n✅ 清洗完成: 原始{len(data)}条，删除{total_removed}条，保留{len(cleaned_data)}条")
    print(f"   清洗后数据: {CLEANED_FILE}")
    print(f"   价格统计: {SUMMARY_FILE}")


if __name__ == "__main__":
    main()