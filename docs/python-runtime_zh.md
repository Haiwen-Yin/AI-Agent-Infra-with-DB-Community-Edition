# Python 运行环境策略 v5.0.1

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](python-runtime.md)

发行包要求可执行的 CPython **3.14 或更高版本**，不指定安装来源。包不会假定 `/home/linuxbrew/.linuxbrew` 可见或可执行；构建沙箱可能无法访问这些主机路径。

## 选择解释器

在包根目录运行。解析器通过实际执行并检查 `sys.version_info` 验证解释器：

```bash
source scripts/python_runtime.sh
export PYTHON_BIN="$(cx_resolve_python)"
cx_prepare_python_environment "$PYTHON_BIN"
"$PYTHON_BIN" --version
```

解释器不在 PATH 时显式指定：

```bash
export PYTHON_BIN=/path/to/python3.14
source scripts/python_runtime.sh
PYTHON_BIN="$(cx_resolve_python "$PYTHON_BIN")"
cx_prepare_python_environment "$PYTHON_BIN"
```

命令替换在子 Shell 中运行。连续执行多个子进程时，也可使用包装器准备各自的库目录：

```bash
PYTHON_BIN="$(cx_resolve_python)"
cx_run_python "$PYTHON_BIN" --version
cx_run_python "$PYTHON_BIN" -m pytest scripts/tests/ -q
```

`cx_run_python` 为每个子进程准备相邻 libpython 路径，适用于沙箱内可见或可迁移的 Python 目录，不依赖 Linuxbrew。解析器会检查安装目录相邻的 `lib/`、`lib64/`，并在当前 Shell 中加入 `LD_LIBRARY_PATH`，无需替换系统库。启动和离线安装脚本使用同样规则。

显式指定的解释器不可访问或版本过低时直接失败。未显式指定时扫描 PATH，测试 `python3.N`，选择可执行且至少为 3.14 的最高版本，不回退到旧 `python3`。

## 沙箱与部署

构建 Agent 的沙箱与客户主机不同。沙箱执行主机专用路径被拒绝，只说明当前边界不允许访问，不能推断客户没有 Python。源码测试使用沙箱可见解释器并通过 `PYTHON_BIN` 传入；客户主机使用同一解析器。无需越过沙箱或替换 glibc，单一路径限制也不能被误写为 Python 版本要求。

## Wheel 兼容性

最低 Python 版本与 Wheel 兼容性是两项检查。`cp314` 扩展 Wheel 对应 CPython 3.14；`abi3` 只有在稳定 ABI 允许时才可用于更高的小版本。`verify_deps.py` 检查当前解释器、全部已选依赖的必需 `Requires-Dist` 及平台条件，不能只确认直接依赖。可选 extras 不属于基础离线安装；未知条件按必需依赖处理，解释清楚前阻止验证。

每个 Wheel 还检查文件名与 METADATA 是否一致、`Requires-Python`、操作系统和架构标签，以及 `dist-info/RECORD` 中的哈希和大小。当前 YashanDB 包包含 CPython 3.14 的 yaspy 原生模块；使用 Python 3.15+ 前须取得匹配驱动。

离线安装核对 glibc 下限。v4.4.11 及以后要求 glibc 2.34+，对应 RHEL/Oracle Linux 9.8+ 基线。发行包仅保留上游 `cryptography==49.0.0` 的 `manylinux_2_34` Wheel，不重新加入已退役的 RHEL 8 `manylinux_2_28` 兼容 Wheel。

五产品构建对七个底座目标分别检查离线依赖。`--skip-dependency-validate` 仅用于依赖目录有意不完整的开发诊断，其输出不能因此视为可发布。
