"""Native MCP directory checks, using this checkout without an application copy."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

from test_mcp_runtime import server_document

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=Path, default=Path("D:/GIT/mdo/.build/host/xs.exe"))
    args = parser.parse_args()
    (ROOT / ".build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mcp-directory-", dir=ROOT / ".build") as temporary:
        base = Path(temporary)
        home = base / "home"
        folder = home / "mcp/mock/bin"
        folder.mkdir(parents=True)
        (folder / "tool.exe").write_bytes(b"not executed during discovery")
        valid = json.loads(server_document("./bin/tool.exe", "unused-script", "unused-marker"))
        valid["transport"]["working_directory"] = "."
        config_file = folder.parent / "mcp.json"
        config_file.write_text(json.dumps(valid))
        legacy=json.loads(server_document(os.sys.executable,"legacy-script","legacy-marker",server_id="legacy"))
        (home / "mcp/legacy.json").write_text(json.dumps(legacy))
        (folder / "ignored.json").write_text("not an MCP configuration")
        bad = json.loads(json.dumps(valid))
        bad["transport"]["program"] = "../escape.exe"
        report = base / "report.json"
        includes = "\n".join(f'#include {json.dumps(name.removeprefix("app/"))}' for name in (
            "app/src/storage/home.c", "app/src/security/secrets.c",
            "app/src/mcp/manager.c", "app/include/mdo/extension_files.h"))
        source = '#include <xsbase.h>\n#include <xwork.h>\nbool MdoApplicationPluginHasFile(cstr Path){(void)Path;return false;}\n' + includes + "\n"
        source += '#define REPORT ' + json.dumps(report.as_posix()) + '\n'
        source += '#define VALID ' + json.dumps(json.dumps(valid)) + '\n'
        source += '#define BAD ' + json.dumps(json.dumps(bad)) + '\n'
        source += r'''
static xvalue* Failures;
static void Check(bool Ok,cstr Name){if(!Ok)xrtValueArrayAppendNew(Failures,xrtValueString(xrtStrView(Name)));}
void ServiceInit(XS_HostInfo* Host){
    (void)Host;Failures=xrtValueArray();xwork_runtime_config Config;xworkRuntimeConfigInit(&Config);
    xwork_error Error={0};xwork_runtime* Runtime=NULL;
    Check(MdoHomeInit(),"home");Runtime=xworkRuntimeCreate(&Config,&Error);
    Check(Runtime&&MdoMcpManagerInit(Runtime),"manager-init");
    MdoMcpDiagnostics* Diagnostics=MdoMcpDiagnosticsSnapshot();
    for(size_t I=0;I<MdoMcpDiagnosticsCount(Diagnostics);I++){MdoMcpDiagnosticInfo D={0};D.Size=sizeof(D);if(MdoMcpDiagnosticsAt(Diagnostics,I,&D)&&D.Message)xrtValueArrayAppendNew(Failures,xrtValueString(xrtStrView(D.Message)));}
    MdoMcpDiagnosticsRelease(Diagnostics);
    MdoMcpCatalog* Catalog=MdoMcpCatalogSnapshot();MdoMcpServerInfo Info={0};Info.Size=sizeof(Info);
    Check(MdoMcpCatalogCount(Catalog)==2,"legacy-coexists");
    bool Found=false;for(size_t I=0;I<MdoMcpCatalogCount(Catalog);I++)if(MdoMcpCatalogAt(Catalog,I,&Info)&&!strcmp(Info.Id,"mock")){Found=true;break;}
    Check(Found,"directory-discovered");
    Check(Info.Program&&xrtPathIsAbs(Info.Program)&&strstr(Info.Program,"tool.exe"),"program-anchored");
    Check(Info.WorkingDirectory&&xrtPathIsAbs(Info.WorkingDirectory),"cwd-anchored");
    MdoMcpCatalogRelease(Catalog);
    MdoMcpServerStatus Status={0};Status.Size=sizeof(Status);
    Check(MdoMcpManagerGetStatus("mock",&Status)&&!Status.Connected,"cold-discovery");
    char Path[160];MdoMcpConfigPath("mock",Path,sizeof(Path));Check(!strcmp(Path,"mcp/mock/mcp.json"),"editor-path");
    Check(MdoHomeAtomicWrite(Path,BAD,strlen(BAD),false)&&MdoMcpManagerReload(),"bad-reload");
    Catalog=MdoMcpCatalogSnapshot();Check(MdoMcpCatalogCount(Catalog)==1,"traversal-rejected");MdoMcpCatalogRelease(Catalog);
    Check(MdoHomeAtomicWrite(Path,VALID,strlen(VALID),false)&&MdoMcpManagerReload(),"restored");
    uint64 Generation=MdoMcpManagerGeneration();
    Check(MdoHomeAtomicWrite("mcp/mock.json",VALID,strlen(VALID),false),"collision-write");
    Check(!MdoMcpManagerReload()&&MdoMcpManagerGeneration()==Generation,"duplicate-id-transaction");
    Check(MdoHomeRemove("mcp/mock.json",false)&&MdoMcpManagerReload(),"collision-clean");
    MdoMcpManagerUnit();if(Runtime)xworkRuntimeRelease(Runtime);MdoHomeUnit();
    size_t Size=0;char* Text=xrtJsonStringify(Failures,false,&Size);
    if(Text)xrtFileWriteAtomic(REPORT,(xbytesview){(cbytes)Text,Size});xrtFree(Text);xrtValueRelease(Failures);
}
XS_RequestResult RequestProc(XS_HttpReq* Request){(void)Request;return XS_FALLBACK;}
'''
        probe_path=ROOT / "app/generated/mcp_directory_test.c"
        probe_path.write_text(source, encoding="utf-8")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        config = {"services": [{"enabled": True, "class": "http", "name": "directory",
            "ip": "127.0.0.1", "port": port, "host_default": {"enabled": True,
            "name": "directory", "path": "web", "devlang": "c",
            "devfile": "generated/mcp_directory_test.c"}}]}
        config_path=ROOT / "app/xs.mcp-directory-test.json"
        config_path.write_text(json.dumps(config))
        with (base / "host.log").open("wb") as output:
            child = subprocess.Popen([str(args.host.resolve()), str(config_path)],
                cwd=ROOT, stdout=output, stderr=output,
                env=dict(os.environ, MDO_HOME=str(home), MDO_MCP_TEST_SECRET="secret-v1"),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                deadline = time.monotonic() + 25
                while not report.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                assert report.exists(), (base / "host.log").read_text(errors="replace")
                assert json.loads(report.read_text()) == [], report.read_text()
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=8)
                config_path.unlink(missing_ok=True)
                probe_path.unlink(missing_ok=True)
    print("PASS native MCP directory discovery, anchored launch, cold lifecycle and ID conflicts")


if __name__ == "__main__":
    main()
