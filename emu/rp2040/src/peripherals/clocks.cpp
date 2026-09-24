// Port of rp2040js src/peripherals/clocks.ts
#include "clocks.h"

namespace rp2040js {

static constexpr uint32_t CLK_GPOUT0_CTRL = 0x00;
static constexpr uint32_t CLK_GPOUT0_DIV = 0x04;
static constexpr uint32_t CLK_GPOUT0_SELECTED = 0x8;
static constexpr uint32_t CLK_GPOUT1_CTRL = 0x0c;
static constexpr uint32_t CLK_GPOUT1_DIV = 0x10;
static constexpr uint32_t CLK_GPOUT1_SELECTED = 0x14;
static constexpr uint32_t CLK_GPOUT2_CTRL = 0x18;
static constexpr uint32_t CLK_GPOUT2_DIV = 0x01c;
static constexpr uint32_t CLK_GPOUT2_SELECTED = 0x20;
static constexpr uint32_t CLK_GPOUT3_CTRL = 0x24;
static constexpr uint32_t CLK_GPOUT3_DIV = 0x28;
static constexpr uint32_t CLK_GPOUT3_SELECTED = 0x2c;
static constexpr uint32_t CLK_REF_CTRL = 0x30;
static constexpr uint32_t CLK_REF_DIV = 0x34;
static constexpr uint32_t CLK_REF_SELECTED = 0x38;
static constexpr uint32_t CLK_SYS_CTRL = 0x3c;
static constexpr uint32_t CLK_SYS_DIV = 0x40;
static constexpr uint32_t CLK_SYS_SELECTED = 0x44;
static constexpr uint32_t CLK_PERI_CTRL = 0x48;
static constexpr uint32_t CLK_PERI_DIV = 0x4c;
static constexpr uint32_t CLK_PERI_SELECTED = 0x50;
static constexpr uint32_t CLK_USB_CTRL = 0x54;
static constexpr uint32_t CLK_USB_DIV = 0x58;
static constexpr uint32_t CLK_USB_SELECTED = 0x5c;
static constexpr uint32_t CLK_ADC_CTRL = 0x60;
static constexpr uint32_t CLK_ADC_DIV = 0x64;
static constexpr uint32_t CLK_ADC_SELECTED = 0x68;
static constexpr uint32_t CLK_RTC_CTRL = 0x6c;
static constexpr uint32_t CLK_RTC_DIV = 0x70;
static constexpr uint32_t CLK_RTC_SELECTED = 0x74;
static constexpr uint32_t CLK_SYS_RESUS_CTRL = 0x78;
static constexpr uint32_t CLK_SYS_RESUS_STATUS = 0x7c;

RPClocks::RPClocks(RP2040 &rp2040, const std::string &name) : BasePeripheral(rp2040, name) {}

uint32_t RPClocks::readUint32(uint32_t offset) {
  switch (offset) {
    case CLK_GPOUT0_CTRL:
      return gpout0Ctrl & 0b100110001110111100000;
    case CLK_GPOUT0_DIV:
      return gpout0Div;
    case CLK_GPOUT0_SELECTED:
      return 1;
    case CLK_GPOUT1_CTRL:
      return gpout1Ctrl & 0b100110001110111100000;
    case CLK_GPOUT1_DIV:
      return gpout1Div;
    case CLK_GPOUT1_SELECTED:
      return 1;
    case CLK_GPOUT2_CTRL:
      return gpout2Ctrl & 0b100110001110111100000;
    case CLK_GPOUT2_DIV:
      return gpout2Div;
    case CLK_GPOUT2_SELECTED:
      return 1;
    case CLK_GPOUT3_CTRL:
      return gpout3Ctrl & 0b100110001110111100000;
    case CLK_GPOUT3_DIV:
      return gpout3Div;
    case CLK_GPOUT3_SELECTED:
      return 1;
    case CLK_REF_CTRL:
      return refCtrl & 0b000001100011;
    case CLK_REF_DIV:
      return refDiv & 0x30;  // b8..9 = int divisor. no frac divisor present
    case CLK_REF_SELECTED:
      return 1u << (refCtrl & 0x03);
    case CLK_SYS_CTRL:
      return sysCtrl & 0b000011100001;
    case CLK_SYS_DIV:
      return sysDiv;
    case CLK_SYS_SELECTED:
      return 1u << (sysCtrl & 0x01);
    case CLK_PERI_CTRL:
      return periCtrl & 0b110011100000;
    case CLK_PERI_DIV:
      return periDiv;
    case CLK_PERI_SELECTED:
      return 1;
    case CLK_USB_CTRL:
      return usbCtrl & 0b100110000110011100000;
    case CLK_USB_DIV:
      return usbDiv;
    case CLK_USB_SELECTED:
      return 1;
    case CLK_ADC_CTRL:
      return adcCtrl & 0b100110000110011100000;
    case CLK_ADC_DIV:
      return adcDiv & 0x30;
    case CLK_ADC_SELECTED:
      return 1;
    case CLK_RTC_CTRL:
      return rtcCtrl & 0b100110000110011100000;
    case CLK_RTC_DIV:
      return rtcDiv & 0x30;
    case CLK_RTC_SELECTED:
      return 1;
    case CLK_SYS_RESUS_CTRL:
      return 0xff;
    case CLK_SYS_RESUS_STATUS:
      return 0; /* clock resus not implemented */
  }
  return BasePeripheral::readUint32(offset);
}

void RPClocks::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case CLK_GPOUT0_CTRL:
      gpout0Ctrl = value;
      break;
    case CLK_GPOUT0_DIV:
      gpout0Div = value;
      break;
    case CLK_GPOUT1_CTRL:
      gpout1Ctrl = value;
      break;
    case CLK_GPOUT1_DIV:
      gpout1Div = value;
      break;
    case CLK_GPOUT2_CTRL:
      gpout2Ctrl = value;
      break;
    case CLK_GPOUT2_DIV:
      gpout2Div = value;
      break;
    case CLK_GPOUT3_CTRL:
      gpout3Ctrl = value;
      break;
    case CLK_GPOUT3_DIV:
      gpout3Div = value;
      break;
    case CLK_REF_CTRL:
      refCtrl = value;
      break;
    case CLK_REF_DIV:
      refDiv = value;
      break;
    case CLK_SYS_CTRL:
      sysCtrl = value;
      break;
    case CLK_SYS_DIV:
      sysDiv = value;
      break;
    case CLK_PERI_CTRL:
      periCtrl = value;
      break;
    case CLK_PERI_DIV:
      periDiv = value;
      break;
    case CLK_USB_CTRL:
      usbCtrl = value;
      break;
    case CLK_USB_DIV:
      usbDiv = value;
      break;
    case CLK_ADC_CTRL:
      adcCtrl = value;
      break;
    case CLK_ADC_DIV:
      adcDiv = value;
      break;
    case CLK_RTC_CTRL:
      rtcCtrl = value;
      break;
    case CLK_RTC_DIV:
      rtcDiv = value;
      break;
    case CLK_SYS_RESUS_CTRL:
      return; /* clock resus not implemented */
    default:
      BasePeripheral::writeUint32(offset, value);
      break;
  }
}

}  // namespace rp2040js
