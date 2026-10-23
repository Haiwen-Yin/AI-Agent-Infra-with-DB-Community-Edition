"""Publish current product facts through existing Knowledge entities and audit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from . import builtin_knowledge, connection, identity_api, product_identity


def _entity_key(product: dict, database: str, section_key: str) -> str:
    identifier = hashlib.sha256((product["product_key"] + ":" + product["version"]
                                + ":" + database + ":" + section_key).encode()).hexdigest()
    # PG uses BIGINT; retain the exact JavaScript integer range.
    return str((1 << 52) + int(identifier[:13], 16)) if database == "pg" else "CXK_" + identifier[:36]


def _version(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("Product knowledge version is invalid")
    return sum(int(part) * factor for part, factor in zip(value.split("."), (1000000, 1000, 1)))


def _supersede_product_entities(tx, actor, product, database):
    """Archive untouched projections of verified earlier product snapshots.

    Published snapshots remain immutable historical records. Only their exact
    public entity projections leave active retrieval, in the same transaction
    that publishes the installed version. Never infer ownership from a title.
    """
    rows = tx.query(
        "SELECT VERSION,CONTENT_JSON,CONTENT_DIGEST,SIGNATURE,SIGNATURE_STATUS "
        "FROM CX_PLATFORM_KNOWLEDGE WHERE KNOWLEDGE_KEY=:key "
        "AND KNOWLEDGE_KIND='BUILTIN_PACKAGE' AND AUDIENCE='PUBLIC' "
        "AND SCOPE_TYPE='PUBLIC' AND STATUS='PUBLISHED' AND VERSION<:version FOR UPDATE",
        {"key": "product-guide:" + product["product_key"], "version": _version(product["version"])})
    retired, preserved = [], []
    for raw in rows:
        row = {str(key).lower(): value for key, value in raw.items()}
        package = json.loads(str(row["content_json"]))
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
        if _version(previous.get("version")) != int(row["version"]):
            raise ValueError("Historical product knowledge version mismatch")
        for section in content["sections"]:
            key = _entity_key(previous, database, section["key"])
            existing = tx.query_one(
                "SELECT TITLE,CONTENT,SUMMARY,CATEGORY,VISIBILITY,STATUS FROM ENTITIES "
                "WHERE ENTITY_ID=:id AND ENTITY_TYPE='KNOWLEDGE' FOR UPDATE", {"id": key})
            if not existing:
                continue
            item = {str(name).lower(): value for name, value in existing.items()}
            if item["status"] != "ACTIVE":
                continue
            if (item["title"] != section["title"] or str(item["content"]) != section["content"]
                    or item["summary"] != section["title"] or item["category"] != "PRODUCT"
                    or item["visibility"] != "PUBLIC"):
                preserved.append(key)
                continue
            tx.execute("UPDATE ENTITIES SET STATUS='ARCHIVED',UPDATED_AT=CURRENT_TIMESTAMP "
                       "WHERE ENTITY_ID=:id AND ENTITY_TYPE='KNOWLEDGE'", {"id": key})
            identity_api._audit_tx(tx, actor, "PRODUCT_KNOWLEDGE_SUPERSEDED", "ENTITY", key, "ALLOW", digest)
            retired.append(key)
    return retired, preserved


def sections(product: dict, database: str) -> tuple[dict, ...]:
    zh, en, version = product["name_zh"], product["name_en"], product["version"]
    prefix = f"{zh} / {en} v{version}"
    enterprise = product["edition"].lower() == "enterprise"
    edition_zh = "企业版" if enterprise else "社区版"
    return (
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


def publish(actor: str, database: str, root: Path | None = None) -> dict:
    product = product_identity.identity(root)
    if product["product_key"] == "legacy":
        return {"status": "NOT_APPLICABLE"}
    if database not in product["databases"]:
        raise ValueError("Product knowledge database mismatch")
    if identity_api.effective_access(actor, "platform.manage").get("decision") != "ALLOW":
        raise PermissionError("Product knowledge publication requires platform management")
    root = root or product_identity.package_root(__file__)
    catalog = json.loads((root / "scripts/resources/legacy-product-knowledge.json").read_text())[database]
    current = sections(product, database)
    def work(tx):
        record = builtin_knowledge.publish(actor, "product-guide:" + product["product_key"],
            {"product": product, "database": database, "sections": current}, audience="PUBLIC", scope_type="PUBLIC",
            version=_version(product["version"]),
            reason="Publish the installed product's current bilingual facts", dialect=database,
            edition=product["edition"].lower(), _tx=tx)
        retired, preserved_product = _supersede_product_entities(tx, actor, product, database)
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
            key = _entity_key(product, database, section["key"])
            existing = tx.query_one("SELECT TITLE,CONTENT FROM ENTITIES WHERE ENTITY_ID=:id AND ENTITY_TYPE='KNOWLEDGE' FOR UPDATE", {"id": key})
            if existing:
                existing = {str(k).lower(): v for k, v in existing.items()}
                if existing["title"] != section["title"] or str(existing["content"]) != section["content"]:
                    raise ValueError("Published product knowledge is immutable")
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
                "package_digest": record["digest"]}
    return connection.execute_transaction_callback(work)
