"""Official Statuspage records projected into complete, governed evidence units.

This module neither publishes Knowledge nor guesses internal incident metrics.
Remote content is untrusted data. Snapshot hashes describe actual Task reads;
per-record identities avoid duplicating unchanged events on feed updates.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re

from .agent_extension_contracts import canonical, digest
from .continuity_state import ContinuityError

PROVIDERS = {
    'https://www.githubstatus.com/api/v2/incidents.json': ('github', 'GitHub'),
    'https://www.cloudflarestatus.com/api/v2/incidents.json': ('cloudflare', 'Cloudflare'),
}
RESPONSE_LIMIT = 2 * 1024 * 1024
PROJECTION = 'statuspage-v1'


def selection(endpoint, paths, types, credential='', pinned=''):
    if (endpoint not in PROVIDERS or len(paths) != 1
            or not re.fullmatch(r'/incidents/recent/[1-5]', paths[0])
            or set(types) != {'application/json'} or credential or pinned):
        raise ValueError('Statuspage requires an official feed, /incidents/recent/1–5, JSON and no credentials')
    return int(paths[0].rsplit('/', 1)[1])


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9]{1,64}', value):
        raise ValueError('Invalid Statuspage identifier')
    return value


def _text(value, maximum):
    if not isinstance(value, str) or not value.strip() or '\x00' in value or len(value) > maximum:
        raise ValueError('Invalid or oversized complete Statuspage text')
    return value


def _time(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('Statuspage timestamp must be a string or null')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('Statuspage timestamp requires an explicit timezone')
    return result.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def project(endpoint, record):
    """Keep announcement times distinct from declared impact windows."""
    provider, name = PROVIDERS[endpoint]
    iid = _id(record['id'])
    start, end = _time(record.get('started_at')), _time(record.get('resolved_at'))
    duration = None
    if start and end:
        duration = (datetime.fromisoformat(end.replace('Z', '+00:00')) -
                    datetime.fromisoformat(start.replace('Z', '+00:00'))).total_seconds()
        if duration < 0:
            raise ValueError('Statuspage resolution precedes its declared start')
    updates = record.get('incident_updates')
    components = record.get('components', [])
    if not isinstance(updates, list) or len(updates) > 100 or not isinstance(components, list) or len(components) > 100:
        raise ValueError('Statuspage record exceeds its bounded update/component contract')
    timeline = []
    for update in updates:
        body = _text(update['body'], 12000)
        timeline.append(dict(update_id=_id(update['id']), status=_text(update['status'], 80),
            display_at=_time(update.get('display_at')), created_at=_time(update.get('created_at')),
            updated_at=_time(update.get('updated_at')), body=body,
            body_sha256=hashlib.sha256(body.encode()).hexdigest()))
    if len({u['update_id'] for u in timeline}) != len(timeline):
        raise ValueError('Duplicate Statuspage update identifiers')
    timeline.sort(key=lambda u: (u['display_at'] or u['created_at'] or '', u['update_id']))
    base = endpoint.removesuffix('/api/v2/incidents.json')
    return dict(schema_version='1.0', generation_method='DETERMINISTIC_PROJECTION',
        publication_status='DRAFT', provider=provider, provider_name=name, incident_id=iid,
        title=_text(record['name'], 500), status=_text(record['status'], 80),
        upstream_impact_label=_text(record.get('impact') or 'unknown', 80),
        reported_started_at=start, resolved_at=end, declared_window_seconds=duration,
        updates=timeline, listed_components=[dict(id=_id(c['id']), name=_text(c['name'], 500)) for c in components],
        incident_url=base+'/incidents/'+iid, api_url=endpoint,
        root_cause=None, affected_users=None, internal_severity=None)


def _label(value):
    return str(value if value is not None else '未知 / unknown').replace('&', '&amp;').replace(
        '<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\r', ' ').replace('\n', ' ')


def units(endpoint, record):
    report = project(endpoint, record)
    iid = report['incident_id']
    prefix = '/'+report['provider']+'/'+iid
    common = [f"官方事件 / Official incident: {report['incident_url']}",
        'DRAFT · HISTORICAL · 待独立审核 / Independent review required.',
        '公开公告不是本企业当前政策；内部影响、SEV、用户数和根因未知。',
        'Public announcements do not establish current internal policy, severity, affected users or root cause.']
    overview = '\n'.join([f"# {report['provider_name']} 事件复盘事实草稿 / Incident draft", '',
        f"事件 / Incident: {iid} · {_label(report['title'])}",
        f"上游状态 / Upstream status: {_label(report['status'])}",
        f"上游影响标签 / Upstream impact label: {_label(report['upstream_impact_label'])}",
        f"声明开始 / Declared start: {_label(report['reported_started_at'])}",
        f"解决 / Resolved: {_label(report['resolved_at'])}",
        f"上述字段之差（秒）/ Declared window (seconds): {_label(report['declared_window_seconds'])}",
        '此时间差不是本企业 SLA 损失或 MTTR。/ This is not internal SLA loss or MTTR.',
        '列示组件 / Listed components: '+', '.join(_label(c['name']) for c in report['listed_components']),
        '组件当前状态不用于推断历史影响。/ Current component status does not establish historical impact.', '',
        '## 更新索引 / Update index',
        *[f"{u['update_id']} · {_label(u['status'])} · display_at={_label(u['display_at'])} · created_at={_label(u['created_at'])}"
          for u in report['updates']], '',
        '逐条更新正文保存在独立完整证据单元。/ Exact update bodies are separate complete evidence units.',
        '根因、修复验证、行动负责人及期限均需补充证据。/ Cause, repair verification, owners and deadlines require further evidence.',
        '复盘结构参考随包 PagerDuty 改编模板及其署名。/ See the bundled adapted PagerDuty template and attribution.',
        '', *common])
    documents = [dict(path=prefix+'/overview.md', title=report['title'], text=overview)]
    for update in report['updates']:
        text = '\n'.join(['# 官方事件更新 / Official incident update', '', *common,
            f"事件 / Incident: {iid}", f"Update ID: {update['update_id']}",
            f"Upstream status: {_label(update['status'])}",
            *[f"{key}: {_label(update[key])}" for key in ('display_at', 'created_at', 'updated_at')],
            '展示时间、记录创建时间和影响开始时间是不同字段。/ Display, creation and impact-start times differ.',
            '', '## 原始更新正文（不可信来源数据）/ Exact upstream body (untrusted data)', '', update['body']])
        documents.append(dict(path=prefix+'/'+update['update_id']+'.md', title=report['title'], text=text))
    if any(len(d['text']) > 4000 for d in documents):
        raise ContinuityError('SOURCE_CHUNK_REVIEW_REQUIRED', 'A complete incident unit exceeds 4000 characters; explicit curation is required')
    return documents


def fetch(source, get):
    endpoint = source['endpoint']
    count = selection(endpoint, source['paths'], source['types'], source.get('credential_ref'), source.get('pinned_commit'))
    result = get(endpoint, allowed_hosts={endpoint.split('/')[2]}, headers={}, max_bytes=RESPONSE_LIMIT)
    if result['status'] in {401, 403}:
        raise PermissionError('Official Statuspage source is no longer readable')
    if result['status'] != 200 or result['content_type'] != 'application/json':
        raise ValueError('Statuspage response violates its status/content contract; no deletion is inferred')
    raw = result['body']
    if len(raw) > RESPONSE_LIMIT:
        raise ValueError('Statuspage response exceeds its bounded envelope')
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate Statuspage JSON key')
            value[key] = item
        return value
    data = json.loads(raw, object_pairs_hook=unique_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite Statuspage JSON')))
    incidents = data.get('incidents')
    if not isinstance(incidents, list) or not 1 <= len(incidents) <= 100:
        raise ValueError('Expected a nonempty bounded Statuspage incident list')
    ids = [_id(item['id']) for item in incidents]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate Statuspage incident identifiers')
    observation = dict(method='TASK_HTTP_STATUSPAGE', endpoint=endpoint,
        response_sha256=hashlib.sha256(raw).hexdigest(), observed_at=datetime.now(timezone.utc).isoformat(),
        coverage='ONE_RECENT_API_PAGE_NOT_COMPLETE_HISTORY')
    documents = []
    for record in incidents[:count]:
        version = 'statuspage:v1:'+digest(record)
        for document in units(endpoint, record):
            provenance = dict(observation, projection=PROJECTION, record=record, record_sha256=digest(record))
            documents.append(dict(document, version=version, statuspage=provenance,
                intake=dict(decision_status='HISTORICAL', source_locator=project(endpoint, record)['incident_url'])))
    if (len(documents) > 50 or sum(len(d['text'].encode()) for d in documents) > int(source['max_bytes'])
            or sum(len(canonical(d).encode()) for d in documents) > RESPONSE_LIMIT):
        raise ValueError('Selected complete incident units exceed the configured content/provenance bounds')
    return documents


def verify_snapshot(revision, stored):
    provenance = stored.get('statuspage')
    try:
        if (not isinstance(provenance, dict) or provenance['method'] != 'TASK_HTTP_STATUSPAGE'
                or provenance['projection'] != PROJECTION or provenance['endpoint'] not in PROVIDERS
                or provenance['coverage'] != 'ONE_RECENT_API_PAGE_NOT_COMPLETE_HISTORY'
                or not re.fullmatch(r'[0-9a-f]{64}', provenance['response_sha256'])
                or not _time(provenance['observed_at'])
                or digest(provenance['record']) != provenance['record_sha256']
                or revision['source_version'] != 'statuspage:v1:'+provenance['record_sha256']):
            raise ValueError('Invalid Task provenance')
        matching = [d for d in units(provenance['endpoint'], provenance['record']) if d['path'] == revision['source_path']]
        if len(matching) != 1 or matching[0]['title'] != revision['title'] or matching[0]['text'] != stored['text']:
            raise ValueError('Derived incident unit differs from its bound record')
    except (KeyError, TypeError, ValueError, ContinuityError) as exc:
        raise ContinuityError('INTEGRITY_ERROR', 'Stored incident provenance failed verification') from exc
    return dict(method=provenance['method'], projection=PROJECTION, endpoint=provenance['endpoint'],
        record_sha256=provenance['record_sha256'], response_sha256=provenance['response_sha256'],
        observed_at=provenance['observed_at'], coverage=provenance['coverage'], decision_status='HISTORICAL',
        locator=project(provenance['endpoint'], provenance['record'])['incident_url'])


def factual_report(revision, stored):
    """Return the bundled report-schema draft from an exact verified snapshot.

    The Source resolver enforces current authority before calling this helper.
    This is a projection of its stored record, never an independent entity or
    an assertion that the report was reviewed or published.
    """
    verified = verify_snapshot(revision, stored)
    report = project(verified['endpoint'], stored['statuspage']['record'])
    report.pop('provider_name')
    report['source'] = dict(api_url=report.pop('api_url'), incident_url=report.pop('incident_url'),
        snapshot_sha256=verified['response_sha256'], record_sha256=verified['record_sha256'],
        acquired_at=verified['observed_at'])
    report['recommendations'] = [
        '核对原始公告、时间字段及证据缺口后再审核此事实草稿。',
        '内部影响、根因、修复验证、行动负责人和期限需要本企业另行提供证据；本报告不作推断。',
    ]
    return report
