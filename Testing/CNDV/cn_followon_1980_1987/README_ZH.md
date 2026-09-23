# 1980–1987 CNDV 连续接续与碳氮库诊断

本试验从 `cndv_precise_onset_1979` 两个版本各自的 `1980-01-01 00:00`
重启状态接续，不重新初始化植被。`mdate0` 固定为原始冷启动日期
`1979-01-01`，因此 CNDV 年序号保持连续。

## 已完成结果

两版 128 核连续积分和统一分析均已完成。完整结论、逐年碳氮检查点、气象驱动
可比性、RegCM4.7 历史文件修复依据及解释边界见
[CONTINUOUS_CN_1980_1987_REPORT_ZH.md](CONTINUOUS_CN_1980_1987_REPORT_ZH.md)，
服务器作业号、门禁与校验哈希见
[SERVER_VALIDATION_EVIDENCE_ZH.md](SERVER_VALIDATION_EVIDENCE_ZH.md)。原始 CSV、JSON、
PNG 和 SHA-256 清单位于 [`results/`](results/)；可用
`sed 's#analysis/#results/#' results/result_sha256.txt | sha256sum -c -`
复核下载文件。

## 为什么先做双烟雾试验

CLM 的重启同时依赖 RegCM `SAV`、CLM `r` 以及三个历史重启文件
`rh0/rh1/rh2`。月度碳氮诊断会改变历史输出清单与频率，因此实际主试验先各跑
一个月、保持 1979 年逐日配置不变。另行执行的配置探测试验证了 CLM 会明确拒绝
在重启时改变历史字段数量，错误为：

`hist_restart_ncd ERROR: number of fields different than on restart file`

因此正式路径为：

1. `exact_smoke` 完全保留 1979 日输出配置；
2. 检查 `SAV/r/rh0/rh1/rh2` 和关键植被碳氮历史字段；
3. 门禁通过后，多年任务使用完全相同的历史配置。

植被碳氮库由逐日历史文件提取；凋落物、土壤、矿质氮和生态系统总库由完整
CLM 重启文件提取。这样不修改模型状态，也不绕过 CLM 的重启一致性保护。

## 多年连续积分

通过门禁后，RegCM4.7-CNDV 和 RegCM5-CNDV 分别使用 2 节点 × 64 MPI 进程，
从同一时刻连续积分到 `1987-01-01`。主试验不是逐年冷启动，也不是把独立年份
拼接起来；碳氮库、年累计 NPP、干旱记忆量和 CNDV 植被状态都沿时间连续传递。

重点诊断包括：

- 植被总碳/氮、叶、细根、木质部、贮存库与临时碳氮库（逐日）；
- 凋落物碳氮、土壤有机碳氮、生态系统总碳氮和矿质氮（完整重启检查点）；
- GPP、NPP、自养/异养呼吸、NEE、火灾碳通量以及植被氮吸收；
- FPC、个体密度、LAI、土壤水分和气象驱动。

生态系统库严格按两版共同的 `mod_clm_cnsummary.F90` 定义重建：
`TOTECOSYSC = CWD + litter + soil organic C + wood products + vegetation C`；
`TOTECOSYSN` 在对应有机氮库之外还包含 `SMINN`。植被氮使用叶、根、茎、粗根、
storage、transfer、`NPOOL` 和 `RETRANSN` 的源码同款求和。

多年 history 文件中的 `pfts1d_wtgcell` 没有时间维，不能表示 CNDV 期间持续变化的
PFT 面积。因而逐日 PFT 表统一使用 `1980-01-01` restart 权重，作为“固定初始面积”
过程诊断；区域实际植被 C/N、FPC 及生态系统库的长期结论只使用每个完整 restart
自身保存的当时权重。两类量在 CSV/JSON 字段名和报告中明确区分，不能混用。
年度 `hv` 文件中的 `FPCGRID` 另作 CNDV 目标覆盖，和 restart 中已经应用的 PFT
权重同时写入 `annual_cndv_fpc_targets.csv`，用于识别目标覆盖与实际面积调整的时滞。

## 目录和运行顺序

服务器目录：

`/public/home/elpt_2024_000795/workdir_for_RCM/cndv_cn_followon_1980_1987`

运行：

```bash
bash prepare_remote.sh
bash submit_followon.sh
```

提交脚本会先串行重建 RegCM4.7 修复版，再并行执行两版常规一个月 smoke 和
RegCM4.7 每日周期 restart 压力试验。只有 31 次关闭/重开成功、无 NetCDF 错误，
且压力试验与常规 smoke 的 `SAV`/CLM 数值状态逐变量一致后，才会启动多年任务。

`analysis/submitted_job_ids.txt` 保存作业号，`analysis/smoke_gate.txt` 保存重启门禁结果。
完成后生成逐日与年度碳氮表、restart 检查点表、审计摘要以及碳氮库时间序列图；分析作业只有在两个
版本都完整到达 `1987-01-01` 后才会执行。

## 科学解释边界

本段接续的是 1979 冷启动定位试验，不是完成平衡的 CN/CNDV spin-up。它适合观察
同一冷启动冲击之后碳氮库如何连续传递、何时达到极小值以及两版是否出现恢复，
不能把 7 年末状态直接当成稳定气候植被。初始 restart 的 `SMINN` 区域均值约为
`2.9e4 gN m-2`，远大于植被和土壤有机氮。因此结果必须把生态系统有机氮与矿质氮
分开报告；包含 `SMINN` 的 `TOTECOSYSN` 主要反映该异常初值，不能单独用来判断
植被氮限制或版本优劣。

## RegCM4.7 周期重启后的历史文件修复

RegCM4.7 在 `savfrq=365` 周期重启点会关闭 CLM 历史文件。旧代码只有在该时刻同时
为月末时才重新打开文件；1980 是闰年，365 天存档落在 `1980-12-31 00:00`，不是
月末，下一次写 `time` 便报 `NetCDF: Variable not found`。RegCM5 已包含正确逻辑。

回移的修复只改一处文件生命周期条件：

```fortran
! RegCM4.7 old
if ( .not. if_stop .and. nlomon ) then

! corrected, same as RegCM5
if ( .not. if_stop ) then
```

即所有非最终周期存档之后都重新打开历史文件。它不改变时间步进、物理过程、CNDV、
碳氮状态或输出字段。正式复测使用独立二进制 `regcmMPICN_CNDV_CLM45_histfix` 和
目录 `regcm47_full_fixed`，原始正式二进制及失败现场均保留以便审计。
