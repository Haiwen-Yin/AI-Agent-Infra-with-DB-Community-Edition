# 模板来源、署名及数据使用范围

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

## PagerDuty 模板

Copyright 2016 PagerDuty, Inc.

源仓库：https://github.com/PagerDuty/incident-response-docs

固定提交：`464fc9d3e47e19e9d8da17cec1a41dc09624e95a`。

原模板：
https://github.com/PagerDuty/incident-response-docs/blob/464fc9d3e47e19e9d8da17cec1a41dc09624e95a/docs/after/post_mortem_template.md

原模板 SHA-256：`64a2393d2d60ebab74cc1dd415a774ca5a1e4d8df88d83da23c3ac0142c86458`。

许可证：Apache License, Version 2.0；随附 [LICENSE-PagerDuty.txt](LICENSE-PagerDuty.txt)，
与该提交 LICENSE 的原始字节一致。固定提交的 Git tree 未列出 NOTICE；单独请求返回 404。

中文模板在 2026-11-05 改编：重写为中文业务字段，保留概要、经过、促成因素、
处置、影响、响应人员、时间线、反思、行动及沟通结构；增加证据与时间语义、
未知值、修订和川序候选审核约束。属于修改后的模板，非 PagerDuty 官方译文或背书。
其示例段落和虚构日期没有作为真实事件数据使用。

## 真实企业事件数据

- GitHub 官方状态页 API：https://www.githubstatus.com/api/v2/incidents.json
- Cloudflare 官方状态页 API：https://www.cloudflarestatus.com/api/v2/incidents.json

两者为公开、无需登录的官方事件接口，实测取得 JSON。公开可读取不等于取得开放
内容许可；本次未核实到将事件正文整体再分发的专门开放许可证，因此不把它们标为
Apache、CC 或自由训练数据。PagerDuty 许可只覆盖其模板，不覆盖这两家事件正文。

原始响应、公告正文、机器 JSON 报告及导入请求保存在本项目本地 runtime 下，
不作为随包默认语料或公开全文镜像。仓库报告样例只整理简短事实和引用链接。
若以后公开全文数据集或随产品分发，应先落实相应使用权和适用条款。

另外只读调查了 GitLab 公开 production 工单。未在该项目核实到适用的内容许可证，
本轮未将其正文纳入示范或导入请求，也不沿用其 handbook 的许可猜测工单许可。
