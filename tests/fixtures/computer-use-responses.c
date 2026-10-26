#include <stdio.h>
#include <stdlib.h>
#include <xsbase.h>
#include <xllm.h>

static xllm_client* Client;
static void Emit(const char* Name, int Mode) {
    xllm_request Request; xllm_message Tool; xllm_part Part; xllm_error Error;
    const unsigned char Image[] = {0x89, 0x50, 0x4e, 0x47};
    xllmRequestInit(&Request);
    Request.bParallelToolCalls = false;
    xllmMessageInit(&Tool, XLLM_ROLE_TOOL);
    xllmMessageSetToolCallId(&Tool, "call-capture");
    if (Mode == 0) xllmMessageSetContent(&Tool, "plain-result");
    if (Mode == 1 || Mode == 2 || Mode == 4) {
        xllmPartInit(&Part, XLLM_PART_TEXT); xllmPartSetText(&Part, "window-tree");
        xllmMessageAddPart(&Tool, &Part); xllmPartUnit(&Part);
    }
    if (Mode == 2 || Mode == 3) {
        xllmPartInit(&Part, XLLM_PART_IMAGE);
        xllmPartSetImageData(&Part, Image, sizeof(Image), "image/png");
        xllmMessageAddPart(&Tool, &Part); xllmPartUnit(&Part);
    }
    if (Mode == 4) {
        xllmPartInit(&Part, XLLM_PART_TEXT); xllmPartSetText(&Part, "second-part");
        xllmMessageAddPart(&Tool, &Part); xllmPartUnit(&Part);
    }
    xllmRequestAddMessage(&Request, &Tool);
    char* Json = xllmClientBuildRequestJson(Client, &Request, &Error);
    if (!Json) { printf("wire_error=%s\n", Error.sMessage); fflush(stdout); exit(2); }
    printf("wire_%s=%s\n", Name, Json);
    xllmFree(Json); xllmMessageUnit(&Tool); xllmRequestUnit(&Request);
}
void ServiceInit(XS_HostInfo* Host) {
    xllm_client_config Config; xllm_model_profile Profile; xllm_error Error;
    (void)Host;
    xllmModelProfileInit(&Profile);
    Profile.sId = "wire-fixture"; Profile.sModel = "wire-fixture";
    Profile.eProvider = XLLM_PROVIDER_OPENAI_RESPONSES;
    Profile.uCapabilities = XLLM_CAP_TEXT_IN | XLLM_CAP_TOOL_RESULT_IN |
        XLLM_CAP_TEXT_OUT | XLLM_CAP_TOOL_CALL_OUT | XLLM_CAP_IMAGE_IN | XLLM_CAP_STREAM;
    Profile.eWindowMode = XLLM_WINDOW_SHARED_CONTEXT;
    Profile.uContextWindowTokens = 4096; Profile.uMaxInputTokens = 4095;
    Profile.uMaxOutputTokens = 512; Profile.uRecommendedOutputReserveTokens = 512;
    Profile.uRecommendedSummaryTokens = 256;
    xllmClientConfigInit(&Config); Config.sBaseUrl = "http://127.0.0.1:1";
    Config.sModel = "wire-fixture"; Config.eProvider = XLLM_PROVIDER_OPENAI_RESPONSES;
    Config.uMaxOutputTokens = 512;
    Config.pModelProfile = &Profile;
    Client = xllmClientCreate(&Config, &Error);
    if (!Client) { printf("wire_init_error=%s\n", Error.sMessage); exit(3); }
    Emit("plain", 0); Emit("text", 1); Emit("mixed", 2);
    Emit("image", 3); Emit("texts", 4);
    xllmClientDestroy(Client); fflush(stdout); exit(0);
}
void ServiceUnit(XS_HostInfo* Host) { (void)Host; }
