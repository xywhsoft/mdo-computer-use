/* The author selects the distribution root explicitly. Never infer a parent
 * directory, follow links, or copy the user's Home/account data implicitly. */
static bool McpCopyProgramTree(xroot Root,cstr Relative,cstr Stage,unsigned Depth,size_t* Count,uint64* Total)
{
    if(Depth>16)return false;xdir Dir=xrtRootDirOpen(Root,Relative[0]?Relative:".",XDIR_STAT);if(!Dir)return false;
    xdirentry E;xdirnext Next=XDIR_NEXT_END;bool Ok=true;
    while(Ok&&(Next=xrtDirNext(Dir,&E))==XDIR_NEXT_ITEM){char P[256],Target[512];int N=snprintf(P,sizeof(P),"%s%s%.*s",Relative,Relative[0]?"/":"",(int)E.Name.Size,E.Name.Data);
        if(N<0||N>=sizeof(P)){Ok=false;break;}
        if(!Relative[0]&&(!strcmp(P,"mcp.json")||!strcmp(P,"template.json")||!strcmp(P,"cache")||!strcmp(P,"logs")||P[0]=='.'))continue;
        if(!MdoPackagePath(P)){Ok=false;break;}
        snprintf(Target,sizeof(Target),"%s/%s",Stage,P);
        if(E.Info.Type==XFILE_TYPE_DIRECTORY)Ok=McpCopyProgramTree(Root,P,Stage,Depth+1,Count,Total);
        else if(E.Info.Type==XFILE_TYPE_FILE&&*Count<MDO_MCP_DIRECTORY_FILES&&E.Info.Size<=MDO_MCP_DIRECTORY_FILE_BYTES&&E.Info.Size<=MDO_MCP_DIRECTORY_BYTES-*Total){
            xfileoptions O;xrtFileOptionsInit(&O);O.Flags=XFILE_READ|XFILE_NOFOLLOW;xfile In=xrtRootFileOpen(Root,P,&O),Out=In?MdoHomeOpenWrite(Target,XFILE_WRITE|XFILE_CREATE|XFILE_TRUNCATE):NULL;
            uint64 Copied=0;uint8 Buffer[65536];Ok=In&&Out;
            while(Ok&&Copied<E.Info.Size){size_t N=(size_t)(E.Info.Size-Copied<sizeof(Buffer)?E.Info.Size-Copied:sizeof(Buffer));Ok=xrtReadFull(In,Buffer,N,NULL)&&xrtWriteFull(Out,Buffer,N,NULL);Copied+=N;}
            uint64 Actual=0;Ok=Ok&&xrtFileSize(In,&Actual)&&Actual==Copied&&xrtFlush(Out);xrtClose(In);xrtClose(Out);
#if !defined(_WIN32) && !defined(_WIN64)
            if(Ok)Ok=MdoHomeSetMode(Target,(E.Info.Mode&0111)?0755:0644);
#endif
            if(Ok){++*Count;*Total+=Copied;}
        }else Ok=false;
    }if(Next==XDIR_NEXT_ERROR)Ok=false;xrtDirClose(Dir);return Ok;
}
static bool McpCopyProgramDirectory(cstr Id,cstr OldPath,cstr Old,const xvalue* OldDoc,cstr Selected,char Error[1024])
{
    const xvalue* Tr=xrtValueObjectGet(OldDoc,XRT_STR_LITERAL("transport"));cstr Type=MdoPackageText(Tr,"type",32),Program=MdoPackageText(Tr,"program",4096);
    if(!Selected||!xrtPathIsAbs(Selected)||!Type||strcmp(Type,"stdio")||!Program||!xrtPathIsAbs(Program)||strstr(OldPath,"/mcp.json")){
        snprintf(Error,1024,"Choose an absolute distribution directory for a custom local stdio MCP program");return false;}
    char* Entry=xrtPathRelative(xrtStrView(Selected),xrtStrView(Program),XPATH_NATIVE);if(Entry)for(char* P=Entry;*P;P++)if(*P=='\\')*P='/';
    if(!Entry||!MdoPackagePath(Entry)){xrtFree(Entry);snprintf(Error,1024,"The selected directory must contain the configured program");return false;}
    char Target[160],Stage[190],ConfigPath[220],Hash[65];bool Exists=false;xfileinfo Info;size_t Count=0;uint64 Total=0;
    snprintf(Target,sizeof(Target),"mcp/%s",Id);MdoExtensionHash(Old,Hash);snprintf(Stage,sizeof(Stage),"mcp/.copy-%s-%.12s",Id,Hash);
    bool Ok=MdoHomeExternalStat(Target,&Exists,&Info)&&!Exists;bool Created=false,Published=false,Removed=false;
    xroot Root=Ok?xrtRootOpen(Selected):NULL;xvalue* Doc=Root?xrtValueDeepClone(OldDoc):NULL;
    if(Ok&&Root){Created=MdoHomeCreateDirectory(Stage);Ok=Created&&McpCopyProgramTree(Root,"",Stage,0,&Count,&Total)&&Count>0;}
    else Ok=false;
    xrtRootClose(Root);
    xvalue* Transport=(xvalue*)xrtValueObjectGet(Doc,XRT_STR_LITERAL("transport"));char* Relative=xrtFormat("./%s",Entry);
    Ok=Ok&&Doc&&Relative&&MdoApiValueSetString(Transport,"program",Relative)&&MdoApiValueSetString(Transport,"working_directory",".");
    if(Doc)xrtValueObjectRemove(Doc,XRT_STR_LITERAL("mdo_template"));
    char* Json=Ok?xrtJsonStringify(Doc,false,NULL):NULL;
    snprintf(ConfigPath,sizeof(ConfigPath),"%s/mcp.json",Stage);Ok=Json&&MdoMcpValidateText(Id,Json,Error,1024)&&MdoHomeAtomicWrite(ConfigPath,Json,strlen(Json),false);
    if(Ok){xwork_error E={0};Ok=MdoMcpManagerDisconnect(Id,&E);if(!Ok)snprintf(Error,1024,"Stop the active MCP request before copying its program");}
    if(Ok){Published=MdoHomeRenameNoReplace(Stage,Target);Ok=Published;}
    if(Ok){Removed=MdoHomeRemove(OldPath,false);Ok=Removed&&MdoMcpManagerReload();}
    if(!Ok){if(Removed&&!MdoHomeAtomicWrite(OldPath,Old,strlen(Old),false))MdoHomeRequireRestart("MCP copy rollback failed");
        if(Published)ExtensionRemoveDirectory(Target);else if(Created)ExtensionRemoveDirectory(Stage);
        if(Removed&&!MdoMcpManagerReload())MdoHomeRequireRestart("MCP copy registration rollback failed");
        if(!Error[0])snprintf(Error,1024,"Cannot copy MCP program directory; inspect paths, file limits, links, or an existing target");}
    xrtFree(Entry);xrtFree(Relative);xrtFree(Json);xrtValueRelease(Doc);return Ok;
}
