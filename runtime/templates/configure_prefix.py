"""Configure this tool's Wine 10 registry after its wineserver has stopped."""
import json
from pathlib import Path
import re
import shutil
import sys
import time


def merge_section(text, section, values, remove=()):
    lines=text.splitlines(keepends=True)
    start=None
    for i,line in enumerate(lines):
        header=re.match(r'^\[(.*)\]',line)
        if header and header.group(1)==section:
            start=i;break
    if start is None:
        if not values:return text
        if text and not text.endswith('\n'):text+='\n'
        text+='\n['+section+'] '+str(int(time.time()))+'\n'
        lines=text.splitlines(keepends=True);start=len(lines)-1
    end=start+1
    while end<len(lines) and not lines[end].startswith('['):end+=1
    names=set(values)|set(remove)
    encoded_names={json.dumps(name)[1:-1] for name in names}
    body=[]
    for line in lines[start+1:end]:
        match=re.match(r'^"((?:[^"\\]|\\.)*)"=',line)
        if not match or match.group(1) not in encoded_names:body.append(line)
    while body and not body[-1].strip():body.pop()
    body += [json.dumps(name)+'='+json.dumps(value)+'\n' for name,value in values.items()]
    lines[start+1:end]=body+['\n']
    return ''.join(lines)


def configure(prefix):
    prefix=Path(prefix)
    system,user=prefix/'system.reg',prefix/'user.reg'
    if not system.is_file() or not user.is_file():raise RuntimeError('Wine初期化が完了していません。')
    changes={system:[(r'System\\CurrentControlSet\\Control\\Nls\\CodePage',{'ACP':'932','OEMCP':'932','MACCP':'10001'},())],
             user:[(r'Control Panel\\International',{'Locale':'00000411','LocaleName':'ja-JP'},()),
                   (r'Software\\Wine\\Direct3D',{'renderer':'gdi'},()),
                   (r'Software\\Wine\\X11 Driver',{'Managed':'N','Decorated':'N'},()),
                   (r'Software\\Wine\\Fonts\\Replacements',{},('MS Gothic','MS PGothic','MS UI Gothic'))]}
    for path,sections in changes.items():
        text=path.read_text(encoding='utf-8')
        for section,values,remove in sections:text=merge_section(text,section,values,remove)
        backup=path.with_name(path.name+'.ds2port-before')
        if not backup.exists():shutil.copy2(path,backup)
        temporary=path.with_name(path.name+'.ds2port-new')
        temporary.write_text(text,encoding='utf-8');temporary.replace(path)
    print('JAPANESE_PREFIX_CONFIGURED ACP=932')


if __name__=='__main__':configure(sys.argv[1])
