"""Pure, bounded interpretation of explicit documentation questions.

Only a complete recognized request frame may separate instructions from its
subject. Unknown words in that frame retain the original conservative query.
Source content never selects a frame or supplies its constraints.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


_STOP_WORDS = frozenset('a an the and or of to in on at for from with by '
    'is are was were be been being it its this that these those i me my we our '
    'you your they their what which who when where why how can could would should '
    'do does did please explain describe tell about one sentence sentences briefly'.split())
_DATE = r'(?:19|20)\d{2}[-/]\d{2}[-/]\d{2}(?:[tT ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[zZ]|[+-]\d{2}:\d{2})?)?'
_VERSION = r'v?\d+(?:\.\d+)+(?:[-+][a-z0-9]+(?:[.-][a-z0-9]+)*)?'
_QUALIFIER = re.compile(r'(?<![a-z0-9_.])(?P<date>'+_DATE+r')(?![a-z0-9_]|[-/]\d)|(?<![a-z0-9_.])(?P<version>'+_VERSION+r')(?![a-z0-9_]|\.\d)|(?<![a-z0-9_])(?P<year>(?:19|20)\d{2})(?![a-z0-9_])',re.I)
_ZH_FRAME = re.compile(r'^(?:请)?(?:依据|根据|基于)(?P<context>.+?)(?:说明|介绍|解释|概述)(?P<attributes>[^:：]+)[：:]\s*(?P<subject>[^:：]+?)\s*[？?。]?$')
_EN_FRAME = re.compile(r'^(?:please\s+)?(?:according\s+to|based\s+on|using)\s+(?P<context>.+?)\s*[,，]\s*(?:please\s+)?(?:state|describe|explain|summarize)\s+(?P<attributes>[^:：]+)[：:]\s*(?P<subject>[^:：]+?)\s*[?.]?$',re.I)
_ZH_CONTEXT = re.compile(r'这份|该|所提供的|提供的|冻结的|产品|来源|资料|文档|快照|源|的')
_EN_CONTEXT = frozenset('a the this that supplied provided frozen product source documentation document documents material materials snapshot'.split())


@dataclass(frozen=True)
class Qualifier:
    kind: str
    value: str


@dataclass(frozen=True)
class Question:
    subject: str
    subject_terms: tuple[str, ...]
    qualifiers: tuple[Qualifier, ...]
    attributes: tuple[str, ...] = ()
    framed: bool = False
    frame_candidate: bool = False
    requirements: tuple[str, ...] = ()

    @property
    def terms(self):
        return list(dict.fromkeys((*self.subject_terms,*(item.value for item in self.qualifiers))))


def qualifiers(text):
    result=[]
    for match in _QUALIFIER.finditer(text.casefold()):
        kind=match.lastgroup;value=match.group()
        if kind=='version':value=value.removeprefix('v')
        item=Qualifier(kind,value)
        if item not in result:result.append(item)
    return tuple(result)


def _literal_terms(text):
    terms=[]
    for term in re.findall(r'[a-z0-9_]{2,}|\d+|[\u4e00-\u9fff]{2,}',text.casefold()):
        if re.fullmatch(r'[\u4e00-\u9fff]+',term):
            previous=None
            while term!=previous:
                previous=term
                term=re.sub(r'^(?:请问|请|帮我|给我|麻烦|我想了解|想了解|查询一下|查询|查一下|介绍一下|介绍|解释一下|解释|告诉我|了解一下|了解|关于)','',term)
                term=re.sub(r'(?:是什么|有哪些功能|有什么功能|的相关信息|的基本情况|的信息|的情况|怎么样)$','',term)
        if (len(term)>=2 or term.isdigit()) and term not in _STOP_WORDS:terms.append(term)
    return tuple(dict.fromkeys(terms))


def _attributes(text,language):
    if language=='zh':
        text=re.sub(r'^(?:其|该(?:产品|平台)的|(?:产品|平台)的?)','',text.strip())
        pieces=re.split(r'以及|和|与|及|[、,，]',text)
        names={'身份':'identity','名称':'identity','版本':'version','快照版本':'version','源版本':'version'}
    else:
        text=re.sub(r'^(?:its|the\s+(?:product|platform)(?:\x27s)?)\s+','',text.strip(),flags=re.I)
        pieces=re.split(r'\s+and\s+|\s*,\s*',text,flags=re.I)
        names={'identity':'identity','name':'identity','version':'version','source version':'version','snapshot version':'version','release version':'version'}
    values=[names.get(piece.strip().casefold()) for piece in pieces]
    return tuple(dict.fromkeys(values)) if 1<=len(values)<=3 and all(values) else ()


def claim_terms(text):
    """Literal claim terms, without guessing synonyms or dropping constraints."""
    return _literal_terms(_QUALIFIER.sub(' ',text))


def _requirements(question):
    # These explicit layouts accept arbitrary claim names. Unknown language
    # outside them keeps the conservative original question, including all
    # qualifiers, negation, numbers and additional subjects.
    patterns=(
        (re.compile(r'^(?:please\s+)?(?:explain|describe|state|list)\s+(?P<claims>.+?)\s+for\s+(?P<subject>[^:;\n]+?)[?.]?$',re.I),'en'),
        (re.compile(r'^(?P<subject>[^:：;；\n]{1,256})[：:]\s*(?P<claims>[^:：\n]+?)[?？。]?$',re.I),'list'),
        (re.compile(r'^(?:请)?(?:说明|介绍|列出|解释)?(?P<subject>[^的:：;；\n]{1,256})的(?P<claims>[^的:：;；\n]+?)(?:是什么|有哪些|[?？。])?$'),'zh'),
    )
    for pattern,language in patterns:
        match=pattern.fullmatch(question.strip())
        if not match:
            continue
        subject=match['subject'].strip()
        raw=re.sub(r'^(?:the|its)\s+','',match['claims'].strip(),flags=re.I) if language=='en' else match['claims'].strip()
        pieces=tuple(dict.fromkeys(item.strip() for item in re.split(r'\s+and\s+|以及|和|与|及|[、,，;；]',raw,flags=re.I) if item.strip()))
        if ((2 if language=='list' else 1)<=len(pieces)<=4 and claim_terms(subject)
                and not re.search(r'以及|和|与|[、,，;；]|\band\b',subject,re.I)
                and all(claim_terms(item) and len(item)<=200 for item in pieces)
                and not re.search(r'https?://|[\n`{}]',question,re.I)):
            return subject,pieces
    return question,()


def interpret(question):
    subject=question;attributes=();framed=False;frame_candidate=False
    for language,pattern in (('zh',_ZH_FRAME),('en',_EN_FRAME)):
        match=pattern.fullmatch(question.strip())
        if not match:continue
        frame_candidate=True
        context=_QUALIFIER.sub(' ',match['context']).strip()
        if language=='zh':
            known=bool(re.search(r'资料|文档',context)) and not re.sub(r'\s+','',_ZH_CONTEXT.sub('',context))
        else:
            words=context.casefold().split()
            known=bool(set(words)&{'documentation','document','documents','source','material','materials','snapshot'}) and all(word in _EN_CONTEXT for word in words)
        parsed_attributes=_attributes(match['attributes'],language)
        focus=match['subject'].strip()
        # A second subject delimiter, URL or additional instruction is outside
        # this grammar. Its original terms must continue to constrain evidence.
        if (known and parsed_attributes and _literal_terms(_QUALIFIER.sub(' ',focus))
                and not re.search(r'[;；\n]',focus)):
            subject=focus;attributes=parsed_attributes;framed=True
        break
    requirements=()
    if not frame_candidate:
        subject,requirements=_requirements(question)
    subject_terms=_literal_terms(_QUALIFIER.sub(' ',subject))
    return Question(subject,subject_terms,qualifiers(question),attributes,framed,frame_candidate,requirements)


def requested_parts(question):
    parsed=interpret(question)
    if not parsed.requirements:
        return ()
    # Reuse exact query qualifiers in every recall request. A fact from a
    # different release/date cannot satisfy a sibling claim through merging.
    scope=' '.join(value.value for value in parsed.qualifiers)
    return tuple(' '.join(part for part in (parsed.subject,scope,claim) if part) for claim in parsed.requirements)


def supports_qualifier(text,qualifier):
    actual=qualifiers(text)
    if qualifier in actual:return True
    if qualifier.kind=='year':
        return any(item.kind=='date' and item.value[:4]==qualifier.value for item in actual)
    if qualifier.kind=='date' and len(qualifier.value)==10:
        return any(item.kind=='date' and item.value.startswith(qualifier.value+'t') for item in actual)
    return False


def supports_term(text,term):
    text=text.casefold();term=term.casefold()
    exact=qualifiers(term)
    if len(exact)==1 and exact[0].value==term.removeprefix('v'):
        return supports_qualifier(text,exact[0])
    return bool(re.search(r'(?<![a-z0-9_])'+re.escape(term)+r'(?![a-z0-9_])',text)) if term.isascii() else term in text
