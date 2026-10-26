/* Directory MCPs keep the private connection beside the reviewed program
 * tree. Payloads use the existing extension transport, compressed per file. */
static bool EcoMcpTemplatePath(cstr P)
{
    if(!P)return false;if(!strncmp(P,"data/ecosystem/mcp/",19))return true;
    if(strncmp(P,"mcp/",4))return false;cstr Slash=strchr(P+4,'/');
    return Slash&&!strcmp(Slash,"/template.json");
}
static bool EcoMcpPrivateConfig(cstr P)
{if(!P||strncmp(P,"mcp/",4))return false;cstr Slash=strchr(P+4,'/');return Slash&&!strcmp(Slash,"/mcp.json");}
static bool EcoMcpDirectoryPrepare(xvalue* Files,const xvalue* Resource,const xvalue* Entry,const xvalue* Package,char* Error)
{
    cstr Id=MdoPackageText(Resource,"id",64),Content=MdoPackageText(Resource,"content",131072);
    xvalue* T=xrtJsonParse(xrtStrView(Content));char Root[160],Path[384],Legacy[160];bool Exists=false;xfileinfo Info;
    snprintf(Root,sizeof(Root),"mcp/%s",Id);snprintf(Legacy,sizeof(Legacy),"mcp/%s.json",Id);
    bool Ok=T&&MdoHomeExternalStat(Legacy,&Exists,&Info)&&!Exists;
    if(!Ok){snprintf(Error,1024,"Remove or rename the legacy MCP connection before installing directory %s",Id);xrtValueRelease(T);return false;}
    snprintf(Path,sizeof(Path),"%s/template.json",Root);Ok=EcoLocalAppend(Files,Path,Content,strlen(Content));
    const xvalue* Payloads=xrtValueObjectGet(Resource,XRT_STR_LITERAL("files"));
    for(size_t I=0;Ok&&I<xrtValueCount(Payloads);I++){const xvalue* F=xrtValueArrayGet(Payloads,I);snprintf(Path,sizeof(Path),"%s/%s",Root,MdoPackageText(F,"path",220));
        xvalue* Change=xrtValueObject();Ok=Change&&MdoApiValueSetString(Change,"path",Path)&&xrtValueObjectSet(Change,XRT_STR_LITERAL("new"),F)&&
            xrtValueObjectSet(Change,XRT_STR_LITERAL("sha256"),xrtValueObjectGet(F,XRT_STR_LITERAL("sha256")))&&xrtValueArrayAppend(Files,Change);xrtValueRelease(Change);}
    snprintf(Path,sizeof(Path),"%s/mcp.json",Root);
    if(Ok)Ok=MdoHomeExternalStat(Path,&Exists,&Info);
    /* Keep existing device values and enabled state across package updates. */
    if(Ok&&!Exists){const xvalue* Vs=xrtValueObjectGet(T,XRT_STR_LITERAL("variants")),*Selected=NULL;
        for(size_t I=0;I<xrtValueCount(Vs)&&!Selected;I++){const xvalue* V=xrtValueArrayGet(Vs,I),*Ps=xrtValueObjectGet(V,XRT_STR_LITERAL("platforms"));
            for(size_t J=0;J<xrtValueCount(Ps);J++){xstrview P;if(xrtValueGetString(xrtValueArrayGet(Ps,J),&P)&&xrtStrEqual(P,xrtStrView(MdoToolPlatform())))Selected=V;}}
        xvalue* Values=xrtValueObject();const xvalue* Inputs=xrtValueObjectGet(T,XRT_STR_LITERAL("inputs"));
        for(size_t I=0;Values&&I<xrtValueCount(Inputs);I++){const xvalue* In=xrtValueArrayGet(Inputs,I),*D=xrtValueObjectGet(In,XRT_STR_LITERAL("default"));
            xrtValueObjectSetNew(Values,xrtStrView(MdoPackageText(In,"id",64)),D?xrtValueDeepClone(D):xrtValueString(XRT_STR_LITERAL("")));}
        xvalue* Config=Selected&&Values?McpConnectionResolve(xrtValueObjectGet(Selected,XRT_STR_LITERAL("config")),Values,0):NULL;
        xvalue* Transport=(xvalue*)xrtValueObjectGet(Config,XRT_STR_LITERAL("transport"));
        /* An unconfigured, disabled connection never needs placeholder keys. */
        for(size_t K=0;Transport&&K<2;K++){cstr Key=K?"headers":"environment";const xvalue* Old=xrtValueObjectGet(Transport,xrtStrView(Key));if(!Old)continue;xvalue* A=xrtValueArray();
            for(size_t I=0;A&&I<xrtValueCount(Old);I++){const xvalue* V=xrtValueArrayGet(Old,I);cstr Ref=MdoPackageText(V,"secret_ref",256);if(Ref&&Ref[0])xrtValueArrayAppend(A,V);}
            if(A)xrtValueObjectSetNew(Transport,xrtStrView(Key),A);}
        xvalue* Receipt=Entry?xrtValueDeepClone(Entry):xrtValueObject(),*Binding=xrtValueObject();
        if(Receipt){xrtValueObjectRemove(Receipt,XRT_STR_LITERAL("package"));xrtValueObjectSet(Receipt,XRT_STR_LITERAL("manifest"),xrtValueObjectGet(Package,XRT_STR_LITERAL("manifest")));
            char Key[80];cstr Source=MdoPackageText(Entry,"source",16),Slug=MdoPackageText(Entry,"slug",64);int64 StoreId=0;MdoPackageNumber(Entry,"id",&StoreId);
            if(Source&&!strcmp(Source,"local"))snprintf(Key,sizeof(Key),"local:%s",Slug?Slug:Id);else snprintf(Key,sizeof(Key),"%lld",(long long)StoreId);
            MdoApiValueSetString(Receipt,"key",Key);
        }
        Ok=Config&&Receipt&&Binding&&MdoApiValueSetString(Config,"id",Id)&&MdoApiValueSetBool(Config,"enabled",false)&&
            xrtValueObjectSet(Binding,XRT_STR_LITERAL("template"),T)&&xrtValueObjectSet(Binding,XRT_STR_LITERAL("receipt"),Receipt)&&
            xrtValueObjectSet(Binding,XRT_STR_LITERAL("variant"),xrtValueObjectGet(Selected,XRT_STR_LITERAL("id")))&&
            xrtValueObjectSet(Binding,XRT_STR_LITERAL("values"),Values)&&xrtValueObjectSet(Config,XRT_STR_LITERAL("mdo_template"),Binding);
        char* Text=Ok?xrtJsonStringify(Config,false,NULL):NULL;Ok=Text&&EcoLocalAppend(Files,Path,Text,strlen(Text));
        xrtFree(Text);xrtValueRelease(Config);xrtValueRelease(Receipt);xrtValueRelease(Binding);xrtValueRelease(Values);
    }
    xrtValueRelease(T);return Ok;
}
static bool EcoMcpStopChanged(const xvalue* Files,char* Error)
{
    for(size_t I=0;I<xrtValueCount(Files);I++){cstr P=MdoPackageText(xrtValueArrayGet(Files,I),"path",599);if(!P||strncmp(P,"mcp/",4))continue;
        cstr Slash=strchr(P+4,'/');if(!Slash||Slash-P-4>64)continue;char Id[65];memcpy(Id,P+4,Slash-P-4);Id[Slash-P-4]=0;
        if(!McpDirectoryStopConnections(Id,Error))return false;}
    return true;
}
static bool EcoMcpDisableRemoved(xvalue* Files,const xvalue* Resources,const xvalue* Owned)
{
    for(size_t I=0;I<xrtValueCount(Resources);I++){const xvalue* R=xrtValueArrayGet(Resources,I);cstr Kind=MdoPackageText(R,"kind",16),Id=MdoPackageText(R,"id",64);
        if(!Kind||strcmp(Kind,"mcp")||!Id)continue;char Path[160];snprintf(Path,sizeof(Path),"mcp/%s/template.json",Id);bool Directory=false;
        for(size_t J=0;J<xrtValueCount(Owned);J++)if(!strcmp(Path,MdoPackageText(xrtValueArrayGet(Owned,J),"path",599)))Directory=true;
        if(!Directory)continue;snprintf(Path,sizeof(Path),"mcp/%s/mcp.json",Id);
        bool Missing=false;char* Old=MdoExtensionRead(Path,true,262144,&Missing);if(!Old){if(Missing)continue;return false;}
        xvalue* Doc=xrtJsonParse(xrtStrView(Old));bool Ok=Doc&&MdoApiValueSetBool(Doc,"enabled",false);char* Text=Ok?xrtJsonStringify(Doc,false,NULL):NULL;
        Ok=Text&&EcoLocalAppend(Files,Path,Text,strlen(Text));char* Enc=Ok?xrtBase64EncodeNew(Old,strlen(Old),NULL):NULL;
        if(Ok){xvalue* F=(xvalue*)xrtValueArrayGet(Files,xrtValueCount(Files)-1);Ok=Enc&&MdoApiValueSetString(F,"old",Enc);}
        xrtFree(Enc);xrtFree(Text);xrtFree(Old);xrtValueRelease(Doc);if(!Ok)return false;
    }return true;
}
static bool EcoMcpDirectoryCollect(cstr Root,cstr Relative,xvalue* Files,size_t* Total,unsigned Depth)
{
    if(Depth>16)return false;char Path[512];snprintf(Path,sizeof(Path),"%s%s%s",Root,Relative[0]?"/":"",Relative);
    xdir Dir=MdoHomeOpenDirectory(Path,XDIR_STAT);if(!Dir)return false;xdirentry E;xdirnext Next=XDIR_NEXT_END;bool Ok=true;
    while(Ok&&(Next=xrtDirNext(Dir,&E))==XDIR_NEXT_ITEM){char P[256],Full[512];int N=snprintf(P,sizeof(P),"%s%s%.*s",Relative,Relative[0]?"/":"",(int)E.Name.Size,E.Name.Data);
        if(N<0||N>=sizeof(P)){Ok=false;break;}
        if(!Relative[0]&&(!strcmp(P,"mcp.json")||!strcmp(P,"template.json")||P[0]=='.'))continue;
        if(!MdoPackagePath(P)){Ok=false;break;}
        snprintf(Full,sizeof(Full),"%s/%s",Root,P);
        if(E.Info.Type==XFILE_TYPE_DIRECTORY){if(!strcmp(P,"cache")||!strcmp(P,"logs")||P[0]=='.')continue;Ok=EcoMcpDirectoryCollect(Root,P,Files,Total,Depth+1);}
        else if(E.Info.Type==XFILE_TYPE_FILE&&E.Info.Size<=MDO_MCP_DIRECTORY_FILE_BYTES&&xrtValueCount(Files)<MDO_MCP_DIRECTORY_FILES&&E.Info.Size<=MDO_MCP_DIRECTORY_BYTES-*Total){
            size_t Size=(size_t)E.Info.Size;bytes Data=xrtMalloc(Size+1);xfile F=MdoHomeOpenRead(Full);
            Ok=Data&&F&&xrtReadFull(F,Data,Size,NULL);xrtClose(F);xvalue* Item=Ok?MdoMcpPayloadEncode(Data,Size,(E.Info.Mode&0111)?0755:0644):NULL;xrtFree(Data);
            Ok=Item&&MdoApiValueSetString(Item,"path",P)&&xrtValueArrayAppend(Files,Item);xrtValueRelease(Item);if(Ok)*Total+=Size;
        }else Ok=false;
    }if(Next==XDIR_NEXT_ERROR)Ok=false;xrtDirClose(Dir);return Ok;
}
