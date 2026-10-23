#include <windows.h>
#include <stdio.h>
int main(void) {
    printf("WINDOWS_ACP=%u SYSTEM_LCID=%lu USER_LCID=%lu\n", GetACP(), GetSystemDefaultLCID(), GetUserDefaultLCID());
    fflush(stdout);
    return 0;
}
