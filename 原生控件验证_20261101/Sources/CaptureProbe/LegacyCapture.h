#pragma once
#include <CoreGraphics/CoreGraphics.h>
CGImageRef _Nullable ProbeLegacyCapture(CGRect rect, uint32_t options, uint32_t windowID, uint32_t imageOptions) CF_RETURNS_RETAINED;
bool ProbeLegacyCaptureAvailable(void);
CGImageRef _Nullable ProbeLegacyDisplayCapture(uint32_t displayID) CF_RETURNS_RETAINED;
bool ProbeLegacyDisplayCaptureAvailable(void);
