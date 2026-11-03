#import <Foundation/Foundation.h>
#import <dlfcn.h>
#import <dispatch/dispatch.h>

int main(void) {
    @autoreleasepool {
        void (*test)(void) = dlsym(RTLD_DEFAULT, "CaptureHookLogSelfTest");
        if (!test) return 2;
        dispatch_apply(200, dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^(size_t index) {
            @autoreleasepool { (void)index; test(); }
        });
    }
    return 0;
}
