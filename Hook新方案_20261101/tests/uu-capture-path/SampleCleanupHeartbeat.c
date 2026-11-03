#define _POSIX_C_SOURCE 200809L
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t keep_running = 1;
static void stop_fixture(int signal_number) {
    (void)signal_number;
    keep_running = 0;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    int fd = open(argv[1], O_WRONLY | O_CREAT | O_EXCL | O_APPEND, 0600);
    if (fd < 0) return 3;
    struct sigaction action = {0};
    action.sa_handler = stop_fixture;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, NULL) != 0) return 4;
    const struct timespec delay = {.tv_sec = 0, .tv_nsec = 20000000};
    uint64_t counter = 0;
    while (keep_running) {
        struct timespec now;
        if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) return 5;
        char line[100];
        int length = snprintf(line, sizeof(line), "%llu %llu\n",
                              (unsigned long long)++counter,
                              (unsigned long long)now.tv_sec * 1000000000ULL +
                                  (unsigned long long)now.tv_nsec);
        if (length <= 0 || write(fd, line, (size_t)length) != length) return 6;
        nanosleep(&delay, NULL);
    }
    close(fd);
    return 0;
}
