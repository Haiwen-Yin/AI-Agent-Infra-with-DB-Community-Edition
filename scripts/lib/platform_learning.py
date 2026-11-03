"""Learning contracts shared by editions, with an optional content payload."""
from __future__ import annotations

import hashlib
from pathlib import Path


def sections(product, database):
    # Community and AgentX ship the entrypoints without the curated payload.
    # Missing content is intentional; errors inside an installed payload are not.
    try:
        from .platform_learning_content import sections as content_sections
    except ModuleNotFoundError as exc:
        if exc.name != __package__ + '.platform_learning_content':
            raise
        return ()
    return content_sections(product, database)


def bind_sources(units, root: Path):
    """Bind exact shipped bytes; an absent reference blocks publication."""
    bound = []
    for unit in units:
        if 'source_paths' not in unit:
            bound.append(unit)
            continue
        sources = []
        for relative in unit['source_paths']:
            path = root / relative
            if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Platform learning source is unavailable: ' + relative)
            sources.append(dict(path=relative, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        content = unit['content'] + '\n\n来源 / Sources:\n' + '\n'.join(
            source['path'] + ' SHA-256 ' + source['sha256'] for source in sources)
        bound.append(dict(unit, content=content, sources=sources))
    return tuple(bound)
