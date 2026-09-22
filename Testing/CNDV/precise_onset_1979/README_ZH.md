# RegCM4.7-CNDV / RegCM5-CNDV 1979 年分歧精准定位试验

最终结果、代码依据和单因素消融结论见
[`PRECISION_LOCALIZATION_REPORT_ZH.md`](PRECISION_LOCALIZATION_REPORT_ZH.md)。机器可读的
独立一致性审计为 `analysis/precision_audit_summary.json`。

## 目的

长期连续积分已经表明，两版在共同的 1979 年初自然植被覆盖状态出发后，到
1980 年首个年末状态时，RegCM5 的年累积 NPP、植被总碳和植被总氮只剩
RegCM4.7 的约 2.5%–3.7%。本试验专门定位这个差异是在何时、经过哪条物理—生物
地球化学链路形成的。

试验不修改现有 1979–2016 年结果，也不重新制作 DOMAIN、CLM 地表或 ICBC。
两版直接只读复用长期试验的同一套输入：

`/public/home/elpt_2024_000795/workdir_for_RCM/cndv_maxrun_regcm47_regcm5_1979_2016/common_input`

## 两级时间分辨率

1. **冷启动 24 小时试验**：1979-01-01 00:00 至 1979-01-02 00:00，逐小时保存
   诊断量，并在 24 小时处写完整重启文件。用于判断差异是否在初始化或第一个模拟日
   内已经出现。
2. **完整 1979 年试验**：1979-01-01 00:00 至 1980-01-01 00:00，逐日保存诊断
   量。用于定位第一个显著差异日，并把年末 CNDV 更新前的历史状态与更新后的重启/
   HV 状态分开。

每个版本、每个阶段都从冷启动独立运行，`ifrest=.false.`。完整年度试验不是由月段
拼接而成。

这里明确使用正值 `hist_nhtfrq=1`（逐小时）和 `hist_nhtfrq=24`（逐日）。
RegCM耦合版CLM的历史写出例程把正值解释为小时；若沿用CLM常见的负值写法，
`-1` 会先按 `dtsrf=600秒` 换算为 `6`，实际只能得到6小时间隔，不能用于本试验。

## 三类历史输出

- `h0`：网格尺度气象、水分和氮供给诊断，时间平均；
- `h1`：原始 PFT 维度的光合作用、呼吸、NPP、氮需求和氮限制诊断，时间平均；
- `h2`：原始 PFT 维度的碳氮库、LAI 等状态量，区间末瞬时值。

关键字段包括：

- 气象/水分：`TBOT`、`QBOT`、`WIND`、`RAIN`、`SNOW`、`FSDS`、`FLDS`、
  `BTRAN`、`SOILWATER_10CM`；
- 碳同化和呼吸：`FPSN`、`GPP`、`INIT_GPP`、`MR`、`GR`、`AR`、`NPP`；
- 氮限制：`PLANT_NDEMAND`、`PLANT_NALLOC`、`FPG`、`DOWNREG`、
  `SMINN_TO_PLANT`、`NDEP_TO_SMINN`、`NFIX_TO_SMINN`；
- 状态库：`TOTVEGC`、`TOTVEGN`、`LEAFC`、`FROOTC`、`WOODC`、`CPOOL`、
  `NPOOL`、`RETRANSN`、`ELAI`、`TLAI`、`ANNSUM_NPP`。

## 资源和提交顺序

两版模型作业均使用 `cpu_parallel` 队列、2 节点 × 64 MPI，共 128 MPI 进程。

提交链为：

1. 两版 24 小时试验并行；
2. 小时输出门控分析；
3. 门控通过后两版完整 1979 年试验并行；
4. 最终逐日和年末更新前后分析。

服务器目标目录：

`/public/home/elpt_2024_000795/workdir_for_RCM/cndv_precise_onset_1979`

部署后执行：

```bash
bash prepare_remote.sh
bash submit_precise_onset.sh
```

## 判定规则

分析同时报告原始差值和比例，不把接近零的冬季通量比值误认为物理分歧。累计碳
通量只有在 RegCM4.7 的绝对累计量达到最小阈值后才进行相对差异判定。最终重点
回答：

1. 第一小时/第一天的初始碳氮库是否已经不同；
2. `INIT_GPP → GPP → NPP` 的差异从哪一环开始；
3. 氮需求、氮分配或 `DOWNREG/FPG` 是否先于 NPP 分歧；
4. 年末 CNDV 调用前碳氮库是否已经塌陷；
5. 年末 `dv` 调用本身又额外改变了多少 FPC、NIND 和碳氮库。

## LAI 单因素消融试验

逐小时基线试验若显示两版在叶碳近似相同的同时 LAI 已显著不同，则继续执行一个
单因素因果试验：仅把 RegCM4.7 的 `leafC → TLAI` 公式和 PFT 最小 LAI 约束移入
RegCM5，其余 RegCM5 代码、输入、编译选项和 128 MPI 配置均保持不变。

```bash
bash submit_lai_ablation.sh
```

构建脚本不会覆盖正式安装的 RegCM5 可执行文件。实验二进制单独保存到
`RegCM5-cndv-experiments/legacy-lai47`；构建完成后恢复源码原始 SHA-256，并重新
生成基线对象。输出表为 `analysis/lai_ablation_*.csv/json`。该试验用于区分：

- LAI 代码块是否是第一个植被状态分歧的充分原因；
- 将 LAI 公式统一后，GPP/NPP 差距能缩小多少；
- 剩余差距是否仍来自两版大气辐射、温湿度和水分胁迫的不同。
