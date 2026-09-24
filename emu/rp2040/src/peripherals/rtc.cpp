// Port of rp2040js src/peripherals/rtc.ts
//
// The TS keeps `baseline` as a JS Date and reads the time back with the
// local-time getters, so what it returns depends on the host time zone. The
// port keeps the Date's time value (ms since the epoch) and reimplements the
// few Date operations used (the ECMAScript MakeDay / MakeTime / MakeDate /
// UTC / LocalTime / TimeClip algorithms), taking the local time zone offset
// from the C library (localtime_r's tm_gmtoff, the same tz database node
// uses), resolving local times in a DST gap or overlap as V8 does. On a UTC
// host (the build machines) the offset is always 0; the differential test
// also passes under TZ=America/New_York, Europe/London, Australia/Lord_Howe
// and Asia/Kolkata with RTC dates around their transitions. Zones with more
// than one offset change within two days could still resolve differently.
#include "rtc.h"

#include <cmath>
#include <ctime>
#include <limits>

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

static constexpr uint32_t RTC_SETUP0 = 0x04;
static constexpr uint32_t RTC_SETUP1 = 0x08;
static constexpr uint32_t RTC_CTRL = 0x0c;
static constexpr uint32_t IRQ_SETUP_0 = 0x10;
static constexpr uint32_t RTC_RTC1 = 0x18;
static constexpr uint32_t RTC_RTC0 = 0x1c;

static constexpr uint32_t RTC_ENABLE_BITS = 0x01;
static constexpr uint32_t RTC_ACTIVE_BITS = 0x2;
static constexpr uint32_t RTC_LOAD_BITS = 0x10;

static constexpr uint32_t SETUP_0_YEAR_SHIFT = 12;
static constexpr uint32_t SETUP_0_YEAR_MASK = 0xfff;
static constexpr uint32_t SETUP_0_MONTH_SHIFT = 8;
static constexpr uint32_t SETUP_0_MONTH_MASK = 0xf;
static constexpr uint32_t SETUP_0_DAY_SHIFT = 0;
static constexpr uint32_t SETUP_0_DAY_MASK = 0x1f;

static constexpr uint32_t SETUP_1_DOTW_SHIFT = 24;
static constexpr uint32_t SETUP_1_DOTW_MASK = 0x7;
static constexpr uint32_t SETUP_1_HOUR_SHIFT = 16;
static constexpr uint32_t SETUP_1_HOUR_MASK = 0x1f;
static constexpr uint32_t SETUP_1_MIN_SHIFT = 8;
static constexpr uint32_t SETUP_1_MIN_MASK = 0x3f;
static constexpr uint32_t SETUP_1_SEC_SHIFT = 0;
static constexpr uint32_t SETUP_1_SEC_MASK = 0x3f;

static constexpr uint32_t RTC_0_YEAR_SHIFT = 12;
static constexpr uint32_t RTC_0_YEAR_MASK = 0xfff;
static constexpr uint32_t RTC_0_MONTH_SHIFT = 8;
static constexpr uint32_t RTC_0_MONTH_MASK = 0xf;
static constexpr uint32_t RTC_0_DAY_SHIFT = 0;
static constexpr uint32_t RTC_0_DAY_MASK = 0x1f;

static constexpr uint32_t RTC_1_DOTW_SHIFT = 24;
static constexpr uint32_t RTC_1_DOTW_MASK = 0x7;
static constexpr uint32_t RTC_1_HOUR_SHIFT = 16;
static constexpr uint32_t RTC_1_HOUR_MASK = 0x1f;
static constexpr uint32_t RTC_1_MIN_SHIFT = 8;
static constexpr uint32_t RTC_1_MIN_MASK = 0x3f;
static constexpr uint32_t RTC_1_SEC_SHIFT = 0;
static constexpr uint32_t RTC_1_SEC_MASK = 0x3f;

// Unused in the TS too; referenced so -Wunused stays quiet.
[[maybe_unused]] static constexpr uint32_t UNUSED_RTC_CONSTS[] = {SETUP_1_DOTW_SHIFT,
                                                                 SETUP_1_DOTW_MASK};

// ---- the parts of JS Date that the TS uses -------------------------------

namespace {

constexpr double msPerDay = 86400000;

double jsMod(double a, double b) {  // the spec's `modulo` (result has the sign of b)
  const double r = std::fmod(a, b);
  return r < 0 ? r + b : r;
}

/** Days from 1970-01-01 to y-m-d (proleptic Gregorian; m is 1..12). */
double daysFromCivil(double y, double m, double d) {
  y -= m <= 2 ? 1 : 0;
  const double era = std::floor(y / 400);
  const double yoe = y - era * 400;
  const double mp = jsMod(m + 9, 12);
  const double doy = std::floor((153 * mp + 2) / 5) + d - 1;
  const double doe = yoe * 365 + std::floor(yoe / 4) - std::floor(yoe / 100) + doy;
  return era * 146097 + doe - 719468;
}

struct Civil {
  double year, month /* 0..11 */, date /* 1..31 */;
};

Civil civilFromDays(double z) {
  z += 719468;
  const double era = std::floor(z / 146097);
  const double doe = z - era * 146097;
  const double yoe = std::floor((doe - std::floor(doe / 1460) + std::floor(doe / 36524) -
                                 std::floor(doe / 146096)) /
                                365);
  const double y = yoe + era * 400;
  const double doy = doe - (365 * yoe + std::floor(yoe / 4) - std::floor(yoe / 100));
  const double mp = std::floor((5 * doy + 2) / 153);
  const double d = doy - std::floor((153 * mp + 2) / 5) + 1;
  const double m = mp < 10 ? mp + 3 : mp - 9;
  return {m <= 2 ? y + 1 : y, m - 1, d};
}

/** MakeDay(year, month, date) */
double makeDay(double year, double month, double date) {
  const double ym = year + std::floor(month / 12);
  const double mn = jsMod(month, 12);
  return daysFromCivil(ym, mn + 1, 1) + date - 1;
}

/** MakeTime(hour, min, sec, ms) */
double makeTime(double hour, double min, double sec, double ms) {
  return hour * 3600000 + min * 60000 + sec * 1000 + ms;
}

/** MakeDate(day, time) */
double makeDate(double day, double time) { return day * msPerDay + time; }

/** TimeClip(time) */
double timeClip(double time) {
  if (!std::isfinite(time) || std::fabs(time) > 8.64e15) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  return std::trunc(time) + 0.0;  // ToIntegerOrInfinity (-0 -> +0)
}

/** The host's UTC offset (ms) at the UTC time value t. */
double offsetAtUtc(double t) {
  const std::time_t secs = static_cast<std::time_t>(std::floor(t / 1000));
  std::tm tm{};
  if (!localtime_r(&secs, &tm)) {
    return 0;
  }
  return static_cast<double>(tm.tm_gmtoff) * 1000;
}

/**
 * UTC(t): a local time value to a UTC one, disambiguated as V8 does
 * ("compatible"): a local time that occurs twice (an overlap) takes the
 * earlier instant; one that does not exist (a gap) is taken with the offset
 * in effect before the transition, i.e. moved forward by the gap.
 */
double utcFromLocal(double t) {
  if (!std::isfinite(t)) {
    return t;
  }
  const double offsetBefore = offsetAtUtc(t - msPerDay);
  const double offsetAfter = offsetAtUtc(t + msPerDay);
  const double c1 = t - offsetBefore;
  const double c2 = t - offsetAfter;
  const bool v1 = offsetAtUtc(c1) == offsetBefore;
  const bool v2 = offsetAtUtc(c2) == offsetAfter;
  if (v1 && v2) {
    return std::fmin(c1, c2);
  }
  if (v1) {
    return c1;
  }
  if (v2) {
    return c2;
  }
  return c1;  // in a gap
}

/** LocalTime(t) */
double localTime(double t) { return t + offsetAtUtc(t); }

/** `new Date(year, month, day, hours, minutes, seconds).getTime()` (all integers) */
double newLocalDate(double year, double month, double day, double hours, double minutes,
                    double seconds) {
  // 0 <= year <= 99 means 1900 + year
  const double yr = year >= 0 && year <= 99 ? 1900 + year : year;
  const double finalDate = makeDate(makeDay(yr, month, day), makeTime(hours, minutes, seconds, 0));
  return timeClip(utcFromLocal(finalDate));
}

/** The local-time fields a Date getter returns (NaN for an invalid Date). */
struct LocalFields {
  double fullYear, month, date, day, hours, minutes, seconds;
};

LocalFields localFields(double t) {
  if (std::isnan(t)) {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    return {nan, nan, nan, nan, nan, nan, nan};
  }
  const double lt = localTime(t);
  const double dayNumber = std::floor(lt / msPerDay);
  const Civil c = civilFromDays(dayNumber);
  return {
      c.year,
      c.month,
      c.date,
      jsMod(dayNumber + 4, 7),
      jsMod(std::floor(lt / 3600000), 24),
      jsMod(std::floor(lt / 60000), 60),
      jsMod(std::floor(lt / 1000), 60),
  };
}

/** `field & mask` with JS ToInt32 (NaN -> 0) */
uint32_t maskField(double field, uint32_t mask) {
  return static_cast<uint32_t>(toInt32(field)) & mask;
}

}  // namespace

RP2040RTC::RP2040RTC(RP2040 &rp2040, const std::string &name)
    : BasePeripheral(rp2040, name), baseline(newLocalDate(2021, 0, 1, 0, 0, 0)) {}

uint32_t RP2040RTC::readUint32(uint32_t offset) {
  // new Date(this.baseline.getTime() + (this.rp2040.clock.nanos - this.baselineNanos) / 1_000_000)
  const double date = timeClip(baseline + (rp2040.clock.nanos() - baselineNanos) / 1000000);
  switch (offset) {
    case RTC_SETUP0:
      return setup0;
    case RTC_SETUP1:
      return setup1;
    case RTC_CTRL:
      return ctrl;
    case IRQ_SETUP_0:
      return 0;
    case RTC_RTC1: {
      const LocalFields f = localFields(date);
      return (maskField(f.fullYear, RTC_0_YEAR_MASK) << RTC_0_YEAR_SHIFT) |
             (maskField(f.month + 1, RTC_0_MONTH_MASK) << RTC_0_MONTH_SHIFT) |
             (maskField(f.date, RTC_0_DAY_MASK) << RTC_0_DAY_SHIFT);
    }
    case RTC_RTC0: {
      const LocalFields f = localFields(date);
      return (maskField(f.day, RTC_1_DOTW_MASK) << RTC_1_DOTW_SHIFT) |
             (maskField(f.hours, RTC_1_HOUR_MASK) << RTC_1_HOUR_SHIFT) |
             (maskField(f.minutes, RTC_1_MIN_MASK) << RTC_1_MIN_SHIFT) |
             (maskField(f.seconds, RTC_1_SEC_MASK) << RTC_1_SEC_SHIFT);
    }
    default:
      break;
  }
  return BasePeripheral::readUint32(offset);
}

void RP2040RTC::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case RTC_SETUP0:
      setup0 = value;
      break;
    case RTC_SETUP1:
      setup1 = value;
      break;
    case RTC_CTRL:
      // Though RTC_LOAD_BITS is type SC and should be cleared on next cycle, pico-sdk write
      // RTC_LOAD_BITS & RTC_ENABLE_BITS seperatly.
      // https://github.com/raspberrypi/pico-sdk/blob/master/src/rp2_common/hardware_rtc/rtc.c#L76-L80
      if (value & RTC_LOAD_BITS) {
        ctrl |= RTC_LOAD_BITS;
      }
      if (value & RTC_ENABLE_BITS) {
        ctrl |= RTC_ENABLE_BITS;
        ctrl |= RTC_ACTIVE_BITS;
        if (ctrl & RTC_LOAD_BITS) {
          const uint32_t year = (setup0 >> SETUP_0_YEAR_SHIFT) & SETUP_0_YEAR_MASK;
          const uint32_t month = (setup0 >> SETUP_0_MONTH_SHIFT) & SETUP_0_MONTH_MASK;
          const uint32_t day = (setup0 >> SETUP_0_DAY_SHIFT) & SETUP_0_DAY_MASK;
          const uint32_t hour = (setup1 >> SETUP_1_HOUR_SHIFT) & SETUP_1_HOUR_MASK;
          const uint32_t min = (setup1 >> SETUP_1_MIN_SHIFT) & SETUP_1_MIN_MASK;
          const uint32_t sec = (setup1 >> SETUP_1_SEC_SHIFT) & SETUP_1_SEC_MASK;
          baseline = newLocalDate(year, static_cast<double>(month) - 1, day, hour, min, sec);
          baselineNanos = rp2040.clock.nanos();
          ctrl &= ~RTC_LOAD_BITS;
        }
      } else {
        ctrl &= ~RTC_ENABLE_BITS;
        ctrl &= ~RTC_ACTIVE_BITS;
      }
      break;
    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

}  // namespace rp2040js
