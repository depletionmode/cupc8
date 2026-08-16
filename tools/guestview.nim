## CUPC/8 framebuffer renderers for ANSI and Kitty-capable terminals.

import base64
import strutils
import times

import simdisplay
import tui

var
  displayZoom* = 1
  lastKittyX = -1
  lastKittyY = -1
  lastKittyWidth = -1
  lastKittyHeight = -1
  lastKittyFrame = 0.0
  kittyImageSent = false

proc terminalColor(pixel: uint32): uint32 =
  0x01000000'u32 or (pixel and 0x00ffffff'u32)

proc setDisplayZoom*(zoom: int) =
  displayZoom = max(1, min(8, zoom))

proc renderHalfBlock*(x, y, widthCells, heightCells: int) =
  if widthCells <= 0 or heightCells <= 0: return
  let
    sourceWidth = max(1, DispWidth div displayZoom)
    sourceHeight = max(1, DispHeight div displayZoom)
    sourceX = (DispWidth - sourceWidth) div 2
    sourceY = (DispHeight - sourceHeight) div 2
    pixelRows = heightCells * 2
  for row in 0..<heightCells:
    let
      topY = min(DispHeight - 1,
                 sourceY + (row * 2 * sourceHeight) div pixelRows)
      bottomY = min(DispHeight - 1,
                    sourceY + ((row * 2 + 1) * sourceHeight) div pixelRows)
    for column in 0..<widthCells:
      let sampleX = min(DispWidth - 1,
                        sourceX + (column * sourceWidth) div widthCells)
      putStr(x + column, y + row, "▀",
             terminalColor(display_pixel(sampleX, topY)),
             terminalColor(display_pixel(sampleX, bottomY)))
  display_dirty = false

proc kittyDeleteSequence(): string =
  "\e_Ga=d,d=i,i=1,q=2\e\\"

proc kittyPixels(): string =
  result = newStringOfCap(DispWidth * DispHeight * 3)
  for row in 0..<DispHeight:
    for column in 0..<DispWidth:
      let pixel = display_pixel(column, row)
      result.add(char((pixel shr 16) and 0xff))
      result.add(char((pixel shr 8) and 0xff))
      result.add(char(pixel and 0xff))

proc kittyTransmit(widthCells, heightCells: int): string =
  let encoded = base64.encode(kittyPixels())
  var offset = 0
  var first = true
  while offset < encoded.len:
    let
      finish = min(encoded.len, offset + 4096)
      more = finish < encoded.len
      chunk = encoded[offset..<finish]
    result.add("\e_G")
    if first:
      result.add("a=t,f=24,s=$1,v=$2,i=1,q=2," % [$DispWidth, $DispHeight])
      first = false
    result.add("m=" & (if more: "1;" else: "0;") & chunk & "\e\\")
    offset = finish
  result.add("\e_Ga=p,i=1,c=$1,r=$2,q=2\e\\" %
             [$widthCells, $heightCells])

proc renderKitty*(x, y, widthCells, heightCells: int; force = false): bool =
  if widthCells <= 0 or heightCells <= 0: return false
  fillRect(x, y, widthCells, heightCells)
  let terminalTouched = present() and rectTouched(x, y, widthCells, heightCells)
  let geometryChanged = x != lastKittyX or y != lastKittyY or
                        widthCells != lastKittyWidth or
                        heightCells != lastKittyHeight
  let now = epochTime()
  var sendPixels = force or display_dirty or geometryChanged or not kittyImageSent
  if sendPixels and not force and not geometryChanged and now - lastKittyFrame < 1.0 / 30.0:
    sendPixels = false
  if not sendPixels and not terminalTouched:
    return false

  var sequence = ""
  if sendPixels:
    sequence.add(kittyDeleteSequence())
    sequence.add(kittyTransmit(widthCells, heightCells))
    display_dirty = false
    kittyImageSent = true
    lastKittyFrame = now
  else:
    sequence.add("\e_Ga=p,i=1,c=$1,r=$2,q=2\e\\" %
                 [$widthCells, $heightCells])
  rawEmit(x, y, sequence)
  lastKittyX = x
  lastKittyY = y
  lastKittyWidth = widthCells
  lastKittyHeight = heightCells
  true

proc resetKittyImage*() =
  kittyImageSent = false
  lastKittyX = -1
  lastKittyY = -1
  lastKittyWidth = -1
  lastKittyHeight = -1

proc deleteKittyImage*() =
  if kittyImageSent:
    rawEmit(0, 0, kittyDeleteSequence())
  resetKittyImage()
