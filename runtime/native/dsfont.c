/* Compatibility for the packed-font initializer used by DiscStation games. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <limits.h>
#include <string.h>

typedef struct {
    HFONT font;
    int cell_width;
} font_entry;

static CRITICAL_SECTION guard;
static font_entry fonts[128];
static unsigned next_font;

static int magnitude(int value) {
    return value == INT_MIN ? INT_MAX : value < 0 ? -value : value;
}

static BOOL measure(HFONT font, TEXTMETRICA *metrics, char *face, int *advance) {
    HDC dc = CreateCompatibleDC(NULL);
    if (!dc) return FALSE;
    HGDIOBJ previous = SelectObject(dc, font);
    BOOL ok = previous && previous != HGDI_ERROR && GetTextMetricsA(dc, metrics);
    if (ok) {
        const WCHAR fullwidth[] = {0x3042};
        SIZE extent = {0};
        GetTextFaceA(dc, LF_FACESIZE, face);
        if (!GetTextExtentPoint32W(dc, fullwidth, 1, &extent) || extent.cx <= 0) ok = FALSE;
        else *advance = extent.cx;
    }
    if (previous && previous != HGDI_ERROR) SelectObject(dc, previous);
    DeleteDC(dc);
    return ok;
}

static HFONT create_compatible(const LOGFONTA *request) {
    HFONT font = CreateFontIndirectA(request);
    if (!font || request->lfCharSet != SHIFTJIS_CHARSET ||
        (request->lfPitchAndFamily & 3) != FIXED_PITCH ||
        request->lfEscapement || request->lfOrientation) return font;
    TEXTMETRICA actual;
    int advance = 0;
    char family[LF_FACESIZE] = {0};
    if (!measure(font, &actual, family, &advance) || actual.tmCharSet != SHIFTJIS_CHARSET) return font;
    int target = magnitude(request->lfWidth);
    LOGFONTA candidate_request = *request;
    /* Synthetic weight/rounding can add a pixel to the requested average.
       Match the requested average, rather than scaling every game by 90%. */
    for (unsigned attempt = 0; target > 0 && target <= 32768 && attempt < 4; attempt++) {
        int error = actual.tmAveCharWidth - target;
        if (!error) break;
        int width = magnitude(candidate_request.lfWidth) - error;
        if (width < 1 || width > 32768) break;
        candidate_request.lfWidth = request->lfWidth < 0 ? -width : width;
        HFONT candidate = CreateFontIndirectA(&candidate_request);
        if (!candidate) break;
        TEXTMETRICA checked;
        int checked_advance = 0;
        char checked_family[LF_FACESIZE] = {0};
        if (!measure(candidate, &checked, checked_family, &checked_advance) ||
            checked.tmCharSet != actual.tmCharSet || checked.tmHeight != actual.tmHeight ||
            strcmp(family, checked_family) ||
            magnitude(checked.tmAveCharWidth - target) >= magnitude(error)) {
            DeleteObject(candidate);
            break;
        }
        DeleteObject(font);
        font = candidate;
        actual = checked;
        advance = checked_advance;
    }
    if (advance > 0 && advance <= 32767) {
        EnterCriticalSection(&guard);
        unsigned index = next_font++ % (sizeof(fonts) / sizeof(fonts[0]));
        for (unsigned i = 0; i < sizeof(fonts) / sizeof(fonts[0]); i++) {
            if (fonts[i].font == font) { index = i; break; }
        }
        fonts[index].font = font;
        /* The legacy engine uses a full-width fixed cell, not the maximum
           glyph among every Unicode block supplied by a modern Gothic font. */
        fonts[index].cell_width = advance;
        LeaveCriticalSection(&guard);
    }
    return font;
}

__declspec(dllexport) HFONT WINAPI DS_CreateFontIndirectA(const LOGFONTA *request) {
    return request ? create_compatible(request) : CreateFontIndirectA(request);
}

__declspec(dllexport) HFONT WINAPI DS_CreateFontA(int height, int width, int escapement,
        int orientation, int weight, DWORD italic, DWORD underline, DWORD strikeout,
        DWORD charset, DWORD output, DWORD clip, DWORD quality, DWORD pitch, LPCSTR face) {
    LOGFONTA request = {0};
    request.lfHeight = height; request.lfWidth = width;
    request.lfEscapement = escapement; request.lfOrientation = orientation;
    request.lfWeight = weight; request.lfItalic = italic;
    request.lfUnderline = underline; request.lfStrikeOut = strikeout;
    request.lfCharSet = charset; request.lfOutPrecision = output;
    request.lfClipPrecision = clip; request.lfQuality = quality;
    request.lfPitchAndFamily = pitch;
    if (face) lstrcpynA(request.lfFaceName, face, LF_FACESIZE);
    return create_compatible(&request);
}

__declspec(dllexport) BOOL WINAPI DS_GetTextMetricsA(HDC dc, LPTEXTMETRICA metrics) {
    BOOL ok = GetTextMetricsA(dc, metrics);
    if (!ok || metrics->tmCharSet != SHIFTJIS_CHARSET) return ok;
    HFONT selected = (HFONT)GetCurrentObject(dc, OBJ_FONT);
    int width = 0;
    EnterCriticalSection(&guard);
    for (unsigned i = 0; i < sizeof(fonts) / sizeof(fonts[0]); i++) {
        if (fonts[i].font == selected) {
            width = fonts[i].cell_width;
            break;
        }
    }
    LeaveCriticalSection(&guard);
    if (width) {
        const WCHAR fullwidth[] = {0x3042};
        SIZE extent = {0};
        if (GetTextExtentPoint32W(dc, fullwidth, 1, &extent) && extent.cx > 0 && extent.cx <= 32767)
            width = extent.cx;
        metrics->tmMaxCharWidth = width;
    }
    return ok;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        InitializeCriticalSection(&guard);
        DisableThreadLibraryCalls(instance);
    } else if (reason == DLL_PROCESS_DETACH) {
        DeleteCriticalSection(&guard);
    }
    return TRUE;
}
