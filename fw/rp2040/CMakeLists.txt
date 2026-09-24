# RP2040 firmware for the CUPC/8 cards: the real binaries that go into flash.
#   cmake -S fw/rp2040 -B build/rp2040 -G Ninja && ninja -C build/rp2040
# PICO_SDK_PATH defaults to the pinned SDK fetched by tools/fetch_sdks.sh.
cmake_minimum_required(VERSION 3.13)

if(NOT DEFINED PICO_SDK_PATH)
	set(PICO_SDK_PATH $ENV{HOME}/.local/share/cupc8-sdk/pico-sdk)
endif()
set(PICO_BOARD pico)
include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(cupc8_rp2040 C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

set(FW ${CMAKE_CURRENT_LIST_DIR}/..)
# strict warnings on our sources only (the SDKs have their own opinions).
# -Wstack-usage: the main stack is 2 KB and core 1's 1 KB, and an overflow
# silently overwrites SCRATCH_X code (an 8 KB local in gpu_run() did)
function(cupc8_strict)
	set_source_files_properties(${ARGN} PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Werror;-Wno-unused-parameter;-Wstack-usage=512")
endfunction()

# emulator acceptance: the dual-core features the card firmware relies on
add_executable(emu_selftest selftest/selftest.c)
cupc8_strict(selftest/selftest.c)
target_link_libraries(emu_selftest pico_stdlib pico_multicore)
pico_enable_stdio_uart(emu_selftest 1)

add_executable(emu_nested selftest/nested.c)
cupc8_strict(selftest/nested.c)
target_link_libraries(emu_nested pico_stdlib hardware_timer)
pico_enable_stdio_uart(emu_nested 1)

# the slot SPI slave shared by the RP2040 cards (each card's pins.h is on its
# include path)
add_library(slotspi INTERFACE)
target_sources(slotspi INTERFACE common/slotspi.c ${FW}/common/cardproto.c)
cupc8_strict(common/slotspi.c ${FW}/common/cardproto.c)
target_include_directories(slotspi INTERFACE common ${FW}/common)
pico_generate_pio_header(slotspi ${CMAKE_CURRENT_LIST_DIR}/common/slotspi.pio)
target_link_libraries(slotspi INTERFACE pico_stdlib hardware_pio hardware_dma)

# graphics card: PicoDVI (pinned by tools/fetch_sdks.sh)
set(PICODVI ${PICO_SDK_PATH}/../PicoDVI/software)
add_subdirectory(${PICODVI}/libdvi libdvi)
add_executable(gpu gpu/main.c ${FW}/gpu/core/gpu.c ${FW}/common/font8x8_cp437.c
	${PICODVI}/apps/colour_terminal/tmds_encode_font_2bpp.S)
cupc8_strict(gpu/main.c ${FW}/gpu/core/gpu.c)
target_include_directories(gpu PRIVATE ${FW}/gpu ${FW}/gpu/core ${PICODVI}/apps/colour_terminal)
# 5 TMDS buffers: PicoDVI frees one two lines after it is shown, so with 3
# core 1 could never work ahead of the beam (GFX lines alternate encode, copy)
target_compile_definitions(gpu PRIVATE DVI_VERTICAL_REPEAT=1 DVI_N_TMDS_BUFFERS=5 DVI_SYMBOLS_PER_WORD=2
	# core 1 only runs the scanline loop and the DVI IRQ; its stack shares
	# SCRATCH_X with PicoDVI's encode loops
	PICO_CORE1_STACK_SIZE=0x400)
target_link_libraries(gpu pico_stdlib pico_multicore libdvi slotspi)
# everything the scanline loop touches must not wait on flash
pico_set_binary_type(gpu copy_to_ram)

# IO card: TinyUSB host (HID keyboard) on the native port
add_executable(io io/main.c ${FW}/io/core/iocard.c)
cupc8_strict(io/main.c ${FW}/io/core/iocard.c)
target_include_directories(io PRIVATE io ${FW}/io ${FW}/io/core)
target_compile_definitions(io PRIVATE PICO_DEFAULT_UART_TX_PIN=16 PICO_DEFAULT_UART_RX_PIN=17)
target_link_libraries(io pico_stdlib tinyusb_host slotspi)
pico_enable_stdio_uart(io 1)

# system card: the sysctl core on the RP2040, USB CDC device
file(GLOB SYSCTL_CORE ${FW}/sysctl/core/*.c)
add_executable(sysctl sysctl/main.c sysctl/usb_descriptors.c ${SYSCTL_CORE})
cupc8_strict(sysctl/main.c ${SYSCTL_CORE})
target_include_directories(sysctl PRIVATE sysctl ${FW}/sysctl ${FW}/sysctl/core)
target_compile_definitions(sysctl PRIVATE PICO_DEFAULT_UART_TX_PIN=0 PICO_DEFAULT_UART_RX_PIN=1)
target_link_libraries(sysctl pico_stdlib pico_unique_id tinyusb_device hardware_spi hardware_i2c hardware_adc hardware_pio hardware_dma)
pico_generate_pio_header(sysctl ${CMAKE_CURRENT_LIST_DIR}/sysctl/uart.pio)

# e-ink graphics card: the graphics core with mode 2's buffer, the e-ink
# core, the panel on SPI1 (eink.elf: 5.83" GDEY0583T81; eink750.elf: 7.5")
foreach(_eink eink eink750)
	add_executable(${_eink} eink/main.c ${FW}/eink/core/eink.c ${FW}/eink/core/uc8179.c
		${FW}/gpu/core/gpu.c ${FW}/common/font8x8_cp437.c)
	target_include_directories(${_eink} PRIVATE ${FW}/eink ${FW}/eink/core ${FW}/gpu/core)
	target_compile_definitions(${_eink} PRIVATE GPU_GFX_BYTES=96000)
	target_link_libraries(${_eink} pico_stdlib hardware_spi slotspi)
endforeach()
cupc8_strict(eink/main.c ${FW}/eink/core/eink.c ${FW}/eink/core/uc8179.c)
target_compile_definitions(eink750 PRIVATE EINK_PANEL_750)
