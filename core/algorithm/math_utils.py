import random

def generate_random_ratios(reagent_count, ratio_sum):
    """
    指定された合計値 (ratio_sum) になる、指定された個数 (reagent_count) の
    0を含まないランダムな整数のリストを生成します。
    """
    if ratio_sum < reagent_count:
        raise ValueError("Ratio sum (S) cannot be less than the number of reagents (t).")

    dividers = sorted(random.sample(range(1, ratio_sum), reagent_count - 1))
    ratios = []
    last_divider = 0
    for d in dividers:
        ratios.append(d - last_divider)
        last_divider = d
    ratios.append(ratio_sum - last_divider)
    return ratios