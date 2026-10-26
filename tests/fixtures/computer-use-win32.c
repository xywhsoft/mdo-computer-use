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
#include <wchar.h>

static HWND main_window, input, counter, check, combo, lines;
static wchar_t oracle_path[1024];
static int clicks, canvas_clicks, right_clicks;
static HFONT font;

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
    json_text(f,text); fputs(",\"selection\":",f); json_text(f,selected); fputs("}\n",f);
    fclose(f); MoveFileExW(temporary,oracle_path,MOVEFILE_REPLACE_EXISTING);
}
static HWND child(const wchar_t *class_name,const wchar_t *text,DWORD style,int x,int y,int width,int height,int id) {
    HWND h=CreateWindowExW(0,class_name,text,WS_CHILD|WS_VISIBLE|style,x,y,width,height,main_window,(HMENU)(INT_PTR)id,GetModuleHandleW(NULL),NULL);
    SendMessageW(h,WM_SETFONT,(WPARAM)font,TRUE); return h;
}
static LRESULT CALLBACK procedure(HWND h,UINT message,WPARAM w,LPARAM l) {
    switch(message) {
    case WM_CREATE: {
        main_window=h; font=(HFONT)GetStockObject(DEFAULT_GUI_FONT);
        child(L"STATIC",L"MDO Computer Use - project acceptance window",0,20,16,690,24,0);
        child(L"STATIC",L"Input text",0,20,56,120,20,0);
        input=child(L"EDIT",L"",WS_BORDER|WS_TABSTOP|ES_MULTILINE|ES_AUTOVSCROLL,20,80,690,74,101);
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
        SetTimer(h,1,150,NULL); save_state(); return 0;
    }
    case WM_COMMAND:
        if(LOWORD(w)==102 && HIWORD(w)==BN_CLICKED){wchar_t label[64];clicks++;swprintf(label,64,L"Counter: %d",clicks);SetWindowTextW(counter,label);}
        if(LOWORD(w)==106){DestroyWindow(h);return 0;}
        save_state(); return 0;
    case WM_LBUTTONDOWN:
    case WM_RBUTTONDOWN:
        if(GET_X_LPARAM(l)>=440&&GET_X_LPARAM(l)<=710&&GET_Y_LPARAM(l)>=300&&GET_Y_LPARAM(l)<=440){
            if(message==WM_LBUTTONDOWN)canvas_clicks++;else right_clicks++;
            InvalidateRect(h,NULL,TRUE);save_state();return 0;
        }break;
    case WM_TIMER: save_state();return 0;
    case WM_PAINT: {
        PAINTSTRUCT paint;HDC dc=BeginPaint(h,&paint);RECT box={440,300,710,440};
        HBRUSH brush=CreateSolidBrush(RGB(213,235,255));FillRect(dc,&box,brush);DeleteObject(brush);FrameRect(dc,&box,(HBRUSH)GetStockObject(BLACK_BRUSH));
        wchar_t label[100];swprintf(label,100,L"CANVAS TARGET\nLeft: %d  Right: %d",canvas_clicks,right_clicks);
        SetBkMode(dc,TRANSPARENT);DrawTextW(dc,label,-1,&box,DT_CENTER|DT_VCENTER|DT_WORDBREAK);EndPaint(h,&paint);return 0;
    }
    case WM_DESTROY: KillTimer(h,1);save_state();PostQuitMessage(0);return 0;
    }
    return DefWindowProcW(h,message,w,l);
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,PWSTR arguments,int show) {
    (void)previous;(void)show;
    if(!arguments||!arguments[0])return 2;
    wcsncpy(oracle_path,arguments,1023);
    if(oracle_path[0]=='"'){memmove(oracle_path,oracle_path+1,wcslen(oracle_path)*sizeof(wchar_t));wchar_t *last=wcsrchr(oracle_path,'"');if(last)*last=0;}
    SetProcessDPIAware();
    WNDCLASSW cls={0};cls.lpfnWndProc=procedure;cls.hInstance=instance;cls.lpszClassName=L"MdoCuaEvalNative";cls.hCursor=LoadCursorW(NULL,IDC_ARROW);cls.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);RegisterClassW(&cls);
    HWND window=CreateWindowW(cls.lpszClassName,L"MDO Computer Use Acceptance",WS_OVERLAPPEDWINDOW,100,100,760,580,NULL,NULL,instance,NULL);
    ShowWindow(window,SW_SHOWNORMAL);UpdateWindow(window);
    MSG msg;while(GetMessageW(&msg,NULL,0,0)>0){if(!IsDialogMessageW(window,&msg)){TranslateMessage(&msg);DispatchMessageW(&msg);}}return 0;
}
