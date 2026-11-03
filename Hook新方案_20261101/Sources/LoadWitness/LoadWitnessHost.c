#include <stdio.h>
#include <unistd.h>

int main(void) {
    // This executable neither loads the witness itself nor invokes a witness
    // symbol: only the launch environment can cause the dylib to be loaded.
    printf("{\"host\":\"LoadWitnessHost\",\"pid\":%ld,\"completed\":true}\n", (long)getpid());
    return 0;
}
