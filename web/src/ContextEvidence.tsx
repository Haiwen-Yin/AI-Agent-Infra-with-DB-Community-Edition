import React from "react";

type Row = Record<string, any>;
type Props = { assembly: Row; text: (zh: string, en: string) => string };

export default function ContextEvidence({ assembly, text }: Props) {
  const budget = assembly.budget;
  const representations: Row[] = assembly.representations || [];
  const label = (value: string) => ({
    COMPLETE: text("完整", "Complete"), PARTIAL: text("部分", "Partial"), OMITTED: text("遗漏", "Omitted"),
    PREPARED: text("已准备", "Prepared"), CONFIRMED: text("已确认输入", "Input confirmed"),
    UNOBSERVED: text("未观测", "Unobserved"),
    NO_RELEVANCE: text("相关性不足", "No relevance"),
    SOURCE_NOT_APPLICABLE: text("不符合适用条件", "Not applicable"),
    BUDGET_OR_ENTRY_LIMIT: text("预算或条数限制", "Budget or entry limit"),
    DATABASE_HYBRID: text("数据库混合检索", "Database hybrid retrieval"),
    EXPLICIT_REQUEST: text("请求指定来源", "Explicitly requested source"),
  }[value] || value);
  return <section aria-label={text("上下文依据记录", "Context evidence record")}>
    <h4>{text("上下文依据记录", "Context evidence record")}</h4>
    <p>{text("请求", "Request")}: {assembly.request_id} · {text("有效期至", "Valid until")}: {String(assembly.expires_at || text("未知", "Unknown"))}</p>
    {budget ? <dl className="detail-grid">
      <dt>{text("来源 Token 预算", "Source token budget")}</dt><dd>{budget.source_budget}</dd>
      <dt>{text("输入字节上限", "Input byte limit")}</dt><dd>{budget.byte_budget}</dd>
      <dt>{text("模型上下文窗口", "Model context window")}</dt><dd>{budget.context_window}</dd>
      <dt>{text("输出预留", "Output reserve")}</dt><dd>{budget.output_reserve}</dd>
      <dt>{text("系统 / 工具 Token", "System / tool tokens")}</dt><dd>{budget.system_tokens} / {budget.tool_tokens}</dd>
      <dt>{text("计数方法", "Counting method")}</dt><dd>{budget.count_method}</dd>
    </dl> : <p>{text("此历史组装没有详细预算记录。", "This historical assembly has no detailed budget record.")}</p>}
    {representations.length > 0 && <div style={{ overflowX: "auto" }}><table>
      <caption>{text("精确来源、取舍与输入回执", "Exact sources, selection and input receipts")}</caption>
      <thead><tr>{[text("来源 / 修订", "Source / revision"), text("表示", "Representation"), text("原因", "Reason"), text("Token / 字节", "Tokens / bytes"), text("输入回执", "Input receipt")].map(value => <th key={value} scope="col">{value}</th>)}</tr></thead>
      <tbody>{representations.map(row => <tr key={row.source_no}>
        <td>{row.family} · {row.entity_id}<br />{row.revision_id}<br /><small>{row.content_digest}</small></td>
        <td>{label(row.representation)}</td><td>{label(row.selection_reason)}</td>
        <td>{row.token_count} / {row.byte_count}</td><td>{label(row.delivery_status)}</td>
      </tr>)}</tbody>
    </table></div>}
    {Number(assembly.unavailable_representation_count) > 0 && <p>{text("部分历史来源目前不可读取，已隐藏其标识和详细记录。", "Some historical sources are no longer readable; their identifiers and details are hidden.")}</p>}
    <p>{text("组装预算与输入回执不代表模型回答成功，也不等于供应商报告的 Token 用量或费用。未保存的检索降级、阶段耗时和最终传输观测不能由此补推。", "Assembly budgets and input receipts do not establish answer success or provider-reported usage/cost. Missing retrieval degradations, stage timings and final transport observations cannot be reconstructed from them.")}</p>
  </section>;
}
