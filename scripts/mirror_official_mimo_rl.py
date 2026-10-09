#!/usr/bin/env python3
"""Fetch public MiMo RL HTML/assets/API snapshots for a static GitHub Pages mirror."""
from __future__ import annotations
import html, json, mimetypes, os, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

ORIGIN = "https://mimo.xiaomi.com/rl/"
HOST = "mimo.xiaomi.com"
ASSET_DIR = Path("origin")
DATA_DIR = Path("origin-data")
UA = "Mozilla/5.0 (compatible; MiMoRLMirror/1.0)"
EXTS = {".css",".js",".mjs",".map",".svg",".png",".jpg",".jpeg",".webp",".gif",".ico",".woff",".woff2",".ttf",".otf",".eot",".avif"}
ATTR_RE = re.compile(r"""(?P<prefix>\b(?:src|href|poster|xlink:href)=)(?P<q>["'])(?P<url>[^"']+)(?P=q)""", re.I)
URL_RE = re.compile(r"""url\(\s*(?P<q>["']?)(?P<url>[^)"']+)(?P=q)\s*\)""", re.I)
IMPORT_RE = re.compile(r"""@import\s+(?:url\(\s*)?["']?([^"')\s;]+)""", re.I)
STR_RE = re.compile(r"""["']([^"']+\.(?:css|js|mjs|woff2?|ttf|otf|svg|png|jpe?g|webp|gif|ico|avif)(?:\?[^"']*)?)["']""", re.I)

def norm(url):
    p=urlparse(url); return urlunparse((p.scheme,p.netloc,p.path,"","",""))

def get(url, accept="*/*"):
    req=Request(url, headers={"User-Agent":UA,"Accept":accept,"Cache-Control":"no-cache"})
    with urlopen(req, timeout=45) as r: return r.read(),r.geturl()

def local_path(url):
    p=urlparse(url)
    if p.netloc==HOST and p.path.startswith("/rl/"): return ASSET_DIR / p.path[len("/rl/"):]
    return Path("origin-external") / (p.netloc or "relative").replace(":","_") / p.path.lstrip("/")

def is_asset(url):
    p=urlparse(url); return p.scheme in ("http","https") and bool(p.netloc) and Path(p.path).suffix.lower() in EXTS

def relpath(source,target):
    value=os.path.relpath(target.as_posix(), start=source.parent.as_posix() or ".").replace("\\","/")
    return value if value.startswith(".") else "./"+value

def refs(content,base):
    out=[]
    for pat in (URL_RE,):
        for m in pat.finditer(content):
            u=m.group("url").strip()
            if u and not u.startswith(("data:","#","blob:","javascript:")):
                v=urljoin(base,u)
                if is_asset(v): out.append(v)
    for m in IMPORT_RE.finditer(content):
        u=m.group(1).strip()
        if u and not u.startswith(("data:","#")):
            v=urljoin(base,u)
            if is_asset(v): out.append(v)
    for m in STR_RE.finditer(content):
        u=m.group(1).strip()
        if not u.startswith(("data:","#")):
            v=urljoin(base,u)
            if is_asset(v): out.append(v)
    return out

def main():
    ASSET_DIR.mkdir(parents=True,exist_ok=True); DATA_DIR.mkdir(parents=True,exist_ok=True)
    print("Fetching official page",ORIGIN)
    raw,page_url=get(ORIGIN,"text/html,application/xhtml+xml,*/*")
    page=raw.decode("utf-8","replace")
    if "<html" not in page.lower() or len(page)<500: raise RuntimeError("Origin response is not the actual HTML page")
    page=re.sub(r"<base\b[^>]*>",'<base href="./">',page,flags=re.I)
    if not re.search(r"<base\b",page,flags=re.I):
        page=re.sub(r"<head\b[^>]*>",lambda m:m.group(0)+'\n<base href="./">',page,count=1,flags=re.I)

    pending=[]
    for m in ATTR_RE.finditer(page):
        u=html.unescape(m.group("url").strip()); v=urljoin(page_url,u)
        if is_asset(v): pending.append(v)
    pending.extend(refs(page,page_url))
    assets={}; failures=[]
    while pending:
        url=pending.pop(0); key=norm(url)
        if key in assets: continue
        target=local_path(url)
        try:
            content,final=get(url); key=norm(final); target=local_path(final)
            if key in assets: continue
            assets[key]=(target,content,final)
            print("ASSET",url,"->",target,len(content))
            if target.suffix.lower() in {".css",".js",".mjs"}:
                pending.extend(refs(content.decode("utf-8","replace"),final))
        except Exception as e:
            failures.append({"url":url,"error":str(e)})
            print("WARN asset",url,e,file=sys.stderr)

    asset_map={k:v[0] for k,v in assets.items()}
    # Extract exact static-data references and paths from the unmodified upstream bundle.
    for key,(target,content,final) in assets.items():
        if target.suffix.lower() not in {".js", ".mjs"}:
            continue
        source_text=content.decode("utf-8","replace")
        lines=source_text.splitlines()
        printed=0
        for line_no,line in enumerate(lines,1):
            if any(token in line for token in (".json", "const DATA", "getJSON(", "DATA}")):
                print("UPSTREAM_DATA_LINE",target.name,line_no,line.strip()[:500])
                printed+=1
                if printed>=120: break
    for key,(target,content,final) in assets.items():
        if target.suffix.lower() not in {".js", ".mjs"}:
            continue
        source_text=content.decode("utf-8","replace")
        for m in re.finditer(r"data\\.[a-f0-9]+/|[A-Za-z0-9_./-]+\\.json",source_text):
            snippet=source_text[max(0,m.start()-100):min(len(source_text),m.end()+130)].replace("\\n"," ")
            print("UPSTREAM_DATA_PATH",target.name,snippet[:320])
    for key,(target,content,final) in assets.items():
        if target.suffix.lower() not in {".js", ".mjs"}:
            continue
        source_text=content.decode("utf-8","replace")
        seen=set()
        for m in re.finditer(r"(?:fetch|/api|api/|API_BASE|status\?|series\?|live\?|notices|benchmarks|tags\?|runs)",source_text,re.I):
            snippet=source_text[max(0,m.start()-100):min(len(source_text),m.end()+170)].replace("\\n"," ")
            if snippet not in seen:
                print("UPSTREAM_JS_ROUTE",target.name,snippet[:290])
                seen.add(snippet)
            if len(seen)>=50: break
    for key,(target,content,final) in assets.items():
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.suffix.lower() not in {".css",".js",".mjs"}:
            target.write_bytes(content); continue
        s=content.decode("utf-8","replace")
        def replace_url(raw):
            target_path=asset_map.get(norm(urljoin(final,raw.strip())))
            return relpath(target,target_path) if target_path else raw
        if target.suffix.lower()==".css":
            s=URL_RE.sub(lambda m:"url("+m.group("q")+replace_url(m.group("url"))+m.group("q")+")",s)
            s=IMPORT_RE.sub(lambda m:m.group(0).replace(m.group(1),replace_url(m.group(1)),1),s)
        else:
            def repl(m):
                raw=m.group(1); target_path=asset_map.get(norm(urljoin(final,raw)))
                if not target_path: return m.group(0)
                q=m.group(0)[0]; return q+relpath(target,target_path)+q
            s=STR_RE.sub(repl,s)
        target.write_text(s,encoding="utf-8")

    def rewrite_attr(m):
        raw=html.unescape(m.group("url").strip())
        target=asset_map.get(norm(urljoin(page_url,raw)))
        if not target: return m.group(0)
        return m.group("prefix")+m.group("q")+relpath(Path("index.html"),target)+m.group("q")
    page=ATTR_RE.sub(rewrite_attr,page)
    Path("index.html").write_text(page,encoding="utf-8")

    # This upstream build is static: the original app.js reads these files from
    # DATA = "data.04135c89/" and expects these exact filenames.
    app_sources=[content.decode("utf-8","replace") for _,(target,content,_) in assets.items() if target.name.startswith("app.") and target.suffix.lower()==".js"]
    app_source="\\n".join(app_sources)
    data_match=re.search(r'const DATA\\s*=\\s*["\\']([^"\\']+)["\\']',app_source)
    if not data_match:
        raise RuntimeError("The official app bundle no longer declares its static DATA directory.")
    data_prefix=data_match.group(1)
    data_dir=Path(data_prefix.rstrip("/"))
    data_dir.mkdir(parents=True,exist_ok=True)
    data_files=[
        "runs.json","notices.json","benchmarks.json",
        "status-pro.json","status-flash.json",
        "live-pro.json","live-flash.json",
        "tags-pro.json","tags-flash.json",
        "series-pro.json","series-flash.json",
    ]
    data_failures=[]
    for filename in data_files:
        url=urljoin(page_url,data_prefix+filename)
        try:
            content,_=get(url,"application/json,text/plain,*/*")
            payload=json.loads(content.decode("utf-8","replace"))
            if not isinstance(payload,(dict,list)):
                raise ValueError("unexpected JSON document shape")
            (data_dir/filename).write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
            print("STATIC DATA",url,"->",(data_dir/filename).as_posix(),len(content))
        except Exception as e:
            data_failures.append({"url":url,"error":str(e)})
            print("WARN static data",url,e,file=sys.stderr)
    manifest={"upstream":ORIGIN,"fetched_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "html_bytes":len(raw),"assets":[{"url":k,"path":v[0].as_posix(),"bytes":len(v[1])} for k,v in assets.items()],
      "asset_failures":failures,"api_failures":api_failures}
    (DATA_DIR/"mirror-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    required=[data_dir/name for name in data_files]
    missing=[name.as_posix() for name in required if not name.is_file() or name.stat().st_size==0]
    if missing:
        raise RuntimeError("Missing required original static JSON files: "+", ".join(missing))
    essentials=[x for x in failures if re.search(r"\\.(css|js|mjs)(?:$|\\?)",x["url"],re.I)]
    if essentials:
        raise RuntimeError("Original CSS/JS fetch failed: "+json.dumps(essentials))
    manifest["static_data_dir"]=data_prefix
    manifest["static_data_files"]=[p.as_posix() for p in required]
    manifest["static_data_failures"]=data_failures
    (DATA_DIR/"mirror-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Official page mirrored successfully.")

if __name__=="__main__": main()
