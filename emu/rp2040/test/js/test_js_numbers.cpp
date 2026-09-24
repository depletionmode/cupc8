// test_js_numbers: utils/js.h's toUint32 and jsMathRound (which take an exact
// shortcut through int64 where they can) against their plain definitions with
// trunc / fmod / floor, on 20 million doubles of every kind. Run by
// emu/rp2040/test/diffs.sh (EMU-005). Exit 0 and "0 mismatches" when equal.
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <random>

#include "utils/js.h"

static uint32_t oldToUint32(double x) {
  if (!std::isfinite(x)) return 0;
  double t = std::trunc(x);
  double m = std::fmod(t, 4294967296.0);
  if (m < 0) m += 4294967296.0;
  return static_cast<uint32_t>(m);
}
static double oldRound(double x) {
  if (!std::isfinite(x)) return x;
  double r = std::floor(x);
  if (x - r >= 0.5) r += 1;
  return r;
}
static bool same(double a, double b) { return std::memcmp(&a, &b, 8) == 0 || (std::isnan(a) && std::isnan(b)); }

int main() {
  std::mt19937_64 g(1);
  uint64_t bad = 0, n = 0;
  auto check = [&](double x) {
    n++;
    if (rp2040js::toUint32(x) != oldToUint32(x)) {
      if (bad++ < 10) std::printf("toUint32(%.17g)\n", x);
    }
    if (!same(rp2040js::jsMathRound(x), oldRound(x))) {
      if (bad++ < 10) std::printf("round(%.17g)\n", x);
    }
  };
  const double specials[] = {0.0, -0.0, 0.5, -0.5, 1.5, -1.5, 0.49999999999999994, -0.49999999999999994,
                             4294967295.0, 4294967296.0, -4294967296.0, 4294967297.5, -1.0, -2147483648.0,
                             9223372036854775807.0, -9223372036854775808.0, 9223372036854775808.0,
                             4503599627370496.0, -4503599627370496.0, 4503599627370495.5, -4503599627370495.5,
                             9007199254740993.0, 1e300, -1e300, INFINITY, -INFINITY, NAN, 5e-324, -5e-324};
  for (double s : specials) {
    check(s);
    check(std::nextafter(s, INFINITY));
    check(std::nextafter(s, -INFINITY));
  }
  for (int i = 0; i < 20000000; i++) {
    const uint64_t r = g();
    double x;
    switch (i % 5) {
      case 0: std::memcpy(&x, &r, 8); break;                                         // any bit pattern
      case 1: x = static_cast<double>(static_cast<int64_t>(r) >> (r & 63)); break;   // integers of every size
      case 2: x = static_cast<double>(static_cast<int64_t>(r) >> (r & 63)) + 0.5; break;
      case 3: x = std::ldexp(static_cast<double>(static_cast<int64_t>(r >> 11) - (1ll << 52)), static_cast<int>(r % 80) - 60); break;
      default: x = static_cast<double>(static_cast<int32_t>(r)) / (1 + (r >> 60)); break;
    }
    check(x);
  }
  std::printf("%llu values, %llu mismatches\n", (unsigned long long)n, (unsigned long long)bad);
  return bad != 0;
}
