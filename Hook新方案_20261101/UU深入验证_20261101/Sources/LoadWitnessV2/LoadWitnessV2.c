#include <errno.h>
#include <fcntl.h>
#include <mach-o/dyld.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/* No frameworks, capture APIs, hooks, network access, or environment values
 * in stderr. Its first observable action is one fixed-marker stderr write. */
static void enter_marker(pid_t pid) {
    char line[96] = "EXAMHOOK_WITNESS_V2 event=constructor_enter pid=";
    size_t used = sizeof("EXAMHOOK_WITNESS_V2 event=constructor_enter pid=") - 1;
    char digits[24];
    size_t count = 0;
    unsigned long number = (unsigned long)pid;
    do {
        digits[count++] = (char)('0' + number % 10);
        number /= 10;
    } while (number != 0 && count < sizeof(digits));
    while (count > 0) line[used++] = digits[--count];
    line[used++] = '\n';
    ssize_t ignored = write(STDERR_FILENO, line, used);
    (void)ignored;
}

static void diagnostic(const char *event, pid_t pid, int has_log_env, int error) {
    char line[192];
    int length = snprintf(line, sizeof(line),
        "EXAMHOOK_WITNESS_V2 event=%s pid=%ld hasLogEnv=%d errno=%d\n",
        event, (long)pid, has_log_env, error);
    if (length > 0 && (size_t)length < sizeof(line)) {
        ssize_t ignored = write(STDERR_FILENO, line, (size_t)length);
        (void)ignored;
    }
}

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

__attribute__((constructor)) static void load_witness_v2(void) {
    pid_t pid = getpid();
    enter_marker(pid);

    const char *log_path = getenv("HOOK_DEMO_LOG");
    int has_log_env = log_path != NULL;
    if (log_path == NULL || log_path[0] == '\0') {
        diagnostic("log_skipped", pid, has_log_env, 0);
        return;
    }

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
        "{\"event\":\"image_loaded\",\"component\":\"LoadWitnessV2\","
        "\"version\":\"2.0\",\"pid\":%ld,\"uid\":%lu,"
        "\"executable\":\"%s\",\"monotonicSeconds\":%lld,"
        "\"monotonicNanoseconds\":%ld,\"clockAvailable\":%s}\n",
        (long)pid, (unsigned long)getuid(), escaped,
        (long long)timestamp.tv_sec, timestamp.tv_nsec,
        clock_ok ? "true" : "false");
    if (length <= 0 || (size_t)length >= sizeof(line)) {
        diagnostic("log_format_failed", pid, has_log_env, EOVERFLOW);
        return;
    }

    int fd = open(log_path, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, 0600);
    if (fd < 0) {
        int open_error = errno;
        diagnostic("log_open_failed", pid, has_log_env, open_error);
        return;
    }
    size_t offset = 0;
    int write_error = 0;
    while (offset < (size_t)length) {
        ssize_t count = write(fd, line + offset, (size_t)length - offset);
        if (count > 0) offset += (size_t)count;
        else if (count < 0 && errno == EINTR) continue;
        else {
            write_error = count < 0 ? errno : EIO;
            break;
        }
    }
    int close_result = close(fd);
    int close_error = close_result < 0 ? errno : 0;
    if (write_error != 0)
        diagnostic("log_write_failed", pid, has_log_env, write_error);
    else if (close_error != 0)
        diagnostic("log_close_failed", pid, has_log_env, close_error);
    else
        diagnostic("log_written", pid, has_log_env, 0);
}
