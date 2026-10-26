import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {deflateSync} from "node:zlib";
import test from "node:test";
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
