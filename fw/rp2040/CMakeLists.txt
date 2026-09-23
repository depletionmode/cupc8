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
add_compile_options(-Wall -Wextra -Werror -Wno-unused-parameter)

# emulator acceptance: the dual-core features the card firmware relies on
add_executable(emu_selftest selftest/selftest.c)
target_link_libraries(emu_selftest pico_stdlib pico_multicore)
pico_enable_stdio_uart(emu_selftest 1)
