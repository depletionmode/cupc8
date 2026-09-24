// Port of rp2040js src/peripherals/busctrl.ts
#include "busctrl.h"

namespace rp2040js {

/** Bus priority acknowledge */
static constexpr uint32_t BUS_PRIORITY_ACK = 0x004;

/** Bus fabric performance counter 0 */
static constexpr uint32_t PERFCTR0 = 0x008;
/** Bus fabric performance event select for PERFCTR0 */
static constexpr uint32_t PERFSEL0 = 0x00c;

/** Bus fabric performance counter 1 */
static constexpr uint32_t PERFCTR1 = 0x010;
/** Bus fabric performance event select for PERFCTR1 */
static constexpr uint32_t PERFSEL1 = 0x014;

/** Bus fabric performance counter 2 */
static constexpr uint32_t PERFCTR2 = 0x018;
/** Bus fabric performance event select for PERFCTR2 */
static constexpr uint32_t PERFSEL2 = 0x01c;

/** Bus fabric performance counter 3 */
static constexpr uint32_t PERFCTR3 = 0x020;
/** Bus fabric performance event select for PERFCTR3 */
static constexpr uint32_t PERFSEL3 = 0x024;

RPBUSCTRL::RPBUSCTRL(RP2040 &rp2040, const std::string &name) : BasePeripheral(rp2040, name) {}

uint32_t RPBUSCTRL::readUint32(uint32_t offset) {
  switch (offset) {
    case BUS_PRIORITY_ACK:
      return 1;
    case PERFCTR0:
      return perfCtr[0];
    case PERFSEL0:
      return perfSel[0];
    case PERFCTR1:
      return perfCtr[1];
    case PERFSEL1:
      return perfSel[1];
    case PERFCTR2:
      return perfCtr[2];
    case PERFSEL2:
      return perfSel[2];
    case PERFCTR3:
      return perfCtr[3];
    case PERFSEL3:
      return perfSel[3];
  }
  return BasePeripheral::readUint32(offset);
}

void RPBUSCTRL::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case PERFCTR0:
      perfCtr[0] = 0;
      break;
    case PERFSEL0:
      perfSel[0] = value & 0x1f;
      break;
    case PERFCTR1:
      perfCtr[1] = 0;
      break;
    case PERFSEL1:
      perfSel[1] = value & 0x1f;
      break;
    case PERFCTR2:
      perfCtr[2] = 0;
      break;
    case PERFSEL2:
      perfSel[2] = value & 0x1f;
      break;
    case PERFCTR3:
      perfCtr[3] = 0;
      break;
    case PERFSEL3:
      perfSel[3] = value & 0x1f;
      break;
    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

}  // namespace rp2040js
