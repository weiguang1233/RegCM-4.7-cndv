# 服务器连续积分与校验证据

记录日期：2026-09-24

服务器工作目录：
`/public/home/elpt_2024_000795/workdir_for_RCM/cndv_cn_followon_1980_1987`

## 最终作业

| 内容 | 作业号 | 队列/CPU | 状态 | ExitCode | 用时 |
|---|---:|---|---|---|---:|
| RegCM5 1980–1987 连续积分 | 39639891 | `cpu_parallel` / 128 | COMPLETED | 0:0 | 03:24:31 |
| RegCM4.7 修复版 1980–1987 连续积分 | 39642490 | `cpu_parallel` / 128 | COMPLETED | 0:0 | 03:25:06 |
| 双版本最终分析 | 39642491 | `cpu_single` / 1 | COMPLETED | 0:0 | 00:19:13 |
| RegCM5 完整分析预检 | 39643243 | `cpu_single` / 1 | COMPLETED | 0:0 | 00:16:56 |

两份主日志都包含 7 次 `Annual CNDV calculations are complete`。RegCM4.7 日志末尾为：

```text
Final time  1987-01-01 00:00:00 UTC reached.
RegCM V4 simulation successfully reached end
CNDV_CN_RUN_OK version=regcm47 mode=full_fixed final=1987010100
```

RegCM5 同样到达 `1987-01-01` 并正常结束。两份 stderr 只有 locale 或 Slurm 路由提示，
没有模型/NetCDF 错误。最终分析输出：

```text
CNDV_CN_ANALYSIS_OK
CNDV_CN_ANALYSIS_PASS
```

## RegCM4.7 修复门禁

| 内容 | 作业号 | 状态 | ExitCode | 结果 |
|---|---:|---|---|---|
| 修复二进制最终构建 | 39642419 | COMPLETED | 0:0 | 构建成功 |
| 每日周期 restart 压力试验 | 39642441 | COMPLETED | 0:0 | 31 次 CLM restart 写出，无 NetCDF 错误 |
| 修复前长积分故障现场 | 39639890 | FAILED | 127:0 | 用于定位历史文件未重开，不作为最终结果 |

常规 smoke 与每日 restart 压力试验在相同终点的 CLM restart 和 RegCM SAV 逐变量
数值完全一致，比较时只忽略保存路径元数据 `locfnh/locfnhr`。修复前/后积分在首个原
故障检查点 1980-12-31 的状态也通过相同检查。随后修复版跨过年度 CNDV 更新并完成
全期积分。

RegCM4.7 修复提交：
`a2dd429527ad00a8f97bf3b888dc5aa016061ad9`

服务器修复源码 SHA-256：

```text
ef90ced91da94cdc7a4a493f3d19afa742c7e6907091ccdeb1de0a96aa2296e7  mod_clm_histfile.F90
```

服务器修复二进制 SHA-256：

```text
a6503544a95d281bf8b62f3f72e9c051f8495fab5f0a118c474e86ff9149d438  regcmMPICN_CNDV_CLM45_histfix
```

## 结果完整性

`results/result_sha256.txt` 覆盖完整逐日/年度/restart CSV、汇总 JSON、单位定义和三张
PNG。下载后的 9 个文件均通过 SHA-256 校验。关键哈希：

```text
54decc63c4712490e293e0b19f6f949acd8ba095b67e52777f1dbf448fe275cc  daily_carbon_nitrogen_pools.csv
29baba299cc2f01b051f53102c0fcf0b93e3dbb323e3ccbb4ca26e8bd2608df6  annual_carbon_nitrogen_summary.csv
12a996eff845e382288441b9b85af574cb5e802af6afb86f3839b98dfdfe6a6b  annual_cndv_fpc_targets.csv
d414fdb14a4eec4cd2010ad965263711dad73d4670ed8b017bbd8f2db55ccac1  restart_carbon_nitrogen_checkpoints.csv
e36dc2ea9d7f1fce06ef575a0f2a7e5eb7a2d7e8ed711e835ae550f9af03a487  carbon_nitrogen_summary.json
```

完整清单和执行期测试定义哈希分别保存在：

- `results/result_sha256.txt`
- `results/test_definition_sha256.txt`

`test_definition_sha256.txt` 是准备试验时生成的审计快照。分析器、门禁和恢复脚本在
定位 RegCM4.7 故障后继续增强；仓库中的最终脚本及其 Git 提交是当前可复现版本，
结果文件本身以 `result_sha256.txt` 为准。
