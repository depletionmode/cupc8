# ili9340 display — window is created only by display_init()

import opengl
import sdl2

var
    win: WindowPtr
    gl: GlContextPtr
    should_render: bool = false
    display_inited*: bool = false
    display_init_error*: string = ""

proc display_init*(): bool =
    if display_inited:
        return true
    if sdl2.init(INIT_VIDEO) != SdlSuccess:
        display_init_error = "sdl2.init: " & $getError()
        return false
    discard glSetAttribute(SDL_GL_DOUBLEBUFFER, 1)
    win = createWindow("CUPCake Simulator",
                       SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                       320, 240, SDL_WINDOW_OPENGL or SDL_WINDOW_SHOWN)
    if win.isNil:
        display_init_error = "createWindow: " & $getError()
        return false
    gl = glCreateContext(win)
    if gl.isNil:
        display_init_error = "glCreateContext: " & $getError()
        return false
    loadExtensions()
    glOrtho(0.0, 320.0, 240.0, 0.0, -1.0, 1.0)
    glClear(GL_COLOR_BUFFER_BIT)
    display_inited = true
    return true

proc display_render*() =
    if display_inited and should_render:
        glSwapWindow(win)
        should_render = false

var r : Rect
var state = "NOSTATE"
var rect_bitmask = 0
var is_color_high = true
var is_drawn = false
var dc: bool = false

proc display_set_dc*(b : int) =
    if b == 1:
        dc = true
    else:
        dc = false

proc display_transact*(b : int) =
    var v : cint = (cint)b
    if not dc:
        case v:
            of 0x2a:
                state = "CASET"
                rect_bitmask = 0
                r.x = 0
                r.w = 0
            of 0x2b:
                state = "PASET"
                rect_bitmask = 0
                r.y = 0
                r.h = 0
            of 0x2c:
                state = "RAMWR"
                is_drawn = false
            else:
                state = "NOSTATE"
    else:
        case state:
            of "NOSTATE":
                discard
            of "CASET":
                if (rect_bitmask and 1) == 0:
                    rect_bitmask = rect_bitmask or 1
                elif (rect_bitmask and 2) == 0:
                    r.x = v
                    rect_bitmask = rect_bitmask or 2
                elif (rect_bitmask and 4) == 0:
                    rect_bitmask = rect_bitmask or 4
                else:
                    r.w = (v - r.x) and 0xff
                    state = "NOSTATE"
            of "PASET":
                if (rect_bitmask and 1) == 0:
                    rect_bitmask = rect_bitmask or 1
                elif (rect_bitmask and 2) == 0:
                    r.y = v
                    rect_bitmask = rect_bitmask or 2
                elif (rect_bitmask and 4) == 0:
                    rect_bitmask = rect_bitmask or 4
                else:
                    r.h = (v - r.y) and 0xff
                    state = "NOSTATE"
            of "RAMWR":
                if not is_drawn:
                    if is_color_high:
                        is_color_high = false
                    else:
                        is_color_high = true
                        if display_inited:
                            var c : GLfloat = (GLfloat)v
                            glColor3f(c, c, c)
                            glRecti(r.x, r.y, r.w+r.x, r.h+r.y)
                        should_render = true
                        is_drawn = true
