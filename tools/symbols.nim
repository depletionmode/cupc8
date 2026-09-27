## CUPC/8 assembler map and source-file support.

import algorithm
import os
import strutils
import tables

type
  SourceLoc* = tuple[file: string, line: int]
  DataSym* = tuple[a, size: int, name: string]
  SymTab* = object
    loaded*: bool
    codeBase*, entry*: int
    byName*: Table[string, int]
    byAddr*: Table[int, string]
    sortedSyms*: seq[(int, string)]
    insAddrs*: seq[int]
    lineFor*: Table[int, SourceLoc]
    addrFor*: Table[(string, int), int]
    dataSyms*: seq[DataSym]
    srcDir*: string
    sourceCache: Table[string, seq[string]]

proc emptySymTab(): SymTab =
  result.codeBase = 0x1000
  result.entry = -1
  result.byName = initTable[string, int]()
  result.byAddr = initTable[int, string]()
  result.lineFor = initTable[int, SourceLoc]()
  result.addrFor = initTable[(string, int), int]()
  result.sourceCache = initTable[string, seq[string]]()

proc parseAddress(value: string): int =
  if value.startsWith("0x") or value.startsWith("0X"):
    parseHexInt(value[2..^1])
  elif value.startsWith("$"):
    parseHexInt(value[1..^1])
  else:
    parseInt(value)

proc loadMap*(path: string; srcDir = ""): SymTab =
  ## The assembler's map; sources are looked for beside it, or in srcDir
  ## (a kernel built elsewhere than kernel/)
  result = emptySymTab()
  result.srcDir = if srcDir.len > 0: srcDir else: path.absolutePath.parentDir
  if not fileExists(path):
    return

  let lines = readFile(path).splitLines()
  if lines.len == 0 or lines[0].strip != "CUPC8MAP 1":
    raise newException(ValueError, "unsupported CUPC/8 map: " & path)

  for index in 1..<lines.len:
    let fields = lines[index].splitWhitespace()
    if fields.len == 0:
      continue
    try:
      case fields[0]
      of "sym":
        if fields.len != 3: raise newException(ValueError, "bad sym record")
        let address = parseAddress(fields[1]) and 0xffff
        result.byName[fields[2]] = address
        if not result.byAddr.hasKey(address):
          result.byAddr[address] = fields[2]
        result.sortedSyms.add((address, fields[2]))
      of "line":
        if fields.len != 4: raise newException(ValueError, "bad line record")
        let
          address = parseAddress(fields[1]) and 0xffff
          source = fields[2].extractFilename
          line = parseInt(fields[3])
        result.lineFor[address] = (source, line)
        if not result.addrFor.hasKey((source, line)):
          result.addrFor[(source, line)] = address
        result.insAddrs.add(address)
      of "data", "bss":
        if fields.len != 4: raise newException(ValueError, "bad data record")
        let
          address = parseAddress(fields[1]) and 0xffff
          name = fields[3]
        result.dataSyms.add((address, parseInt(fields[2]), name))
        result.byName[name] = address
        if not result.byAddr.hasKey(address): result.byAddr[address] = name
        result.sortedSyms.add((address, name))
      of "base":
        if fields.len < 2: raise newException(ValueError, "bad base record")
        result.codeBase = parseAddress(fields[1]) and 0xffff
      of "entry":
        if fields.len < 2: raise newException(ValueError, "bad entry record")
        result.entry = parseAddress(fields[1]) and 0xffff
      else:
        discard
    except ValueError as error:
      raise newException(ValueError,
        "$1:$2: $3" % [path, $(index + 1), error.msg])

  result.sortedSyms.sort(proc(a, b: (int, string)): int =
    result = cmp(a[0], b[0])
    if result == 0: result = cmp(a[1], b[1]))
  result.insAddrs.sort()
  var uniqueAddrs: seq[int]
  for address in result.insAddrs:
    if uniqueAddrs.len == 0 or uniqueAddrs[^1] != address:
      uniqueAddrs.add(address)
  result.insAddrs = uniqueAddrs
  result.dataSyms.sort(proc(a, b: DataSym): int = cmp(a.a, b.a))
  result.loaded = true

proc symbolize*(t: SymTab; a: int): string =
  let address = a and 0xffff
  if t.byAddr.hasKey(address):
    return t.byAddr[address]
  var lo = 0
  var hi = t.sortedSyms.len
  while lo < hi:
    let mid = (lo + hi) div 2
    if t.sortedSyms[mid][0] <= address: lo = mid + 1
    else: hi = mid
  if lo == 0:
    return "$" & toHex(address, 4)
  let symbol = t.sortedSyms[lo - 1]
  symbol[1] & "+0x" & toHex(address - symbol[0], 1)

proc resolve*(t: SymTab; token: string): int =
  let value = token.strip
  if value.len == 0:
    return -1
  if t.byName.hasKey(value):
    return t.byName[value]
  try:
    if value.startsWith("$"):
      return parseHexInt(value[1..^1]) and 0xffff
    if value.startsWith("0x") or value.startsWith("0X"):
      return parseHexInt(value[2..^1]) and 0xffff
    return parseInt(value) and 0xffff
  except ValueError:
    return -1

proc prevInsAddr*(t: SymTab; a, n: int): int =
  if n <= 0:
    return a and 0xffff
  if t.insAddrs.len == 0:
    return max(0, a - n)
  let address = a and 0xffff
  var lo = 0
  var hi = t.insAddrs.len
  while lo < hi:
    let mid = (lo + hi) div 2
    if t.insAddrs[mid] < address: lo = mid + 1
    else: hi = mid
  if lo == 0:
    return min(address, t.codeBase)
  max(0, t.insAddrs[max(0, lo - n)])

proc sourceLines*(t: var SymTab; file: string): seq[string] =
  let name = file.extractFilename
  if t.sourceCache.hasKey(name):
    return t.sourceCache[name]
  let path = t.srcDir / name
  if fileExists(path):
    result = readFile(path).splitLines()
  else:
    result = @[]
  t.sourceCache[name] = result
