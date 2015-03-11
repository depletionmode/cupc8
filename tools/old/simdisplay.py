import pygame

WHITE = (255,255,255,255)

screen = None
screen = pygame.display.set_mode((256, 256))
pygame.display.set_caption('Cupcake Simulator')
pygame.mouse.set_visible(0)
def init():
    pass

def draw_pixel(x, y):
    screen.set_at((x,y),WHITE)
    pygame.display.update()

def fill(x0, x1, y0, y1):
    #print(x0,x1,y0,y1)
    #screen.set_at((x0,y0),WHITE)
    screen.fill(WHITE, ((x0,y0),(x1-x0,y1-y0)))
    pygame.display.update()

state = ''
x0 = None
x1 = None
y0 = None
y1 = None
color = None
def transact(v):
    global state
    #print(state)
    global x0, x1
    global y0, y1
    global color
    if state == 'CASET':
        if x0 == None: x0 = v
        elif x1 == None: x1 = v
        if x0 != None and x1 != None: state = None
        return
    elif state == 'RASET':
        if y0 == None: y0 = v
        elif y1 == None: y1 = v
        if y0 != None and y1 != None: state = None
        return
    elif state == 'COLOR_A':
        state = 'COLOR_B'
        return
    elif state == 'COLOR_B':
        state = None
        return
        
    if v == 42: #CASET
        state = 'CASET'
        x0 = None
        x1 = None
    elif v == 43: #RASET
        state = 'RASET'
        y0 = None
        y1 = None
    elif v == 44: #RAMWR
        state = 'COLOR_A'
        fill(x0, x1, y0, y1)
