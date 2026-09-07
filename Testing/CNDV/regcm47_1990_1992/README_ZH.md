# RegCM 4.7-CNDV 两整年连续性测试

本目录保存 1990 冷启动年和 1991 restart 年的实测配置、Slurm 脚本及分析程序。
这些文件来自 `huan` 集群上的 RegCM 4.7 独立试验，不是 RegCM5 的分支或运行
目录。绝对路径、资料类型、队列和资源是站点相关示例，复用前必须按目标环境修改。
提交分析作业时，请让对应 `.slurm` 与本目录的三个 Python 分析器保持在同一目录；
作业脚本通过自身路径定位分析器，不依赖当前 shell 的工作目录。

完整结果及解释见：

- [`Doc/CNDV_FIRST_YEAR_TEST_REGCM47_ZH.md`](../../../Doc/CNDV_FIRST_YEAR_TEST_REGCM47_ZH.md)；
- [`Doc/CNDV_TWO_YEAR_TEST_REGCM47_ZH.md`](../../../Doc/CNDV_TWO_YEAR_TEST_REGCM47_ZH.md)。

## 文件说明

- `cndv_crossyear_1990.in`：1990-01-01 至 1991-01-01 冷启动年；
- `preprocess_1990.slurm`、`run_1990_8r.slurm`：首年前处理和 8 MPI 全年积分；
- `analyze_1990.slurm`：首年年度状态独立验收；
- `cndv_year2_1991.in`：从 1991-01-01 restart 至 1992-01-01；
- `preprocess_1991.slurm`：复制静态网格/surface，并重建 1991 SST/ICBC；
- `stage_restart_19910101.slurm`：复制并逐文件核对 SAV、CLM r、CLM rh0；
- `run_1991_32r.slurm`：32 MPI 的第二整年积分；
- `analyze_1990_1992.slurm`：成对和三状态 PFT 验收；
- `validate_drought_1990_1992.slurm`：第二年 `drought_days20` 递推验收；
- `analyze_pft_change.py`：HV 成对差异、restart、`present` 和状态一致性检查；
- `analyze_three_year_states.py`：初始、第一年末、第二年末三状态比较和图表；
- `validate_drought_recurrence.py`：用年末 pre-DV history 独立复算 19/20 递推。

分析器使用 `scipy.io.netcdf_file`，因为本次 RegCM4.7 构建的输出是 NetCDF-3
64-bit-offset；不要直接换成只能读取 HDF5/NetCDF4 的 h5py。脚本同时检查
`numpft=17`、时间、映射、坐标、有限值、逐格闭合及 restart 一致性，QA 失败时
返回非零退出码。

## 关键时间和状态约束

第二年必须保持原始起点：

```text
mdate0 = 1990010100
mdate1 = 1991010100
mdate2 = 1992010100
ifrest = .true.
```

若把 `mdate0` 改为 1991，会使 CNDV 年份计数和初始写出语义错误。restart 必须
成套保存同一时刻的：

```text
c47yr1990_SAV.1991010100.nc
c47yr1990.clm.regcm.r.1991010100.nc
c47yr1990.clm.regcm.rh0.1991010100.nc
```

分段前后的 CLM history 配置也必须一致。`create_crop_landunit=.false.` 是当前
CNDV 的硬性要求；namelist 没有运行时 CNDV 开关，主程序必须由
`--enable-clm45 --enable-cndv` 构建。

HV 文件名存在现有代码导致的一年偏移：内部日期 1990-01-01、1991-01-01、
1992-01-01 分别写为 `hv.1991.nc`、`hv.1992.nc`、`hv.1993.nc`。分析必须读取
`mcdate`，不能用文件名推断状态日期。

## 推荐提交顺序

在两个空白、互相隔离的运行目录中准备脚本并修改其中绝对路径。以下示例允许第二年
前处理与第一年积分并行，第二年积分则同时等待边界数据和完整 restart：

```bash
pre1=$(cd YEAR1_DIR && sbatch --parsable preprocess_1990.slurm)
run1=$(cd YEAR1_DIR && sbatch --parsable --dependency=afterok:$pre1 run_1990_8r.slurm)

pre2=$(cd YEAR2_DIR && sbatch --parsable preprocess_1991.slurm)
stage=$(cd YEAR2_DIR && sbatch --parsable --dependency=afterok:$run1 stage_restart_19910101.slurm)
run2=$(cd YEAR2_DIR && sbatch --parsable --dependency=afterok:$pre2:$stage run_1991_32r.slurm)

cd YEAR2_DIR
sbatch --dependency=afterok:$run2 analyze_1990_1992.slurm
sbatch --dependency=afterok:$run2 validate_drought_1990_1992.slurm
```

本次实际首年作业为 `39250713`、`39250715`、`39257234`；第二年作业为
`39257198`（前处理）、`39257199`（restart 暂存）、`39257200`（积分）、
`39257201`（PFT 分析）和 `39257404`（干旱递推分析）。所有正式作业均为
`COMPLETED 0:0`。

## 验收口径

至少要求：

1. 每年 2920 个三小时时次连续无缺口或重复；
2. 每段年末 CNDV 仅调用一次，`kyr` 分别为 1 和 2；
3. 第二段明确是 continuation，且不得再次写初始 CNDV HV；
4. PFT0—16 在每个 soil gridcell 上闭合为 100%，最大误差不超过 `1e-6` pp；
5. 同时刻 HV 与 restart 的 FPC/NIND 一致，restart 年度差与相邻 HV 差一致；
6. 年末 active-soil `drought_days` 全部归零；
7. 第二年 `drought_days20=(19*第一年值+第二年当年值)/20`。history 是
   float32，当前容差为 `5e-5` 天；restart 状态本身是双精度；
8. 日志不含真实 `FATAL`、NaN、Inf、MPI abort 或 SIGSEGV。

`FPCGRID` 是年度目标覆盖；实际用于通量耦合的 PFT 权重在随后一年内插。建立与
消亡必须优先使用相邻 restart 中精确的 `present` 标志，不能只用 HV 的
FPC/NIND 阈值代理。

## 不入库的内容

本目录 `.gitignore` 排除 NetCDF、输入/输出、日志和派生分析目录。它们体量较大且
含服务器绝对路径。仓库只保存可复现配置、代码、小型数值摘要和最终图表；原始文件
身份由报告中的 SHA-256 记录。
