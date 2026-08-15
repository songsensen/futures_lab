# 真实数据导入模板

这几份 CSV 是 `flask import-xxx` 系列命令期望的列格式示例（列名和顺序固定，不做智能匹配）。
把真实数据整理成同样的列，替换掉里面的示例行，再执行对应命令即可，重复导入同一份文件是安全的
（按日期/合约做 upsert，不会产生重复行）。

```bash
cd /path/to/futures_lab
flask --app run.py import-daily-bar import_templates/daily_bar.csv
flask --app run.py import-position-rank import_templates/position_rank.csv
flask --app run.py import-warehouse-receipt import_templates/warehouse_receipt.csv
flask --app run.py import-basis import_templates/basis.csv
flask --app run.py import-macro-data import_templates/macro_data.csv
```

说明：

- `variety_code` 必须是已经在 `/admin` 后台建好的品种代码（如 SA/FG/M），品种本身不会被自动创建——
  防止代码打错时系统悄悄生成一个没人注意到的垃圾品种。
- `contract_code` 如果第一次出现会自动创建对应的合约记录，不用先去后台手动建。
- `basis.csv` 的 `basis_value` 留空时会自动按 `spot_price - futures_price` 算出来（见第二行示例）。
- 除了这五张表，案例库、事前状态、生产端工艺、上下游产业链、政策等需要人工写文字判断的表，
  走 `/admin` 后台逐条录入，不走 CSV（见 `app/data_import.py` 顶部说明）。
