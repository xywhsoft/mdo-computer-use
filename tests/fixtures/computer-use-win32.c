#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <windowsx.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <wchar.h>

static HWND main_window, input, counter, check, combo, lines;
static wchar_t oracle_path[1024];
static int clicks, canvas_clicks, right_clicks;
static int double_clicks, drags, menu_marks, key_events, char_events;
static int drag_x, drag_y, drag_end_x, drag_end_y, dragging;
static WNDPROC original_input;
static unsigned int visual_code;
static HFONT font;
typedef struct ClipboardCopy { UINT format; SIZE_T size; void* bytes; } ClipboardCopy;
static ClipboardCopy clipboard_copy[128];
static unsigned int clipboard_count;
static int clipboard_saved,clipboard_restored;

static void discard_clipboard_copy(void) {
    for(unsigned int i=0;i<clipboard_count;i++){
        if(clipboard_copy[i].bytes){SecureZeroMemory(clipboard_copy[i].bytes,clipboard_copy[i].size);free(clipboard_copy[i].bytes);}
    }
    memset(clipboard_copy,0,sizeof(clipboard_copy));clipboard_count=0;
}
/* Test-only resource preservation. Never serialize clipboard data. Refuse
 * any format that cannot be faithfully copied as a bounded HGLOBAL. */
static void snapshot_clipboard(void) {
    discard_clipboard_copy();clipboard_saved=0;clipboard_restored=0;
    if(!OpenClipboard(main_window))return;
    UINT format=0;SIZE_T total=0;int ok=1;
    while((format=EnumClipboardFormats(format))!=0){
        if(format!=CF_TEXT&&format!=CF_OEMTEXT&&format!=CF_UNICODETEXT&&format!=CF_LOCALE&&format!=CF_DIB&&format!=CF_DIBV5){
            wchar_t name[128]={0};GetClipboardFormatNameW(format,name,128);
            if(wcscmp(name,L"HTML Format")&&wcscmp(name,L"Rich Text Format")&&
               wcscmp(name,L"Chromium internal source RFH token")&&wcscmp(name,L"Chromium internal source URL")){ok=0;break;}
        }
        HANDLE source=GetClipboardData(format);SIZE_T size=source?GlobalSize(source):0;
        if(!size||size>16u*1024u*1024u||total+size>32u*1024u*1024u||clipboard_count>=128){ok=0;break;}
        void* locked=GlobalLock(source);void* copy=locked?malloc(size):NULL;
        if(!locked||!copy){if(locked)GlobalUnlock(source);ok=0;break;}
        memcpy(copy,locked,size);GlobalUnlock(source);
        clipboard_copy[clipboard_count++]=(ClipboardCopy){format,size,copy};total+=size;
    }
    CloseClipboard();
    if(ok&&clipboard_count)clipboard_saved=1;else discard_clipboard_copy();
}
static void restore_clipboard(void) {
    if(!clipboard_saved||!OpenClipboard(main_window))return;
    /* Restore only while our known test text is still current. */
    HANDLE current=GetClipboardData(CF_UNICODETEXT);
    const wchar_t* value=current?(const wchar_t*)GlobalLock(current):NULL;
    int ours=value&&!wcscmp(value,L"MDO 剪贴板验收");if(value)GlobalUnlock(current);
    if(!ours){CloseClipboard();return;}
    HGLOBAL copies[128]={0};int ok=1;
    for(unsigned int i=0;i<clipboard_count;i++){
        copies[i]=GlobalAlloc(GMEM_MOVEABLE,clipboard_copy[i].size);
        void* out=copies[i]?GlobalLock(copies[i]):NULL;
        if(!out){ok=0;break;}
        memcpy(out,clipboard_copy[i].bytes,clipboard_copy[i].size);GlobalUnlock(copies[i]);
    }
    if(ok)ok=EmptyClipboard()!=0;
    if(ok)for(unsigned int i=0;i<clipboard_count;i++){
        if(SetClipboardData(clipboard_copy[i].format,copies[i]))copies[i]=NULL;else ok=0;
    }
    if(ok)for(unsigned int i=0;i<clipboard_count;i++){
        HANDLE restored=GetClipboardData(clipboard_copy[i].format);
        const void* data=restored?GlobalLock(restored):NULL;
        if(!data||GlobalSize(restored)!=clipboard_copy[i].size||memcmp(data,clipboard_copy[i].bytes,clipboard_copy[i].size))ok=0;
        if(data)GlobalUnlock(restored);
    }
    CloseClipboard();for(unsigned int i=0;i<clipboard_count;i++)if(copies[i])GlobalFree(copies[i]);
    clipboard_restored=ok;if(ok)discard_clipboard_copy();
}

static void json_text(FILE *f, const wchar_t *wide) {
    char text[16384];
    WideCharToMultiByte(CP_UTF8,0,wide,-1,text,sizeof(text),NULL,NULL);
    fputc('"',f);
    for (const unsigned char *p=(unsigned char*)text; *p; ++p) {
        if (*p=='"'||*p=='\\') { fputc('\\',f); fputc(*p,f); }
        else if (*p<32) fprintf(f,"\\u%04x",*p);
        else fputc(*p,f);
    }
    fputc('"',f);
}
static void save_state(void) {
    wchar_t temporary[1100], text[4096], selected[256];
    _snwprintf(temporary,1100,L"%ls.tmp",oracle_path);
    GetWindowTextW(input,text,4096);
    int index=(int)SendMessageW(combo,CB_GETCURSEL,0,0);
    selected[0]=0;
    if(index>=0)SendMessageW(combo,CB_GETLBTEXT,index,(LPARAM)selected);
    FILE *f=_wfopen(temporary,L"wb");
    if(!f)return;
    fprintf(f,"{\"pid\":%lu,\"window_id\":%llu,\"foreground\":%llu,\"clicks\":%d,\"canvas_clicks\":%d,\"right_clicks\":%d,\"checked\":%s,\"scroll_line\":%ld,\"text\":",
        GetCurrentProcessId(),(unsigned long long)(uintptr_t)main_window,
        (unsigned long long)(uintptr_t)GetForegroundWindow(),clicks,canvas_clicks,right_clicks,
        SendMessageW(check,BM_GETCHECK,0,0)==BST_CHECKED?"true":"false",
        (long)SendMessageW(lines,EM_GETFIRSTVISIBLELINE,0,0));
    json_text(f,text); fputs(",\"selection\":",f); json_text(f,selected);
    DWORD selection_start=0,selection_end=0;
    SendMessageW(input,EM_GETSEL,(WPARAM)&selection_start,(LPARAM)&selection_end);
    fprintf(f,",\"double_clicks\":%d,\"drags\":%d,\"menu_marks\":%d,\"key_events\":%d,\"char_events\":%d,\"drag_end\":[%d,%d],\"selection_start\":%lu,\"selection_end\":%lu",
        double_clicks,drags,menu_marks,key_events,char_events,drag_end_x,drag_end_y,
        (unsigned long)selection_start,(unsigned long)selection_end);
    fprintf(f,",\"clipboard_saved\":%s,\"clipboard_restored\":%s,\"visual_code\":\"%06u\"}\n",
        clipboard_saved?"true":"false",clipboard_restored?"true":"false",visual_code);
    fclose(f); MoveFileExW(temporary,oracle_path,MOVEFILE_REPLACE_EXISTING);
}
static LRESULT CALLBACK input_procedure(HWND h,UINT message,WPARAM w,LPARAM l) {
    if(message==WM_KEYDOWN)key_events++;
    if(message==WM_CHAR)char_events++;
    return CallWindowProcW(original_input,h,message,w,l);
}
static HWND child(const wchar_t *class_name,const wchar_t *text,DWORD style,int x,int y,int width,int height,int id) {
    HWND h=CreateWindowExW(0,class_name,text,WS_CHILD|WS_VISIBLE|style,x,y,width,height,main_window,(HMENU)(INT_PTR)id,GetModuleHandleW(NULL),NULL);
    SendMessageW(h,WM_SETFONT,(WPARAM)font,TRUE); return h;
}
static LRESULT CALLBACK procedure(HWND h,UINT message,WPARAM w,LPARAM l) {
    switch(message) {
    case WM_CREATE: {
        main_window=h; font=(HFONT)GetStockObject(DEFAULT_GUI_FONT);
        HMENU bar=CreateMenu(),test_menu=CreatePopupMenu();
        AppendMenuW(test_menu,MF_STRING,201,L"Mark verified");
        AppendMenuW(bar,MF_POPUP,(UINT_PTR)test_menu,L"Test");SetMenu(h,bar);
        child(L"STATIC",L"MDO Computer Use - project acceptance window",0,20,16,690,24,0);
        child(L"STATIC",L"Input text",0,20,56,120,20,0);
        input=child(L"EDIT",L"",WS_BORDER|WS_TABSTOP|ES_MULTILINE|ES_AUTOVSCROLL,20,80,690,74,101);
        original_input=(WNDPROC)SetWindowLongPtrW(input,GWLP_WNDPROC,(LONG_PTR)input_procedure);
        child(L"BUTTON",L"Increment counter",WS_TABSTOP|BS_PUSHBUTTON,20,172,165,36,102);
        counter=child(L"STATIC",L"Counter: 0",0,210,180,180,24,0);
        check=child(L"BUTTON",L"Enable option",WS_TABSTOP|BS_AUTOCHECKBOX,440,173,190,32,103);
        child(L"STATIC",L"Color",0,20,222,70,20,0);
        combo=child(L"COMBOBOX",L"",WS_TABSTOP|CBS_DROPDOWNLIST|WS_VSCROLL,90,218,200,160,104);
        SendMessageW(combo,CB_ADDSTRING,0,(LPARAM)L"Red"); SendMessageW(combo,CB_ADDSTRING,0,(LPARAM)L"Green"); SendMessageW(combo,CB_ADDSTRING,0,(LPARAM)L"Blue"); SendMessageW(combo,CB_SETCURSEL,0,0);
        child(L"STATIC",L"Scroll document",0,20,260,240,20,0);
        lines=child(L"EDIT",L"",WS_BORDER|WS_VSCROLL|ES_MULTILINE|ES_READONLY|ES_AUTOVSCROLL,20,284,380,210,105);
        wchar_t document[12000]=L"",row[80];
        for(int i=1;i<=120;i++){swprintf(row,80,L"Line %03d - scroll verification\r\n",i);wcscat(document,row);}
        SetWindowTextW(lines,document);
        child(L"STATIC",L"Visual-only canvas target below",0,440,260,270,24,0);
        child(L"BUTTON",L"Close fixture",WS_TABSTOP|BS_PUSHBUTTON,540,474,170,34,106);
        child(L"BUTTON",L"Save clipboard",WS_TABSTOP|BS_PUSHBUTTON,20,520,160,30,107);
        child(L"BUTTON",L"Restore clipboard",WS_TABSTOP|BS_PUSHBUTTON,200,520,160,30,108);
        SetTimer(h,1,150,NULL); save_state(); return 0;
    }
    case WM_COMMAND:
        if(LOWORD(w)==201)menu_marks++;
        if(LOWORD(w)==102 && HIWORD(w)==BN_CLICKED){wchar_t label[64];clicks++;swprintf(label,64,L"Counter: %d",clicks);SetWindowTextW(counter,label);}
        if(LOWORD(w)==106){DestroyWindow(h);return 0;}
        if(LOWORD(w)==107)snapshot_clipboard();
        if(LOWORD(w)==108)restore_clipboard();
        save_state(); return 0;
    case WM_LBUTTONDOWN:
    case WM_RBUTTONDOWN:
        if(GET_X_LPARAM(l)>=440&&GET_X_LPARAM(l)<=710&&GET_Y_LPARAM(l)>=300&&GET_Y_LPARAM(l)<=440){
            if(message==WM_LBUTTONDOWN){canvas_clicks++;dragging=1;drag_x=GET_X_LPARAM(l);drag_y=GET_Y_LPARAM(l);}else right_clicks++;
            InvalidateRect(h,NULL,TRUE);save_state();return 0;
        }break;
    case WM_LBUTTONDBLCLK:
        double_clicks++;save_state();return 0;
    case WM_LBUTTONUP:
        if(dragging){drag_end_x=GET_X_LPARAM(l);drag_end_y=GET_Y_LPARAM(l);
            if(abs(drag_end_x-drag_x)+abs(drag_end_y-drag_y)>20)drags++;
            dragging=0;save_state();return 0;}break;
    case WM_KEYDOWN:key_events++;save_state();break;
    case WM_CHAR:char_events++;save_state();break;
    case WM_TIMER: save_state();return 0;
    case WM_PAINT: {
        PAINTSTRUCT paint;HDC dc=BeginPaint(h,&paint);RECT box={440,300,710,440};
        HBRUSH brush=CreateSolidBrush(RGB(213,235,255));FillRect(dc,&box,brush);DeleteObject(brush);FrameRect(dc,&box,(HBRUSH)GetStockObject(BLACK_BRUSH));
        wchar_t label[100];swprintf(label,100,L"CANVAS TARGET\nVisual code: %06u\nLeft: %d  Right: %d",visual_code,canvas_clicks,right_clicks);
        HFONT visual_font=CreateFontW(23,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
        HGDIOBJ old_font=SelectObject(dc,visual_font);
        SetBkMode(dc,TRANSPARENT);DrawTextW(dc,label,-1,&box,DT_CENTER|DT_VCENTER|DT_WORDBREAK);
        SelectObject(dc,old_font);DeleteObject(visual_font);EndPaint(h,&paint);return 0;
    }
    case WM_DESTROY: KillTimer(h,1);restore_clipboard();discard_clipboard_copy();save_state();PostQuitMessage(0);return 0;
    }
    return DefWindowProcW(h,message,w,l);
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,PWSTR arguments,int show) {
    (void)previous;(void)show;
    visual_code=(unsigned int)((GetTickCount64() ^ GetCurrentProcessId()) % 1000000);
    if(!arguments||!arguments[0])return 2;
    wcsncpy(oracle_path,arguments,1023);
    if(oracle_path[0]=='"'){memmove(oracle_path,oracle_path+1,wcslen(oracle_path)*sizeof(wchar_t));wchar_t *last=wcsrchr(oracle_path,'"');if(last)*last=0;}
    SetProcessDPIAware();
    WNDCLASSW cls={0};cls.style=CS_DBLCLKS;cls.lpfnWndProc=procedure;cls.hInstance=instance;cls.lpszClassName=L"MdoCuaEvalNative";cls.hCursor=LoadCursorW(NULL,IDC_ARROW);cls.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);RegisterClassW(&cls);
    HWND window=CreateWindowW(cls.lpszClassName,L"MDO Computer Use Acceptance",WS_OVERLAPPEDWINDOW,100,100,760,580,NULL,NULL,instance,NULL);
    ShowWindow(window,SW_SHOWNORMAL);UpdateWindow(window);
    MSG msg;while(GetMessageW(&msg,NULL,0,0)>0){if(!IsDialogMessageW(window,&msg)){TranslateMessage(&msg);DispatchMessageW(&msg);}}return 0;
}
