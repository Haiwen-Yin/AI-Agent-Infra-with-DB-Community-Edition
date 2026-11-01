import React from "react";
import "./ModelEndpointCapacity.css";
type Row = Record<string, any>;
type Props = { items: Row[]; text: (zh: string, en: string) => string };

export default function RuntimeObservations({ items, text }: Props) {
  const value = (number: unknown, suffix = "") => typeof number === "number" && Number.isFinite(number) && number >= 0 ? `${number}${suffix}` : text("未观测", "Unobserved");
  const provenance = (state: string) => ({ PROVIDER_REPORTED: text("服务端报告", "Provider reported"), DERIVED_TOTAL: text("由已报告输入和输出相加", "Sum of reported input and output"), PARTIAL: text("部分用量", "Partial usage"), INCOMPLETE: text("用量未观测", "Usage unobserved") }[state] || state);
  return <section className="model-runtime-observations" aria-label={text("模型请求观测", "Model request observations")}>
    <h4>{text("模型请求观测", "Model request observations")}</h4>
    <p>{text("时长来自客户端观测；首内容时间以首段回答内容为界，不含隐藏推理的正文。缓存与推理用量属于输入或输出中的明细，不重复累加。", "Timings are client observations. First-content time ends at the first answer content and excludes hidden reasoning text. Cache and reasoning details are subsets of input or output and are not counted twice.")}</p>
    {!items.length && <p>{text("当前没有已记录的模型请求观测。", "No recorded model request observations are available.")}</p>}
    {items.map(item => <article key={item.admission_id}>
      <p><code>{item.admission_id}</code> · {item.model_id} · {text("配置版本", "Profile revision")} {item.profile_version}</p>
      {item.origin_receipt_id && <p>{text("协调器观测 · 本地原请求回执", "Coordinator observation · original local receipt")}: <code>{item.origin_receipt_id}</code></p>}
      <p role="status">{item.request_complete === "Y" ? (item.result_state === "REJECTED" ? text("模型请求已结束，业务输出被拒绝", "Model request ended; business output rejected") : text("模型请求已结束", "Model request ended")) : text("远端结果未知，容量仍按原请求状态保留", "Remote outcome is unknown; capacity follows the original request state")}</p>
      <dl className="detail-grid">
        <dt>{text("排队", "Queue")}</dt><dd>{value(item.queue_ms, " ms")}</dd>
        <dt>{text("发送至首内容", "Dispatch to first content")}</dt><dd>{value(item.first_content_ms, " ms")}</dd>
        <dt>{text("模型请求时长", "Provider request duration")}</dt><dd>{value(item.provider_ms, " ms")}</dd>
        <dt>{text("请求总时长", "Total request duration")}</dt><dd>{value(item.total_ms, " ms")}</dd>
        <dt>{text("输入 / 输出 / 总 token", "Input / output / total tokens")}</dt><dd>{value(item.prompt_tokens)} / {value(item.completion_tokens)} / {value(item.total_tokens)}</dd>
        <dt>{text("缓存读取 / 写入 token", "Cache read / write tokens")}</dt><dd>{value(item.cached_tokens)} / {value(item.cache_write_tokens)}</dd>
        <dt>{text("推理 token", "Reasoning tokens")}</dt><dd>{value(item.reasoning_tokens)}</dd>
        <dt>{text("用量来源", "Usage provenance")}</dt><dd>{provenance(item.usage_provenance)}</dd>
      </dl>
    </article>)}
  </section>;
}
