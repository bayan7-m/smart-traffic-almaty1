import sqlite3
import time

class SmartDB:
    def __init__(self, db_name='traffic_analytics.db'):
        self.db_name = db_name
        self.conn = None
        self.cursor = None
        self._connect()
        self._create_table() # сразу создаем таблицу, если ее нет

    def _connect(self):
        # устанавливаем коннект к sqlite. check_same_thread=False нужен для streamlit
        try:
            self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
            self.cursor = self.conn.cursor()
        except sqlite3.Error as e:
            print(f"ошибка подключения к бд: {e}")

    def _create_table(self):
        # создаем таблицу для логов трафика
        if self.cursor:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS traffic_logs (
                    timestamp REAL,
                    zone_id INTEGER,
                    car_count INTEGER,
                    weighted_score REAL,
                    is_green INTEGER,
                    phase_duration REAL,
                    priority_override INTEGER
                );
            """)
            self.conn.commit()

    # вставляем запись
    def log_traffic_data(self, zone_id, car_count, weighted_score, is_green, phase_duration, is_priority=0):
        # эту функцию будет дергать контроллер (раз в 0.5 сек)
        if self.cursor:
            try:
                # используем time.time() для timestamp
                self.cursor.execute("""
                    INSERT INTO traffic_logs VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (time.time(), zone_id, car_count, weighted_score, is_green, phase_duration, is_priority))
                # коммит не делаем тут, чтоб не замедлять. коммит будет в контроллере раз в N записей
                
            except sqlite3.Error as e:
                print(f"ошибка записи данных: {e}")
                
    # принудительный коммит. дергаем его, чтоб не потерять данные при падении
    def commit_data(self):
        if self.conn:
            self.conn.commit()

    # закрытие коннекта, обязательно при завершении программы
    def close(self):
        if self.conn:
            self.conn.close()

# инициализируем соединение сразу. его потом импортируем в main.py
traffic_db = SmartDB()