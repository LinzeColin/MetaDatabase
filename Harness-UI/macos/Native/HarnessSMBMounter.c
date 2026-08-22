#include <CoreFoundation/CoreFoundation.h>
#include <NetFS/NetFS.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>

static int is_guest_url(const char *url) {
    return strncasecmp(url, "smb://guest@", strlen("smb://guest@")) == 0;
}

int main(int argc, const char *argv[]) {
    if (argc != 2 || strncmp(argv[1], "smb://", strlen("smb://")) != 0) {
        fprintf(stderr, "usage: HarnessSMBMounter smb://server/share\n");
        return 64;
    }

    CFStringRef url_string = CFStringCreateWithCString(
        kCFAllocatorDefault,
        argv[1],
        kCFStringEncodingUTF8
    );
    if (url_string == NULL) {
        return 65;
    }
    CFURLRef share = CFURLCreateWithString(kCFAllocatorDefault, url_string, NULL);
    CFRelease(url_string);
    if (share == NULL) {
        return 65;
    }

    CFMutableDictionaryRef open_options = CFDictionaryCreateMutable(
        kCFAllocatorDefault,
        0,
        &kCFTypeDictionaryKeyCallBacks,
        &kCFTypeDictionaryValueCallBacks
    );
    CFMutableDictionaryRef mount_options = CFDictionaryCreateMutable(
        kCFAllocatorDefault,
        0,
        &kCFTypeDictionaryKeyCallBacks,
        &kCFTypeDictionaryValueCallBacks
    );
    CFDictionarySetValue(open_options, kNAUIOptionKey, kNAUIOptionNoUI);
    if (is_guest_url(argv[1])) {
        CFDictionarySetValue(open_options, kNetFSUseGuestKey, kCFBooleanTrue);
    }
    CFDictionarySetValue(mount_options, kNetFSSoftMountKey, kCFBooleanTrue);

    CFArrayRef mountpoints = NULL;
    int status = NetFSMountURLSync(
        share,
        NULL,
        NULL,
        NULL,
        open_options,
        mount_options,
        &mountpoints
    );

    if (status == 0 && mountpoints != NULL) {
        CFIndex count = CFArrayGetCount(mountpoints);
        for (CFIndex index = 0; index < count; ++index) {
            CFStringRef path = CFArrayGetValueAtIndex(mountpoints, index);
            char buffer[4096];
            if (CFStringGetCString(path, buffer, sizeof(buffer), kCFStringEncodingUTF8)) {
                printf("%s\n", buffer);
            }
        }
    } else {
        fprintf(stderr, "NetFSMountURLSync status=%d\n", status);
    }

    if (mountpoints != NULL) {
        CFRelease(mountpoints);
    }
    CFRelease(mount_options);
    CFRelease(open_options);
    CFRelease(share);
    return status == 0 ? 0 : 1;
}
