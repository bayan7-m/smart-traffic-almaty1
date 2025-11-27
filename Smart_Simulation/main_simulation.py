import random
import math
import time
import pygame
import sys
import os

# --- НАСТРОЙКИ ---
screenWidth = 1400
screenHeight = 800
screenSize = (screenWidth, screenHeight)

# Картинки и ресурсы
BACKGROUND_IMAGE = 'images/mod_int.png'

# Параметры светофоров
defaultGreen = 20
defaultRed = 150
defaultYellow = 5

signals = []
noOfSignals = 4
currentGreen = 0   
nextGreen = (currentGreen + 1) % noOfSignals
currentYellow = 0  

# Координаты (ВЗЯТО ИЗ ТВОЕГО ФАЙЛА simulation.py - НЕ МЕНЯТЬ!)
x = {'right':[0,0,0], 'down':[755,727,697], 'left':[1400,1400,1400], 'up':[602,627,657]}    
y = {'right':[348,370,398], 'down':[0,0,0], 'left':[498,466,436], 'up':[800,800,800]}

vehicles = {'right': {0:[], 1:[], 2:[], 'crossed':0}, 'down': {0:[], 1:[], 2:[], 'crossed':0}, 
            'left': {0:[], 1:[], 2:[], 'crossed':0}, 'up': {0:[], 1:[], 2:[], 'crossed':0}}

vehicleTypes = {0:'car', 1:'bus', 2:'truck', 3:'rickshaw', 4:'bike'}
directionNumbers = {0:'right', 1:'down', 2:'left', 3:'up'}

# Координаты стоп-линий
stopLines = {'right': 590, 'down': 330, 'left': 800, 'up': 535}
defaultStop = {'right': 580, 'down': 320, 'left': 810, 'up': 545}

# Координаты отрисовки светофоров
signalCoods = [(530,230),(810,230),(810,570),(530,570)]
signalTimerCoods = [(530,210),(810,210),(810,550),(530,550)]
vehicleCountCoods = [(480,210),(880,210),(880,550),(480,550)]

# Середина для поворотов
mid = {'right': {'x':705, 'y':445}, 'down': {'x':695, 'y':450}, 'left': {'x':695, 'y':425}, 'up': {'x':695, 'y':400}}
rotationAngle = 3
gap = 15
gap2 = 15

pygame.init()
simulation = pygame.sprite.Group()
font = pygame.font.Font(None, 30)

class TrafficSignal:
    def __init__(self, red, yellow, green):
        self.red = red
        self.yellow = yellow
        self.green = green
        self.signalText = ""
        self.timer = 0 # Таймер в секундах

class Vehicle(pygame.sprite.Sprite):
    def __init__(self, lane, vehicleClass, direction_number, direction, will_turn):
        pygame.sprite.Sprite.__init__(self)
        self.lane = lane
        self.vehicleClass = vehicleClass
        self.speed = 4 # Чуть быстрее для динамики
        self.direction_number = direction_number
        self.direction = direction
        self.x = x[direction][lane]
        self.y = y[direction][lane]
        self.crossed = 0
        self.willTurn = will_turn
        self.turned = 0
        self.rotateAngle = 0
        
        vehicles[direction][lane].append(self)
        self.index = len(vehicles[direction][lane]) - 1
        
        # Загрузка картинки (Обработка ошибок)
        path = f"images/{direction}/{vehicleClass}.png"
        try:
            self.originalImage = pygame.image.load(path)
            self.currentImage = pygame.image.load(path)
        except:
            print(f"ERROR: Could not load image {path}. Check your folder structure!")
            # Создаем красный квадрат если нет картинки, чтобы не крашилось
            self.originalImage = pygame.Surface((40, 20))
            self.originalImage.fill((255, 0, 0))
            self.currentImage = self.originalImage

        # Логика остановки (Взято из твоего кода)
        if(direction=='right'):
            if(len(vehicles[direction][lane])>1 and vehicles[direction][lane][self.index-1].crossed==0):
                self.stop = vehicles[direction][lane][self.index-1].stop - vehicles[direction][lane][self.index-1].currentImage.get_rect().width - gap
            else:
                self.stop = defaultStop[direction]
            temp = self.currentImage.get_rect().width + gap    
            x[direction][lane] -= temp
        elif(direction=='left'):
            if(len(vehicles[direction][lane])>1 and vehicles[direction][lane][self.index-1].crossed==0):
                self.stop = vehicles[direction][lane][self.index-1].stop + vehicles[direction][lane][self.index-1].currentImage.get_rect().width + gap
            else:
                self.stop = defaultStop[direction]
            temp = self.currentImage.get_rect().width + gap
            x[direction][lane] += temp
        elif(direction=='down'):
            if(len(vehicles[direction][lane])>1 and vehicles[direction][lane][self.index-1].crossed==0):
                self.stop = vehicles[direction][lane][self.index-1].stop - vehicles[direction][lane][self.index-1].currentImage.get_rect().height - gap
            else:
                self.stop = defaultStop[direction]
            temp = self.currentImage.get_rect().height + gap
            y[direction][lane] -= temp
        elif(direction=='up'):
            if(len(vehicles[direction][lane])>1 and vehicles[direction][lane][self.index-1].crossed==0):
                self.stop = vehicles[direction][lane][self.index-1].stop + vehicles[direction][lane][self.index-1].currentImage.get_rect().height + gap
            else:
                self.stop = defaultStop[direction]
            temp = self.currentImage.get_rect().height + gap
            y[direction][lane] += temp
            
        simulation.add(self)

    def render(self, screen):
        screen.blit(self.currentImage, (self.x, self.y))

    def move(self):
        # Сначала получаем актуальный список машин в моей полосе
        my_lane_vehicles = vehicles[self.direction][self.lane]
        
        # Если меня почему-то нет в списке (глюк удаления), ничего не делаем
        if self not in my_lane_vehicles:
            return

        # Узнаем мой РЕАЛЬНЫЙ текущий индекс (потому что передние машины могли удалиться)
        my_current_index = my_lane_vehicles.index(self)

        # --- ЛОГИКА ДВИЖЕНИЯ ---
        
        # 1. НАПРАВЛЕНИЕ: ВПРАВО (RIGHT)
        if(self.direction=='right'):
            # Проверка стоп-линии
            if(self.crossed==0 and self.x+self.currentImage.get_rect().width>stopLines[self.direction]):
                self.crossed = 1
                vehicles[self.direction]['crossed'] += 1
            
            can_move = True
            # Если еще не пересек -> проверяем светофор
            if self.crossed == 0:
                if (self.x + self.currentImage.get_rect().width > self.stop):
                     if currentGreen != 0 and currentGreen != -1: 
                         can_move = False
            
            # Проверка лидера (машины спереди) - ИСПОЛЬЗУЕМ НОВЫЙ ИНДЕКС
            if my_current_index > 0:
                leader = my_lane_vehicles[my_current_index - 1]
                if self.x + self.currentImage.get_rect().width > leader.x - gap2:
                    can_move = False

            # Поворот
            if(self.willTurn==1):
                if(self.crossed==0 or self.x+self.currentImage.get_rect().width<mid[self.direction]['x']):
                    if can_move: self.x += self.speed
                else:
                    if(self.turned==0):
                        self.rotateAngle += rotationAngle
                        self.currentImage = pygame.transform.rotate(self.originalImage, -self.rotateAngle)
                        self.x += 2
                        self.y += 1.8
                        if(self.rotateAngle==90): self.turned = 1
                    else:
                        self.y += self.speed
            else:
                if can_move: self.x += self.speed

        # 2. НАПРАВЛЕНИЕ: ВНИЗ (DOWN)
        elif(self.direction=='down'):
            if(self.crossed==0 and self.y+self.currentImage.get_rect().height>stopLines[self.direction]):
                self.crossed = 1
                vehicles[self.direction]['crossed'] += 1
            
            can_move = True
            if self.crossed == 0:
                if (self.y + self.currentImage.get_rect().height > self.stop):
                     if currentGreen != 1: can_move = False
            
            if my_current_index > 0:
                leader = my_lane_vehicles[my_current_index - 1]
                if self.y + self.currentImage.get_rect().height > leader.y - gap2: can_move = False

            if(self.willTurn==1):
                if(self.crossed==0 or self.y+self.currentImage.get_rect().height<mid[self.direction]['y']):
                    if can_move: self.y += self.speed
                else:   
                    if(self.turned==0):
                        self.rotateAngle += rotationAngle
                        self.currentImage = pygame.transform.rotate(self.originalImage, -self.rotateAngle)
                        self.x -= 2.5
                        self.y += 2
                        if(self.rotateAngle==90): self.turned = 1
                    else:
                        self.x -= self.speed
            else: 
                if can_move: self.y += self.speed

        # 3. НАПРАВЛЕНИЕ: ВЛЕВО (LEFT)
        elif(self.direction=='left'):
            if(self.crossed==0 and self.x<stopLines[self.direction]):
                self.crossed = 1
                vehicles[self.direction]['crossed'] += 1
            
            can_move = True
            if self.crossed == 0:
                if (self.x < self.stop):
                     if currentGreen != 2: can_move = False
            
            if my_current_index > 0:
                leader = my_lane_vehicles[my_current_index - 1]
                if self.x < leader.x + leader.currentImage.get_rect().width + gap2: can_move = False

            if(self.willTurn==1):
                if(self.crossed==0 or self.x>mid[self.direction]['x']):
                    if can_move: self.x -= self.speed
                else: 
                    if(self.turned==0):
                        self.rotateAngle += rotationAngle
                        self.currentImage = pygame.transform.rotate(self.originalImage, -self.rotateAngle)
                        self.x -= 1.8
                        self.y -= 2.5
                        if(self.rotateAngle==90): self.turned = 1
                    else:
                        self.y -= self.speed
            else: 
                if can_move: self.x -= self.speed

        # 4. НАПРАВЛЕНИЕ: ВВЕРХ (UP)
        elif(self.direction=='up'):
            if(self.crossed==0 and self.y<stopLines[self.direction]):
                self.crossed = 1
                vehicles[self.direction]['crossed'] += 1
            
            can_move = True
            if self.crossed == 0:
                if (self.y < self.stop):
                     if currentGreen != 3: can_move = False
            
            if my_current_index > 0:
                leader = my_lane_vehicles[my_current_index - 1]
                if self.y < leader.y + leader.currentImage.get_rect().height + gap2: can_move = False

            if(self.willTurn==1):
                if(self.crossed==0 or self.y>mid[self.direction]['y']):
                    if can_move: self.y -= self.speed
                else:   
                    if(self.turned==0):
                        self.rotateAngle += rotationAngle
                        self.currentImage = pygame.transform.rotate(self.originalImage, -self.rotateAngle)
                        self.x += 1
                        self.y -= 1
                        if(self.rotateAngle==90): self.turned = 1
                    else:
                        self.x += self.speed
            else: 
                if can_move: self.y -= self.speed

# Инициализация
def initialize():
    # Создаем 4 светофора
    for i in range(4):
        signals.append(TrafficSignal(defaultRed, defaultYellow, defaultGreen))
    
    # Первый зеленый
    signals[currentGreen].red = 0
    signals[currentGreen].timer = defaultGreen

def run_simulation():
    global currentGreen, currentYellow, nextGreen

    # Загрузка изображений (КЭШИРОВАНИЕ)
    background = pygame.image.load(BACKGROUND_IMAGE)
    
    # Светофоры
    img_red = pygame.image.load('images/signals/red.png')
    img_yellow = pygame.image.load('images/signals/yellow.png')
    img_green = pygame.image.load('images/signals/green.png')

    screen = pygame.display.set_mode(screenSize)
    pygame.display.set_caption("AI TRAFFIC CONTROL SIMULATION")
    
    clock = pygame.time.Clock()
    initialize()
    
    # Таймеры
    vehicle_spawn_timer = 0
    traffic_light_timer = time.time()
    
    running = True
    while running:
        dt = clock.tick(60) / 1000.0 # Delta time in seconds
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # --- ЛОГИКА СВЕТОФОРА (AI BRAIN) ---
        # Каждую секунду обновляем таймер
        if time.time() - traffic_light_timer >= 1.0:
            traffic_light_timer = time.time()
            
            if currentYellow == 0: # Сейчас горит ЗЕЛЕНЫЙ
                signals[currentGreen].timer -= 1
                if signals[currentGreen].timer <= 0:
                    # Время вышло, включаем желтый
                    currentYellow = 1
                    signals[currentGreen].timer = defaultYellow
            else: # Сейчас горит ЖЕЛТЫЙ
                signals[currentGreen].timer -= 1
                if signals[currentGreen].timer <= 0:
                    # Желтый кончился, переключаем на следующий
                    currentYellow = 0
                    
                    # === AI LOGIC: ВЫБОР СЛЕДУЮЩЕГО ===
                    # Считаем машины в очередях
                    queues = [0, 0, 0, 0] # Right, Down, Left, Up
                    for i in range(4):
                        d = directionNumbers[i]
                        # Считаем только тех, кто еще не переехал и не повернул
                        count = sum(1 for lanes in vehicles[d].values() if isinstance(lanes, list) for v in lanes if v.crossed == 0)
                        queues[i] = count
                    
                    # Выбираем направление с самой большой очередью
                    max_queue = max(queues)
                    if max_queue > 0:
                        # Если есть очередь, даем зеленый ей
                        # Но не тому же самому, если он только что горел (чтобы не вечно горел)
                        potential_next = queues.index(max_queue)
                        if potential_next == currentGreen:
                             # Если та же самая, ищем вторую по величине или просто следующую
                             nextGreen = (currentGreen + 1) % 4
                        else:
                            nextGreen = potential_next
                    else:
                        # Если пусто, идем по кругу
                        nextGreen = (currentGreen + 1) % 4
                    
                    # Адаптивное время: 2 сек на машину + база, но не более 40 сек
                    new_time = max(defaultGreen, min(40, max_queue * 2 + 5))
                    
                    currentGreen = nextGreen
                    signals[currentGreen].timer = int(new_time)

        # --- СПАВН МАШИН ---
        vehicle_spawn_timer += dt
        if vehicle_spawn_timer > 0.8: # Каждые 0.8 сек пытаемся создать машину
            vehicle_spawn_timer = 0
            if random.randint(0, 10) < 8: # 80% шанс
                vehicle_type = random.randint(0,4)
                lane_number = random.randint(1,2) if vehicle_type != 4 else 0
                
                will_turn = 0
                if lane_number == 2:
                    will_turn = 1 if random.randint(0,1) == 0 else 0
                
                temp = random.randint(0,999)
                direction_number = 0
                # Распределение потока
                a = [400,800,900,1000]
                if temp<a[0]: direction_number = 0
                elif temp<a[1]: direction_number = 1
                elif temp<a[2]: direction_number = 2
                elif temp<a[3]: direction_number = 3
                
                Vehicle(lane_number, vehicleTypes[vehicle_type], direction_number, directionNumbers[direction_number], will_turn)

        # --- ОТРИСОВКА ---
        screen.blit(background,(0,0))
        
        # Светофоры
        for i in range(noOfSignals):
            state_img = img_red
            text_val = "---"
            color = (255, 0, 0)
            
            if i == currentGreen:
                if currentYellow == 1:
                    state_img = img_yellow
                    text_val = str(signals[i].timer)
                    color = (255, 255, 0)
                else:
                    state_img = img_green
                    text_val = str(signals[i].timer)
                    color = (0, 255, 0)
            
            screen.blit(state_img, signalCoods[i])
            
            # Таймер
            text_surf = font.render(text_val, True, (255, 255, 255))
            screen.blit(text_surf, signalTimerCoods[i])
            
            # Кол-во машин (Dashboard)
            d = directionNumbers[i]
            q_count = sum(1 for lanes in vehicles[d].values() if isinstance(lanes, list) for v in lanes if v.crossed == 0)
            
            q_surf = font.render(f"Q: {q_count}", True, (255, 255, 255))
            screen.blit(q_surf, vehicleCountCoods[i])

        # Машины
        for vehicle in simulation:
            vehicle.render(screen)
            vehicle.move()
            # Удаление уехавших машин для очистки памяти
            if (vehicle.x < -100 or vehicle.x > screenWidth + 100 or 
                vehicle.y < -100 or vehicle.y > screenHeight + 100):
                vehicle.kill()
                # Удаляем из списка vehicles тоже, чтобы не было утечки памяти
                if vehicle in vehicles[vehicle.direction][vehicle.lane]:
                     vehicles[vehicle.direction][vehicle.lane].remove(vehicle)

        # AI Status Overlay
        pygame.draw.rect(screen, (0,0,0), (10, 10, 300, 100))
        pygame.draw.rect(screen, (0,255,0), (10, 10, 300, 100), 2)
        screen.blit(font.render(f"AI STATUS: ACTIVE", True, (0,255,0)), (20, 20))
        screen.blit(font.render(f"Logic: Adaptive Queue", True, (200,200,200)), (20, 50))
        
        if currentYellow == 0:
            d_name = directionNumbers[currentGreen].upper()
            screen.blit(font.render(f"Priority: {d_name}", True, (255,255,0)), (20, 80))
        else:
            screen.blit(font.render(f"Calculating...", True, (255,0,0)), (20, 80))

        pygame.display.update()

    pygame.quit()
    sys.exit()

if __name__ == '__main__':
    run_simulation()