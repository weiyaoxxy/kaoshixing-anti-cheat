#import <Foundation/Foundation.h>
#import <dlfcn.h>
int main(void) { @autoreleasepool { void (*test)(void)=(void(*)(void))dlsym(RTLD_DEFAULT,"CaptureHookLogSelfTest"); if(test)test(); puts("Hook load smoke completed"); } return 0; }
