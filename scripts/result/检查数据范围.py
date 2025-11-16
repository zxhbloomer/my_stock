"""检查Qlib数据的时间范围"""
import qlib
from qlib.data import D
import pandas as pd


def check_data_range():
    # 初始化Qlib
    qlib.init(provider_uri='D:/Data/my_stock', region='cn')
    print("[OK] Qlib初始化完成\n")

    # 测试单只股票
    test_stock = 'sh600000'  # 浦发银行

    print(f"测试股票: {test_stock}")
    print("=" * 80)

    # 尝试不同的时间范围
    time_ranges = [
        ('2020-01-01', '2020-12-31'),
        ('2019-01-01', '2019-12-31'),
        ('2018-01-01', '2018-12-31'),
        ('2017-01-01', '2017-12-31'),
        ('2015-01-01', '2015-12-31'),
        ('2010-01-01', '2010-12-31'),
        ('2008-01-01', '2008-12-31'),
    ]

    for start, end in time_ranges:
        try:
            data = D.features(
                [test_stock],
                fields=['$close'],
                start_time=start,
                end_time=end
            )

            if data is not None and len(data) > 0:
                dates = data.index.get_level_values('datetime')
                print(f"[OK] {start} ~ {end}: {len(data)} 条数据")
                print(f"     实际范围: {dates.min()} ~ {dates.max()}")
            else:
                print(f"[NO] {start} ~ {end}: 无数据")

        except Exception as e:
            print(f"[ERROR] {start} ~ {end}: {e}")

    print("\n" + "=" * 80)
    print("测试calendar数据...")
    try:
        # 获取交易日历
        cal = D.calendar()
        print(f"[OK] 总交易日数: {len(cal)}")
        print(f"交易日范围: {cal.min()} ~ {cal.max()}")
    except Exception as e:
        print(f"[ERROR] calendar获取失败: {e}")


if __name__ == '__main__':
    check_data_range()
