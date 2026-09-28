# 两版 CNDV 氮沉降单位与植被因果验证

本包核验地表年氮沉降如何进入逐秒碳氮通量，并以同一冷启动输入比较
RegCM4.7、RegCM5 和 RegCM5 的旧 LAI 单因素实验。基线安装程序及其既有结果保留；
候选修正在独立配置构建副本中编译，补丁与全部对照结果用于审查。

结果与边界见 [验证报告](NDEP_UNIT_VALIDATION_REPORT_ZH.md)，代码链路见
[代码证据](CODE_EVIDENCE_ZH.md)。本包只验证修正的一天/一个月效应，
不把它当作已完成年度 CNDV、自旋或生态系统总碳氮守恒的验收。

## 试验矩阵

| 版本 | 原版 | 只修正 NDEP 单位 | 只使用 4.7 LAI | 同时修正 NDEP 与使用 4.7 LAI |
|---|---|---|---|---|
| RegCM4.7 | 是 | 是 | — | — |
| RegCM5 | 是 | 是 | 是 | 是 |

六组设置各执行一天逐小时输出和一个月逐日输出，共 12 个 128 MPI 进程作业。
全部从 1979-01-01 冷启动，使用同一个地形、CLM surface、侧边界及 SST；
`ichem=0`，`calendar='gregorian'`。本月内没有年度 CNDV 更新，因此 history
中的静态 PFT 权重在该测试时段内可以用于过程比较。动态自然覆盖反馈的长期效果
需要另行从修正后的合格状态验证。

## 代码与量纲

原始 surface `NDEP` 的单位为 `g(N)/m2/yr`，区域均值为
`0.16808491552337634`。`CNNDeposition` 的非化学分支直接把年率赋给每秒通量，
`CNNStateUpdate1` 再乘以以秒计的时间步。候选补丁只将该赋值变为：

```fortran
ndep_to_sminn(c) = ndep(c) / (secspday * dayspy)
```

`dayspy` 来自模式日历，与 `CNNFixation` 的换算一致：Gregorian 为
365.2422、noleap 为 365、360_day 为 360。化学耦合输入原本已经是每秒通量，
该分支没有二次转换。

## 重现

服务器试验目录：
`/public/home/elpt_2024_000795/workdir_for_RCM/cndv_ndep_unit_validation_1979`

先将本包上传，再运行：

```bash
bash prepare_remote.sh
bash submit_experiments.sh
```

构建使用配置完成的 baseline 源目录副本，按串行顺序重建 Fortran 模块。
已有输出的试验目录会拒绝重新准备，避免混入旧结果。原始 1979 定位试验和软件模块
路径见各脚本。`analysis/submitted_jobs.txt` 保存实际作业号。
复现时请使用新的试验目录，并同步修改各服务器脚本中的 `root`；不要清理或覆盖
这里已经完成的输出。`BUILD47`、`BUILD5` 仅在已有对应构建作业时用于接续提交，
不是跳过编译校验的开关。

本地的实际 Fortran 子程序量纲测试：

```bash
python3 test_deposition_fortran.py \
  /path/to/RegCM-4.7.1/Main/clmlib/clm4.5/mod_clm_cnndynamics.F90 \
  /path/to/RegCM-cndv/Main/clmlib/clm4.5/mod_clm_cnndynamics.F90
```

测试抽取真实 `CNNDeposition`，使用最小状态容器编译运行；验证三个日历的年度
输入积分、零输入和化学分支的网格到 column 映射。

分析器校验完整时刻、原版/修正版通量与 surface 输入对应、NPP=GPP−AR 闭合，
并从完整 restart 中按土壤/作物列提取矿质氮。独立检查器直接读原始 NetCDF，
不用原分析聚合函数，复算 12 组的氮输入、FPG 最小记录值、累计 NPP、最终植被
C/N/LAI 和 restart 矿质氮。历史 `SMINN` 的字段单位与 restart 柱积分单位
可能不同，两者分别记录。

完成后运行 `bash capture_execution_evidence.sh` 保留作业状态、配置、二进制及
源码校验值、正常结束标记。下载的记录保存在 `results/`。其中
`test_definition_sha256.txt` 是准备阶段快照，`final_definition_sha256.txt` 是
分析器完善后的最终脚本快照；远端绝对路径校验表用于服务器复核，不应直接当作
本地路径表运行。
