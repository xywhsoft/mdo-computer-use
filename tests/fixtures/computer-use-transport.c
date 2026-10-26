/* Test-only command harness around the same native MCP client used by mdo.
 * No MCP codec, alternate driver, model, or production API is implemented here. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <xsbase.h>
#include <xwork.h>
#include <xllm-time.h>

static void Put(xvalue* Object, const char* Key, xvalue* Value) {
    if (!Value || !xrtValueObjectSetNew(Object,xrtStrView(Key),Value)) exit(9);
}
static void Emit(const char* Prefix,xvalue* Value) {
    char* Json=xrtJsonStringify(Value,false,NULL);
    if (!Json) exit(10);
    printf("%s%s\n",Prefix,Json);fflush(stdout);
    xrtFree(Json);xrtValueRelease(Value);
}
void ServiceInit(XS_HostInfo* Host) {
    xwork_mcp_stdio_config Config;xwork_error Error;xwork_agent_config AgentConfig;
    const char* Args[]={"mcp","--direct"};char Tool[256],Json[262144];(void)Host;
    xworkMcpStdioConfigInit(&Config);Config.sServerName="cua-driver";
    Config.sProgram=getenv("MDO_CUA_DRIVER");Config.psArguments=Args;Config.iArgumentCount=2;
    Config.sProtocolVersion="2026-07-28";Config.iMaxMessageBytes=16777216;
    Config.iMaxTools=256;Config.uStartupTimeoutMs=10000;Config.uRequestTimeoutMs=30000;
    xwork_mcp_client* Client=xworkMcpClientCreate(&Config,&Error);
    xworkAgentConfigInit(&AgentConfig);AgentConfig.bRegisterBuiltinTools=false;
    xllm_session_config SessionConfig;xllmSessionConfigInit(&SessionConfig);
    xllm_session* Session=xllmSessionCreate(&SessionConfig,NULL);
    AgentConfig.pSession=Session;AgentConfig.sWorkspaceRoot=".";
    xwork_agent* Agent=xworkAgentCreate(&AgentConfig,&Error);
    if (!Client || !Agent || !xworkMcpClientConnect(Client,&Error) ||
        !xworkMcpClientRefreshTools(Client,Agent,&Error)) {
        printf("native_error=%s\n",Error.sMessage);fflush(stdout);exit(2);
    }
    xvalue* Ready=xrtValueObject(),*Tools=xrtValueArray();
    for(size_t i=0;i<xworkAgentToolCount(Agent);++i) {
        xwork_tool_info Info;
        if(!xworkAgentToolAt(Agent,i,&Info)||!Info.sParametersJson||!Info.sParametersJson[0])exit(3);
        xrtValueArrayAppendNew(Tools,xrtValueString(xrtStrView(Info.sName)));
    }
    Put(Ready,"tools",Tools);Emit("native_ready=",Ready);
    while(fgets(Tool,sizeof(Tool),stdin)) {
        Tool[strcspn(Tool,"\r\n")]=0;if(!strcmp(Tool,"quit"))break;
        if(!fgets(Json,sizeof(Json),stdin))break;
        xwork_tool_output Output;xworkToolOutputInit(&Output);
        xwork_result Status=xworkMcpClientCallTool(Client,Tool,Json,NULL,
            xllmClockUs()+35000000u,&Output,&Error);
        xvalue* Result=xrtValueObject();
        Put(Result,"success",xrtValueBool(Status==XWORK_RESULT_OK&&Output.bSuccess));
        Put(Result,"status",xrtValueInt(Status));
        Put(Result,"content",xrtValueString(xrtStrView(Output.sContent?Output.sContent:"")));
        Put(Result,"error",xrtValueString(xrtStrView(Error.sMessage)));
        Put(Result,"image_bytes",xrtValueInt(Output.iImageSize));
        if(Output.iImageSize) {
            FILE* File=fopen(getenv("MDO_CUA_CAPTURE"),"wb");
            if(!File||fwrite(Output.pImageBytes,1,Output.iImageSize,File)!=Output.iImageSize)exit(4);
            fclose(File);
        }
        Emit("native_result=",Result);xworkToolOutputUnit(&Output);
    }
    xworkAgentDestroy(Agent);xllmSessionDestroy(Session);xworkMcpClientDestroy(Client);
    puts("native_closed=1");fflush(stdout);exit(0);
}
void ServiceUnit(XS_HostInfo* Host){(void)Host;}
