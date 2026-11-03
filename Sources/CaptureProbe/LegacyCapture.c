#include "LegacyCapture.h"
#include <dlfcn.h>
// Runtime lookup permits evaluating the legacy exported public API even when the
// current SDK marks direct calls unavailable. This is not a replacement API.
typedef CGImageRef (*CaptureFn)(CGRect, uint32_t, uint32_t, uint32_t);
static CaptureFn resolve(void) { return (CaptureFn)dlsym(RTLD_DEFAULT, "CGWindowListCreateImage"); }
bool ProbeLegacyCaptureAvailable(void) { return resolve() != NULL; }
CGImageRef ProbeLegacyCapture(CGRect rect, uint32_t options, uint32_t windowID, uint32_t imageOptions) {
    CaptureFn fn = resolve();
    return fn ? fn(rect, options, windowID, imageOptions) : NULL;
}
