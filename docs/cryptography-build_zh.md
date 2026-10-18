# 加密 wheel 构建策略 v5.0.0

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

该平台使用 `cryptography==49.0.0` 进行配置和凭据加密。v4.4.11 及更高版本的目标是 RHEL 9.8+（Oracle Linux 9.8+），或具有 glibc 2.34 或更新版本的等效受维护 Linux 发行版。

## 发布 wheel

每次发布恰好包含一个加密 wheel：

`cryptography-49.0.0-cp311-abi3-manylinux_2_34_x86_64.whl`

`cp311-abi3` 标签与 CPython 3.14 及支持稳定 ABI 的后续 CPython 3.x 版本兼容。此前面向 RHEL 8/glibc 2.28 的 `manylinux_2_28` 源码构建 wheel已退役，不得添加到发布归档中。

## 验证

在受支持的主机上运行标准的离线依赖项门禁：

```bash
python3.14 scripts/verify_deps.py
```

该门禁会拒绝 glibc 低于 2.34 的主机、外部平台标签、不兼容的 Python 标签、元数据不匹配以及不完整的传递依赖项。请勿重命名wheel 或替换系统 glibc 以绕过检查。

## 历史工件

旧版发布说明可能会提及 RHEL 8 兼容性构建，因为它在之前的验证期间被使用过。这些工件仅为历史记录，不是 v4.4.11+ 打包的有效输入。
