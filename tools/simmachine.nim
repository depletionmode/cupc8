# The Milestone 1 machine as the simulator CLI (sim.nim) and its tests
# (simtest.nim) set it up: slot card kinds by name, the ROM image (boot ROM
# + kernel, built as the hardware's ROM chip holds it), the console's text,
# and a blank FAT image for the storage card.

import os
import osproc
import strutils
import simcards

const
  simRoot = currentSourcePath().parentDir.parentDir
  romDir = simRoot / "build" / "rom"

  CardKindNames* = "hdmi, eink, eink750, io, storage, wifi, empty"

proc cardKind*(name: string): int =
  ## Slot card kind by name (the native emulator's names), 0 = empty slot,
  ## -1 = unknown.
  case name.strip.toLowerAscii
  of "hdmi": CardGpu
  of "eink": CardEink
  of "eink750": CardEink750
  of "io": CardIo
  of "storage": CardStorage
  of "wifi": CardWifi
  of "empty", "none", "-": 0
  else: -1

proc run(cmd, what: string) =
  let r = execCmdEx(cmd)
  if r.exitCode != 0:
    raise newException(IOError, what & ": " & r.output)

proc buildBootRom*(): string =
  ## Assemble rom/boot.s into build/rom/boot.bin.
  createDir(romDir)
  result = romDir / "boot.bin"
  run("python3 " & quoteShell(simRoot / "tools" / "as.py") & " " &
      quoteShell(simRoot / "rom" / "boot.s") & " " & quoteShell(result) &
      " 0xe000,0xe600,0x0f00", "boot ROM")

proc makeRom*(boot, kernel, dest: string): string =
  ## The ROM image: the boot ROM and the kernel with its header (tools/mkrom.py).
  createDir(dest.parentDir)
  run("python3 " & quoteShell(simRoot / "tools" / "mkrom.py") & " " &
      quoteShell(boot) & " " & quoteShell(kernel) & " -o " & quoteShell(dest), "mkrom")
  dest

proc buildKernelRom*(): string =
  ## Assemble the real kernel (kernel/assemble.sh) and the boot ROM into
  ## build/rom/kernel.rom.
  run("cd " & quoteShell(simRoot / "kernel") & " && bash assemble.sh", "kernel build")
  makeRom(buildBootRom(), simRoot / "kernel" / "kernel.o", romDir / "kernel.rom")

proc screenLines*(g: SimCard): seq[string] =
  ## The graphics card's text screen, one string per row, trailing blanks cut.
  for row in 0..29:
    var line = ""
    for col in 0..79:
      let ch = int(simcard_gpu_cell(g, cint(col), cint(row))) and 0xff
      line.add(if ch == 0: ' ' else: char(ch))
    result.add(line.strip(leading = false))

proc makeFatImage*(path: string; kb = 32768) =
  ## A blank FAT volume, as a PC formats a card (mkfs.fat, from dosfstools).
  if findExe("mkfs.fat").len == 0:
    raise newException(IOError, "mkfs.fat (dosfstools) is not installed; make the image with " &
                       "`mkfs.fat -C " & path & " 32768` or tools/fatcheck.py blank")
  if path.parentDir.len > 0:
    createDir(path.parentDir)
  run("mkfs.fat -C " & quoteShell(path) & " " & $kb, "mkfs.fat")
