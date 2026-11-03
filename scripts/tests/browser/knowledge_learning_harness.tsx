/* Browser-only component fixtures. Never imported by the product or corpus. */
import React from 'react';
import { createRoot } from 'react-dom/client';
import PlatformLearning from '../../web/src/PlatformLearning';
import ContinuityCandidates from '../../web/src/ContinuityCandidates';
import ContinuityContext from '../../web/src/ContinuityContext';
import '../../web/src/app.css';

const params = new URLSearchParams(location.search);
const language = params.get('language') || 'en';
const scenario = params.get('scenario') || 'normal';
const suite = params.get('suite') || 'knowledge';
const text = (zh: string, en: string) => language === 'zh' ? zh : en;
document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
document.documentElement.dataset.theme = params.get('theme') || 'light';
const calls: {path: string; method: string; body?: any}[] = [];
Object.assign(window, {fixtureCalls: calls});
const digest = 'a'.repeat(64);
const source = {family:'SOURCE', entity_id:'fixture-source', revision_id:'fixture-revision',content_digest:digest};
const body = 'Retention: 30 days.\n\n| Case | Limit |\n| legal hold | never delete |\n\nDo not delete legal holds.';
const preview = {publication_eligible:false,findings:[{code:'MISSING_PURPOSE',field:'purpose'}],
  chunks:[{number:1,start:0,end:body.length,text:body}],comparisons:[]};
const candidate = {candidate_id:'fixture-candidate',version:1,revision_no:1,current_revision_no:1,
  proposed_by:'fixture-owner',status:'PENDING',content_digest:digest,
  payload:{content:{family:'KNOWLEDGE',title:'Fixture knowledge',body},sources:[source],replaces:null,intake:null},
  intake_preview:preview};
const request = async (path: string, options?: RequestInit) => {
  calls.push({path,method:options?.method||'GET',...(options?.body ? {body:JSON.parse(String(options.body))}: {})});
  await new Promise(resolve => setTimeout(resolve,20));
  if (scenario === 'error') throw new Error(text('当前授权资料不可用。','Currently authorized material is unavailable.'));
  if (suite==='task') {
    if (path==='/api/context/assemble') return {assembly_id:'fixture-assembly'};
    if (path.startsWith('/api/context/assemblies/')) {
      if ((window as any).fixtureRevoke) throw new Error(text('原始来源已撤回。','Original source was withdrawn.'));
      const empty=scenario==='empty';
      return {assembly_id:'fixture-assembly',content_digest:digest,status:'PREPARED',
        retrieval_policy:'QUERY_HYBRID_BUDGET_SOURCE_CONTEXT_V3',item_count:empty?0:1,
        items:empty?[]:[{item_no:1,family:'KNOWLEDGE',entity_id:'fixture-knowledge',revision_id:'fixture-revision',content_digest:digest,rendered_tokens:100}],
        text:empty?'':body};
    }
    if (path.startsWith('/api/context/assemblies?')) return {items:[{assembly_id:'fixture-assembly',status:'PREPARED'}]};
    if (path.startsWith('/api/context/runtime-agents?')) return {items:[{agent_id:'fixture-agent',display_name:'Fixture Agent'}]};
    if (path==='/api/context/runtime-executions') return {execution_id:'fixture-execution',status:'PENDING'};
    throw new Error('Unexpected Task fixture route');
  }
  if (path.startsWith('/api/learning?')) return {items: scenario==='empty' ? [] : [{entity_id:'fixture-guide',
    title:text('首次使用与权限前提','First use and permission prerequisites'),content_digest:digest,
    product_key:'fixture-product',database:'pg',version:'5.0.3'}]};
  if (path.startsWith('/api/learning/')) {
    if (scenario==='stale') throw new Error(text('此版本或来源已不可用，请刷新目录。','This revision or source is unavailable; refresh the directory.'));
    return {title:text('首次使用与权限前提','First use and permission prerequisites'),content:body,content_digest:digest};
  }
  if (path.startsWith('/api/artifact-candidates?')) return {items:[{candidate_id:candidate.candidate_id,family:'KNOWLEDGE',status:'PENDING'}]};
  if (path==='/api/knowledge-intake/preview') return preview;
  if (path.endsWith('/revisions') || path==='/api/artifact-candidates') return {candidate_id:candidate.candidate_id};
  if (path.startsWith('/api/artifact-candidates/')) return candidate;
  throw new Error('Unexpected fixture route');
};

createRoot(document.getElementById('root')!).render(<main className={`page-stack${suite==='task' ? ' continuity-workbench' : ''}`} style={{padding:16,minWidth:0}}>
  {suite==='task' ? <ContinuityContext request={request} text={text} domain="fixture-domain" domains={[]} canWrite={scenario!=='readonly'}/>
    : <><PlatformLearning request={request} text={text}/>
      <div className="continuity-workbench"><ContinuityCandidates request={request} text={text} domain="fixture-domain" principalId="fixture-owner" canWrite={scenario!=='readonly'}/></div></>}
</main>);
