// Port of rp2040js src/utils/bit.ts
#pragma once

#include <cstdint>

#include "js.h"

namespace rp2040js {

inline uint32_t bit(uint32_t n) { return static_cast<uint32_t>(1u << (n & 31)); }

/** `n | 0` */
inline int32_t s32(double n) { return toInt32(n); }

/** `n >>> 0` */
inline uint32_t u32(double n) { return toUint32(n); }

}  // namespace rp2040js
