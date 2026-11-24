#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

static RECT client_on_screen(HWND window)
{
    RECT rect = {0};
    if (GetClientRect(window, &rect))
        MapWindowPoints(window, NULL, (POINT *)&rect, 2);
    return rect;
}

static int fit_origin(int position, int size, int limit)
{
    if (position < 0 || size >= limit) return 0;
    return position + size > limit ? limit - size : position;
}

static RECT viewport(DWORD game)
{
    RECT empty = {0};
    HWND window = GetForegroundWindow();
    DWORD owner = 0;
    if (!window || !IsWindowVisible(window) || IsIconic(window))
        return empty;
    GetWindowThreadProcessId(window, &owner);
    // Show the desktop while a modal or an unrelated window has focus.
    if (owner != game || GetWindow(window, GW_OWNER))
        return empty;

    RECT outer, client = client_on_screen(window);
    if (IsRectEmpty(&client) || !GetWindowRect(window, &outer))
        return empty;
    int width = client.right - client.left;
    int height = client.bottom - client.top;
    int screen_width = GetSystemMetrics(SM_CXSCREEN);
    int screen_height = GetSystemMetrics(SM_CYSCREEN);
    int left = fit_origin(client.left, width, screen_width);
    int top = fit_origin(client.top, height, screen_height);
    if (left != client.left || top != client.top || width > screen_width || height > screen_height) {
        int fit_width = width > screen_width ? screen_width : width;
        int fit_height = height > screen_height ? screen_height : height;
        SetWindowPos(window, NULL, outer.left + left - client.left, outer.top + top - client.top,
                     outer.right - outer.left + fit_width - width,
                     outer.bottom - outer.top + fit_height - height,
                     SWP_NOACTIVATE | SWP_NOZORDER | SWP_NOOWNERZORDER | SWP_ASYNCWINDOWPOS);
        client = client_on_screen(window);
    }
    RECT screen = {0, 0, screen_width, screen_height};
    IntersectRect(&client, &client, &screen);
    return client;
}

static int publish(const wchar_t *path, const wchar_t *temporary, const RECT *rect)
{
    FILE *file = _wfopen(temporary, L"w");
    if (!file) return 0;
    int written = fprintf(file, "%ld %ld %ld %ld\n", rect->left, rect->top, rect->right, rect->bottom);
    if (fclose(file) || written < 0) return 0;
    return MoveFileExW(temporary, path, MOVEFILE_REPLACE_EXISTING);
}

int wmain(int argc, wchar_t **argv)
{
    wchar_t path[MAX_PATH], temporary[MAX_PATH + 4], command[MAX_PATH + 4];
    DWORD length = GetEnvironmentVariableW(L"DS2PORT_VIEWPORT", path, MAX_PATH);
    if (argc != 2 || !length || length >= MAX_PATH || wcslen(argv[1]) >= MAX_PATH)
        return 1;
    swprintf(temporary, MAX_PATH + 4, L"%ls.new", path);
    swprintf(command, MAX_PATH + 4, L"\".\\%ls\"", argv[1]);
    SetProcessDPIAware();
    STARTUPINFOW startup = {.cb = sizeof(startup)};
    PROCESS_INFORMATION process;
    if (!CreateProcessW(NULL, command, NULL, NULL, FALSE, 0, NULL, NULL, &startup, &process)) {
        fprintf(stderr, "Cannot start game: Win32 error %lu\n", GetLastError());
        return 1;
    }
    CloseHandle(process.hThread);
    RECT previous = {0};
    do {
        RECT client = viewport(process.dwProcessId);
        if (!EqualRect(&client, &previous) && publish(path, temporary, &client))
            previous = client;
    } while (WaitForSingleObject(process.hProcess, 100) == WAIT_TIMEOUT);
    DWORD status = 1;
    GetExitCodeProcess(process.hProcess, &status);
    CloseHandle(process.hProcess);
    DeleteFileW(path);
    DeleteFileW(temporary);
    return (int)status;
}
