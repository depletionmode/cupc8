# Slot cards for the simulator: the real firmware cores (fw/*/core), compiled
# in through the C shim fw/sim/simcards.c.

import os

const fwDir = currentSourcePath().parentDir & "/../fw"

{.passC: "-I" & fwDir & "/common -I" & fwDir & "/gpu/core -I" & fwDir & "/io/core -I" & fwDir & "/wifi/core -I" & fwDir & "/wifi/host -I" & fwDir & "/storage/core -I" & fwDir & "/storage/host -I" & fwDir & "/third_party/fatfs -I" & fwDir & "/sim -I" & fwDir & "/eink/core -I" & fwDir & "/test".}
{.passC: "-D_GNU_SOURCE".}
# the e-ink card's mode 2 shares the GFX buffer: every card here is built so
{.passC: "-DGPU_GFX_BYTES=96000".}
{.compile: fwDir & "/common/cardproto.c".}
{.compile: fwDir & "/common/font8x8_cp437.c".}
{.compile: fwDir & "/gpu/core/gpu.c".}
{.compile: fwDir & "/eink/core/eink.c".}
{.compile: fwDir & "/eink/core/uc8179.c".}
{.compile: fwDir & "/test/epdmodel.c".}
{.compile: fwDir & "/io/core/iocard.c".}
{.compile: fwDir & "/wifi/core/wifi.c".}
{.compile: fwDir & "/wifi/host/netposix.c".}
{.compile: fwDir & "/storage/core/storage.c".}
{.compile: fwDir & "/storage/core/diskio.c".}
{.compile: fwDir & "/storage/host/imgdisk.c".}
{.compile: fwDir & "/third_party/fatfs/ff.c".}
{.compile: fwDir & "/sim/simcards.c".}

const
  CardGpu* = 1
  CardIo* = 2
  CardWifi* = 3
  CardStorage* = 4
  CardEink* = 0x101      ## the e-ink graphics card (type $01 on the slot), 5.83" panel
  CardEink750* = 0x102
  GpuOutW* = 640
  GpuOutH* = 480

type SimCard* = distinct pointer

proc simcard_new*(kind: cint): SimCard {.importc, cdecl.}
proc simcard_free*(c: SimCard) {.importc, cdecl.}
proc simcard_type*(c: SimCard): cint {.importc, cdecl.}
proc simcard_select*(c: SimCard, selected: cint) {.importc, cdecl.}
proc simcard_miso*(c: SimCard): uint8 {.importc, cdecl.}
proc simcard_mosi*(c: SimCard, b: uint8) {.importc, cdecl.}
proc simcard_irq*(c: SimCard): cint {.importc, cdecl.}
proc simcard_tick*(c: SimCard, nowMs: uint32) {.importc, cdecl.}
proc simcard_out_w*(c: SimCard): cint {.importc, cdecl.}
proc simcard_out_h*(c: SimCard): cint {.importc, cdecl.}
proc simcard_render*(c: SimCard, rgb: ptr uint32) {.importc, cdecl.}
proc simcard_gpu_cell*(c: SimCard, x, y: cint): cint {.importc, cdecl.}
proc simcard_gpu_pixel*(c: SimCard, x, y: cint): cint {.importc, cdecl.}
proc simcard_gpu_mode*(c: SimCard): cint {.importc, cdecl.}
proc simcard_eink_refreshes*(c: SimCard, waveform: cint): cint {.importc, cdecl.}
proc simcard_eink_errors*(c: SimCard): cint {.importc, cdecl.}
proc simcard_eink_pixel2*(c: SimCard, x, y: cint): cint {.importc, cdecl.}
proc simcard_gpu_errors*(c: SimCard): cint {.importc, cdecl.}
proc simcard_gpu_hold*(c: SimCard, on: cint) {.importc, cdecl.}
proc simcard_type_ascii*(c: SimCard, ch: uint8, nowMs: uint32) {.importc, cdecl.}
proc simcard_hid*(c: SimCard, report: ptr uint8, nowMs: uint32) {.importc, cdecl.}

proc simcard_storage_image*(c: SimCard, path: cstring, wp: cint): cint {.importc, cdecl.}
proc simcard_storage_latency*(c: SimCard, ms: uint32) {.importc, cdecl.}
proc simcard_storage_status*(c: SimCard): cint {.importc, cdecl.}

proc isNil*(c: SimCard): bool = pointer(c).isNil
