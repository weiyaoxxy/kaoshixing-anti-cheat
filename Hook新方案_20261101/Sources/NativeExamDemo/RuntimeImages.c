#include "RuntimeImages.h"
#include <mach-o/dyld.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>

// Keep a bounded, append-only history, including images subsequently unloaded.
// The callback does no Foundation work, file IO, or code-signature validation
// while dyld holds its loader lock. Strings live until process exit.
#define IMAGE_LIMIT 8192
static pthread_mutex_t image_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t tracker_once = PTHREAD_ONCE_INIT;
static char *paths[IMAGE_LIMIT];
static size_t path_count;
static int incomplete;

static void image_added(const struct mach_header *header, intptr_t slide) {
    (void)slide;
    Dl_info info = {0};
    int found = dladdr(header, &info);
    pthread_mutex_lock(&image_lock);
    if (!found || !info.dli_fname) {
        incomplete = 1;
    } else {
        int seen = 0;
        for (size_t i = 0; i < path_count; i++) {
            if (strcmp(paths[i], info.dli_fname) == 0) { seen = 1; break; }
        }
        if (!seen) {
            if (path_count == IMAGE_LIMIT) incomplete = 1;
            else {
                char *path = strdup(info.dli_fname);
                if (path) paths[path_count++] = path;
                else incomplete = 1;
            }
        }
    }
    pthread_mutex_unlock(&image_lock);
}

static void register_tracker(void) { _dyld_register_func_for_add_image(image_added); }
void exam_start_image_tracking(void) { pthread_once(&tracker_once, register_tracker); }
size_t exam_image_count(void) {
    pthread_mutex_lock(&image_lock);
    size_t result = path_count;
    pthread_mutex_unlock(&image_lock);
    return result;
}
const char *exam_image_path(size_t index) {
    pthread_mutex_lock(&image_lock);
    const char *result = index < path_count ? paths[index] : NULL;
    pthread_mutex_unlock(&image_lock);
    return result;
}
int exam_image_tracking_incomplete(void) {
    pthread_mutex_lock(&image_lock);
    int result = incomplete;
    pthread_mutex_unlock(&image_lock);
    return result;
}
int exam_read_code(const void *address, void *destination, size_t count) {
    mach_vm_size_t copied = 0;
    kern_return_t result = mach_vm_read_overwrite(mach_task_self(),
        (mach_vm_address_t)address, count, (mach_vm_address_t)destination, &copied);
    return result == KERN_SUCCESS && copied == count;
}
