# RegCM 4.7 CNDV 安装与使用说明

本文面向 packages 提供的 RegCM 4.7 归档，说明 Linux 下的配置、编译、安装、
数据准备、前处理、耦合运行、诊断和 restart。代码改动、科学依据及未修改范围见
[RegCM 4.7 CNDV 实现说明](CNDV_IMPLEMENTATION_REGCM47_ZH.md)。

## 1. 两个必须先明确的事实

1. CNDV 是编译期功能。必须用 `--enable-clm45 --enable-cndv` 构建，并运行该
   构建生成的程序；namelist 中不存在 `enable_cndv=.true.`。
2. 本次安装的程序名以 `CN` 为后缀，例如 `regcmMPICN`。这是本版本
   `makeinc` 的命名方式；实际编译参数同时包含 `-DCLM45 -DCN -DCNDV`，不能
   因文件名只有 `CN` 就认为 CNDV 未启用。

以下命令假定源码位于：

```text
/home/lwg/Desktop/update_regcm-cndv/RegCM-4.7.1
```

## 2. 选择本地分支

```bash
cd /home/lwg/Desktop/update_regcm-cndv/RegCM-4.7.1
git switch feature/regcm47-cndv
git branch --show-current
git status --short
```

本仓库由无 Git 历史的归档本地初始化。`vendor/regcm-4.7.1` 保存导入基线，
`feature/regcm47-cndv` 保存本次实现。归档身份和 SHA256 见实现说明。

## 3. 软件依赖和本机环境

至少需要：

- C 和 Fortran 编译器；
- GNU Make；
- Autoconf、Automake、Libtool；
- MPI 编译包装器和运行器；
- NetCDF-C、NetCDF-Fortran 及其开发文件；
- HDF5、zlib 和 NetCDF 的相关依赖；
- Git。

本机已经验证：GCC/GFortran 15.2、GNU Make 4.4、Autoconf 2.72、Automake
1.18、OpenMPI 5.0、NetCDF-C 4.9、NetCDF-Fortran 4.6、HDF5 serial 1.14。
NetCDF 可以是 serial 构建，RegCM 主程序仍可使用 MPI；本机没有 parallel
NetCDF/PnetCDF，因此没有启用相应选项。

### 3.1 避免本机 Conda 包装器

本机 Anaconda 目录中的 `mpicc`、`mpifort` 和 HDF5 包装器指向不存在的 Conda
编译器，因此下面显式使用系统工具：

```text
PATH=/usr/bin:/bin
CC=/usr/bin/gcc
FC=/usr/bin/gfortran
MPICC=/usr/bin/mpicc
MPIFC=/usr/bin/mpifort
```

不要在一次构建中混用不同编译器族生成的 `.mod`、NetCDF-Fortran 和 MPI。

### 3.2 新版 GNU Fortran 的兼容参数

该老归档含旧式 BOZ 常量、跨调用参数和有符号 32 位常量写法。GFortran 15
构建需使用：

```text
-fallow-invalid-boz -fallow-argument-mismatch -fno-range-check
```

这些参数用于兼容原有 RegCM4.7/RRTMG 源码，不改变本次 CNDV 科学算法。它们
是 GNU Fortran 选项，不可直接用于 Intel 编译器。若使用 Intel 工具链，应让
MPI、NetCDF-Fortran 和主编译器保持 ABI 一致，并重新完整构建；本机未验证
Intel 版本。

## 4. 配置、编译和安装

### 4.1 生成 Autotools 文件

```bash
cd /home/lwg/Desktop/update_regcm-cndv/RegCM-4.7.1
env PATH=/usr/bin:/bin ./bootstrap.sh
```

当 `configure.ac` 或 `Makefile.am` 改变后也应重新执行。出现
`AC_HELP_STRING is obsolete` 一类警告是该旧构建系统与新版 Autoconf 的兼容
提示，本次生成过程能够成功完成。

### 4.2 配置 CNDV

```bash
cd /home/lwg/Desktop/update_regcm-cndv/RegCM-4.7.1
env PATH=/usr/bin:/bin \
  CC=/usr/bin/gcc \
  FC=/usr/bin/gfortran \
  MPICC=/usr/bin/mpicc \
  MPIFC=/usr/bin/mpifort \
  FCFLAGS='-O2 -fallow-invalid-boz -fallow-argument-mismatch -fno-range-check' \
  ./configure \
    --enable-clm45 \
    --enable-cndv \
    --with-netcdf=/usr \
    --prefix="$PWD/install-cndv"
```

约束：

- 必须使用 `--enable-clm45`，不是 CLM3.5 的 `--enable-clm`；
- `--enable-cndv` 自动加入 `-DCN -DCNDV`；
- 不要同时定义 `DYNPFT`；
- 不要手工修改生成的 `Main/clmlib/clm4.5/Makefile`；
- 不要加入旧 4.3.4 方法中的 `-DMAXPATCH_PFT=17`，本版本 CLM4.5 已由
  `numpft+1` 计算相应维数；
- 不要在本机加入 `--enable-parallel-nc` 或 `--enable-pnetcdf`。

NetCDF 不在 `/usr` 时，应把 `--with-netcdf` 改成真实前缀。

### 4.3 编译和安装

```bash
make version
make
make install
make check
```

这里建议使用串行 `make`。本归档部分旧式 Fortran 模块依赖没有完整写入
Makefile；本机从干净状态执行 `make -j4` 时曾在 `Main/ocnlib` 发生多个编译
任务同时生成同一 `.mod` 文件的竞态。该问题不在 CNDV 模块中，但会让全量
并行构建偶发失败。增量构建或补齐全部模块依赖后可以再尝试 `make -jN`。

切换编译器、预处理宏或关键编译参数后，先执行：

```bash
make clean
```

再重新配置并完整编译。旧 4.3.4 中进入 `Main/radlib` 继续 make 的绕行步骤不是
本分支的标准流程；本次已在顶层从干净状态完成全量串行构建。

本归档的 `make check` 没有实质性自动测试用例，显示“Nothing to be done”只说明
检查目标成功返回，不能替代真实模拟。

### 4.4 核实 CNDV 确实启用

```bash
./configure --help | grep enable-cndv
grep '^AM_CPPFLAGS' Main/clmlib/clm4.5/Makefile
find install-cndv/bin -maxdepth 1 -type f -printf '%f\n' | sort
ldd install-cndv/bin/regcmMPICN
strings install-cndv/bin/regcmMPICN | \
  grep -E 'DROUGHT_DAYS|drought_days|CNDV called'
```

应看到：

- `AM_CPPFLAGS` 含 `-DCLM45 -DCN -DCNDV`；
- `ldd` 没有 `not found`；
- 二进制含 `DROUGHT_DAYS`、`DROUGHT_DAYS20` 和 CNDV 年度调用信息。

## 5. 安装后的程序

本机 `install-cndv/bin` 中与标准耦合试验直接相关的程序为：

| 程序 | 用途 |
| --- | --- |
| `terrainCN` | 生成区域 DOMAIN 和土地利用文件 |
| `mksurfdataCN` | 生成 CLM4.5 区域 surface 文件 |
| `sstCN` | 生成区域 SST 文件 |
| `icbcCN` | 生成大气初始和侧边界文件 |
| `regcmMPICN` | 大气—CLM4.5—CN—DV 耦合积分 |
| `interpinicCN` | 在已有新网格 restart 中插入/插值旧 CLM 状态 |
| `chem_icbcCN` | 仅化学试验需要的边界前处理 |
| `clm45_1dto2dCN` | CLM4.5 一维子网格输出转换工具 |

该 4.7 归档没有 RegCM5 中的 `clmbcCN` 和 `clmsaMPICN`，不要把 RegCM5 的
独立 CLM 流程套用到本版本。旧用户手册中的 `regcmMPICLM45` 也不是本次安装的
实际文件名，应以 `install-cndv/bin` 为准。

## 6. 输入数据布局

全局数据根建议至少包含：

```text
REGCM_DATA/
├── SURFACE/
├── CLM45/
│   ├── megan/
│   ├── pftdata/
│   │   └── pft-physiology.c130503.nc
│   ├── snicardata/
│   │   ├── snicar_optics_5bnd_c090915.nc
│   │   └── snicar_drdt_bst_fit_60_c070416.nc
│   └── surface/
├── SST/                   # 视 ssttyp 而定
└── EIN15/                 # 或 dattyp 对应的其他大气资料目录
```

- `terrainCN` 从 `inpter/SURFACE` 读取高程、土地利用和土壤资料；
- `mksurfdataCN` 从 `inpglob/CLM45/surface` 等子目录读取 CLM4.5 全球资料；
- 模型从 `inpglob/CLM45/pftdata` 和 `inpglob/CLM45/snicardata` 解析三个
  CLM 文件名；
- `mksurfdataCN` 输出 `${dirglob}/${domname}_CLM45_surface.nc`；
- SST 和大气资料目录由 `ssttyp`、`dattyp` 与数据集版本决定。

原始说明见 [ObtainData.tex](UserGuide/ObtainData.tex)。其中旧下载站点可能已经
变化；正式试验应保存输入文件清单、来源、版本和校验和。

## 7. 建立试验目录和 namelist

建议将源码、全局数据、区域前处理文件和结果分开：

```bash
export REGCM47_SRC=/home/lwg/Desktop/update_regcm-cndv/RegCM-4.7.1
export REGCM47_PREFIX="$REGCM47_SRC/install-cndv"
export REGCM47_DATA=/path/to/RegCM_Data
export REGCM47_RUN=/path/to/run-regcm47-cndv

mkdir -p "$REGCM47_RUN/input" "$REGCM47_RUN/output"
cp "$REGCM47_SRC/Testing/test_001.in" "$REGCM47_RUN/regcm-cndv.in"
cd "$REGCM47_RUN"
```

编辑 `regcm-cndv.in`。下列片段只突出 CNDV 相关关键项，区域、日期和物理方案
仍须按实际试验设置。

### 7.1 网格、路径和日期示例

```fortran
&dimparam
  iy  = 34,
  jx  = 64,
  kz  = 18,
  nsg = 1,
/

&terrainparam
  domname = 'test_001',
  dirter  = 'input/',
  inpter  = '/path/to/RegCM_Data',
/

&globdatparam
  dattyp  = 'EIN15',
  ssttyp  = 'OI_WK',
  gdate1  = 1990060100,
  gdate2  = 1990070100,
  dirglob = 'input/',
  inpglob = '/path/to/RegCM_Data',
/

&restartparam
  ifrest = .false.,
  mdate0 = 1990060100,
  mdate1 = 1990060100,
  mdate2 = 1990060600,
/

&outparam
  ifsave = .true.,
  savfrq = 0.,
  dirout = 'output/',
/
```

`EIN15` 和 `OI_WK` 只是归档自带 test_001 的示例，必须与实际输入数据一致。
CLM4.5 使用 `nsg=1`。`dirglob` 同时存放 SST、ICBC 和生成的 CLM4.5 surface
文件。

### 7.2 CNDV 必需和建议的 CLM 配置

```fortran
&clm_inparm
  fpftcon = 'pft-physiology.c130503.nc',
  fsnowoptics = 'snicar_optics_5bnd_c090915.nc',
  fsnowaging = 'snicar_drdt_bst_fit_60_c070416.nc',

  create_crop_landunit = .false.,

  hist_nhtfrq = 0,
  hist_fincl1 = 'DROUGHT_DAYS:I', 'DROUGHT_DAYS20:I',
/

&clm_soilhydrology_inparm
  h2osfcflag = 1,
  origflag = 0,
/

&clm_hydrology1_inparm
  oldfflag = 0,
/

&clm_regcm
  enable_megan_emission = .false.,
  enable_urban_landunit = .true.,
  enable_more_crop_pft = .false.,
  enable_dv_baresoil = .false.,
  enable_cru_precip = .false.,
/
```

关键说明：

- `create_crop_landunit` 默认是 `.true.`，CNDV 必须显式设为 `.false.`，否则
  模型会主动终止；
- `enable_dv_baresoil` 不是 CNDV 开关。`.false.` 使用 surface 文件中的初始
  植被权重；`.true.` 从裸地开始，通常需要更长 spin-up；
- `DROUGHT_DAYS` 和 `DROUGHT_DAYS20` 默认不输出，必须用 `hist_fincl*` 请求；
- `hist_nhtfrq=0` 表示月输出；负值按小时频率解释，例如 `-24` 为日输出；
- CNDV 与独立 crop landunit、`DYNPFT` 不兼容。

默认 `hist_dov2xy=.true.`，column 字段会映射/平均到二维网格。若需要保存 column
维度，可在 `clm_inparm` 中设置：

```fortran
hist_dov2xy = .false.,
hist_type1d_pertape = 'COLS',
```

## 8. 标准前处理和耦合运行

在试验目录按顺序执行：

```bash
"$REGCM47_PREFIX/bin/terrainCN" regcm-cndv.in
"$REGCM47_PREFIX/bin/mksurfdataCN" regcm-cndv.in
"$REGCM47_PREFIX/bin/sstCN" regcm-cndv.in
"$REGCM47_PREFIX/bin/icbcCN" regcm-cndv.in
/usr/bin/mpirun -np 4 \
  "$REGCM47_PREFIX/bin/regcmMPICN" regcm-cndv.in
```

预期关键文件包括：

```text
input/test_001_DOMAIN000.nc
input/test_001_LANDUSE
input/test_001_CLM45_surface.nc
input/test_001_SST.nc
input/test_001_ICBC.YYYYMMDDHH.nc
```

MPI 进程数应与网格大小匹配。可用 `njxcpus`、`niycpus` 指定二维分解，并确保
两者乘积等于 MPI rank 数。当前 Codex 沙箱可能限制多进程 OpenMPI 的网络接口
枚举；这种沙箱报错不等同于编译失败，应在正常终端或作业调度系统中运行。

`interpinicCN` 不是每个新试验的标准步骤。它用于把旧 CLM 初始/restart 状态
插入一个已经存在的新网格 restart 文件，调用形式为：

```bash
"$REGCM47_PREFIX/bin/interpinicCN" old.r.nc new.r.nc
```

两个文件都必须存在，使用前应备份并检查网格/PFT 权重是否确实需要转换。

## 9. 输出和 CNDV 诊断

新增诊断：

- `DROUGHT_DAYS`：当前日历年已累计的干旱时长，单位天；
- `DROUGHT_DAYS20`：20 年权重的递推长期量，单位天。

CLM history 文件由 `dirout`、`caseid`、实例后缀和日期组成。CNDV 还会自动写
年度 `.hv.YYYY.nc` 文件，其中包含 `FPCGRID` 和 `NIND`。建议正式试验同时
保存：

- LAI、GPP/NPP、植被碳和土壤水势；
- `DROUGHT_DAYS`、`DROUGHT_DAYS20`；
- 年度 `FPCGRID`、`NIND`；
- 使用的 namelist、PFT 参数文件和代码提交哈希。

短试验只能验证程序链路，不能验证 20 年气候约束和植被竞争平衡。

## 10. Restart

RegCM restart 的基本步骤：

1. 前一段保持 `ifsave=.true.`，用 `savfrq` 控制保存频率，0 表示月保存；
2. 继续积分时设 `ifrest=.true.`；
3. `mdate0` 保持整个试验最初日期不变；
4. 把新的 `mdate1` 设为上一段 `mdate2`，再设置新的 `mdate2`；
5. 保留同一日期的 RegCM SAV、CLM restart 和 CLM history-restart 文件。

新状态会自动进入 CLM restart，无需额外开关。检查文件可用：

```bash
ncdump -h output/*.clm.*.r.*.nc | \
  grep -E 'drought_days|drought_days20'
```

从本分支生成的新 restart 应含两个字段。旧 restart 缺字段时会警告并使用
0/-1 初始化；若旧 restart 日期不是年初，第一次年末干旱样本不是完整年度，
不适合直接作为正式长期试验的统计起点。

## 11. Spin-up 和试验建议

1. 先做数天短积分，检查 NaN、守恒错误、输出字段和日志；
2. 做跨月和跨年的小域测试，确认年度 `.hv` 文件与干旱累计清零；
3. 做 restart 往返，对比分段和连续积分；
4. 再进行足够长的 CN/CNDV spin-up；
5. 最后做目标时段试验和观测验证。

`drought_days20` 采用 `(19*old+current)/20` 递推平滑，不是严格的最近 20 年
样本队列；首个年末样本会立即成为长期值，代码不会自动等待 20 年后才应用
45 天限制。这些实现细节应写入实验方法。

## 12. 常见故障

### `--enable-cndv requires --enable-clm45`

配置命令缺少 `--enable-clm45`。两个选项必须同时给出。

### BOZ、integer too big 或参数不匹配错误

使用 GFortran 10 及以上时检查 `FCFLAGS` 是否包含本机验证的三项兼容参数。改变
参数后执行 `make clean` 再完整构建。

### 找不到 MPI/NetCDF 或链接到 Conda

检查：

```bash
command -v gcc gfortran mpicc mpifort mpirun nf-config nc-config
nf-config --all
nc-config --all
```

本机应显式使用 `/usr/bin` 工具。不要把不同编译器 ABI 的 NetCDF-Fortran 和
主程序混在一起。

### `CNDV mode cannot work with create_crop_landunit = T`

在 `&clm_inparm` 中加入：

```fortran
create_crop_landunit = .false.,
```

### 缺少 CLM45 surface 或 PFT/SNICAR 文件

确认先运行 `mksurfdataCN`，并检查 `inpglob/CLM45/{surface,pftdata,snicardata}`
目录以及 `dirglob` 是否一致。

### 程序名只有 `CN`

这是 4.7 的安装后缀逻辑。以生成 Makefile 中三个宏和二进制字符串检查为准，
不要手工重命名或据此重复修改 Makefile。

## 13. 本次本机验证结论

已经验证：配置依赖检查、三个预处理宏、干净状态全量串行编译、安装、动态库解析和
二进制字段；`make check` 成功但无实质用例。尚未执行依赖外部气象/地表数据的
真实积分、多 rank 沙箱外运行、restart 数值等价性、长期 spin-up 或论文复现。

RegCM5 的独立说明与本 4.7 文档同时保留，入口见
[CNDV 双版本说明索引](../../CNDV_VERSIONS_ZH.md)。
