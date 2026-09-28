# 年氮沉降进入碳氮库的代码证据

复核日期：2026-09-28。RegCM4.7 和 RegCM5 是两个独立版本；以下复核不将
RegCM4.7 视为 RegCM5 的分支。

## 实际执行链路

| 环节 | 两版行为 | 原始代码位置 |
|---|---|---|
| 地表预处理 | 读入 `NDEP_year`，只做插值/缺失值处理和非负截断；输出 `NDEP` 单位为 `g(N)/m2/yr` | `PreProc/CLM45/mod_mkndep.F90`、`mksurfdata.F90` |
| 地表到 column | `ndep(c) = ndep_in(g)`，没有换算年到秒 | `mod_clm_initimeconst.F90`：4.7 第 1060 行，5 第 1096 行 |
| 非化学通路 | 默认 `ndep_nochem=.true.`；`CNNDeposition` 直接令 `ndep_to_sminn(c)=ndep(c)` | `mod_clm_varctl.F90` 第 25 行、`mod_clm_cnndynamics.F90` 第 67 行 |
| 氮状态更新 | `dt=dtsrf`；`sminn_vr += ndep_to_sminn * dt * ndep_prof`；`dt` 单位为秒，`ndep_prof` 单位为 m⁻¹ | `mod_clm_cnnstateupdate1.F90` 第 301—322 行 |
| 化学耦合通路 | `ndep_to_sminn(c)=forc_ndep(g)`；该输入已标注为 gN m⁻² s⁻¹ | `mod_clm_cnndynamics.F90` 第 48、70—72 行 |
| 年到秒的参照实现 | 同一模块的 `CNNFixation` 使用 `secspday*dayspy` 换算 | `mod_clm_cnndynamics.F90` 第 112—131 行 |
| 日历年长度 | Gregorian/proleptic Gregorian 为 365.2422 天；noleap 为 365；360_day 为 360 | `Share/mod_dynparam.F90` 第 845—856 行 |
| 冷启动矿质氮 | `sminn(c)=0`、`sminn_vr(c,j)=0`；不是几万 gN m⁻² 的设定初值 | 两版 `mod_clm_cninitimevar.F90` 第 744—758 行 |

实际试验 `ichem=0`，执行非化学通路。输入 surface 的 `NDEP` 年率均值为
0.16808491552337634 gN m⁻² yr⁻¹；每秒率应为 5.3264033099188455×10⁻⁹
gN m⁻² s⁻¹。错误通路将输入放大 31,556,926.08 倍。

## 候选修正和未修改的部分

补丁 [regcm47_ndep_units.patch](regcm47_ndep_units.patch) 与
[regcm5_ndep_units.patch](regcm5_ndep_units.patch) 只做两处文本改动：

1. 从已有的 `mod_clm_varcon` 引入常数 `secspday`；
2. 在非化学分支将赋值改为 `ndep(c)/(secspday*dayspy)`。

没有改变化学输入分支、固氮通量、氮淋失、氮分配、生理参数、碳氮库冷启动设定、
PFT 初始覆盖、年度 CNDV 竞争/建立/死亡算法，也没有对任何 restart 的氮库做手工
清零、相减或替换。使用 365.2422 是为与模式已有年率约定一致；31 个自然日的
积分是年率乘 `31/365.2422`，而不是年率乘 `31/365`。

`regcm5_legacy_lai.patch` 是另一个独立单因素实验，只用于分离旧 LAI 公式的影响。
它不是氮沉降修正的一部分，也不是对区域调参的正式推荐。

基线程序保留；所有候选程序在服务器独立的 `build/` 和 `bin/` 中构建。
`results/regcm47_source_change.diff` 和 `results/regcm5_source_change.diff` 给出
基线与实验副本的源码校验值差异（检查 F90/f90/C/H/inc）；程序和地表文件的
校验值另行归档。

## 证据边界

量纲链路及 Fortran 子程序测试确认的是输入错误。模型对照确认它在一天/一个月
内对氮库与生理过程的实际影响；二者不能互相替代。

历史 `SMINN`、restart `sminn` 和自然 PFT 加权 `TOTVEGN` 的空间支撑及单位不同，
不能直接相加比较。历史单位保存在 `results/history_units.json`；restart 矿质氮
以土壤/作物 column 的 `cols1d_wtxy` 加权、除以 1193 个陆地格点得到贡献均值。
植被 C/N/LAI 是自然 PFT 1—14 按 `pfts1d_wtgcell` 加权后的格点均值，
未再除以自然植被面积比例。这里不是另行计算的地理面积加权平均。

一月份没有年度 CNDV 更新，不能凭本试验宣称多年植被已得到验证。旧错误输入下
产生的 restart 已包含状态和反馈的历史，不宜仅从其中扣掉矿质氮后接着做科学积分。

另外，两版 `mod_clm_cnbalancecheck.F90` 的碳与氮报错条件分别在第 180、338 行
带有 `.and. 1==2`，因此即使计算出较大误差也不会触发该守恒报错。本次没有改动
这个开关。已检验的 `NPP=GPP-AR` 只是植被生产力通量恒等式，不是生态系统全部
碳氮输入、输出和库变化的质量守恒验收；正常结束也不能替代这项验收。
