from pathlib import Path
import hashlib,importlib.metadata,json,shutil,sys,zipfile
root=Path(__file__).resolve().parents[1]
folder=root/'bld/dist/DS2PortV90S'
for name in ('README.md','THIRD_PARTY.md','LICENSE','NOTICE'):
    shutil.copyfile(root/name,folder/name)
shutil.copytree(root/'docs',folder/'docs',dirs_exist_ok=True)
license_dir=folder/'licenses/python'
versions={}
for distribution in importlib.metadata.distributions():
    name=distribution.metadata['Name'];versions[name]=distribution.version
    for entry in distribution.files or []:
        if any(part.lower().startswith(('license','copying','notice')) for part in entry.parts):
            source=Path(distribution.locate_file(entry))
            if source.is_file():
                target=license_dir/name/Path(*entry.parts)
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
for name in ('LICENSE.txt','LICENSE'):
    source=Path(sys.base_prefix)/name
    if source.is_file():
        license_dir.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,license_dir/'CPython-LICENSE.txt');break
for source in (Path(sys.base_prefix)/'tcl').rglob('license.terms'):
    target=folder/'licenses/tcl-tk'/(source.parent.name+'-license.txt')
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
(folder/'python-packages.json').write_text(json.dumps(versions,indent=2))
for forbidden in ('msgothic.ttc','JUMP3.EXE','JUMP3.original.exe','FLOAT.EXE','FLOAT.original.exe','known_hosts','.env'):
    if any(p.name.casefold()==forbidden.casefold() for p in folder.rglob('*')):raise SystemExit('Private file in release')
items={p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file() and p.name!='checksums.json'}
(folder/'checksums.json').write_text(json.dumps(items,indent=2))
with zipfile.ZipFile(root/'bld/dist/ds2port-v90s-0.1.0-windows-x64.zip','w',zipfile.ZIP_DEFLATED) as z:
    for path in sorted(folder.rglob('*')):
        if path.is_file():z.write(path,path.relative_to(folder.parent))
print('RELEASE_PACKAGE_READY',flush=True)
