# 脚本说明

## 下载数据脚本

### 方式1：使用官方脚本（推荐）

需要从 Qlib 官方仓库获取 `get_data.py`：

```bash
# 下载 get_data.py
curl -O https://raw.githubusercontent.com/microsoft/qlib/main/scripts/get_data.py

# 或者克隆官方仓库
git clone https://github.com/microsoft/qlib.git
cp qlib/scripts/get_data.py scripts/
```

然后运行：
```bash
python scripts/get_data.py qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn
```

### 方式2：使用 Python 包内置方法

```bash
# 直接使用 qlib 包下载
python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn
```

### 方式3：使用提供的 bat 脚本

前提：需要先按方式1获取 `get_data.py` 文件

双击运行：
```
scripts\download_data.bat
```

## 运行示例脚本

```
scripts\run_example.bat
```

## 参考

- [Qlib 数据下载文档](https://qlib.readthedocs.io/en/latest/component/data.html)
- [get_data.py 源码](https://github.com/microsoft/qlib/blob/main/scripts/get_data.py)
