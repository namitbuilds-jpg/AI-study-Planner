import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'study_planner.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            student_class TEXT NOT NULL,
            mode TEXT DEFAULT 'Boards', -- Boards, ISC, JEE
            days_left_exam INTEGER DEFAULT 30,
            weak_subject TEXT DEFAULT 'Maths',
            study_hours FLOAT DEFAULT 4.0,
            sleep_hours FLOAT DEFAULT 8.0,
            attendance FLOAT DEFAULT 80.0,
            test_score FLOAT DEFAULT 75.0,
            distraction_level INTEGER DEFAULT 5,
            physical_activity FLOAT DEFAULT 1.0,
            maths_difficulty INTEGER DEFAULT 5,
            physics_difficulty INTEGER DEFAULT 5,
            chemistry_difficulty INTEGER DEFAULT 5,
            ai_robotics_difficulty INTEGER DEFAULT 5,
            english_difficulty INTEGER DEFAULT 5,
            physical_education_difficulty INTEGER DEFAULT 5,
            streak INTEGER DEFAULT 0,
            last_activity_date TEXT,
            is_admin INTEGER DEFAULT 0,
            is_disabled INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    ''')

    # Migration safety net: add columns for users created before this schema existed.
    # SQLite has no "ADD COLUMN IF NOT EXISTS", so we check pragma info first.
    cursor.execute("PRAGMA table_info(users)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    migrations = {
        'is_admin': "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0",
        'is_disabled': "ALTER TABLE users ADD COLUMN is_disabled INTEGER DEFAULT 0",
        'created_at': "ALTER TABLE users ADD COLUMN created_at TEXT",
        'failed_login_attempts': "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0",
        'lockout_until': "ALTER TABLE users ADD COLUMN lockout_until TEXT",
    }
    for col, ddl in migrations.items():
        if col not in existing_cols:
            cursor.execute(ddl)

    # Admin action audit log
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_user_id INTEGER,
            details TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (admin_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # Study schedules table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS study_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day_number INTEGER NOT NULL,
            date_string TEXT NOT NULL,
            subject TEXT NOT NULL,
            hours_scheduled FLOAT NOT NULL,
            holiday_mode INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # Daily logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            study_hours_completed FLOAT NOT NULL,
            sleep_hours FLOAT NOT NULL,
            attendance FLOAT NOT NULL,
            distraction_level INTEGER NOT NULL,
            physical_activity FLOAT NOT NULL,
            test_score FLOAT NOT NULL,
            completed_pomodoros INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, log_date)
        )
    ''')
    
    conn.commit()
    conn.close()

# User functions
def create_user(username, password, name, student_class):
    conn = get_db_connection()
    cursor = conn.cursor()
    password_hash = generate_password_hash(password)
    try:
        cursor.execute(
            'INSERT INTO users (username, password_hash, name, student_class) VALUES (?, ?, ?, ?)',
            (username, password_hash, name, student_class)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def get_user_by_username(username):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return user

def get_user_by_id(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user

def update_user_profile(user_id, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    keys = list(data.keys())
    values = list(data.values())
    values.append(user_id)
    set_clause = ", ".join([f"{k} = ?" for k in keys])
    cursor.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()

# Schedule functions
def save_schedule(user_id, schedule_items):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM study_schedules WHERE user_id = ?', (user_id,))
    for item in schedule_items:
        cursor.execute(
            'INSERT INTO study_schedules (user_id, day_number, date_string, subject, hours_scheduled, holiday_mode) VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, item['day_number'], item['date_string'], item['subject'], item['hours_scheduled'], item.get('holiday_mode', 0))
        )
    conn.commit()
    conn.close()

def get_schedule(user_id):
    conn = get_db_connection()
    schedule = conn.execute('SELECT * FROM study_schedules WHERE user_id = ? ORDER BY day_number ASC', (user_id,)).fetchall()
    conn.close()
    return schedule

def update_day_holiday_mode(user_id, day_number, holiday_mode):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Fetch current subject & hours scheduled
    row = cursor.execute('SELECT subject, hours_scheduled FROM study_schedules WHERE user_id = ? AND day_number = ?', (user_id, day_number)).fetchone()
    if row:
        hours = row['hours_scheduled']
        # If toggled on (holiday), cut hours in half. If toggled off (regular), restore original or just cut/restore relative.
        # However, to be robust, we'll store holiday_mode flag and we will let the UI handle the actual view logic,
        # or we update hours. Let's update the holiday_mode field itself first.
        cursor.execute(
            'UPDATE study_schedules SET holiday_mode = ? WHERE user_id = ? AND day_number = ?',
            (holiday_mode, user_id, day_number)
        )
    conn.commit()
    conn.close()

# Progress log functions
def add_daily_log(user_id, log_date, study_hours_completed, sleep_hours, attendance, distraction_level, physical_activity, test_score, completed_pomodoros=0):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''INSERT OR REPLACE INTO daily_logs 
               (user_id, log_date, study_hours_completed, sleep_hours, attendance, distraction_level, physical_activity, test_score, completed_pomodoros) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, log_date, study_hours_completed, sleep_hours, attendance, distraction_level, physical_activity, test_score, completed_pomodoros)
        )
        conn.commit()
        # Update streak logic
        update_streak(user_id, log_date, cursor)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Error saving log:", e)
        conn.close()
        return False

def get_user_logs(user_id):
    conn = get_db_connection()
    logs = conn.execute('SELECT * FROM daily_logs WHERE user_id = ? ORDER BY log_date ASC', (user_id,)).fetchall()
    conn.close()
    return logs

# --- Admin functions ---

def get_all_users(search=None, limit=50, offset=0):
    conn = get_db_connection()
    if search:
        like = f"%{search}%"
        rows = conn.execute(
            '''SELECT id, username, name, student_class, is_admin, is_disabled, streak, created_at
               FROM users WHERE username LIKE ? OR name LIKE ?
               ORDER BY id DESC LIMIT ? OFFSET ?''',
            (like, like, limit, offset)
        ).fetchall()
    else:
        rows = conn.execute(
            '''SELECT id, username, name, student_class, is_admin, is_disabled, streak, created_at
               FROM users ORDER BY id DESC LIMIT ? OFFSET ?''',
            (limit, offset)
        ).fetchall()
    conn.close()
    return rows

def count_users(search=None):
    conn = get_db_connection()
    if search:
        like = f"%{search}%"
        count = conn.execute(
            'SELECT COUNT(*) FROM users WHERE username LIKE ? OR name LIKE ?', (like, like)
        ).fetchone()[0]
    else:
        count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    conn.close()
    return count

def get_admin_stats():
    conn = get_db_connection()
    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_logs = conn.execute('SELECT COUNT(*) FROM daily_logs').fetchone()[0]
    total_admins = conn.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1').fetchone()[0]
    disabled_users = conn.execute('SELECT COUNT(*) FROM users WHERE is_disabled = 1').fetchone()[0]
    avg_streak = conn.execute('SELECT AVG(streak) FROM users').fetchone()[0] or 0
    signups_by_day = conn.execute(
        '''SELECT date(created_at) as d, COUNT(*) as c FROM users
           WHERE created_at IS NOT NULL
           GROUP BY date(created_at) ORDER BY d DESC LIMIT 14'''
    ).fetchall()
    conn.close()
    return {
        'total_users': total_users,
        'total_logs': total_logs,
        'total_admins': total_admins,
        'disabled_users': disabled_users,
        'avg_streak': round(avg_streak, 1),
        'signups_by_day': [dict(r) for r in signups_by_day]
    }

def set_admin_status(user_id, is_admin):
    conn = get_db_connection()
    conn.execute('UPDATE users SET is_admin = ? WHERE id = ?', (1 if is_admin else 0, user_id))
    conn.commit()
    conn.close()

def set_disabled_status(user_id, is_disabled):
    conn = get_db_connection()
    conn.execute('UPDATE users SET is_disabled = ? WHERE id = ?', (1 if is_disabled else 0, user_id))
    conn.commit()
    conn.close()

def delete_user(user_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))  # cascades to schedules/logs
    conn.commit()
    conn.close()

def count_admins():
    conn = get_db_connection()
    count = conn.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1').fetchone()[0]
    conn.close()
    return count

def log_admin_action(admin_user_id, action, target_user_id=None, details=None):
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO admin_audit_log (admin_user_id, action, target_user_id, details) VALUES (?, ?, ?, ?)',
        (admin_user_id, action, target_user_id, details)
    )
    conn.commit()
    conn.close()

def get_audit_log(limit=100):
    conn = get_db_connection()
    rows = conn.execute(
        '''SELECT al.*, admin.username AS admin_username, target.username AS target_username
           FROM admin_audit_log al
           LEFT JOIN users admin ON admin.id = al.admin_user_id
           LEFT JOIN users target ON target.id = al.target_user_id
           ORDER BY al.id DESC LIMIT ?''', (limit,)
    ).fetchall()
    conn.close()
    return rows

# --- Login throttling (brute-force protection) ---

def register_failed_login(username):
    """Increments failed attempts; locks the account for 15 min after 5 failures."""
    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute('SELECT id, failed_login_attempts FROM users WHERE username = ?', (username,)).fetchone()
    if user:
        attempts = (user['failed_login_attempts'] or 0) + 1
        lockout_until = None
        if attempts >= 5:
            import datetime
            lockout_until = (datetime.datetime.utcnow() + datetime.timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            'UPDATE users SET failed_login_attempts = ?, lockout_until = ? WHERE id = ?',
            (attempts, lockout_until, user['id'])
        )
        conn.commit()
    conn.close()

def reset_failed_login(user_id):
    conn = get_db_connection()
    conn.execute('UPDATE users SET failed_login_attempts = 0, lockout_until = NULL WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

def is_locked_out(user_row):
    if not user_row or not user_row['lockout_until']:
        return False
    import datetime
    try:
        lockout_until = datetime.datetime.strptime(user_row['lockout_until'], "%Y-%m-%d %H:%M:%S")
        return datetime.datetime.utcnow() < lockout_until
    except Exception:
        return False


def update_streak(user_id, log_date, cursor):
    import datetime
    user = cursor.execute('SELECT streak, last_activity_date FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        return
        
    streak = user['streak']
    last_date_str = user['last_activity_date']
    
    current_date = datetime.datetime.strptime(log_date, "%Y-%m-%d").date()
    
    if last_date_str:
        try:
            last_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
            delta = current_date - last_date
            if delta.days == 1:
                streak += 1
            elif delta.days > 1:
                streak = 1
            # If delta.days == 0, keep same streak
        except Exception:
            streak = 1
    else:
        streak = 1
        
    cursor.execute('UPDATE users SET streak = ?, last_activity_date = ? WHERE id = ?', (streak, log_date, user_id))
