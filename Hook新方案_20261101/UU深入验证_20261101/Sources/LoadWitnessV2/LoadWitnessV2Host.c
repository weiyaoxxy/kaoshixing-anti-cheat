#include <stdio.h>
#include <unistd.h>

int main(void) {
    printf("{\"event\":\"host_main\",\"pid\":%ld,\"uid\":%lu}\n",
           (long)getpid(), (unsigned long)getuid());
    return 0;
}
