#include <errno.h>
#include <fcntl.h>
#include <mach-o/dyld.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

// Deliberately has no Objective-C runtime, framework, interposition, or capture
// dependency. The only side effect is an optional append to HOOK_DEMO_LOG.
static size_t append_json_string(char *output, size_t capacity, const char *input) {
    static const char hex[] = "0123456789abcdef";
    size_t used = 0;
    for (const unsigned char *p = (const unsigned char *)input; *p; ++p) {
        unsigned char c = *p;
        if (c == '"' || c == '\\') {
            if (used + 2 >= capacity) return 0;
            output[used++] = '\\'; output[used++] = (char)c;
        } else if (c < 0x20) {
            if (used + 6 >= capacity) return 0;
            output[used++] = '\\'; output[used++] = 'u';
            output[used++] = '0'; output[used++] = '0';
            output[used++] = hex[c >> 4]; output[used++] = hex[c & 15];
        } else {
            if (used + 1 >= capacity) return 0;
            output[used++] = (char)c;
        }
    }
    output[used] = '\0';
    return used;
}

__attribute__((constructor)) static void load_witness(void) {
    const char *log_path = getenv("HOOK_DEMO_LOG");
    if (log_path == NULL || log_path[0] == '\0') return;

    char executable[4096];
    uint32_t path_size = sizeof(executable);
    if (_NSGetExecutablePath(executable, &path_size) != 0)
        strcpy(executable, "<executable path exceeds witness capacity>");

    char escaped[24577];
    if (append_json_string(escaped, sizeof(escaped), executable) == 0)
        strcpy(escaped, "<executable path unavailable>");

    struct timespec timestamp = {0, 0};
    int clock_ok = clock_gettime(CLOCK_MONOTONIC, &timestamp) == 0;
    char line[25600];
    int length = snprintf(line, sizeof(line),
        "{\"event\":\"image_loaded\",\"component\":\"LoadWitness\","
        "\"version\":\"1.0\",\"pid\":%ld,\"uid\":%lu,"
        "\"executable\":\"%s\",\"monotonicSeconds\":%lld,"
        "\"monotonicNanoseconds\":%ld,\"clockAvailable\":%s}\n",
        (long)getpid(), (unsigned long)getuid(), escaped,
        (long long)timestamp.tv_sec, timestamp.tv_nsec,
        clock_ok ? "true" : "false");
    if (length <= 0 || (size_t)length >= sizeof(line)) return;

    int fd = open(log_path, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, 0600);
    if (fd < 0) return;
    size_t offset = 0;
    while (offset < (size_t)length) {
        ssize_t count = write(fd, line + offset, (size_t)length - offset);
        if (count > 0) offset += (size_t)count;
        else if (count < 0 && errno == EINTR) continue;
        else break;
    }
    close(fd);
}
