"""Publish current product facts through existing Knowledge entities and audit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from . import builtin_knowledge, connection, identity_api, product_identity


def _entity_key(product: dict, database: str, section_key: str, snapshot_revision: str = "") -> str:
    identity = product["product_key"] + ":" + product["version"] + ":" + database + ":" + section_key
    identifier = hashlib.sha256((identity + (":" + snapshot_revision if snapshot_revision else "")).encode()).hexdigest()
    # PG uses BIGINT; retain the exact JavaScript integer range.
    return str((1 << 52) + int(identifier[:13], 16)) if database == "pg" else "CXK_" + identifier[:36]


def _version(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("Product knowledge version is invalid")
    return sum(int(part) * factor for part, factor in zip(value.split("."), (1000000, 1000, 1)))


def _snapshot(product, database, units):
    content = {"product": product, "database": database, "sections": units}
    if _version(product["version"]) >= _version("5.0.3"):
        content["snapshot_revision"] = builtin_knowledge._digest(content)
    return content


def _snapshot_revision(content):
    revision = content.get("snapshot_revision", "")
    if 'snapshot_revision' in content and (not isinstance(revision, str) or not re.fullmatch("[a-f0-9]{64}", revision)
            or revision != builtin_knowledge._digest({key: value for key, value in content.items()
                                                      if key != "snapshot_revision"})):
        raise ValueError("Product knowledge snapshot verification failed")
    return revision


def _package_key(product, revision=""):
    return "product-guide:" + product["product_key"] + (":" + revision if revision else "")


def _current_snapshot(product, database, root):
    root = root or product_identity.package_root(__file__)
    current = sections(product, database)
    if delivery(root)['delivery'] == 'separate':
        current = tuple(unit for unit in current if not unit['key'].startswith('learn-'))
    if _version(product["version"]) >= _version("5.0.3"):
        from . import platform_learning
        current = platform_learning.bind_sources(current, root)
    return _snapshot(product, database, current)


def _retire_projection(tx, actor, package, digest, event):
    content=package['content']; product=content['product']; database=content['database']
    revision = _snapshot_revision(content)
    retired, preserved=[],[]
    for section in content['sections']:
        key=_entity_key(product,database,section['key'],revision)
        existing=tx.query_one("SELECT TITLE,CONTENT,SUMMARY,CATEGORY,VISIBILITY,STATUS FROM ENTITIES "
            "WHERE ENTITY_ID=:id AND ENTITY_TYPE='KNOWLEDGE' FOR UPDATE",{'id':key})
        if not existing:
            continue
        item={str(name).lower():value for name,value in existing.items()}
        if item['status']!='ACTIVE':
            continue
        body=item['content'].read() if hasattr(item['content'],'read') else item['content']
        if (item['title']!=section['title'] or body!=section['content'] or item['summary']!=section['title']
                or item['category']!='PRODUCT' or item['visibility']!='PUBLIC'):
            preserved.append(key)
            continue
        tx.execute("UPDATE ENTITIES SET STATUS='ARCHIVED',UPDATED_AT=CURRENT_TIMESTAMP "
            "WHERE ENTITY_ID=:id AND ENTITY_TYPE='KNOWLEDGE'",{'id':key})
        identity_api._audit_tx(tx,actor,event,'ENTITY',key,'ALLOW',digest)
        retired.append(key)
    return retired,preserved


def withdraw_projection(tx, actor, row):
    """Retire only exact verified product projections in the withdrawal tx.

    An unrelated built-in package has no native product projection. Edited
    user content is preserved and explicitly reported, never matched by title.
    """
    if not str(row['knowledge_key']).startswith('product-guide:'):
        return [],[]
    raw=row['content_json']; package=json.loads(raw.read() if hasattr(raw,'read') else raw)
    digest=builtin_knowledge._digest(package)
    content=package.get('content') or {}; product=content.get('product') or {}; database=content.get('database')
    if (row['content_digest']!=digest or row['signature']!='LOCAL-SHA256:'+digest
            or row['signature_status']!='VERIFIED_BUILTIN' or row['knowledge_kind']!='BUILTIN_PACKAGE'
            or row['audience']!='PUBLIC' or row['scope_type']!='PUBLIC'
            or package.get('audience')!='PUBLIC' or package.get('scope_type')!='PUBLIC'
            or database not in {'pg','oracle','yashandb'} or package.get('dialect')!=database
            or product.get('edition') not in {'Community','Enterprise'}
            or package.get('edition')!=product['edition'].lower()
            or row['knowledge_key']!=_package_key(product,_snapshot_revision(content))
            or _version(product.get('version'))!=int(row['version'])):
        raise ValueError('Product knowledge withdrawal verification failed')
    return _retire_projection(tx,actor,package,digest,'PRODUCT_KNOWLEDGE_WITHDRAWN')


def _supersede_product_entities(tx, actor, product, database, current_key):
    """Archive untouched projections of verified earlier product snapshots.

    Published snapshots remain immutable historical records. Only their exact
    public entity projections leave active retrieval, in the same transaction
    that publishes the installed version. Never infer ownership from a title.
    """
    rows = tx.query(
        "SELECT KNOWLEDGE_KEY,VERSION,CONTENT_JSON,CONTENT_DIGEST,SIGNATURE,SIGNATURE_STATUS "
        "FROM CX_PLATFORM_KNOWLEDGE WHERE (KNOWLEDGE_KEY=:key OR KNOWLEDGE_KEY LIKE :snapshot_keys) "
        "AND KNOWLEDGE_KIND='BUILTIN_PACKAGE' AND AUDIENCE='PUBLIC' "
        "AND SCOPE_TYPE='PUBLIC' AND STATUS='PUBLISHED' AND VERSION<=:version "
        "AND NOT (KNOWLEDGE_KEY=:current_key AND VERSION=:version) FOR UPDATE",
        {"key": _package_key(product), "snapshot_keys": _package_key(product) + ":%",
         "current_key": current_key, "version": _version(product["version"])})
    retired, preserved = [], []
    for raw in rows:
        row = {str(key).lower(): value for key, value in raw.items()}
        raw=row['content_json']
        package = json.loads(raw.read() if hasattr(raw,'read') else raw)
        digest = builtin_knowledge._digest(package)
        if (row["content_digest"] != digest or row["signature"] != "LOCAL-SHA256:" + digest
                or row["signature_status"] != "VERIFIED_BUILTIN"):
            raise ValueError("Historical product knowledge verification failed")
        content = package.get("content") or {}
        previous = content.get("product") or {}
        if (package.get("dialect") != database or content.get("database") != database
                or package.get("edition") != product["edition"].lower()
                or package.get("audience") != "PUBLIC" or package.get("scope_type") != "PUBLIC"
                or previous.get("product_key") != product["product_key"]
                or previous.get("edition") != product["edition"]):
            raise ValueError("Historical product knowledge identity mismatch")
        if (_version(previous.get("version")) != int(row["version"])
                or row['knowledge_key'] != _package_key(previous,_snapshot_revision(content))):
            raise ValueError("Historical product knowledge version mismatch")
        archived,modified=_retire_projection(tx,actor,package,digest,'PRODUCT_KNOWLEDGE_SUPERSEDED')
        retired.extend(archived);preserved.extend(modified)
    return retired, preserved


def sections(product: dict, database: str) -> tuple[dict, ...]:
    zh, en, version = product["name_zh"], product["name_en"], product["version"]
    prefix = f"{zh} / {en} v{version}"
    enterprise = product["edition"].lower() == "enterprise"
    edition_zh = "企业版" if enterprise else "社区版"
    current = (
        {"key": "overview", "title": prefix + " 平台总览 / Platform overview",
         "content": f"{zh}（{en}）是基于数据库的 AI Agent 管理平台，当前版本为 v{version}，属于{edition_zh}，当前进程使用 {database}。"
                    f"{en} is a database-backed AI Agent management platform, version {version}, {product['edition']} Edition, running on {database}. "
                    "任务、步骤、知识、记忆、通用属性图、身份权限和审计以数据库实体保存。"
                    "Task Plans, Steps, Knowledge, versioned Memory, property graphs, identities, authorization and audit are database entities."},
        {"key": "portal", "title": prefix + " Portal 与频道问答 / Portal and Channel answers",
         "content": "Portal 为人用户分配可用的本地托管 Agent，与外部 Agent 注册独立。频道中的 Agent 需要明确成员关系、激活、运行隔离及授权。"
                    "双方共同有权读取的知识命中时，回答带知识引用；未命中且策略允许时由获准模型回答，并标明模型来源。"
                    "Portal allocates eligible local managed Agents independently of external Agent registration. Channel Agents need membership, activation, runtime isolation and grants. "
                    "Answers cite Knowledge authorized for both principals; policy-permitted no-match answers use the approved model with a general-model source label."},
        {"key": "collaboration", "title": prefix + " 工作协作与连续性 / Work and continuity",
         "content": "任务计划、步骤、协作关卡、工作区、分支、循环、属性图和连续性组装支持长期协作。A2A 与 DB4A2A 保留各自传输，但关联同一任务与步骤，复用租约令牌、取消和结果核对。"
                    "Task Plans, Steps, collaboration barriers, Workspaces, Branches, Loops, property graphs and continuity assemblies support durable work. "
                    "A2A and DB4A2A retain their transports while linking the same task/step identities and reusing fenced attempts, cancellation and unknown-outcome reconciliation."},
        {"key": "security", "title": prefix + " 身份与能力边界 / Identity and capabilities",
         "content": "人用户注册与外部 Agent 注册分别控制；Agent 必须完成注册、凭据验证和激活。角色、组织、安全域和资源授权决定访问范围。"
                    "受控 MCP、A2A、框架和模型能力需检查当前授权及证据，模型输出或 Skill 文件不授予操作权限。"
                    "Human and external Agent registration are separate policies. Agents require registration, credential proof and activation. "
                    "Roles, organizations, Security Domains and resource grants bound access. Controlled MCP, A2A, framework and model features require current authority and evidence; model text and Skill files confer no authority. "
                    + ("本企业包包含其获许可的审批、合规和审计查看能力。 This Enterprise package includes its licensed approval, compliance and audit-view capabilities."
                       if enterprise else "本社区包不包含企业版专属审批、合规和审计查看模块；保留必要审计写入。 This Community package excludes Enterprise approval, compliance and audit-view modules while retaining mandatory audit writing.")},
    )
    if _version(version) >= _version('5.0.3'):
        from . import platform_learning
        current += platform_learning.sections(product, database)
    return current


def publish(actor: str, database: str, root: Path | None = None, *, _content=None) -> dict:
    product = product_identity.identity(root)
    if product["product_key"] == "legacy":
        return {"status": "NOT_APPLICABLE"}
    if database not in product["databases"]:
        raise ValueError("Product knowledge database mismatch")
    if identity_api.effective_access(actor, "platform.manage").get("decision") != "ALLOW":
        raise PermissionError("Product knowledge publication requires platform management")
    root = root or product_identity.package_root(__file__)
    catalog = json.loads((root / "scripts/resources/legacy-product-knowledge.json").read_text())[database]
    content = _current_snapshot(product, database, root) if _content is None else _content
    current = content['sections']
    revision = _snapshot_revision(content)
    package_key = _package_key(product, revision)
    def work(tx):
        record = builtin_knowledge.publish(actor, package_key,
            content, audience="PUBLIC", scope_type="PUBLIC",
            version=_version(product["version"]),
            reason="Publish the installed product's current bilingual facts", dialect=database,
            edition=product["edition"].lower(), _tx=tx)
        if record['status']!='PUBLISHED':
            raise builtin_knowledge.KnowledgeLifecycleError('Withdrawn product knowledge cannot be republished at the same version')
        retired, preserved_product = _supersede_product_entities(tx, actor, product, database, package_key)
        preserved = []
        # Retire only exact, untouched historical public seeds. User edits,
        # private knowledge and unrelated titles remain unchanged.
        for legacy in catalog:
            rows = tx.query("SELECT ENTITY_ID,TITLE,CONTENT FROM ENTITIES WHERE ENTITY_TYPE='KNOWLEDGE' "
                            "AND TITLE=:title AND CATEGORY='PRODUCT' AND VISIBILITY='PUBLIC' AND STATUS='ACTIVE' FOR UPDATE",
                            {"title": legacy["title"]})
            for raw in rows:
                item = {str(key).lower(): value for key, value in raw.items()}
                digest = hashlib.sha256(str(item["content"] or "").encode()).hexdigest()
                if digest not in legacy["hashes"] or legacy.get("id") and item["entity_id"] != legacy["id"]:
                    preserved.append(str(item["entity_id"]))
                    continue
                tx.execute("UPDATE ENTITIES SET STATUS='ARCHIVED',UPDATED_AT=CURRENT_TIMESTAMP WHERE ENTITY_ID=:id AND ENTITY_TYPE='KNOWLEDGE'",
                           {"id": item["entity_id"]})
                identity_api._audit_tx(tx, actor, "PRODUCT_KNOWLEDGE_SUPERSEDED", "ENTITY", item["entity_id"], "ALLOW", digest)
                retired.append(str(item["entity_id"]))
        ids = []
        for section in current:
            key = _entity_key(product, database, section["key"], revision)
            existing = tx.query_one("SELECT TITLE,CONTENT,STATUS FROM ENTITIES WHERE ENTITY_ID=:id AND ENTITY_TYPE='KNOWLEDGE' FOR UPDATE", {"id": key})
            if existing:
                existing = {str(k).lower(): v for k, v in existing.items()}
                body = existing['content'].read() if hasattr(existing['content'],'read') else existing['content']
                if existing["title"] != section["title"] or body != section["content"]:
                    raise ValueError("Published product knowledge is immutable")
                if existing.get('status') != 'ACTIVE':
                    raise builtin_knowledge.KnowledgeLifecycleError('Superseded product knowledge cannot be republished')
            else:
                identity_override = "OVERRIDING SYSTEM VALUE " if database == "pg" else ""
                tx.execute("INSERT INTO ENTITIES(ENTITY_ID,ENTITY_TYPE,TITLE,CONTENT,SUMMARY,CATEGORY,IMPORTANCE,STATUS,VISIBILITY) "
                           + identity_override + "VALUES(:id,'KNOWLEDGE',:title,:content,:summary,'PRODUCT',10,'ACTIVE','PUBLIC')",
                           {"id": key, "title": section["title"], "content": section["content"], "summary": section["title"]})
                tx.execute("INSERT INTO KNOWLEDGE_META(ENTITY_ID,ENTITY_TYPE,DOMAIN,TOPIC,DIFFICULTY) "
                           "VALUES(:id,'KNOWLEDGE','PLATFORM',:topic,'INTERMEDIATE')", {"id": key, "topic": product["name_en"] + " v" + product["version"]})
                identity_api._audit_tx(tx, actor, "PRODUCT_KNOWLEDGE_PUBLISH", "ENTITY", key, "ALLOW", record["digest"])
            ids.append(key)
        return {"status": "PUBLISHED", "knowledge_ids": ids, "superseded": retired,
                "preserved_modified_legacy": preserved, "preserved_modified_product": preserved_product,
                "package_digest": record["digest"], "snapshot_revision": revision}
    return connection.execute_transaction_callback(work)


def delivery(root=None):
    """An absent policy retains historical packages' original behavior."""
    policy = product_identity.read_manifest(root).get('platform_learning') or {'delivery': 'bundled'}
    if policy.get('delivery') not in {'bundled', 'separate'}:
        raise ValueError('Unsupported platform learning delivery policy')
    return policy


def install_default(actor, database, root=None, *, initialize=False):
    if delivery(root)['delivery'] == 'separate' and not initialize:
        # An upgrade must not replace an optional guide already in the DB with
        # the four short built-in product summaries, or remove user additions.
        return {'status': 'PRESERVED_EXISTING', 'learning_delivery': 'separate'}
    return publish(actor, database, root)


def import_learning(actor, database, bundle, *, root=None):
    """Explicit admin import of the companion bytes pinned by this software.

    The pin is an integrity/applicability check, not a publisher signature.
    Publication, projections and retirement reuse the same audited transaction.
    """
    if identity_api.effective_access(actor, 'platform.manage').get('decision') != 'ALLOW':
        raise PermissionError('Platform learning import requires platform management')
    policy = delivery(root)
    if policy['delivery'] != 'separate' or not isinstance(bundle, dict) or bundle.get('format') != 'platform-learning/1':
        raise ValueError('Platform learning companion is not applicable')
    snapshots = bundle.get('snapshots')
    if not isinstance(snapshots, dict):
        raise ValueError('Platform learning companion snapshots are invalid')
    content = snapshots.get(database)
    pin = (policy.get('snapshots') or {}).get(database) or {}
    product = product_identity.identity(root)
    if (not isinstance(content, dict) or content.get('product') != product or content.get('database') != database
            or not pin.get('sha256') or builtin_knowledge._digest(content) != pin['sha256']
            or _snapshot_revision(content) != pin.get('revision')):
        raise ValueError('Platform learning companion integrity or applicability mismatch')
    return publish(actor, database, root, _content=content)


def _learning_units(tx, actor, database, root):
    product = product_identity.identity(root)
    if identity_api.effective_access(actor, 'knowledge.read').get('decision') != 'ALLOW':
        raise PermissionError('Learning discovery requires current Knowledge read authority')
    if database not in product['databases']:
        raise ValueError('Product learning database mismatch')
    if product['product_key'] == 'legacy' or _version(product['version']) < _version('5.0.3'):
        return product, []
    policy = delivery(root)
    external = policy['delivery'] == 'separate'
    pin = (policy.get('snapshots') or {}).get(database) or {}
    expected = None if external else _current_snapshot(product, database, root)
    revision = pin.get('revision') if external else _snapshot_revision(expected)
    if external and (not re.fullmatch('[a-f0-9]{64}', str(revision or ''))
                     or not re.fullmatch('[a-f0-9]{64}', str(pin.get('sha256') or ''))):
        raise ValueError('Platform learning companion reference is invalid')
    raw = tx.query_one("SELECT CONTENT_JSON,CONTENT_DIGEST,SIGNATURE,SIGNATURE_STATUS FROM CX_PLATFORM_KNOWLEDGE "
        "WHERE KNOWLEDGE_KEY=:key AND VERSION=:version AND KNOWLEDGE_KIND='BUILTIN_PACKAGE' "
        "AND AUDIENCE='PUBLIC' AND SCOPE_TYPE='PUBLIC' AND STATUS='PUBLISHED' "
        "AND VALID_FROM<=CURRENT_TIMESTAMP AND (VALID_UNTIL IS NULL OR VALID_UNTIL>CURRENT_TIMESTAMP)",
        {'key': _package_key(product,revision), 'version': _version(product['version'])})
    if raw is None:
        return product, []
    row = {str(key).lower(): value for key, value in raw.items()}
    value = row['content_json']
    package = json.loads(value.read() if hasattr(value, 'read') else value)
    digest = builtin_knowledge._digest(package)
    if (row['content_digest'] != digest or row['signature'] != 'LOCAL-SHA256:' + digest
            or row['signature_status'] != 'VERIFIED_BUILTIN' or package.get('dialect') != database
            or package.get('edition') != product['edition'].lower()
            or package.get('audience') != 'PUBLIC' or package.get('scope_type') != 'PUBLIC'
            or package.get('content', {}).get('product') != product
            or package.get('content', {}).get('database') != database
            or (builtin_knowledge._digest(package.get('content')) != pin['sha256'] if external
                else package.get('content') != json.loads(json.dumps(expected)))):
        raise ValueError('Published platform learning integrity or applicability mismatch')
    return product, [dict(section,snapshot_revision=revision) for section in package['content']['sections']
                     if section['key'].startswith('learn-')]


def _learning_entity(tx, actor, product, database, unit):
    from .knowledge_api import knowledge_access_predicate
    key = _entity_key(product, database, unit['key'], unit.get('snapshot_revision',''))
    entity = tx.query_one("SELECT e.TITLE,e.CONTENT FROM ENTITIES e WHERE e.ENTITY_ID=:entity "
        "AND e.ENTITY_TYPE='KNOWLEDGE' AND e.STATUS='ACTIVE' "
        "AND (e.EXPIRES_AT IS NULL OR e.EXPIRES_AT>CURRENT_TIMESTAMP) AND " + knowledge_access_predicate('e', ':actor'),
        {'entity': int(key) if database == 'pg' else key, 'actor': actor})
    if entity is None:
        return None
    entity = {str(name).lower(): value for name, value in entity.items()}
    body = entity['content'].read() if hasattr(entity['content'], 'read') else entity['content']
    if entity['title'] != unit['title'] or body != unit['content']:
        return None
    return {'entity_id': key, 'content_digest': hashlib.sha256(body.encode()).hexdigest()}


def learning_catalog(actor, database, *, role=None, goal=None, root=None):
    if role not in {None, 'HUMAN', 'ADMIN', 'AGENT'} or goal not in {None, 'onboarding', 'collaboration', 'access',
            'tasks', 'workflow', 'knowledge', 'memory', 'integration', 'capabilities', 'handoff', 'answers', 'recovery', 'models'}:
        raise ValueError('Unsupported platform learning role or goal')
    def work(tx):
        product, units = _learning_units(tx, actor, database, root)
        items = []
        for unit in units:
            if role and role not in unit['roles'] or goal and goal not in unit['goals']:
                continue
            source = _learning_entity(tx, actor, product, database, unit)
            if source is not None:
                items.append({**source, 'key': unit['key'], 'title': unit['title'], 'roles': unit['roles'],
                              'goals': unit['goals'], 'sources': unit['sources'], 'version': unit['version'],
                              'product_key': unit['product_key'], 'database': unit['database']})
        return {'status': 'AVAILABLE' if items else 'NO_APPLICABLE_PUBLISHED_GUIDANCE', 'items': items,
                'delivery': delivery(root)['delivery'],
                'can_import': delivery(root)['delivery'] == 'separate' and
                    identity_api.effective_access(actor, 'platform.manage').get('decision') == 'ALLOW',
                'execution_authority': 'CURRENT_CONTRACTS_AND_GRANTS', 'automatic_execution': False}
    return connection.execute_transaction_callback(work)


def read_learning(actor, database, entity_id, expected_digest, *, root=None):
    def work(tx):
        product, units = _learning_units(tx, actor, database, root)
        for unit in units:
            if _entity_key(product, database, unit['key'],unit.get('snapshot_revision','')) != entity_id:
                continue
            source = _learning_entity(tx, actor, product, database, unit)
            if source is not None and source['content_digest'] == expected_digest:
                return dict(source, title=unit['title'], content=unit['content'], sources=unit['sources'],
                            version=unit['version'], product_key=unit['product_key'], automatic_execution=False)
        raise PermissionError('Exact current learning source is unavailable')
    return connection.execute_transaction_callback(work)
