#ifndef FONT8X8_CP437_H
#define FONT8X8_CP437_H

#include <stdint.h>

/* 256 CP437 glyphs, 8 rows each, bit 7 = leftmost pixel (public domain). */
extern const uint8_t font8x8_cp437[256][8];

#endif
