// Port of rp2040js src/interpolator.ts
//
// JS arithmetic here mixes int32 (`|`, `<<`, s32) and float (`+`, `*`,
// Math.floor) values; the comments give the TS expression wherever the C++
// had to spell the conversion out.
#include "interpolator.h"

#include <cmath>

#include "utils/bit.h"

namespace rp2040js {

InterpolatorConfig::InterpolatorConfig(uint32_t value) {
  shift = (value >> 0) & 0b11111;
  maskLSB = (value >> 5) & 0b11111;
  maskMSB = (value >> 10) & 0b11111;
  signed_ = static_cast<bool>((value >> 15) & 1);
  crossInput = static_cast<bool>((value >> 16) & 1);
  crossResult = static_cast<bool>((value >> 17) & 1);
  addRaw = static_cast<bool>((value >> 18) & 1);
  forceMSB = (value >> 19) & 0b11;
  blend = static_cast<bool>((value >> 21) & 1);
  clamp = static_cast<bool>((value >> 22) & 1);
  overf0 = static_cast<bool>((value >> 23) & 1);
  overf1 = static_cast<bool>((value >> 24) & 1);
  overf = static_cast<bool>((value >> 25) & 1);
}

uint32_t InterpolatorConfig::toUint32() const {
  return ((shift & 0b11111) << 0) | ((maskLSB & 0b11111) << 5) | ((maskMSB & 0b11111) << 10) |
         ((static_cast<uint32_t>(signed_) & 1) << 15) |
         ((static_cast<uint32_t>(crossInput) & 1) << 16) |
         ((static_cast<uint32_t>(crossResult) & 1) << 17) |
         ((static_cast<uint32_t>(addRaw) & 1) << 18) | ((forceMSB & 0b11) << 19) |
         ((static_cast<uint32_t>(blend) & 1) << 21) | ((static_cast<uint32_t>(clamp) & 1) << 22) |
         ((static_cast<uint32_t>(overf0) & 1) << 23) |
         ((static_cast<uint32_t>(overf1) & 1) << 24) | ((static_cast<uint32_t>(overf) & 1) << 25);
}

Interpolator::Interpolator(uint32_t index) : index(index) { update(); }

void Interpolator::update() {
  const uint32_t N = index;
  InterpolatorConfig ctrl0(this->ctrl0);
  InterpolatorConfig ctrl1(this->ctrl1);

  const bool do_clamp = ctrl0.clamp && N == 1;
  const bool do_blend = ctrl0.blend && N == 0;

  ctrl0.clamp = do_clamp;
  ctrl0.blend = do_blend;
  ctrl1.clamp = false;
  ctrl1.blend = false;
  ctrl1.overf0 = false;
  ctrl1.overf1 = false;
  ctrl1.overf = false;

  const int32_t input0 = s32(ctrl0.crossInput ? accum1 : accum0);
  const int32_t input1 = s32(ctrl1.crossInput ? accum0 : accum1);

  // `(1 << (maskMSB + 1)) - 1`: for maskMSB 30 that is -2147483649 in JS,
  // which every later bitwise use takes ToInt32 of (0x7fffffff): uint32 math
  // gives the same bits.
  const uint32_t msbmask0 = ctrl0.maskMSB == 31 ? 0xffffffff : (1u << (ctrl0.maskMSB + 1)) - 1;
  const uint32_t msbmask1 = ctrl1.maskMSB == 31 ? 0xffffffff : (1u << (ctrl1.maskMSB + 1)) - 1;
  const uint32_t mask0 = msbmask0 & ~((1u << ctrl0.maskLSB) - 1);
  const uint32_t mask1 = msbmask1 & ~((1u << ctrl1.maskLSB) - 1);

  const uint32_t uresult0 = (static_cast<uint32_t>(input0) >> ctrl0.shift) & mask0;
  const uint32_t uresult1 = (static_cast<uint32_t>(input1) >> ctrl1.shift) & mask1;

  const bool overf0 = static_cast<bool>((static_cast<uint32_t>(input0) >> ctrl0.shift) & ~msbmask0);
  const bool overf1 = static_cast<bool>((static_cast<uint32_t>(input1) >> ctrl1.shift) & ~msbmask1);
  const bool overf = overf0 || overf1;

  const uint32_t sextmask0 = uresult0 & (1u << ctrl0.maskMSB) ? 0xffffffffu << ctrl0.maskMSB : 0;
  const uint32_t sextmask1 = uresult1 & (1u << ctrl1.maskMSB) ? 0xffffffffu << ctrl1.maskMSB : 0;

  // JS numbers from here on: sresultN is an int32, uresultN a uint32.
  const double sresult0 = static_cast<int32_t>(uresult0 | sextmask0);
  const double sresult1 = static_cast<int32_t>(uresult1 | sextmask1);

  const double result0 = ctrl0.signed_ ? sresult0 : static_cast<double>(uresult0);
  const double result1 = ctrl1.signed_ ? sresult1 : static_cast<double>(uresult1);

  const double addresult0 = static_cast<double>(base0) + (ctrl0.addRaw ? input0 : result0);
  const double addresult1 = static_cast<double>(base1) + (ctrl1.addRaw ? input1 : result1);
  const double addresult2 = static_cast<double>(base2) + result0 + (do_blend ? 0 : result1);

  const double uclamp0 = u32(result0) < u32(base0)   ? static_cast<double>(base0)
                         : u32(result0) > u32(base1) ? static_cast<double>(base1)
                                                     : result0;
  const double sclamp0 = s32(result0) < s32(base0)   ? static_cast<double>(base0)
                         : s32(result0) > s32(base1) ? static_cast<double>(base1)
                                                     : result0;
  const double clamp0 = ctrl0.signed_ ? sclamp0 : uclamp0;

  const uint32_t alpha1 = toUint32(result1) & 0xff;  // `result1 & 0xff`
  const double ublend1 =
      static_cast<double>(u32(base0)) +
      toInt32(std::floor((alpha1 * (static_cast<double>(u32(base1)) - u32(base0))) / 256));
  const double sblend1 =
      static_cast<double>(s32(base0)) +
      toInt32(std::floor((alpha1 * (static_cast<double>(s32(base1)) - s32(base0))) / 256));
  const double blend1 = ctrl1.signed_ ? sblend1 : ublend1;

  smresult0 = u32(result0);
  smresult1 = u32(result1);
  // `u32(do_blend ? alpha1 : (do_clamp ? clamp0 : addresult0) | (ctrl0.forceMSB << 28))`
  result0 = do_blend ? alpha1
                     : u32(static_cast<double>(toInt32(do_clamp ? clamp0 : addresult0) |
                                               static_cast<int32_t>(ctrl0.forceMSB << 28)));
  // `u32((do_blend ? blend1 : addresult1) | (ctrl0.forceMSB << 28))`
  result1 = static_cast<uint32_t>(toInt32(do_blend ? blend1 : addresult1) |
                                  static_cast<int32_t>(ctrl0.forceMSB << 28));
  result2 = u32(addresult2);

  ctrl0.overf0 = overf0;
  ctrl0.overf1 = overf1;
  ctrl0.overf = overf;
  this->ctrl0 = ctrl0.toUint32();
  this->ctrl1 = ctrl1.toUint32();
}

void Interpolator::writeback() {
  const InterpolatorConfig ctrl0(this->ctrl0);
  const InterpolatorConfig ctrl1(this->ctrl1);

  accum0 = u32(ctrl0.crossResult ? result1 : result0);
  accum1 = u32(ctrl1.crossResult ? result0 : result1);

  update();
}

void Interpolator::setBase01(uint32_t value) {
  const uint32_t N = index;
  const InterpolatorConfig ctrl0(this->ctrl0);
  const InterpolatorConfig ctrl1(this->ctrl1);

  const bool do_blend = ctrl0.blend && N == 0;

  const uint32_t input0 = value & 0xffff;
  const uint32_t input1 = (value >> 16) & 0xffff;

  const uint32_t sextmask0 = input0 & (1 << 15) ? 0xffffffffu << 15 : 0;
  const uint32_t sextmask1 = input1 & (1 << 15) ? 0xffffffffu << 15 : 0;

  const uint32_t base0 = (do_blend ? ctrl1.signed_ : ctrl0.signed_) ? input0 | sextmask0 : input0;
  const uint32_t base1 = ctrl1.signed_ ? input1 | sextmask1 : input1;

  this->base0 = u32(base0);
  this->base1 = u32(base1);

  update();
}

}  // namespace rp2040js
