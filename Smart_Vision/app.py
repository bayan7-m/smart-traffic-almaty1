import sys
import os
import streamlit as st
import cv2
import numpy as np
import pickle
import time
import math
import gc
from ultralytics import YOLO
from tracker import Tracker 
from smart_db import traffic_db # <--- импорт нашей базы данных
import cvzone

# конфиг streamlit
st.set_page_config(page_title="SmartTraffic Almaty", page_icon="🚦", layout="wide")

# стили css, чтобы стримлит не выглядел как говно
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    div[data-testid="metric-container"] {
        background-color: #1c1e24;
        border: 1px solid #2d303a;
        padding: 10px;
        border-radius: 8px;
        color: #fff;
    }
    h1, h2, h3 { font-family: 'Segoe UI', sans-serif; color: #e0e0e0; }
</style>
""", unsafe_allow_html=True)

# константы
VIDEO_PATH = os.path.join(os.path.dirname(__file__), 'video1.mp4') 
ZONES_FILE = 'traffic_zones.pkl'
FRAME_WIDTH, FRAME_HEIGHT = 1020, 600

# cO2: взято с потолка, типа сколько кг за секунду простоя
CO2_PER_CAR_SECOND = 0.00005 

# веса для приоритета. чем больше, тем быстрее даем зеленый
VEHICLE_WEIGHTS = {
    0: 0,   # person, пофиг
    2: 1,   # car
    3: 1,   # moto
    5: 5,   # bus - высокий вес, чтобы ОТ ехал быстрее
    7: 3    # truck - средний
}

# цвета для отрисовки
CLASS_COLORS = {
    2: (0, 200, 255), 
    5: (255, 0, 0),    
    7: (255, 0, 255), 
    "active": (0, 255, 0),
    "stop": (0, 0, 255),
    "yellow": (0, 255, 255)
}

# загрузка модели
@st.cache_resource
def load_model():
    return YOLO('yolov8n.pt')

try:
    model = load_model()
    # трекер должен быть глобальным, чтобы не терять id
    tracker = Tracker() 
except Exception as e:
    st.error(f"ошибка загрузки модели: {e}")
    st.stop()

# загрузка зон (полигонов)
polygons = []
if os.path.exists(ZONES_FILE):
    try:
        with open(ZONES_FILE, 'rb') as f:
            polygons = pickle.load(f)
    except Exception as e:
        st.error(f"ошибка загрузки зон: {e}")
else:
    st.warning("⚠️ файл зон не найден. запусти zone_editor.py.")

# мозг системы (контроллер)
class SmartTrafficController:
    def __init__(self, num_zones):
        self.num_zones = num_zones
        self.current_zone = 0
        self.state = "GREEN" # green, yellow
        
        # настройки тайминга
        self.min_green = 4
        self.max_green = 25
        self.yellow_duration = 3
        
        self.emergency_mode = False # для скорых/пожарных
        self.timer_start = time.time()
        self.current_phase_duration = self.min_green
        self.time_left = 0
        self.priority_overrides = 0
        
        # аналитика и бд
        self.co2_saved = 0.0
        self.last_log_time = time.time()
        self.log_counter = 0

    # скоринг зоны на основе взвешенного кол-ва машин
    def get_zone_score(self, stats):
        return stats['weighted_count']

    def update(self, zone_stats):
        now = time.time()
        elapsed = now - self.timer_start
        
        # 1. логика co2
        time_delta = now - self.last_log_time
        waiting_cars = 0
        is_priority = 0
        
        for i, stats in enumerate(zone_stats):
            # считаем, сколько машин стоит на красном
            if i != self.current_zone and self.state != "YELLOW": 
                waiting_cars += stats['count']
            
            if stats['has_priority_vehicle']:
                is_priority = 1 # был ли приоритет в кадре
        
        # расчет co2
        self.co2_saved += waiting_cars * CO2_PER_CAR_SECOND * time_delta
        
        
        # 2. логирование в бд
        if now - self.last_log_time >= 0.5: # логгируем раз в полсекунды
            current_weighted_score = self.get_zone_score(zone_stats[self.current_zone])
            
            traffic_db.log_traffic_data(
                zone_id=self.current_zone, 
                car_count=zone_stats[self.current_zone]['count'],
                weighted_score=current_weighted_score,
                is_green=1 if self.state == "GREEN" else 0,
                phase_duration=self.current_phase_duration,
                is_priority=is_priority
            )
            self.log_counter += 1
            self.last_log_time = now
            
            # сохраняем бд на диск каждые 200 записей, чтоб не потерять
            if self.log_counter % 200 == 0:
                traffic_db.commit_data()

        # 3. логика переключения и приоритета
        emergency_zone = -1
        for i, stats in enumerate(zone_stats):
            if i != self.current_zone and stats['has_priority_vehicle']:
                emergency_zone = i # нашли скорую
                break
        
        # если нашли скорую, и мы не в желтом
        if emergency_zone != -1 and not self.emergency_mode and self.state != "YELLOW":
            self.emergency_mode = True
            self.state = "YELLOW"
            self.timer_start = now
            self.current_phase_duration = 2 # короткий желтый для экстренного переключения
            self.priority_overrides += 1
            return

        if self.state == "GREEN":
            self.time_left = max(0, int(self.current_phase_duration - elapsed))
            if elapsed >= self.current_phase_duration:
                self.state = "YELLOW"
                self.timer_start = now
                self.current_phase_duration = self.yellow_duration # обычный желтый
                
        elif self.state == "YELLOW":
            self.time_left = max(0, int(self.current_phase_duration - elapsed))
            
            if elapsed >= self.current_phase_duration:
                if self.emergency_mode:
                    # если был режим чс, переключаем на нее
                    next_zone = emergency_zone if emergency_zone != -1 else (self.current_zone + 1) % self.num_zones
                    self.emergency_mode = False
                else:
                    # ищем самую загруженную зону (по весу)
                    scores = [self.get_zone_score(z) for z in zone_stats]
                    scores[self.current_zone] = -1 # текущую зону пропускаем
                    
                    best_zone = np.argmax(scores)
                    if scores[best_zone] <= 0:
                        # если трафика нет нигде, просто по кругу
                        next_zone = (self.current_zone + 1) % self.num_zones
                    else:
                        next_zone = best_zone

                self.current_zone = next_zone
                self.state = "GREEN"
                self.timer_start = now
                
                # динамический расчет длительности зеленого света
                car_count = zone_stats[next_zone]['count']
                # min_green <= time <= max_green
                calculated_time = max(self.min_green, min(car_count * 3.0, self.max_green))
                self.current_phase_duration = calculated_time
        
        # обновляем время для ко2
        self.last_log_time = now 

# инициализация
controller = SmartTrafficController(len(polygons)) if polygons else None

# ui интерфейс
st.title("SmartTraffic: Almaty Control System")
col1, col2 = st.columns([1, 3])

# метрики
with col1:
    st.subheader("настройки")
    run_system = st.checkbox("запустить систему", value=False)
    show_labels = st.checkbox("показывать метки", value=True)
    conf = st.slider("точность ai", 0.2, 1.0, 0.4)
    st.markdown("---")
    kpi1 = st.metric(label="трафик (авто)", value="0")
    kpi2 = st.metric(label="приоритетные пропуски", value="0")
    kpi3 = st.metric(label="СО2 сэкономлено (кг)", value="0.0") # новая метрика
    
    status_placeholder = st.empty()
    zone_debug = st.empty()

image_spot = col2.empty()

# основной цикл
def main():
    cap = cv2.VideoCapture(VIDEO_PATH)
    
    if not cap.isOpened():
        st.error(f"не удалось открыть видео: {VIDEO_PATH}")
        return

    id_to_class = {} # кэш классов объектов по id трекинга

    while run_system and cap.isOpened():
        success, frame = cap.read()
        if not success:
            # зацикливаем видео
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        if controller and controller.log_counter % 30 == 0: 
             gc.collect() # чистим память, чтоб не упасть

        frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        overlay = frame.copy() # копия для заливки зон
        
        # 1. детекция и трекинг
        results = model(frame, stream=True, verbose=False, conf=conf, classes=[2, 3, 5, 7])
        detections = []
        curr_frame_objs = [] # объекты в текущем кадре
        
        for r in results:
            boxes = r.boxes
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                w, h = x2-x1, y2-y1
                cls = int(box.cls[0])
                detections.append([x1, y1, w, h])
                curr_frame_objs.append(((x1+w//2, y1+h//2), cls))
        
        tracks = tracker.update(detections)
        
        # 2. аналитика зон
        zone_stats = [{'count': 0, 'weighted_count': 0, 'has_priority_vehicle': False} for _ in polygons]
        
        # ТЕМПОРАРНОЕ ИЗМЕНЕНИЕ: ОТКЛЮЧАЕМ ЛОГИКУ ПРОВЕРКИ ЗОНЫ ДЛЯ ОТРИСОВКИ
        
        # Сначала обрабатываем все объекты для кэша классов (как было)
        for track in tracks:
            x1, y1, w, h, obj_id = track
            cx, cy = x1+w//2, y1+h//2 # центр объекта
            
            obj_cls = 2
            # ищем класс объекта
            if obj_id in id_to_class:
                obj_cls = id_to_class[obj_id]
            else:
                # новый id, надо найти класс
                min_d = 50
                for center, cls_raw in curr_frame_objs:
                    d = math.hypot(cx-center[0], cy-center[1])
                    if d < min_d:
                        obj_cls = cls_raw
                        id_to_class[obj_id] = obj_cls # сохраняем
                        break
            
            # --- ВРЕМЕННЫЙ КОД ДЛЯ ПОКАЗА ВСЕХ МАШИН ---
            # Логика подсчета трафика по зонам осталась, но отрисовка теперь для всех.
            
            # Проверяем, в какой зоне машина находится (для контроллера и логирования!)
            # Если не в зоне, то машина просто не учитывается в zone_stats
            is_in_zone = False
            for i, poly in enumerate(polygons):
                if cv2.pointPolygonTest(poly, (cx, cy), False) >= 0:
                    is_in_zone = True
                    weight = VEHICLE_WEIGHTS.get(obj_cls, 1)
                    zone_stats[i]['count'] += 1
                    zone_stats[i]['weighted_count'] += weight
                    if obj_cls in [5, 7]: # автобус или грузовик
                        zone_stats[i]['has_priority_vehicle'] = True
                    break
            
            # Отрисовка: теперь рисуем ВСЕ объекты, которые нашел трекер, независимо от зоны
            if show_labels:
                # Цвет бокса теперь зависит только от класса, а не от статуса светофора
                color = CLASS_COLORS.get(obj_cls, (255,255,255))
                
                # Дополнительная подсветка, если машина попала в АКТИВНУЮ зону.
                # Если в активной зоне, цвет будет зеленым (для наглядности)
                if controller and is_in_zone and i == controller.current_zone and controller.state == "GREEN":
                    color = (0, 255, 0)
                
                cvzone.cornerRect(frame, (x1, y1, w, h), l=8, rt=1, colorR=color)
                if obj_cls == 5:
                    cvzone.putTextRect(frame, "BUS", (x1, y1-10), scale=0.8, colorR=color)

        # 3. обновление контроллера и отрисовка зон (остается без изменений, так как нужно для логики)
        if controller:
            controller.update(zone_stats)
            
            # отрисовка зон
            for i, poly in enumerate(polygons):
                color = (0, 0, 200) # красный
                thick = 2
                if i == controller.current_zone:
                    if controller.state == "GREEN":
                        color = (0, 255, 0)
                        thick = 4
                    elif controller.state == "YELLOW":
                        color = (0, 255, 255)
                        thick = 3
                
                cv2.polylines(frame, [poly], True, color, thick)
                if i == controller.current_zone:
                    cv2.fillPoly(overlay, [poly], color)
            
            # hud
            cvzone.putTextRect(frame, f"Z{controller.current_zone+1}: {controller.time_left}s", (50, 50), scale=2, thickness=2, colorR=(20,20,20))
            if controller.emergency_mode:
                 cvzone.putTextRect(frame, "EMERGENCY PRIORITY", (50, 120), scale=1.5, colorR=(0,0,255))

        # вывод
        frame = cv2.addWeighted(overlay, 0.25, frame, 0.75, 0)
        image_spot.image(frame, channels="BGR", use_container_width=True)
        
        # метрики
        total_cars = sum(z['count'] for z in zone_stats)
        kpi1.metric("Active Cars", total_cars)
        if controller:
            kpi2.metric("Priority Actions", controller.priority_overrides)
            kpi3.metric("СО2 Сэкономлено (кг)", f"{controller.co2_saved:.4f} kg")
            
            # дебаг статус зон
            status_html = ""
            for i, zs in enumerate(zone_stats):
                active = "border: 2px solid #0f0;" if i == controller.current_zone else ""
                status_html += f"<div style='background:#333; padding:5px; margin:2px; {active}'>Zone {i+1}: {zs['count']} veh</div>"
            zone_debug.markdown(status_html, unsafe_allow_html=True)

    # закрытие бд и видео при выходе
    traffic_db.commit_data()
    traffic_db.close()
    cap.release()


if __name__ == "__main__":
    if run_system:
        main()
    else:
        # показываем превью
        cap = cv2.VideoCapture(VIDEO_PATH)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
                image_spot.image(frame, channels="BGR", caption="система готова к запуску")
        cap.release()