// JavaScript number semantics, for a faithful port of rp2040js.
//
// Not a TS module: these are the helpers every port file uses wherever the
// TypeScript relies on how JS numbers behave (ToInt32 / ToUint32 on `| 0`,
// `>>> 0` and typed-array stores, Math.round, shift counts taken & 31,
// Number.prototype.toString(16), little-endian DataView access).
#pragma once

#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>

namespace rp2040js {

/** JS ToUint32 (what `x >>> 0` and a Uint32Array store do to any number). */
inline uint32_t toUint32(double x) {
  if (x > -9223372036854775808.0 && x < 9223372036854775808.0) {
    // |x| < 2**63 (not NaN): the conversion truncates towards zero, like
    // trunc(), and the two's complement wrap to 32 bits is t mod 2**32, what
    // the fmod below computes (exactly, without the library calls)
    return static_cast<uint32_t>(static_cast<uint64_t>(static_cast<int64_t>(x)));
  }
  if (!std::isfinite(x)) {
    return 0;
  }
  double t = std::trunc(x);
  double m = std::fmod(t, 4294967296.0);
  if (m < 0) {
    m += 4294967296.0;
  }
  return static_cast<uint32_t>(m);
}

/** JS ToInt32 (what `x | 0` and every bitwise operator do to their operands). */
inline int32_t toInt32(double x) { return static_cast<int32_t>(toUint32(x)); }

/** JS ToUint16 / ToUint8 (Uint16Array / Uint8Array stores, DataView.setUint16/8). */
inline uint16_t toUint16(double x) { return static_cast<uint16_t>(toUint32(x)); }
inline uint8_t toUint8(double x) { return static_cast<uint8_t>(toUint32(x)); }

/** `a << n` on int32 values: JS takes the count & 31. */
inline int32_t jsShl(int32_t a, uint32_t n) {
  return static_cast<int32_t>(static_cast<uint32_t>(a) << (n & 31));
}
/** `a >> n` (arithmetic) with the count & 31. */
inline int32_t jsSar(int32_t a, uint32_t n) { return a >> (n & 31); }
/** `a >>> n` (logical) with the count & 31. */
inline uint32_t jsShr(uint32_t a, uint32_t n) { return a >> (n & 31); }

/** Math.round: rounds half up (towards +Infinity), unlike std::round. */
inline double jsMathRound(double x) {
  if (!std::isfinite(x)) {
    return x;
  }
  double r;
  if (x != 0 && std::fabs(x) < 4503599627370496.0) {
    // |x| < 2**52: floor(x) through int64 (exact; x = -0 keeps the library's
    // floor below, which returns -0)
    r = static_cast<double>(static_cast<int64_t>(x));
    if (r > x) {
      r -= 1;
    }
  } else {
    r = std::floor(x);  // 0, or |x| >= 2**52: x is an integer
  }
  if (x - r >= 0.5) {
    r += 1;
  }
  return r;
}

/** `value.toString(16)` for an integral JS number (lowercase, no padding). */
inline std::string toHex(double value) {
  bool neg = value < 0;
  double v = std::trunc(neg ? -value : value);
  std::string digits;
  if (v == 0) {
    digits = "0";
  }
  while (v >= 1) {
    int d = static_cast<int>(std::fmod(v, 16.0));
    digits.insert(digits.begin(), "0123456789abcdef"[d]);
    v = std::floor(v / 16);
  }
  return neg ? "-" + digits : digits;
}

/** DataView.getUint32(offset, true) / setUint32(offset, value, true) etc. */
inline uint32_t loadLE32(const uint8_t *p) {
  return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
         (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
}
inline uint16_t loadLE16(const uint8_t *p) {
  return static_cast<uint16_t>(p[0] | (p[1] << 8));
}
inline void storeLE32(uint8_t *p, uint32_t v) {
  p[0] = static_cast<uint8_t>(v);
  p[1] = static_cast<uint8_t>(v >> 8);
  p[2] = static_cast<uint8_t>(v >> 16);
  p[3] = static_cast<uint8_t>(v >> 24);
}
inline void storeLE16(uint8_t *p, uint16_t v) {
  p[0] = static_cast<uint8_t>(v);
  p[1] = static_cast<uint8_t>(v >> 8);
}

/** console.warn / console.error from TS code that bypasses the Logger. */
void consoleWarn(const std::string &message);
void consoleError(const std::string &message);

}  // namespace rp2040js

/** Stub marker: a not-yet-ported method that must not run. Prints and aborts. */
#define TODO_PORT_ABORT(tsFile, what) ::rp2040js::todoPortAbort(tsFile, what)
namespace rp2040js {
[[noreturn]] void todoPortAbort(const char *tsFile, const char *what);
}
