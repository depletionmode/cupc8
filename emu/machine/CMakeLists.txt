cmake_minimum_required(VERSION 3.16)
project(cupc8machine LANGUAGES C CXX)

# The native whole-machine emulator (doc/milestone-1.md, "Emulator speed"):
#   tools/emu_build.sh                       # the Verilated main board (build/emu/obj_dir)
#   cmake -G Ninja -S emu/machine -B build/emu-machine && ninja -C build/emu-machine
# builds build/emu-machine/machine.node (test/emu/machinenative.mjs) and
# build/emu-machine/machinerun (speed and determinism runs).

get_filename_component(CUPC8_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
set(EMU_OBJ_DIR "${CUPC8_ROOT}/build/emu/obj_dir" CACHE PATH "Verilator output for machine_core (tools/emu_build.sh)")
if(NOT EXISTS "${EMU_OBJ_DIR}/Vmachine_core__ALL.a")
  message(FATAL_ERROR "${EMU_OBJ_DIR}/Vmachine_core__ALL.a not found: run tools/emu_build.sh first")
endif()
# the Verilator kit that generated obj_dir (its headers must match the model)
file(STRINGS "${EMU_OBJ_DIR}/Vmachine_core.mk" _vroot REGEX "^VERILATOR_ROOT = ")
string(REGEX REPLACE "^VERILATOR_ROOT = " "" VERILATOR_ROOT "${_vroot}")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${EMU_OBJ_DIR}/Vmachine_core.mk")
find_program(NODE node REQUIRED)
get_filename_component(_node_bin "${NODE}" DIRECTORY)
set(NODE_INCLUDE "${_node_bin}/../include/node" CACHE PATH "Node's headers (node_api.h)")

set(CMAKE_CXX_STANDARD 20)                # emu/rp2040 keeps its own C++17
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)   # the RP2040 library goes into a Node addon
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
# Link-time optimisation and -O3 (no fast-math: the port's float time
# arithmetic is exact JS semantics, and rp2040run built this way gives
# byte-identical --trace-every traces on the GPU, IO and system card images).
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION ON)
# the RP2040 port, untouched, as a PIC static library of this build
add_subdirectory("${CUPC8_ROOT}/emu/rp2040" rp2040 EXCLUDE_FROM_ALL)
target_compile_options(rp2040emu PRIVATE -O3)

# the B1 bootrom, extracted from rp2040js as emu/rp2040 does
set(BOOTROM_INC "${CMAKE_CURRENT_BINARY_DIR}/generated/bootrom_b1.inc")
add_custom_command(
  OUTPUT "${BOOTROM_INC}"
  COMMAND ${CMAKE_COMMAND} -DIN=${RP2040JS_DIR}/demo/bootrom.ts -DOUT=${BOOTROM_INC}
          -P "${CUPC8_ROOT}/emu/rp2040/cmake/extract_bootrom.cmake"
  DEPENDS "${RP2040JS_DIR}/demo/bootrom.ts" "${CUPC8_ROOT}/emu/rp2040/cmake/extract_bootrom.cmake"
  VERBATIM)

add_library(machine STATIC machine.cpp emu.cpp "${CUPC8_ROOT}/fw/test/sysmodels.c" "${BOOTROM_INC}")
target_include_directories(machine PUBLIC
  "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/generated" "${CUPC8_ROOT}/soc/emu" "${CUPC8_ROOT}/fw/test")
target_include_directories(machine SYSTEM PUBLIC
  "${EMU_OBJ_DIR}" "${VERILATOR_ROOT}/include" "${VERILATOR_ROOT}/include/vltstd")
target_compile_options(machine PRIVATE -O3 $<$<COMPILE_LANGUAGE:CXX>:-Wall -Wextra -Wno-unused-parameter>)
target_link_libraries(machine PUBLIC rp2040emu
  "${EMU_OBJ_DIR}/Vmachine_core__ALL.a" "${EMU_OBJ_DIR}/verilated.o" "${EMU_OBJ_DIR}/verilated_threads.o" pthread)

add_executable(machinerun machinerun.cpp)
target_compile_options(machinerun PRIVATE -O2 -Wall -Wextra)
target_link_libraries(machinerun PRIVATE machine)

add_library(machine_node MODULE addon.cpp)
set_target_properties(machine_node PROPERTIES PREFIX "" SUFFIX ".node" OUTPUT_NAME machine)
target_include_directories(machine_node PRIVATE "${NODE_INCLUDE}")
target_compile_options(machine_node PRIVATE -O2 -Wall -Wextra)
target_link_libraries(machine_node PRIVATE machine)
