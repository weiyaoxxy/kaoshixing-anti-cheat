#include <stddef.h>
void exam_start_image_tracking(void);
size_t exam_image_count(void);
const char *exam_image_path(size_t index);
int exam_image_tracking_incomplete(void);
int exam_read_code(const void *address, void *destination, size_t count);
