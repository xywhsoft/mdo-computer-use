import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {deflateSync} from "node:zlib";
import test from "node:test";
import {readFileSync} from "node:fs";
import {testDocument,descendants} from "./helpers/extension-dom.mjs";
import {decodePackageAttachment} from "../app/web/js/utils/source-markdown.js";
import {makeStorePackage} from "../app/web/js/features/settings/store-formats.js";

test("compressed program download preserves bytes and rejects forged hashes and expansion limits",async()=>{
  const data=Buffer.from("Unicode 目录\0\xff".repeat(500)),file={base64:deflateSync(data).toString("base64"),encoding:"zlib",size:data.length,sha256:createHash("sha256").update(data).digest("hex")};
  assert.deepEqual(Buffer.from(await decodePackageAttachment(file)),data);
  await assert.rejects(decodePackageAttachment({...file,size:data.length-1}),/declared size/);
  await assert.rejects(decodePackageAttachment({...file,sha256:"0".repeat(64)}),/hash/);
  await assert.rejects(decodePackageAttachment({...file,encoding:"unknown"}),/encoding/);
});
test("MCP program packages select v2 with the compatibility floor",()=>{
  const p=makeStorePackage({slug:"folder",name:"Folder",version:"1.0.0",description:"Program",readme:"Inspect",license:"MIT",platforms:["windows-x86_64"]},[{kind:"mcp",id:"folder",content:"{}",files:[]}]);
  assert.equal(p.format,"mdo.extension.v2");assert.equal(p.manifest.min_build_id,70000057);
});
test("directory copy sends only the explicitly selected root and discards drafts on device switches",async()=>{
  const previous=globalThis.document;globalThis.document=testDocument();let target="local",notify,changed=0;const calls=[];
  globalThis.__directoryFixture={api:{post:async(path,body,options)=>{calls.push({path,body,options});return {data:{}};}},targetState:()=>({selected:{id:target}}),subscribeTarget:fn=>{notify=fn;return()=>{};}};
  const url=new URL("../app/web/js/features/settings/mcp-directory-authoring.js",import.meta.url);
  const source=readFileSync(url,"utf8").replace('import { api } from "../../api/client.js";','const {api}=globalThis.__directoryFixture;')
    .replace('import { targetState, subscribeTarget } from "../../api/target.js";','const {targetState,subscribeTarget}=globalThis.__directoryFixture;')
    .replace(/from "(\.[^"]+)"/g,(_,path)=>`from ${JSON.stringify(new URL(path,url).href)}`);
  let author;
  try{const {createMcpDirectoryAuthoring}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));author=createMcpDirectoryAuthoring(()=>{changed++;});
    const item={id:"cua-driver",revision:"revision"};author.open(item);
    const nodes=()=>descendants(document.body);let submit=nodes().find(n=>n.tagName==="BUTTON"&&n.textContent==="复制到 MCP 目录");submit.click();assert.equal(calls.length,0);
    const directory=nodes().find(n=>n.getAttribute?.("aria-label")==="程序分发目录");directory.value="D:\\Cua\\official";submit.click();await new Promise(resolve=>setImmediate(resolve));
    assert.deepEqual(calls[0].body,{action:"copy_program",id:"cua-driver",directory:"D:\\Cua\\official",confirm_copy:true});assert.equal(changed,1);
    author.open(item);target="remote";notify();assert.equal(author.hasPendingChanges(),false);assert.equal(calls.length,1);
  }finally{author?.destroy();delete globalThis.__directoryFixture;globalThis.document=previous;}
});
