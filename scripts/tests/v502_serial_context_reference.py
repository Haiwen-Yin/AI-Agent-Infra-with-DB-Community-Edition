"""Read the original final501 serial implementation in private module names.

This is a test reference, not a second runtime or an old authorization service.
Only the selected read implementations come from the original archive. Their
ordinary connection and policy dependencies remain the actual tested package.
No production ``lib.*`` module is replaced and no selected source is edited.
"""
from contextlib import contextmanager
import builtins
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace
import uuid
import zipfile

FILES=('continuity_sources','context_selection','continuity_assembly','memory_lifecycle','agent_assets')
INVENTORY='release_evidence/v5.0.1-development/local-delivery-r21-20261023/local-delivery-inventory.json'
INVENTORY_SHA256='3a5a8d34ef647c24be44ddaf5d186dbb7b0c2f57014fadccf2eb4ccd56683fe2'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def regular(root,path):
    path=Path(path)
    if not path.is_absolute():path=root/path
    if '..' in path.parts or not path.is_relative_to(root) or any(item.is_symlink() for item in (path,*path.parents) if item!=root):
        raise ValueError('Original reference paths must stay in the selected checkout')
    if not path.is_file():raise ValueError('Original reference file is missing')
    return path


def describe(root,entry):
    root=Path(root).absolute()
    inventory=regular(root,root/INVENTORY)
    if sha(inventory)!=INVENTORY_SHA256:raise ValueError('Original final501 inventory changed')
    observed=json.loads(inventory.read_text())
    if observed.get('version')!='5.0.1' or observed.get('completed_packaging_date')!='2026-10-23' or observed.get('release_ready') is not True:
        raise ValueError('Original final501 delivery identity is required')
    rows=[item for item in observed['archives'] if item.get('product')==entry['product']]
    if len(rows)!=1:raise ValueError('Select exactly the same product original501 archive')
    row=rows[0];archive=regular(root,root/row['path'])
    package=root/'build_output/v5.0.1/final-20261023-r21'/entry['package']
    if archive!=package.parent/(entry['package']+'-v5.0.1.zip') or sha(archive)!=row['sha256'] or archive.stat().st_size!=row['bytes']:
        raise ValueError('The actual original final501 archive changed')
    manifest=regular(root,package/'build-manifest.json');inventory_file=regular(root,package/'package-files.sha256')
    identity=json.loads(manifest.read_text());product=identity.get('delivery_product',{})
    if identity.get('version')!='5.0.1' or identity.get('release_date')!='2026-10-23' or product.get('key')!=entry['product'] or entry['database'] not in product.get('databases',[]):
        raise ValueError('The serial reference must match this product/backend')
    selected={name:regular(root,package/'scripts/lib'/(name+'.py')) for name in FILES}
    with zipfile.ZipFile(archive) as saved:
        for path in (manifest,inventory_file,*selected.values()):
            if saved.read(entry['package']+'/'+str(path.relative_to(package)))!=path.read_bytes():
                raise ValueError('Original reference source differs from its final501 archive')
    return dict(schema='chuanxu-v502-original501-read-reference/v1',root=str(root),product=entry['product'],
        database=entry['database'],package=str(package),inventory=dict(path=str(inventory),sha256=INVENTORY_SHA256),
        archive=dict(path=str(archive),sha256=row['sha256']),package_manifest_sha256=sha(inventory_file),
        build_manifest_sha256=sha(manifest),files={name:dict(path=str(path),sha256=sha(path)) for name,path in selected.items()},
        scope='ORIGINAL501_SERIAL_READS_ON_CURRENT_PACKAGE_AUTHORITY_FACADE')


@contextmanager
def load(value):
    """Verify original bytes, then redirect only this reference's imports."""
    from product_delivery import acceptance_targets
    from lib.product_identity import read_manifest
    from lib import connection
    if not isinstance(value,dict) or value.get('schema')!='chuanxu-v502-original501-read-reference/v1':
        raise ValueError('Select the exact original501 read-reference descriptor')
    root=Path(value['root'])
    entry=next((item for item in acceptance_targets() if item['product']==value.get('product') and item['database']==value.get('database')),None)
    if entry is None or describe(root,entry)!=value:raise ValueError('The original501 reference identity changed')
    current=read_manifest()
    actual_database='pg' if connection.DATABASE_DIALECT in {'pg','postgresql'} else connection.DATABASE_DIALECT
    if current.get('version')!='5.0.2' or current.get('delivery_product',{}).get('key')!=entry['product'] or actual_database!=entry['database']:
        raise ValueError('The original reference must run against the same actual502 product/backend')
    selected={};private=[]
    def imports(name,globals=None,locals=None,fromlist=(),level=0):
        original=builtins.__import__(name,globals,locals,fromlist,level)
        if level==1 and name in selected:return selected[name]
        if level==1 and name=='' and any(item in selected for item in fromlist):
            proxy=ModuleType('lib');proxy.__dict__.update(vars(original))
            for item in fromlist:
                if item in selected:setattr(proxy,item,selected[item])
            return proxy
        return original
    try:
        for name in FILES:
            module=ModuleType('_cx501_read_reference_'+uuid.uuid4().hex+'_'+name)
            module.__package__='lib';module.__file__=value['files'][name]['path']
            module.__dict__['__builtins__']={**vars(builtins),'__import__':imports}
            selected[name]=module;sys.modules[module.__name__]=module;private.append(module.__name__)
            exec(compile(Path(module.__file__).read_bytes(),module.__file__,'exec'),module.__dict__)
        yield SimpleNamespace(**selected,identity=value)
    finally:
        for name in private:sys.modules.pop(name,None)
