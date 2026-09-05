# RegCM 4.7 CNDV 实现说明：改动、依据与边界

本文说明 packages 中 RegCM 4.7 归档的 CNDV 实现，回答三个问题：具体改了
什么、依据是什么、哪些内容没有修改。编译、安装、输入数据、前处理、运行和
restart 方法见 [RegCM 4.7 CNDV 安装与使用说明](CNDV_BUILD_AND_RUN_REGCM47_ZH.md)。

## 1. 源码身份和分支

本地源码目录为：

```text
/home/lwg/Desktop/update_regcm-cndv/RegCM-4.7.1
```

来源归档为：

```text
/home/lwg/Desktop/update_regcm-cndv/packages/RegCM-4.7.1.tar.gz
SHA256: c9be445bca6d01b706f0b8af14829fb260e483c852a92decdc9445c5a5c72ca9
```

该归档没有 Git 历史，因此本地建立了独立仓库：

- `vendor/regcm-4.7.1`：原始归档导入，基线提交 `c828848`；
- `feature/regcm47-cndv`：本次 CNDV 实现分支。

需要注意，归档文件名是 `RegCM-4.7.1.tar.gz`，但其中
[configure.ac](../configure.ac) 的 `AC_INIT` 写作 4.7.0，README 又称其为
“4.8 release candidate”。因此本文把它称为“packages 提供的 RegCM 4.7
归档”，不宣称它与某个官方标签逐字节相同。复现实验应同时记录归档校验和和
本地提交哈希。

## 2. 实现目标与科学依据

本分支利用归档中已经存在的 CLM4.5、碳氮循环（CN）和动态植被（CNDV）框架，
完成以下工作：

1. 增加正式的 `--enable-cndv` 配置入口；
2. 实现论文所述的 RefinedCN 胁迫落叶物候；
3. 实现 ModifiedDV 干旱季长度和热带常绿阔叶树生存限制；
4. 补齐新状态的分配、初始化、年度更新、history 和 restart；
5. 修复启用现有 CNDV 路径后发现的两项 FPC 逻辑问题和一项并行构建依赖。

主要科学依据是：

> G. Wang et al., *On the development of a coupled regional
> climate–vegetation model RCM–CLM–CN–DV and its validation in Tropical
> Africa*, Climate Dynamics 46, 515–539 (2016), online publication 2015,
> DOI: [10.1007/s00382-015-2596-z](https://doi.org/10.1007/s00382-015-2596-z)。

本次直接新增的科学逻辑对应论文第 2.3.2 和 2.3.3 节。用户提供的
RegCM4.3.4 可工作源码和补丁只用于交叉核对，不作整文件复制，因为其中部分
实现与论文正文不完全一致，并含未赋值索引等缺陷。

## 3. ModifiedDV 数据流

新增状态位于 CLM column 层级：

1. 每个陆面时间步计算活动自然土壤 column 的顶部三层土壤水势；
2. 若三层中最湿层仍严格低于 `-2 MPa`，按 `dtsrf/86400` 累计当年干旱天数；
3. 日历年末把当年值更新到长期量，然后清零当年累计；
4. 每个 PFT 通过 `pcolumn(p)` 映射到所属 column；
5. 热带常绿阔叶树的长期干旱量大于 45 天时，禁止生存和建立；
6. 两个状态进入 CLM restart，并可按需加入 CLM history。

## 4. 具体修改

### 4.1 正式 CNDV 配置开关

修改 [configure.ac](../configure.ac)：

- 新增 `--enable-cndv`；
- 只接受 `yes` 或 `no`；
- 启用时自动加入 `-DCN -DCNDV`；
- 未同时给出 `--enable-clm45` 时立即报错；
- 不新增运行时 namelist 开关。

正确配置组合是：

```text
--enable-clm45 --enable-cndv
```

旧版 `--enable-clm` 对应 CLM3.5，不用于本实现。也不需要在 configure 后手工
编辑生成的 Makefile。

### 4.2 RefinedCN 胁迫落叶物候

修改
[mod_clm_cnphenology.F90](../Main/clmlib/clm4.5/mod_clm_cnphenology.F90)
中的 `CNStressDecidPhenology`。

| 项目 | 归档基线 | 当前实现 | 依据 |
| --- | --- | --- | --- |
| 展叶水势 | 固定读取第 3 层 | 顶部三层的最干值 `minval` | 论文 §2.3.2 |
| 衰老水势 | 固定读取第 3 层 | 顶部三层的最湿值 `maxval` | 论文 §2.3.2 |
| 水势阈值 | `-2 MPa` | 不变 | 论文 §2.3.2 |
| 连续触发期 | 15 天 | 不变 | 论文 §2.3.2 |
| 展叶完成期 | 30 天 | 不变 | 论文 §2.3.2 |
| 胁迫落叶完成期 | 15 天 | 30 天 | 论文 §2.3.2 |
| 季节性落叶完成期 | 15 天 | 15 天，不受影响 | 限定论文修改范围 |

土壤水势是负数，数值越负表示越干。因此：

- 展叶用 `minval`，要求最干层也达到湿润阈值；
- 落叶用 `maxval`，要求最湿层也低于干旱阈值。

实现用 `lbound`/`ubound` 安全截取最多三层。落叶时间新增独立参数
`ndays_off_stress=30`，没有把季节性落叶植被的 15 天参数一起改变。

### 4.3 ModifiedDV 年度干旱时长

相关文件：

- [mod_clm_type.F90](../Main/clmlib/clm4.5/mod_clm_type.F90)：新增
  `drought_days` 和 `drought_days20`；
- [mod_clm_typeinit.F90](../Main/clmlib/clm4.5/mod_clm_typeinit.F90)：分配并
  初始化新状态；
- [mod_clm_cndvecosystemdynini.F90](../Main/clmlib/clm4.5/mod_clm_cndvecosystemdynini.F90)：
  CNDV 冷启动初始化；
- [mod_clm_hydrology2.F90](../Main/clmlib/clm4.5/mod_clm_hydrology2.F90)：
  逐陆面时间步累计；
- [mod_clm_cndv.F90](../Main/clmlib/clm4.5/mod_clm_cndv.F90)：年末更新；
- [mod_clm_driver.F90](../Main/clmlib/clm4.5/mod_clm_driver.F90)：向年度例程
  传递 column 边界。

干旱判据为：

```text
max(soilpsi(c, top 3 layers)) < -2 MPa
```

这里的 `max` 是三层中的最湿值。最湿层仍低于阈值，等价于三层全部低于阈值。
比较采用严格小于号，对应论文的 “below -2 MPa”。累计只作用于 `cactive` 且
landunit 类型为 `istsoil` 的 column，不把湖泊、冰川、城市表面或独立 crop
landunit 计入自然植被干旱统计。

长期量沿用本版本原有 `tmomin20`、`agdd20` 的递推约定：

```text
首个年末样本： drought_days20 = drought_days
后续年末样本： drought_days20 =
              (19 * drought_days20 + drought_days) / 20
```

`drought_days20=-1` 表示尚无完整年末样本，避免在 restart 后根据模拟年份编号
覆盖已恢复状态。该算法是 20 年权重的递推平滑，不是保存最近 20 个年度样本的
严格有限滑动窗口，分析结果时必须保留这一差别。

### 4.4 热带常绿阔叶树生存限制

修改
[mod_clm_cndvestablishment.F90](../Main/clmlib/clm4.5/mod_clm_cndvestablishment.F90)：

- 通过 `pcolumn(p)` 获取 PFT 所属 column；
- 通过命名常量 `nbrdlf_evr_trp_tree` 定位目标 PFT，不硬编码编号 4；
- 当 `drought_days20 > 45 days` 时，同时令 `survive=.false.` 和
  `estab=.false.`。

严格大于 45 天对应论文 §2.3.3 的“长于 45 天”。规则没有扩展到其他树、灌木
或草本 PFT。45 天是论文采用的经验约束，不应解释为未经验证即可适用于所有
地区的普适生态阈值。

### 4.5 初始化、history 与 restart

修改：

- [mod_clm_cnsetvalue.F90](../Main/clmlib/clm4.5/mod_clm_cnsetvalue.F90)；
- [mod_clm_histflds.F90](../Main/clmlib/clm4.5/mod_clm_histflds.F90)；
- [mod_clm_cnrest.F90](../Main/clmlib/clm4.5/mod_clm_cnrest.F90)。

行为如下：

- `drought_days` 和 `drought_days20` 自动写入并恢复自 CLM restart；
- 旧 restart 缺少新字段时发出警告，分别以 0 和 -1 初始化，而不是立即终止；
- 新增可选 history 字段 `DROUGHT_DAYS`、`DROUGHT_DAYS20`，单位均为天；
- 两个 history 字段默认 `inactive`，必须由用户显式请求；
- 特殊 column 的统一赋值流程包含新字段，避免未定义值进入输出。

如果从不含新字段的旧 restart 在年中启动，第一次年末样本只覆盖 restart 后的
部分年份。正式试验应从年初启动新统计，或重新完成一致的 spin-up。

### 4.6 现有 CNDV 工程问题修复

这些修复不是论文新参数化。

1. [Makefile.am](../Main/clmlib/clm4.5/Makefile.am) 为
   `mod_clm_cndvecosystemdynini.o` 增加 `mod_clm_atmlnd.o` 依赖，避免并行编译
   时缺少 `.mod` 文件。
2. [mod_clm_cndvestablishment.F90](../Main/clmlib/clm4.5/mod_clm_cndvestablishment.F90)
   修正新建立 PFT 的 seed FPC：木本为 `0.000844`，非木本为 `0.05`。基线的
   判断与旧可工作实现及相邻注释含义相反。
3. [mod_clm_cndvlight.F90](../Main/clmlib/clm4.5/mod_clm_cndvlight.F90)
   把 shrub 总 FPC 超额按各 shrub PFT 覆盖比例分摊。原公式得到无量纲比例却
   直接从 FPC 中扣除；新公式量纲一致，并使调整后的总量回到上限。

与 RegCM5 不同，本归档的 `mod_clm_cndecompcascadebgc.F90` 已把
`implicit none` 放在合法位置，因此没有移植 RegCM5 针对该文件的预处理修复。

## 5. 与 RegCM4.3.4 参考实现的差异

| 4.3.4 参考代码情况 | 当前处理 |
| --- | --- |
| 声称顶部三层，但第三层代码被注释，实际只用两层 | 明确使用顶部三层 |
| 某版本把胁迫落叶型展叶期设成 60 天 | 按论文保留 30 天 |
| 手工修改生成的 Makefile | 增加正式 `--enable-cndv` |
| 手工设置 `MAXPATCH_PFT=17` | 不采用；CLM4.5 使用 `numpft+1` |
| 用固定常数初始化长期干旱量 | 使用 -1 标志和首个年末样本 |
| 以 `ivt==4` 判断目标树种 | 使用 PFT 命名常量 |
| establishment 中使用未赋值的 column 索引 | 显式使用 `pcolumn(p)` |

所以本分支是按论文语义和 4.7 接口进行的组件级移植，不保证与旧补丁
bit-for-bit 一致。

## 6. 明确没有修改的内容

- 没有回拷或重写论文的 GPP 模块。该归档已经包含 CLM4.5 冠层辐射、光合与
  气孔方案，本次没有相关 tracked diff。
- 没有改动 RegCM 大气动力、积云、PBL、微物理、辐射或海洋方案。
- 没有改变常规 CN 分解、碳氮分配、火灾、背景死亡和 gap mortality 公式。
- 没有加入新的植物水力学、根系适应、显式水力死亡或物种演化机制。
- 没有改变 `-2 MPa`、15 天触发期、45 天阈值或 PFT 生理参数数据。
- 没有修改 terrain、SST、ICBC 或 CLM4.5 surface 数据的科学内容。
- 没有增加运行时 CNDV 开关；关闭 CNDV 需要重新配置和构建。
- 没有解除 CNDV 与 `DYNPFT`、独立 crop landunit 的既有不兼容限制。
- 没有实现严格的 20 年年度样本队列。
- 没有复现论文的热带非洲实验、spin-up、观测对比或统计检验。

因此准确表述是：“在 RegCM 4.7 归档已有 CLM4.5/CN/CNDV 框架上实现了论文
RefinedCN 和 ModifiedDV 的关键逻辑”，而不是“已经复现论文全部科学结果”。

## 7. 工程验证与边界

### 7.1 本机 GNU 构建

本机已完成：

- `./bootstrap.sh`；
- CNDV 依赖 CLM4.5 的负向配置测试；
- 配置结果确认含 `-DCLM45 -DCN -DCNDV`；
- GNU/OpenMPI/NetCDF 环境下从干净状态全量串行 `make`；
- `make install`，本机 GNU Make 4.4 安装的主程序为
  `install-cndv/bin/regcmMPICN`；
- `make check`（该归档没有实质性自动测试用例）；
- `ldd` 检查，无缺失动态库；
- 二进制字符串检查，包含新增 history/restart 字段。

本归档的部分非 CNDV Fortran 模块依赖声明不完整；干净状态 `make -j4` 曾在
`Main/ocnlib` 因并发生成同一 `.mod` 文件而失败，所以安装文档推荐串行
`make`。这不影响上述串行构建成功结论，也不应被误报为 CNDV 科学代码错误。

安装结果应以实际文件为准，不能依据旧文档猜测短后缀：

```bash
find install-cndv/bin -maxdepth 1 -type f -printf '%f\n' | sort
test -x install-cndv/bin/regcmMPICN
ldd install-cndv/bin/regcmMPICN
strings install-cndv/bin/regcmMPICN | \
  grep -E 'DROUGHT_DAYS|DROUGHT_DAYS20'
```

### 7.2 `huan` 集群的版本隔离部署

服务器部署的是本 RegCM4.7 仓库快照，而不是 RegCM5 的分支或安装覆盖。其
版本隔离根目录是：

```text
/public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv
├── source/
├── install/
└── logs/
```

服务器构建显式使用以下一致模块栈：

```bash
export LANG=C LC_ALL=C
module purge
module load compiler/intel/2021.3.0
module load mpi/intelmpi/2021.3.0
module load mathlib/hdf5/intel/1.8.20
module load mathlib/netcdf/intel/4.4.1
module load mathlib/zlib/intel/1.2.11
hash -r
```

由于该归档的 VPATH 规则和部分旧 Fortran 模块依赖不完整，服务器必须在
`source/` 内执行 in-source configure，并使用串行 `make`/`make install`：

```bash
root=/public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv
cd "$root/source"
printf '%s\n' 'fbc6c6a2bd015a8565bc642ce768ba2416089095' > tag
./bootstrap.sh
CC=icc FC=ifort MPIFC=mpiifort ./configure \
  --prefix="$root/install" \
  --enable-clm45 --enable-cndv \
  --with-netcdf=/public/software/mathlib/libs-intel/netcdf/4.4.1 \
  --with-hdf5=/public/software/mathlib/libs-intel/hdf5/1.8.20
make version
make >"$root/logs/make.log" 2>&1
make install >"$root/logs/install.log" 2>&1
find "$root/install/bin" -maxdepth 1 -type f -printf '%f\n' | sort
```

服务器现有 PnetCDF 属于不同 Intel MPI 构建组合，因此本部署明确不使用
`--enable-pnetcdf` 或 `--enable-parallel-nc`。这只是 ABI/构建边界，不改变
CNDV 科学实现；MPI 主程序仍可使用上述普通 NetCDF 库。

曾尝试的 out-of-source/VPATH 构建以及 `make -j4` 并行构建暴露的是旧构建系统
的路径或依赖顺序问题，不能据此归因为 RefinedCN/ModifiedDV 算法错误。本次
正式验收只认 in-source 串行构建的退出码、安装清单、`ldd` 结果和二进制字段。

### 7.3 服务器 smoke test 状态与验收边界

RegCM4.7 使用独立运行目录：

```text
/public/home/elpt_2024_000795/workdir_for_RCM/cndv_smoke_regcm47_fbc6c6a
```

其中 `preprocess.slurm` 使用 1 task 调用带完整 `CN_CNDV_CLM45` 后缀的四个
前处理程序，`run.slurm` 使用 4 MPI tasks 调用
`regcmMPICN_CNDV_CLM45`。两个作业均加载第 7.2 节的相同模块栈；前处理作业
成功后才以 `afterok` 依赖提交积分作业。历史
`/public/home/elpt_2024_000795/workdir_for_RCM/regcm5_run` 属于不同版本且现有
内容不足以作为本测试输入，所以不复用也不修改。

smoke namelist 显式设置 `create_crop_landunit=.false.`，并请求
`DROUGHT_DAYS`、`DROUGHT_DAYS20` 日输出。验收至少包括：

- Slurm 状态 `COMPLETED` 且退出码 `0:0`；
- DOMAIN、CLM45 surface、SST 和指定时刻 ICBC 均非空且通过 `ncdump -h`；
- 日志明确到达前处理和模型脚本结尾，并且无 `NaN`、`SIGSEGV`、`FATAL` 或
  MPI abort；
- CLM history-restart/年度 CNDV 文件存在，并能找到请求的干旱字段。

实际服务器验收结果为：原位串行 `make`、`make install`、`make check` 均返回
0；安装主程序 SHA256 为
`ddd562a74732d43de28996138b30756dd2ed4a54614e680eb28e109f9436dacd`，
`ldd` 无缺库，构建宏和新增字段均核对通过。前处理作业 `39224095` 为
`COMPLETED 0:0`；4 MPI rank、24 小时积分作业 `39224117` 也为
`COMPLETED 0:0`。8 个输出 NetCDF 均可读，restart/history-restart 中找到两项
干旱状态/诊断，年度 CNDV 文件中找到 `FPCGRID` 和 `NIND`，日志有明确完成标记
且未发现 NaN、段错误、FATAL 或 MPI abort。

这些结果证明当前源码能配置、编译、链接、安装、完成前处理并在多 MPI rank 下
做短程积分，但尚未证明科学结果正确。仍需跨年年度更新、restart 往返、长期
spin-up、热带非洲基准和观测对比。首个完整年结束后长期量就取该年值，代码不会
自动等待积累满 20 个年度样本；稳定植被分布仍依赖足够长的连续积分。

## 8. 与 RegCM5 文档的关系

RegCM5 和本 RegCM4.7 归档分别保留独立源码、分支、安装目录和说明文档。两者
科学规则一致，但构建兼容参数、可执行程序集合和少量源码接口不同。不要把 4.7
的 GNU 兼容参数或旧手册程序名机械套用到 RegCM5。RegCM5 的实现位于独立的
[RegCM5-cndv 仓库](https://github.com/weiguang1233/RegCM5-cndv)，不是本
RegCM4.7 分支的子分支或升级分支。
