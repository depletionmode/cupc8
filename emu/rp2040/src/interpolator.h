// Port of rp2040js src/interpolator.ts
#pragma once

#include <cstdint>

namespace rp2040js {

class InterpolatorConfig {
 public:
  uint32_t shift = 0;
  uint32_t maskLSB = 0;
  uint32_t maskMSB = 0;
  bool signed_ = false;  // TS `signed` (a C++ keyword)
  bool crossInput = false;
  bool crossResult = false;
  bool addRaw = false;
  uint32_t forceMSB = 0;
  bool blend = false;
  bool clamp = false;
  bool overf0 = false;
  bool overf1 = false;
  bool overf = false;

  explicit InterpolatorConfig(uint32_t value);

  uint32_t toUint32() const;
};

/**
 * All registers are uint32_t. In TS, `accum0 += value` (SIO ACCUMx_ADD) lets
 * accum grow past 32 bits, but every use of it goes through s32()/u32() or a
 * Uint32Array store, so wrapping at 32 bits is exactly equivalent.
 */
class Interpolator {
 public:
  uint32_t accum0 = 0;
  uint32_t accum1 = 0;
  uint32_t base0 = 0;
  uint32_t base1 = 0;
  uint32_t base2 = 0;
  uint32_t ctrl0 = 0;
  uint32_t ctrl1 = 0;
  uint32_t result0 = 0;
  uint32_t result1 = 0;
  uint32_t result2 = 0;
  uint32_t smresult0 = 0;
  uint32_t smresult1 = 0;

  explicit Interpolator(uint32_t index);

  void update();
  void writeback();
  void setBase01(uint32_t value);

 private:
  const uint32_t index;
};

}  // namespace rp2040js
