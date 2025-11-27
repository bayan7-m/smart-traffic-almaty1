import cv2
import pickle
import numpy as np
import os

# настройки
# путь к видео
VIDEO_PATH = os.path.join(os.path.dirname(__file__), 'video1.mp4') 
ZONES_FILE = 'traffic_zones.pkl' 

polygons = [] # тут хранятся готовые зоны
current_polygon = [] # текущий полигон, который мы рисуем

# колбэк для обработки кликов мыши
def mouse_callback(event, x, y, flags, param):
    global current_polygon
    
    if event == cv2.EVENT_LBUTTONDOWN:
        current_polygon.append((x, y)) # левый клик — добавляем точку
        
    elif event == cv2.EVENT_RBUTTONDOWN:
        # правый клик — завершаем рисование, если точек > 2
        if len(current_polygon) > 2:
            # конвертируем список точек в numpy array, как требует cv2
            polygons.append(np.array(current_polygon, np.int32))
            current_polygon = [] # сбрасываем, чтобы рисовать новую зону
            print(f"зона {len(polygons)} сохранена!")

def main():
    global current_polygon 
    
    cap = cv2.VideoCapture(VIDEO_PATH)
    success, frame = cap.read()
    if not success:
        print(f"ошибка: не могу открыть видео {VIDEO_PATH}")
        return

    # ресайзим кадр до нужного размера, как в основном коде
    frame = cv2.resize(frame, (1020, 600))
    
    # настраиваем окно и колбэк
    cv2.namedWindow('ZONE EDITOR')
    cv2.setMouseCallback('ZONE EDITOR', mouse_callback)

    print("=== УПРАВЛЕНИЕ ===")
    print("left click: добавить точку")
    print("right click: закрыть полигон и сохранить зону")
    print("s: сохранить и выйти")
    print("q: выйти без сохранения")
    print("c: очистить последнюю зону/сбросить текущую")

    while True:
        img_copy = frame.copy()
        overlay = img_copy.copy()
        
        # отрисовываем все сохраненные зоны
        for i, poly in enumerate(polygons):
            # полупрозрачная заливка
            cv2.fillPoly(overlay, [poly], (0, 255, 0))
            # зеленый контур
            cv2.polylines(img_copy, [poly], True, (0, 255, 0), 2)
            
            # ищем центр зоны для подписи Z1, Z2...
            M = cv2.moments(poly)
            if M['m00'] != 0:
                cx = int(M['m10']/M['m00'])
                cy = int(M['m01']/M['m00'])
                # пишем номер зоны
                cv2.putText(img_copy, f"Z{i+1}", (cx, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
        
        # смешиваем кадр с заливкой (0.3 прозрачности)
        cv2.addWeighted(overlay, 0.3, img_copy, 0.7, 0, img_copy)

        # отрисовываем текущий, незакрытый полигон
        if len(current_polygon) > 0:
            # красная линия и точки
            cv2.polylines(img_copy, [np.array(current_polygon)], False, (0, 0, 255), 2)
            for point in current_polygon:
                cv2.circle(img_copy, point, 5, (0, 0, 255), -1)

        cv2.imshow('ZONE EDITOR', img_copy)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('s'):
            # s — сохраняем полигоны в pickle-файл
            with open(ZONES_FILE, 'wb') as f:
                pickle.dump(polygons, f)
            print("сохранено в traffic_zones.pkl")
            break
        elif key == ord('c'):
            # c — очистить
            if polygons: polygons.pop() # удаляем последнюю сохраненную зону
            if current_polygon: current_polygon = [] # сбрасываем, если рисовали текущую
        elif key == ord('q'):
            # q — просто выходим
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()