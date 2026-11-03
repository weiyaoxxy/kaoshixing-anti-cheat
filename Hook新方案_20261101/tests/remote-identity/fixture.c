#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#ifndef FIXTURE_VARIANT
#define FIXTURE_VARIANT 1
#endif

// No network, capture, input, privileged operations or target process signals.
int main(int argc, char **argv) {
    if (argc == 3 && strcmp(argv[1], "exec-after") == 0) {
        usleep(1500000);
        execl(argv[2], argv[2], "6", NULL);
        return 111;
    }
    int seconds = argc > 1 ? atoi(argv[1]) : 8;
    if (seconds < 1 || seconds > 30) return 64;
    fprintf(stdout, "fixture-%d\n", FIXTURE_VARIANT);
    fflush(stdout);
    sleep((unsigned int)seconds);
    return 0;
}
