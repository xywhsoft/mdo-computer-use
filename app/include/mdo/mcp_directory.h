#ifndef MDO_MCP_DIRECTORY_H
#define MDO_MCP_DIRECTORY_H
/* Shared data-only directory package policy. Included after package helpers. */
#define MDO_MCP_DIRECTORY_FORMAT "mdo.mcp-template.v2"
#define MDO_MCP_DIRECTORY_MIN_BUILD 70000057u
#define MDO_MCP_DIRECTORY_BYTES (128u*1024u*1024u)
#define MDO_MCP_DIRECTORY_FILE_BYTES (64u*1024u*1024u)
#define MDO_MCP_DIRECTORY_FILES 1024u
static bool MdoMcpDirectoryTemplate(const xvalue* T)
{cstr F=MdoPackageText(T,"format",32);return F&&!strcmp(F,MDO_MCP_DIRECTORY_FORMAT);}
static cstr MdoMcpDirectoryEntry(cstr Path)
{return Path&&!strncmp(Path,"./",2)&&MdoPackagePath(Path+2)?Path+2:NULL;}
static bool MdoMcpDirectoryOverlap(cstr A,cstr B)
{
    size_t I=0;while(A[I]&&B[I]){unsigned char X=A[I],Y=B[I];if(X>='A'&&X<='Z')X+=32;if(Y>='A'&&Y<='Z')Y+=32;if(X!=Y)return false;I++;}
    return (!A[I]&&(!B[I]||B[I]=='/'))||(!B[I]&&(!A[I]||A[I]=='/'));
}
static bool MdoMcpPayloadHash(const void* Data,size_t Size,char Hash[65])
{uint8 Digest[32];cstr Hex="0123456789abcdef";if(!xrtSha256(Data,Size,Digest))return false;for(size_t I=0;I<32;I++){Hash[2*I]=Hex[Digest[I]>>4];Hash[2*I+1]=Hex[Digest[I]&15];}Hash[64]=0;return true;}
static bytes MdoMcpPayloadRead(const xvalue* F,size_t* Size)
{
    cstr Enc=MdoPackageText(F,"base64",90u*1024u*1024u),Codec=MdoPackageText(F,"encoding",16),Hash=MdoPackageText(F,"sha256",64);
    int64 Declared=0,Mode=0;size_t N=0;bytes Data=NULL;char Actual[65];
    if(!Enc||!Hash||strlen(Hash)!=64||!MdoPackageNumber(F,"size",&Declared)||Declared<0||Declared>MDO_MCP_DIRECTORY_FILE_BYTES||
       !MdoPackageNumber(F,"mode",&Mode)||(Mode!=0644&&Mode!=0755))return NULL;
    Data=xrtBase64DecodeNew(Enc,strlen(Enc),&N,NULL);if(!Data)return NULL;
    if(Codec&&!strcmp(Codec,"zlib")){xinflateconfig C;xrtInflateConfigInit(&C);C.Format=XINFLATE_ZLIB;C.OutputLimit=Declared?Declared:1;
        bytes Inflated=xrtInflateAll((xbytesview){Data,N},&C,&N);xrtFree(Data);Data=Inflated;
    }else if(Codec&&strcmp(Codec,"identity")){xrtFree(Data);return NULL;}
    if(!Data||N!=(size_t)Declared||!MdoMcpPayloadHash(Data,N,Actual)||strcmp(Hash,Actual)){xrtFree(Data);return NULL;}
    *Size=N;return Data;
}
static xvalue* MdoMcpPayloadEncode(const void* Data,size_t Size,uint32 Mode)
{
    if(Size>MDO_MCP_DIRECTORY_FILE_BYTES)return NULL;
    size_t PackedSize=0;bytes Packed=NULL;char Hash[65];
    if(Size>256){xdeflateconfig C;xrtDeflateConfigInit(&C);C.Format=XDEFLATE_ZLIB;C.Level=6;C.OutputLimit=Size;
        Packed=xrtDeflateAll((xbytesview){(cbytes)Data,Size},&C,&PackedSize);if(!Packed)xrtClearError();}
    char* Enc=xrtBase64EncodeNew(Packed?Packed:Data,Packed?PackedSize:Size,NULL);xvalue* F=xrtValueObject();
    bool Ok=F&&Enc&&MdoMcpPayloadHash(Data,Size,Hash)&&xrtValueObjectSetNew(F,XRT_STR_LITERAL("base64"),xrtValueString(xrtStrView(Enc)))&&
        xrtValueObjectSetNew(F,XRT_STR_LITERAL("encoding"),xrtValueString(xrtStrView(Packed?"zlib":"identity")))&&
        xrtValueObjectSetNew(F,XRT_STR_LITERAL("size"),xrtValueUInt(Size))&&xrtValueObjectSetNew(F,XRT_STR_LITERAL("mode"),xrtValueUInt(Mode))&&
        xrtValueObjectSetNew(F,XRT_STR_LITERAL("sha256"),xrtValueString(xrtStrView(Hash)));
    xrtFree(Enc);xrtFree(Packed);if(!Ok){xrtValueRelease(F);return NULL;}return F;
}
static bool MdoMcpDirectoryFiles(const xvalue* T,const xvalue* Files,char* Error,size_t Capacity)
{
    if(!MdoMcpDirectoryTemplate(T)||xrtValueType(Files)!=XVALUE_ARRAY||!xrtValueCount(Files)||xrtValueCount(Files)>MDO_MCP_DIRECTORY_FILES)goto bad;
    size_t Total=0;
    for(size_t I=0;I<xrtValueCount(Files);I++){const xvalue* F=xrtValueArrayGet(Files,I);cstr P=MdoPackageText(F,"path",220);
        if(!MdoPackagePath(P)||MdoMcpDirectoryOverlap(P,"mcp.json")||MdoMcpDirectoryOverlap(P,"template.json"))goto bad;
        for(size_t J=0;J<I;J++)if(MdoMcpDirectoryOverlap(P,MdoPackageText(xrtValueArrayGet(Files,J),"path",220)))goto bad;
        size_t N=0;bytes Data=MdoMcpPayloadRead(F,&N);bool Ok=Data!=NULL;xrtFree(Data);if(!Ok||N>MDO_MCP_DIRECTORY_BYTES-Total)goto bad;Total+=N;
    }
    const xvalue* Variants=xrtValueObjectGet(T,XRT_STR_LITERAL("variants"));
    for(size_t I=0;I<xrtValueCount(Variants);I++){const xvalue* V=xrtValueArrayGet(Variants,I),*C=xrtValueObjectGet(V,XRT_STR_LITERAL("config")),*Tr=xrtValueObjectGet(C,XRT_STR_LITERAL("transport"));
        cstr Type=MdoPackageText(Tr,"type",32),Entry=MdoMcpDirectoryEntry(MdoPackageText(Tr,"program",4096));bool Found=false;
        if(!Type||strcmp(Type,"stdio")||!Entry)goto bad;
        for(size_t J=0;J<xrtValueCount(Files);J++)if(!strcmp(Entry,MdoPackageText(xrtValueArrayGet(Files,J),"path",220))){int64 Size=0;Found=MdoPackageNumber(xrtValueArrayGet(Files,J),"size",&Size)&&Size>0;}
        if(!Found)goto bad;
    }return true;
bad:if(Error&&Capacity)snprintf(Error,Capacity,"Invalid MCP directory files, compressed size, hash, path or program entry");return false;
}
#endif
