# ili9340

import strutils
import opengl
import sdl2, sdl2/gfx
import sdl2/ttf

discard sdl2.init(INIT_EVERYTHING)

var
    win: WindowPtr
    render: RendererPtr
    gl: GlContextPtr
    should_render: bool = false
    glClear: pointer

loadExtensions()
discard glSetAttribute(SDL_GL_DOUBLEBUFFER, 1)
win = createWindow("CUPCake Simulator", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, 320, 240, SDL_WINDOW_OPENGL or SDL_WINDOW_SHOWN)
gl = glCreateContext(win)
glOrtho(0.0, 320.0, 240.0, 0.0, -1.0, 1.0)

glClear(GL_COLOR_BUFFER_BIT)

#when defined(emscripten):
#  render = createRenderer(win, -1, Renderer_Software)
#else:
#  render = createRenderer(win, -1, Renderer_Accelerated)
#
#
#render.setDrawColor 0,0,0,255 # black background
#render.clear
#render.present

proc display_speed*(speed: int) =
    var text_font = openFont("/usr/share/wine/fonts/tahoma.ttf", 50)
    var text_color = color(255, 40, 20, 100)
    var text_surface = renderTextSolid(text_font, "AAAAAAAAAAAAAAAAAAA", text_color)
    var text_texture = createTextureFromSurface(render, text_surface)
    var text_quad: Rect
    text_quad.x = 0
    text_quad.y = 0
    text_quad.w = 256
    text_quad.h = 256
    render.copy(text_texture, nil, addr text_quad)
    freeSurface(text_surface)
    destroyTexture(text_texture)

proc display_render*() = 
    if (should_render):
        glSwapWindow(win)
        #render.present
        #display_speed(10)
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

proc display_transact*(b) =
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
                # this doesn't correspond to actual ili9340 module
                # where there each pixel color is stored in memory
                # here we just draw the rectangle witht he first color
                # as kernel driver only supports single color per rectangle anyway
                if not is_drawn:
                    if is_color_high:
                        is_color_high = false
                    else:
                        is_color_high = true
                        var c : GLfloat = (GLfloat)v
                        glColor3f(c, c, c,)
                        glRecti(r.x, r.y, r.w+r.x, r.h+r.y)
                        should_render = true
                        is_drawn = true
                
            #of "COLOR_A":
            #    #var c : uint8 = (uint8)v
            #    #render.setDrawColor c,c,c,c
            #    var c : GLfloat = (GLfloat)v
            #    glColor3f(c, c, c)
            #    state = "COLOR_B"
            #of "COLOR_B":
            #    #render.fillRect r
            #    glRecti(r.x, r.y, r.w+r.x, r.h+r.y)
