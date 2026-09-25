/* The system card's USB identity: a composite device with two CDC serial
 * ports (doc/hardware/sysctl.md, doc/proposals/usb-console.md). The first is
 * cupc8.py's protocol port, the second the kernel's console. Each CDC
 * function has its interface association descriptor, so a PC binds a
 * serial driver to each (Linux: /dev/ttyACM0 and ttyACM1, interfaces 0 and 2). */
#include "pico/unique_id.h"
#include "tusb.h"

#define VID 0x1209              /* pid.codes open-source VID */
#define PID 0xC8C8

static const tusb_desc_device_t device = {
	.bLength = sizeof(tusb_desc_device_t), .bDescriptorType = TUSB_DESC_DEVICE, .bcdUSB = 0x0200,
	.bDeviceClass = TUSB_CLASS_MISC, .bDeviceSubClass = MISC_SUBCLASS_COMMON, .bDeviceProtocol = MISC_PROTOCOL_IAD,
	.bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE, .idVendor = VID, .idProduct = PID, .bcdDevice = 0x0210,
	.iManufacturer = 1, .iProduct = 2, .iSerialNumber = 3, .bNumConfigurations = 1,
};

uint8_t const *tud_descriptor_device_cb(void)
{
	return (uint8_t const *)&device;
}

enum { ITF_CDC, ITF_CDC_DATA, ITF_CONSOLE, ITF_CONSOLE_DATA, ITF_COUNT };
#define CONFIG_LEN (TUD_CONFIG_DESC_LEN + 2 * TUD_CDC_DESC_LEN)

static const uint8_t configuration[] = {
	TUD_CONFIG_DESCRIPTOR(1, ITF_COUNT, 0, CONFIG_LEN, 0x00, 100),
	/* interface, string, notification EP, its size, data OUT EP, data IN EP, their size */
	TUD_CDC_DESCRIPTOR(ITF_CDC, 4, 0x81, 8, 0x02, 0x82, 64),
	TUD_CDC_DESCRIPTOR(ITF_CONSOLE, 5, 0x83, 8, 0x04, 0x84, 64),
};

uint8_t const *tud_descriptor_configuration_cb(uint8_t index)
{
	(void)index;
	return configuration;
}

static uint16_t desc_str[33];

uint16_t const *tud_descriptor_string_cb(uint8_t index, uint16_t langid)
{
	(void)langid;
	char serial[2 * PICO_UNIQUE_BOARD_ID_SIZE_BYTES + 1];
	const char *s;
	switch (index) {
	case 0: desc_str[1] = 0x0409; desc_str[0] = (uint16_t)((TUSB_DESC_STRING << 8) | 4); return desc_str;
	case 1: s = "Kaplan Labs"; break;
	case 2: s = "CUPC/8 system card"; break;
	case 3: pico_get_unique_board_id_string(serial, sizeof serial); s = serial; break;
	case 4: s = "CUPC/8 sysctl"; break;
	case 5: s = "CUPC/8 console"; break;
	default: return NULL;
	}
	int n = 0;
	while (s[n] && n < 32) {
		desc_str[1 + n] = (uint8_t)s[n];
		n++;
	}
	desc_str[0] = (uint16_t)((TUSB_DESC_STRING << 8) | (2 * n + 2));
	return desc_str;
}
