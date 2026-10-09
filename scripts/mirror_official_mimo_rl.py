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
    shim=Path("origin-fetch-shim.js")
    shim.write_text(r"""/* Maps the original public read-only API routes to captured JSON snapshots. */
(() => {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    let u;
    try { u = new URL(typeof input === "string" ? input : input.url, window.location.href); }
    catch (_) { return nativeFetch(input, init); }
    const method = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
    if (method !== "GET" && method !== "HEAD") return nativeFetch(input, init);
    const path = u.pathname.replace(/\/+$/, "");
    const endpoint = (path.match(/\/api\/([a-z0-9_-]+)$/i) || [])[1];
    const run = u.searchParams.get("run");
    const key = run === "flash" ? "flash" : "pro";
    const table = {
      runs: "runs.json", notices: "notices.json", benchmarks: "benchmarks.json",
      status: "status_" + key + ".json", live: "live_" + key + ".json",
      series: "series_" + key + ".json",
      tags: run ? "tags_" + key + ".json" : "tags.json"
    };
    if (!endpoint || !table[endpoint]) return nativeFetch(input, init);
    return nativeFetch(new URL("./origin-data/" + table[endpoint], window.location.href).href, init);
  };
})();""",encoding="utf-8")
    tag='<script src="./origin-fetch-shim.js"></script>'
    if "origin-fetch-shim.js" not in page:
        if re.search(r"</head\s*>",page,re.I): page=re.sub(r"</head\s*>",tag+"\n</head>",page,count=1,flags=re.I)
        else: page=tag+"\n"+page
    Path("index.html").write_text(page,encoding="utf-8")

    endpoints=[
      ("runs","","runs.json"),("notices","","notices.json"),("benchmarks","","benchmarks.json"),
      ("tags","?run=pro","tags_pro.json"),("tags","?run=flash","tags_flash.json"),("tags","","tags.json"),
      ("status","?run=pro","status_pro.json"),("status","?run=flash","status_flash.json"),
      ("live","?run=pro","live_pro.json"),("live","?run=flash","live_flash.json"),
      ("series","?run=pro","series_pro.json"),("series","?run=flash","series_flash.json")
    ]
    api_failures=[]
    api_bases=["https://mimo.xiaomi.com/","https://mimo.xiaomi.com/rl/"]
    for endpoint,query,filename in endpoints:
        errors=[]
        success=False
        for api_base in api_bases:
            url=urljoin(api_base,"api/"+endpoint+query)
            try:
                content,_=get(url,"application/json,text/plain,*/*")
                data=json.loads(content.decode("utf-8","replace"))
                if endpoint=="runs" and not isinstance(data.get("runs"),list): raise ValueError("missing runs array")
                if endpoint=="notices" and not isinstance(data.get("notices"),list): raise ValueError("missing notices array")
                if endpoint=="benchmarks" and not isinstance(data.get("benchmarks"),list): raise ValueError("missing benchmarks array")
                (DATA_DIR/filename).write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
                print("API",url,"->",filename,len(content))
                success=True
                break
            except Exception as e:
                errors.append({"url":url,"error":str(e)})
        if not success:
            optional=(endpoint=="tags")
            if not optional: api_failures.extend(errors)
            print("WARN API",endpoint,errors,file=sys.stderr)
    if not (DATA_DIR/"tags.json").exists():
        for source in ("tags_pro.json","tags_flash.json"):
            if (DATA_DIR/source).exists():
                (DATA_DIR/"tags.json").write_bytes((DATA_DIR/source).read_bytes())
                break
    if (DATA_DIR/"tags.json").exists():
        for alias in ("tags_pro.json","tags_flash.json"):
            if not (DATA_DIR/alias).exists():
                (DATA_DIR/alias).write_bytes((DATA_DIR/"tags.json").read_bytes())
    manifest={"upstream":ORIGIN,"fetched_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "html_bytes":len(raw),"assets":[{"url":k,"path":v[0].as_posix(),"bytes":len(v[1])} for k,v in assets.items()],
      "asset_failures":failures,"api_failures":api_failures}
    (DATA_DIR/"mirror-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    required=["runs.json","notices.json","benchmarks.json","status_pro.json","status_flash.json","series_pro.json","series_flash.json"]
    missing=[n for n in required if not (DATA_DIR/n).is_file()]
    if missing: raise RuntimeError("Missing required upstream snapshots: "+", ".join(missing))
    essentials=[x for x in failures if re.search(r"\.(css|js|mjs)(?:$|\?)",x["url"],re.I)]
    if essentials: raise RuntimeError("Original CSS/JS fetch failed: "+json.dumps(essentials))
    if api_failures: raise RuntimeError("One or more upstream API routes failed: "+json.dumps(api_failures))
    print("Official page mirrored successfully.")

if __name__=="__main__": main()
