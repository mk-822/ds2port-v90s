#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef HFONT (WINAPI *create_fn)(const LOGFONTA *);
typedef BOOL (WINAPI *metrics_fn)(HDC, LPTEXTMETRICA);

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    HMODULE dll = LoadLibraryA(argv[1]);
    if (!dll) { printf("DLL_LOAD_FAILED %lu\n", GetLastError()); return 3; }
    create_fn create = (create_fn)(void *)GetProcAddress(dll, "DS_CreateFontIndirectA");
    metrics_fn metrics = (metrics_fn)(void *)GetProcAddress(dll, "DS_GetTextMetricsA");
    if (!create || !metrics) return 4;
    HDC dc = CreateCompatibleDC(NULL);
    const int cases[][3] = {{16,8,700},{24,6,700},{-24,-10,700},{-22,-8,700},
        {-16,-8,600},{-16,-6,600},{-32,-16,400},{-20,8,400},{-24,0,700}};
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        LOGFONTA request = {0};
        request.lfHeight = cases[i][0]; request.lfWidth = cases[i][1]; request.lfWeight = cases[i][2];
        request.lfCharSet = SHIFTJIS_CHARSET; request.lfPitchAndFamily = FIXED_PITCH;
        HFONT font = create(&request);
        if (!font) return 5;
        HGDIOBJ old = SelectObject(dc, font);
        TEXTMETRICA actual = {0}, compatibility = {0};
        SIZE extent = {0}; const WCHAR fullwidth[] = {0x3042};
        if (!GetTextMetricsA(dc, &actual) || !metrics(dc, &compatibility) ||
            !GetTextExtentPoint32W(dc, fullwidth, 1, &extent)) return 6;
        if ((request.lfWidth && actual.tmAveCharWidth != abs(request.lfWidth)) ||
            compatibility.tmMaxCharWidth != extent.cx || compatibility.tmHeight != actual.tmHeight) {
            printf("FONT_FAILED %u avg=%ld target=%d cell=%ld extent=%ld\n",i,actual.tmAveCharWidth,abs(request.lfWidth),compatibility.tmMaxCharWidth,extent.cx);
            return 7;
        }
        printf("FONT_COMPAT %d,%d,%d avg=%ld cell=%ld height=%ld\n",cases[i][0],cases[i][1],cases[i][2],actual.tmAveCharWidth,compatibility.tmMaxCharWidth,compatibility.tmHeight);
        SelectObject(dc, old); DeleteObject(font);
    }
    LOGFONTA other = {0}; other.lfHeight = -16; other.lfWidth = 8;
    other.lfCharSet = ANSI_CHARSET; other.lfPitchAndFamily = FIXED_PITCH;
    HFONT font = create(&other); HGDIOBJ old = SelectObject(dc, font);
    TEXTMETRICA a = {0}, b = {0};
    GetTextMetricsA(dc, &a); metrics(dc, &b);
    if (memcmp(&a, &b, sizeof(a))) return 8;
    SelectObject(dc, old); DeleteObject(font); DeleteDC(dc);
    puts("FONT_COMPAT_ALL_OK cases=10");
    FreeLibrary(dll); return 0;
}
