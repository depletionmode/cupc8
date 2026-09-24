# Extract the B1 bootrom words from rp2040js demo/bootrom.ts, exactly as
# test/emu/rp2040emu.mjs does: from "bootromB1", the text between the first
# "[" and the first "]", every 0x... literal.
#   cmake -DIN=<bootrom.ts> -DOUT=<bootrom_b1.inc> -P extract_bootrom.cmake
file(READ "${IN}" src)
string(FIND "${src}" "bootromB1" pos)
if(pos EQUAL -1)
  message(FATAL_ERROR "no bootromB1 in ${IN}")
endif()
string(SUBSTRING "${src}" ${pos} -1 body)
string(FIND "${body}" "[" lb)
string(FIND "${body}" "]" rb)
math(EXPR start "${lb} + 1")
math(EXPR len "${rb} - ${start}")
string(SUBSTRING "${body}" ${start} ${len} arr)
string(REGEX MATCHALL "0[xX][0-9a-fA-F]+" words "${arr}")
list(LENGTH words n)
string(REPLACE ";" ",\n" joined "${words}")
file(WRITE "${OUT}" "// generated from ${IN} by extract_bootrom.cmake: ${n} words\n${joined}\n")
