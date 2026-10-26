import { openLayer } from "../../components/layers.js";
import { api } from "../../api/client.js";
import { targetState, subscribeTarget } from "../../api/target.js";
import { element, errorMessage } from "../../utils/dom.js";

export function createMcpDirectoryAuthoring(onChange) {
  let layer=null,busy=false,dirty=false,owner="",controller=null;
  const target=()=>targetState().selected?.id||"local";
  const close=()=>{controller?.abort();layer?.dispose();layer=null;busy=dirty=false;};
  function open(item) {
    if(layer)return;
    owner=target();controller=new AbortController();
    const view=openLayer({title:"复制程序到 MCP 目录",icon:"globe",width:"40rem",
      beforeClose:()=>!busy&&(!dirty||confirm("放弃目录选择？")),onClosed:()=>{layer=null;controller?.abort();busy=dirty=false;}});
    layer=view;
    const directory=element("input",{attrs:{type:"text",maxlength:"4096",required:"","aria-label":"程序分发目录"}});
    const message=element("p",{attrs:{role:"status"}});
    const form=element("form",{},[element("p",{text:"明确选择包含入口程序及 DLL 等依赖的目录。mdo 会保留原文件，将配置与完整程序复制到 mcp/"+item.id+"/。"}),
      element("label",{},[element("span",{text:"程序分发目录（绝对路径）"}),directory]),
      element("p",{text:"仅选择需要分发的程序目录。隐藏目录、cache、logs 和原配置不复制；复制不会启动程序。"}),message]);
    directory.addEventListener("input",()=>{dirty=true;});view.body.append(form);
    const submit=element("button",{className:"primary-button",text:"复制到 MCP 目录",attrs:{type:"button"}});
    submit.addEventListener("click",async()=>{
      if(busy||!directory.value.trim())return;busy=true;submit.disabled=true;directory.disabled=true;message.textContent="正在复制程序文件…";
      try {await api.post("/mcp/connections",{action:"copy_program",id:item.id,directory:directory.value.trim(),confirm_copy:true},
          {signal:controller.signal,ifMatch:`"${item.revision}"`});
        if(layer===view&&target()===owner){close();onChange();}
      }catch(e){if(layer===view&&e.name!=="AbortError")message.textContent=errorMessage(e);}
      finally{if(layer===view){busy=false;submit.disabled=false;directory.disabled=false;}}
    });
    view.footer.append(submit);directory.focus?.();
  }
  const stop=subscribeTarget(()=>{if(owner!==target())close();});
  return {open,hasPendingChanges:()=>Boolean(layer),destroy(){close();stop();}};
}
