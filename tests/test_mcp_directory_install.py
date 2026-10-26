"""Directory MCP API round trips against the current source, with no app copy."""
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zlib

ROOT=Path(__file__).resolve().parents[1]
def default_host():
    return next((p for p in (ROOT/".build/host/xs.exe",ROOT/".build/mcp-directory-host/xsw.exe") if p.is_file()),ROOT/".build/host/xs.exe")


def payload(path,data):
    return dict(path=path,base64=base64.b64encode(zlib.compress(data)).decode(),encoding="zlib",
                size=len(data),sha256=hashlib.sha256(data).hexdigest(),mode=0o755 if path.endswith(".exe") else 0o644)


def package(files=None):
    recipe=json.loads((ROOT/"computer_use/template.json").read_text(encoding="utf-8"))
    recipe.update(format="mdo.mcp-template.v2",id="folder-fixture",inputs=[])
    recipe["variants"]=recipe["variants"][:1]
    recipe["variants"][0]["config"]["transport"].update(program="./bin/windows-x86_64/server.exe",working_directory=".",inherit_environment=False)
    return dict(format="mdo.extension.v2",manifest=dict(slug="folder-fixture",name="Directory fixture",version="1.0.0",
        description="Directory transport",readme="Inspect the directory.",license="MIT",platforms=["windows-x86_64"],min_build_id=70000057),
        resources=[dict(kind="mcp",id="folder-fixture",content=json.dumps(recipe,ensure_ascii=False),
        files=files or [payload("bin/windows-x86_64/server.exe",b"not executed by installation"*300),payload("resources/readme.txt","中文 file\0".encode())])])


class NativeApp:
    def __init__(self,base,host):
        self.base,self.host=base,host.resolve()
        self.home=base/"home";self.home.mkdir(exist_ok=True)
        self.probe=ROOT/"app/generated/mcp_directory_app_test.c"
        self.config=ROOT/"app/xs.mcp-directory-app-test.json"
        self.probe.write_text('#define MDO_BUILD_ID 70000057u\n#include "generated/mdo_unity.c"\n')
        with socket.socket() as s:s.bind(("127.0.0.1",0));self.port=s.getsockname()[1]
        self.config.write_text(json.dumps(dict(services=[dict(enabled=True,**{"class":"http"},name="mcp-directory",ip="127.0.0.1",port=self.port,
            recv_limit=104988672,body_limit=104873984,
            host_default=dict(enabled=True,name="mdo",path="web",devlang="c",devfile="generated/mcp_directory_app_test.c"))])))
        self.token="";self.child=None
    def request(self,path,body=None,status=200,revision=None,method=None):
        headers={"Content-Type":"application/json"}
        if body is not None or method in ("PUT","POST","DELETE"):headers["X-Mdo-Write-Token"]=self.token
        if revision:headers["If-Match"]='"'+revision+'"'
        req=urllib.request.Request(f"http://127.0.0.1:{self.port}/api/v1"+path,
            data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers=headers,method=method)
        try:r=urllib.request.urlopen(req,timeout=180)
        except urllib.error.HTTPError as e:r=e
        raw=r.read();assert r.status==status,(path,r.status,raw[:3000])
        result=json.loads(raw);self.token=r.headers.get("X-Mdo-Write-Token",self.token)
        return result.get("data")
    def __enter__(self):
        self.log=(self.base/"runtime.log").open("wb")
        self.child=subprocess.Popen([str(self.host),str(self.config)],cwd=ROOT/"app",stdout=self.log,stderr=self.log,
            env=dict(os.environ,MDO_HOME=str(self.home),USE_WEBVIEW="0"),creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        deadline=time.monotonic()+45
        while time.monotonic()<deadline and self.child.poll() is None:
            try:self.request("/account");return self
            except (OSError,AssertionError):time.sleep(.1)
        self.close();raise AssertionError((self.base/"runtime.log").read_text(errors="replace")[-12000:])
    def close(self):
        if self.child and self.child.poll() is None:
            try:
                for item in self.request("/mcp").get("items",[]):
                    if item.get("connected"):self.request("/mcp/"+item["id"]+"/disconnect",method="POST")
            except (OSError,AssertionError):pass
            if self.child.poll() is None:
                if os.name=="nt":subprocess.run(["taskkill","/PID",str(self.child.pid),"/T","/F"],capture_output=True)
                else:self.child.terminate()
        if self.child:self.child.wait(timeout=8)
        if hasattr(self,"log"):self.log.close()
        self.config.unlink(missing_ok=True);self.probe.unlink(missing_ok=True)
    def __exit__(self,*args):self.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--host",type=Path,default=default_host());args=parser.parse_args()
    (ROOT/".build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mcp-install-",dir=ROOT/".build") as raw:
        with NativeApp(Path(raw),args.host) as app:
            from test_mcp_runtime import server_document
            selected=Path(raw)/"program";selected.mkdir();(selected/"entry.exe").write_bytes(b"source executable");(selected/"dependency.dll").write_bytes(b"dependency")
            original=json.loads(server_document(str(selected/"entry.exe"),"one","two",server_id="author"));original["enabled"]=False;original["transport"]["environment"]=[]
            authored=app.request("/extensions/mcp/author",dict(content=json.dumps(original)),revision="new",method="PUT")
            app.request("/mcp/connections",dict(action="copy_program",id="author",directory=str(Path(raw)),confirm_copy=False),revision=authored["revision"],status=409)
            app.request("/mcp/connections",dict(action="copy_program",id="author",directory=str(selected),confirm_copy=True),revision=authored["revision"])
            author_root=app.home/"mcp/author";assert (author_root/"dependency.dll").read_bytes()==b"dependency" and (selected/"entry.exe").exists()
            assert not (app.home/"mcp/author.json").exists()
            authored=json.loads((author_root/"mcp.json").read_text(encoding="utf-8"));assert authored["transport"]["program"]=="./entry.exe"
            (author_root/".env").write_text("private-marker-do-not-publish")
            authored_export=app.request("/ecosystem",dict(action="export",single_kind="mcp",references=[dict(kind="mcp",id="author")]))
            assert {f["path"] for f in authored_export["resources"][0]["files"]}=={"entry.exe","dependency.dll"}
            p=package();bundle=app.home/"mcp/folder-fixture"
            def store(action,**extra):return app.request("/ecosystem",dict(action=action,single_kind="mcp",**extra))
            plan=store("plan_import",package=p);assert not bundle.exists()
            assert any(f["path"]=="mcp/folder-fixture/mcp.json" for f in plan["files"])
            store("import",package=p,expected_plan=plan["sha256"])
            for f in p["resources"][0]["files"]:
                assert hashlib.sha256((bundle/f["path"]).read_bytes()).hexdigest()==f["sha256"]
            cfg=json.loads((bundle/"mcp.json").read_text(encoding="utf-8"));assert cfg["enabled"] is False and cfg["transport"]["program"].startswith("./")
            items=app.request("/extensions/mcp")["items"];item=next(i for i in items if i["id"]=="folder-fixture")
            assert item["valid"] and item["path"]=="mcp/folder-fixture/mcp.json",item
            assert any(i["template"]["format"]=="mdo.mcp-template.v2" for i in app.request("/mcp/templates")["items"])
            assert not next(i for i in app.request("/mcp")["items"] if i["id"]=="folder-fixture")["connected"]
            exported=store("export",references=[dict(kind="mcp",id="folder-fixture")])
            assert len(exported["resources"][0]["files"])==2
            assert json.loads(exported["resources"][0]["content"])["variants"][0]["config"]["transport"]["program"].startswith("./")
            app.request("/mcp/connections",dict(id="folder-fixture",action="save",name="Device name",variant="windows",values={},confirm_launch=True),revision=item["revision"])
            updated=copy.deepcopy(p);updated["manifest"]["version"]="1.0.1";updated["resources"][0]["files"][0]=payload("bin/windows-x86_64/server.exe",b"updated program")
            store("import",package=updated)
            assert json.loads((bundle/"mcp.json").read_text(encoding="utf-8"))["name"]=="Device name"
            assert (bundle/"bin/windows-x86_64/server.exe").read_bytes()==b"updated program"
            store("uninstall",entry=dict(source="local",slug="folder-fixture"))
            assert (bundle/"mcp.json").exists() and not json.loads((bundle/"mcp.json").read_text(encoding="utf-8"))["enabled"]
            assert not (bundle/"bin/windows-x86_64/server.exe").exists()
    print("PASS source-native directory MCP plan/import/export/update/uninstall, private configuration preservation and cold install")


if __name__=="__main__":main()
