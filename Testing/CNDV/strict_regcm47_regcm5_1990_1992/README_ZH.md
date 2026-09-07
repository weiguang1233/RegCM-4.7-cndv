# RegCM4.7-CNDV 与 RegCM5-CNDV 严格比较测试

## 1. 目的

本测试用于回答：在相同区域、相同网格、相同初始陆面状态、相同大气与海温驱动、相同物理参数、相同时间步长和相同 MPI 分解下，RegCM4.7-CNDV 与 RegCM5-CNDV 的逐年 CNDV 更新是否一致，以及差异有多大。

本次服务器实测结果及结论见 [`STRICT_COMPARISON_REPORT_ZH.md`](STRICT_COMPARISON_REPORT_ZH.md)。

测试不是把两个宿主模式版本的数值结果预设为必须完全相等。RegCM4.7 与 RegCM5 的宿主大气模式和耦合代码本身不同；严格测试的含义是先排除输入、网格和初态混杂因素，再量化两个版本在同一实验条件下产生的差异。

## 2. 共同实验条件

- 区域：`iy=34`、`jx=64`、`kz=18`，LAMCON 投影，水平分辨率 60 km；
- 模拟时段：1990-01-01 00:00 至 1992-01-01 00:00，连续两个完整年份；
- 大气驱动：EIN15；
- 海温：ERSST；
- 日历：Gregorian；
- 模式时间步长：150 s；
- CLM 地表时间步长：600 s；
- 对流、边界层、海气通量等物理参数逐项一致；
- 正式积分均使用 32 个 MPI 进程，分解为 `8 × 4`；
- 两个版本使用同一个 `common_input` 目录中的同一批 NetCDF 文件。

共同输入只由 RegCM4.7 的前处理程序生成一次。这样做不是把 RegCM4.7 当作科学基准，而是因为它可生成两个版本都能读取的 NetCDF3 文件。RegCM5 还要求 DOMAIN 中存在网格面积 `areacella`，而 RegCM4.7 不输出该字段；前处理后以 `areacella=(60000 m / xmap)^2` 增加这个只读兼容字段，并保留未修改的 RegCM4.7 DOMAIN 原件。该公式已与 RegCM5 自身 terrain 输出逐元素核验，差异仅为浮点舍入量级。两个模式随后读取同一个已兼容化的 DOMAIN。每个输入文件均保存 SHA-256 摘要。

RegCM4.7 配置中额外出现的 `idesseas=0` 和 `iconvlwp=0` 是该版本要求的兼容字段；RegCM5 配置不接受这两个字段。除此之外，两份正式积分 namelist 的科学设置一致，输出目录除外。

## 3. 分阶段门控

测试按以下依赖链运行：

1. 共同前处理：生成 1990—1992 所需的 DOMAIN、CLM45 surface、SST 和 ICBC；
2. 双版本 24 小时短测：确认两个可执行文件都能读取完全相同的共同输入；
3. 初始状态硬门控：比较短测生成的初始 HV 文件；
4. 双版本两年连续积分：只有初始状态门控成功才会提交到正式队列；
5. 严格配对分析：只有两个两年积分都成功才会执行。

初始状态门控同时要求：

- 日期均为 1990-01-01 00:00；
- 两边均有 17 个 PFT；
- 网格数量、经纬度、`regcm_mask` 完全匹配；
- soil landunit 上的 `(gridcell, PFT)` 映射完全匹配；
- 初始 `FPCGRID` 和 `NIND` 的逐元素最大绝对误差不超过 `1e-12`；
- 每个网格的 17 个 PFT 覆盖度之和为 100%，闭合误差不超过 `1e-6` 个百分点。

门控失败时，正式两年积分不会启动。此前两个版本各自前处理得到的旧测试结果网格数分别为 1193 和 1311，已作为反例验证：门控会拒绝这种不可直接配对的数据。

## 4. 严格比较指标

### 4.1 数据有效性

- 三个 HV 状态时点分别对应 1990-01-01、1991-01-01、1992-01-01；
- 两年内 grid/PFT 映射保持不变；
- `FPCGRID` 合法且每个网格闭合到 100%；
- `NIND` 非负；
- 每年 CNDV 更新后，restart 中 `drought_days` 已清零；
- 独立复算长期干旱状态：冷启动时 `drought_days20=-1`，第一年以当年 `drought_days` 初始化；第二年起使用 `drought_days20=(19×上一年值+当年 drought_days)/20`。与 history/restart 的最大误差不超过 `5e-5` 天；
- 历史文件和 restart 的经纬度可与 HV 网格逐点配对。

### 4.2 PFT 变化

- 初始、第一年末、第二年末的自然 PFT 总覆盖度；
- 每年、每个自然 PFT 槽位的 `ΔFPC`；
- RegCM5 减 RegCM4.7 的配对 MAE、RMSE、最大绝对差；
- 两版本 `ΔFPC` 的相关系数；
- 对绝对变化至少 0.01 个百分点的槽位，比较变化方向的一致率；
- 各 PFT 的网格平均覆盖度和逐年变化；
- 每个网格的优势自然 PFT 一致数量。

### 4.3 干旱状态

- CNDV 更新前历史场中的 `DROUGHT_DAYS` 与 `DROUGHT_DAYS20`；
- CNDV 更新后 restart 中保留的 `drought_days20`；
- 配对均值差、RMSE、相关系数；
- `drought_days20 > 45` 阈值的 2×2 配对计数：两边均超过、仅 4.7 超过、仅 5 超过、两边均不超过。

`45` 天使用严格大于号，与代码中的 CNDV 干旱触发条件一致。

## 5. 文件和输出

- `common_preprocess_regcm47.in`：唯一的共同前处理配置；
- `add_areacella_compat.sh`：增加 RegCM5 必需的网格面积字段，并保留原 DOMAIN；
- `regcm47_smoke.in`、`regcm5_smoke.in`：24 小时兼容性短测；
- `regcm47_two_year.in`、`regcm5_two_year.in`：两年正式积分；
- `submit_strict_chain.sh`：创建目录并提交完整依赖链；
- `validate_initial_gate.py`：共同网格和共同初态门控；
- `strict_compare_io.py`：NetCDF3/NetCDF4 双格式读取；
- `analyze_strict_compare.py`：跨版本严格配对分析；
- `analyze_pft_change_regcm47.py`、`analyze_pft_change_regcm5.py`：各版本内部逐年 QA；
- `analysis/common_input_sha256.txt`：共同输入文件摘要；
- `analysis/original_regcm47_domain_sha256.txt`：未增加兼容字段的原始 DOMAIN 摘要；
- `analysis/initial_gate/initial_gate_summary.txt`：初态门控报告；
- `analysis/strict/strict_comparison_summary.txt`：跨版本核心统计；
- `analysis/strict/strict_pft_comparison_by_type.csv`：逐 PFT 结果；
- `analysis/strict/strict_paired_grid_summary.csv`：逐网格配对结果；
- `analysis/strict/strict_comparison.png`：结果概览图。

## 6. 运行方法

服务器目标目录为：

```text
/public/home/elpt_2024_000795/workdir_for_RCM/cndv_strict_compare_regcm47_regcm5_1990_1992
```

把本目录中的文本文件上传到目标目录后，在目标目录执行：

```bash
bash submit_strict_chain.sh
```

脚本会输出七个作业号并写入 `analysis/submitted_jobs.txt`。依赖关系使用 `afterok`，任何上游阶段失败时，下游阶段不会误运行。

## 7. 判读原则

以下项目属于测试有效性的硬性通过条件：共同输入完整、双版本短测成功、共同网格和共同初态门控通过、两个版本内部的 FPC 闭合与 restart 清零语义通过。

跨版本的 PFT 和干旱数值差异属于实验结果，不人为设定“必须相等”的通过阈值。最终结论应同时报告绝对差异、相关性、变化方向一致率和干旱阈值一致性，并明确差异包含宿主 RegCM4.7 与 RegCM5 响应不同的贡献，不能仅凭本实验把全部差异归因于 CNDV 子程序。
