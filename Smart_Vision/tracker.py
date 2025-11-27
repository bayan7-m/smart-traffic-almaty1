import math

class Tracker:
    def __init__(self):
        # где сейчас центры объектов {id: (cx, cy)}
        self.center_points = {}
        # счетчик id, инкрементируется при появлении нового объекта
        self.id_count = 0

    def update(self, objects_rect):
        # список для возврата: [x, y, w, h, id]
        objects_bbs_ids = []

        # проходим по всем прямоугольникам, которые нашел YOLO
        for rect in objects_rect:
            x, y, w, h = rect
            # находим центр текущего бокса
            cx = (x + x + w) // 2
            cy = (y + y + h) // 2

            # проверяем, не является ли это уже отслеживаемый объект
            same_object_detected = False
            for id, pt in self.center_points.items():
                # считаем дистанцию между старым центром (pt) и новым (cx, cy)
                dist = math.hypot(cx - pt[0], cy - pt[1])

                if dist < 35: # magic number: порог для определения, что это тот же объект
                    self.center_points[id] = (cx, cy) # обновляем его координаты
                    objects_bbs_ids.append([x, y, w, h, id]) # добавляем в вывод
                    same_object_detected = True
                    break

            # если ни один старый объект не совпал -> это новый объект
            if same_object_detected is False:
                self.center_points[self.id_count] = (cx, cy) # даем новый id и центр
                objects_bbs_ids.append([x, y, w, h, self.id_count])
                self.id_count += 1 # увеличиваем общий счетчик

        # чистим словарь центров от объектов, которые пропали из кадра
        new_center_points = {}
        for obj_bb_id in objects_bbs_ids:
            # берем id только тех объектов, которые мы детектировали в текущем кадре
            _, _, _, _, object_id = obj_bb_id
            center = self.center_points[object_id]
            new_center_points[object_id] = center

        # обновляем словарь
        self.center_points = new_center_points.copy()
        return objects_bbs_ids # возвращаем актуальные боксы с id