import os
import sqlite3
import pickle
import pandas as pd
import numpy as np
import datetime
import random
import csv
import json
import secrets
from functools import wraps
from io import StringIO
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response, abort
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import database as db

app = Flask(__name__)

# SECRET_KEY must be set in the environment for production. Falling back to a
# random key means every restart invalidates all sessions AND, worse, means a
# misconfigured deployment could silently run with a key that resets on every
# reload. We fail loudly in production instead of masking the problem.
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    if os.environ.get('FLASK_ENV') == 'production':
        raise RuntimeError(
            "SECRET_KEY environment variable must be set in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    _secret_key = secrets.token_hex(32)
    print("WARNING: SECRET_KEY not set — using a temporary key for this run only "
          "(dev mode). Set SECRET_KEY in your .env for real deployments.")
app.secret_key = _secret_key

# Session cookie hardening
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=12)

# CSRF protection on all state-changing form submissions
csrf = CSRFProtect(app)

# Basic rate limiting — mainly to slow down credential stuffing / brute force
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per hour"])

# Initialize database
db.init_db()


def admin_required(f):
    """Restricts a route to authenticated users with is_admin = 1.
    Always re-checks the DB rather than trusting a session flag, so revoking
    admin rights takes effect immediately rather than at next login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = db.get_user_by_id(session['user_id'])
        if not user or not user['is_admin']:
            abort(403)
        if user['is_disabled']:
            session.clear()
            flash("This account has been disabled.")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Chart.js is loaded from a CDN in base.html, so it's allowlisted here.
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "media-src 'self';"
    )
    if os.environ.get('FLASK_ENV') == 'production':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


@app.cli.command('create-admin')
def create_admin_command():
    """Promote an existing user to admin, or create a new admin account.
    Run from the command line only: flask create-admin
    Deliberately NOT exposed as a web route — admin creation should never be
    reachable over HTTP."""
    import getpass
    username = input("Username: ").strip()
    existing = db.get_user_by_username(username)
    if existing:
        db.set_admin_status(existing['id'], True)
        print(f"'{username}' is now an admin.")
        return
    name = input("Full name: ").strip()
    password = getpass.getpass("Password: ")
    student_class = "Class 12 Science"
    user_id = db.create_user(username, password, name, student_class)
    if user_id:
        db.set_admin_status(user_id, True)
        print(f"Created admin user '{username}'.")
    else:
        print("Failed to create user (username may already exist).")

# Load trained Random Forest model
try:
    with open("study_planner_model.pkl", "rb") as f:
        model = pickle.load(f)
except Exception as e:
    model = None
    print("WARNING: study_planner_model.pkl not found or failed to load. Defaulting to heuristics.", e)

# Motivational Quotes
QUOTES = [
    ("Discipline is choosing between what you want now and what you want most.", "Abraham Lincoln"),
    ("Small daily improvements over time lead to stunning results.", "Robin Sharma"),
    ("Success is the sum of small efforts, repeated day in and day out.", "Robert Collier"),
    ("Focus on being productive instead of busy.", "Tim Ferriss"),
    ("You don't have to be extreme, just consistent.", "Unknown"),
    ("Action is the foundational key to all success.", "Pablo Picasso"),
    ("It's not that I'm so smart, it's just that I stay with problems longer.", "Albert Einstein"),
    ("The secret of your future is hidden in your daily routine.", "Mike Murdock"),
    ("Your mind is for having ideas, not holding them.", "David Allen"),
    ("Discipline beats motivation every single time.", "Namit"),
    ("Consistency is the key that unlocks potential.", "Unknown")
]

# Helper: Map subjects to stream
def get_subjects_by_class(student_class):
    if "Commerce" in student_class:
        return ["Accountancy", "Economics", "Business Studies", "Maths", "English", "Physical Education"]
    elif "Humanities" in student_class:
        return ["History", "Geography", "Political Science", "English", "Physical Education", "AI and Robotics"]
    elif "Class 10" in student_class:
        return ["Science", "Social Studies", "Maths", "English", "Hindi", "Physical Education"]
    else:  # Science Stream
        return ["Maths", "Physics", "Chemistry", "AI and Robotics", "English", "Physical Education"]

# Helper: Get subject difficulty from DB user row by index mapping
def get_subject_difficulty(user, subject_name):
    subjects = get_subjects_by_class(user['student_class'])
    try:
        idx = subjects.index(subject_name)
    except ValueError:
        return 5  # default
        
    diff_cols = [
        'maths_difficulty',
        'physics_difficulty',
        'chemistry_difficulty',
        'ai_robotics_difficulty',
        'english_difficulty',
        'physical_education_difficulty'
    ]
    return user[diff_cols[idx]]

# Helper: Calculate Productivity Score
def calculate_productivity_score(user):
    # Inputs: sleep, attendance, distraction, physical activity, test_score
    # Max score = 100
    sleep_score = min(20, (user['sleep_hours'] / 8.0) * 20) if user['sleep_hours'] <= 8 else max(0, 20 - (user['sleep_hours'] - 8) * 4)
    attendance_score = (user['attendance'] / 100.0) * 20
    distraction_score = ((10 - user['distraction_level']) / 10.0) * 20
    activity_score = min(10, (user['physical_activity'] / 2.0) * 10)
    test_score_contrib = (user['test_score'] / 100.0) * 30
    
    total = sleep_score + attendance_score + distraction_score + activity_score + test_score_contrib
    return int(max(0, min(100, total)))

# Helper: AI Prediction
def predict_study_plan(user):
    if model is None:
        # Fallback to rule-based classification if model pickle fails
        score = calculate_productivity_score(user)
        if score < 50:
            return "Heavy"
        elif score > 80:
            return "Light"
        return "Medium"
        
    # Format user data as DataFrame matching training features
    input_data = pd.DataFrame([[
        user['study_hours'],
        user['sleep_hours'],
        user['attendance'],
        user['test_score'],
        user['distraction_level'],
        user['physical_activity'],
        user['maths_difficulty'],
        user['physics_difficulty'],
        user['chemistry_difficulty'],
        user['ai_robotics_difficulty'],
        user['english_difficulty'],
        user['physical_education_difficulty']
    ]], columns=[
        'study_hours',
        'sleep_hours',
        'attendance',
        'test_score',
        'distraction_level',
        'physical_activity',
        'maths_difficulty',
        'physics_difficulty',
        'chemistry_difficulty',
        'ai_robotics_difficulty',
        'english_difficulty',
        'physical_education_difficulty'
    ])
    
    try:
        prediction = model.predict(input_data)
        return prediction[0]
    except Exception as e:
        print("Model prediction failed, falling back to heuristics:", e)
        return "Medium"

# Helper: Generate 30-Day Rotating Timetable
def generate_30_day_schedule(user_id, user):
    subjects = get_subjects_by_class(user['student_class'])
    weak_sub = user['weak_subject']
    days_left = user['days_left_exam']
    plan = predict_study_plan(user)
    
    schedule_items = []
    start_date = datetime.date.today()
    
    for day in range(1, 31):
        current_date = start_date + datetime.timedelta(days=day-1)
        date_str = current_date.strftime("%Y-%m-%d")
        
        # 1. Revision / Mock Test on Sundays
        if day % 7 == 0:
            subject = "Revision + Mock Test"
            # Adjust hours based on countdown
            if days_left < 10:
                hours = 5.0
            elif days_left < 30:
                hours = 4.0
            else:
                hours = 3.0
        # 2. Focus on weak subject on Saturdays
        elif day % 7 == 6:
            subject = weak_sub if weak_sub in subjects else subjects[0]
            hours = 2.0
            diff = get_subject_difficulty(user, subject)
            if diff >= 8: hours += 1.5
            elif diff >= 5: hours += 0.8
            # Weak subject Saturday bonus
            hours += 1.0
        # 3. Rotating subjects on weekdays
        else:
            # Simple rotation index
            sub_idx = (day - 1) % len(subjects)
            subject = subjects[sub_idx]
            
            # Base hours
            if subject == "Physical Education":
                hours = 0.5
            else:
                hours = 1.5
                
            # Difficulty tuning
            diff = get_subject_difficulty(user, subject)
            if diff >= 8: hours += 1.5
            elif diff >= 5: hours += 0.8
            
            # Weak subject boost
            if subject == weak_sub:
                hours += 1.0
                
        # 4. Model predictions adjustments
        if plan == "Heavy" and subject != "Physical Education":
            hours += 0.5
        elif plan == "Light":
            if subject == "Physical Education":
                hours += 0.5
            else:
                hours = max(0.5, hours - 0.5)
                
        # 5. Exam Countdown Intensive adjustments
        if subject != "Physical Education" and subject != "Revision + Mock Test":
            if days_left < 10:
                hours += 1.5
            elif days_left < 30:
                hours += 0.7
                
        # Clamp hours
        hours = round(max(0.5, min(8.0, hours)), 1)
        
        schedule_items.append({
            'day_number': day,
            'date_string': date_str,
            'subject': subject,
            'hours_scheduled': hours,
            'holiday_mode': 0
        })
        
    db.save_schedule(user_id, schedule_items)

# Filters / Decorators
def get_today_subject_and_hours(user_id, user):
    schedule = db.get_schedule(user_id)
    if not schedule:
        # Generate initial schedule if missing
        generate_30_day_schedule(user_id, user)
        schedule = db.get_schedule(user_id)
        
    # Get day index based on user logs count or relative date
    logs = db.get_user_logs(user_id)
    # Day count = logs completed mod 30
    day_idx = len(logs) % 30
    if day_idx < len(schedule):
        today_row = schedule[day_idx]
        hours = today_row['hours_scheduled']
        # If holiday mode activated for the day, cut hours in half
        if today_row['holiday_mode']:
            hours = round(hours * 0.5, 1)
        return today_row['subject'], hours
    return "Revision + Mock Test", 2.0

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        user = db.get_user_by_username(username)

        if user and db.is_locked_out(user):
            flash("Too many failed attempts. This account is temporarily locked — try again in a few minutes.")
            return render_template('login.html')

        if user and user['is_disabled']:
            flash("This account has been disabled. Contact an administrator.")
            return render_template('login.html')

        if user and check_password_hash(user['password_hash'], password):
            db.reset_failed_login(user['id'])
            session.clear()
            session.permanent = True
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['class'] = user['student_class']
            session['is_admin'] = bool(user['is_admin'])
            return redirect(url_for('dashboard'))
        else:
            if user:
                db.register_failed_login(username)
            # Same generic message whether the username exists or not, so login
            # can't be used to enumerate valid usernames.
            flash("Invalid username or password.")

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        username = request.form['username'].strip()
        password = request.form['password']
        student_class = request.form['student_class']
        
        # Check if username exists
        existing = db.get_user_by_username(username)
        if existing:
            flash("Username already taken.")
            return render_template('register.html')
            
        user_id = db.create_user(username, password, name, student_class)
        if user_id:
            session['user_id'] = user_id
            session['name'] = name
            session['class'] = student_class
            
            # Generate default schedule
            user = db.get_user_by_id(user_id)
            generate_30_day_schedule(user_id, user)
            
            return redirect(url_for('dashboard'))
        else:
            flash("Database registration failed.")
            
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    user = db.get_user_by_id(user_id)
    
    productivity = calculate_productivity_score(user)
    today_sub, today_hrs = get_today_subject_and_hours(user_id, user)
    
    # Completed pomodoros count today
    logs = db.get_user_logs(user_id)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    today_log = next((l for l in logs if l['log_date'] == today_str), None)
    pomodoros = today_log['completed_pomodoros'] if today_log else 0
    
    # Pick a random quote
    random.seed(datetime.date.today().toordinal())
    quote = random.choice(QUOTES)
    
    return render_template(
        'dashboard.html', 
        active_page='dashboard',
        user=user,
        name=user['name'],
        productivity_score=productivity,
        today_subject=today_sub,
        today_hours=today_hrs,
        pomodoros_completed=pomodoros,
        quote_text=quote[0],
        quote_author=quote[1]
    )

@app.route('/calendar')
def calendar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    user = db.get_user_by_id(user_id)
    schedule = db.get_schedule(user_id)
    
    # Process schedule list to reflect holiday mode halving
    processed_schedule = []
    for item in schedule:
        hours = item['hours_scheduled']
        if item['holiday_mode']:
            hours = round(hours * 0.5, 1)
        processed_schedule.append({
            'day_number': item['day_number'],
            'date_string': item['date_string'],
            'subject': item['subject'],
            'hours_scheduled': hours,
            'holiday_mode': item['holiday_mode']
        })
        
    return render_template(
        'calendar.html',
        active_page='calendar',
        user=user,
        schedule=processed_schedule
    )

@app.route('/regenerate_schedule', methods=['POST'])
def regenerate_schedule():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    
    # Update profile tuning parameters
    profile_data = {
        'mode': request.form['mode'],
        'days_left_exam': int(request.form['days_left']),
        'weak_subject': request.form['weak_subject'],
        'maths_difficulty': int(request.form['maths_diff']),
        'physics_difficulty': int(request.form['physics_diff']),
        'chemistry_difficulty': int(request.form['chemistry_diff']),
        'ai_robotics_difficulty': int(request.form['ai_diff']),
        'english_difficulty': int(request.form['english_diff']),
        'physical_education_difficulty': int(request.form['pe_diff'])
    }
    
    db.update_user_profile(user_id, profile_data)
    user = db.get_user_by_id(user_id)
    
    # Regenerate 30-day timetable
    generate_30_day_schedule(user_id, user)
    
    flash("Study schedule regenerated successfully!")
    return redirect(url_for('calendar'))

@app.route('/progress')
def progress():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    logs = db.get_user_logs(user_id)
    return render_template('progress.html', active_page='progress', logs=logs)

@app.route('/log_progress', methods=['POST'])
def log_progress():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    log_date = request.form['log_date']
    study_hours = float(request.form['study_hours'])
    sleep_hours = float(request.form['sleep_hours'])
    attendance = float(request.form['attendance'])
    distraction = int(request.form['distraction_level'])
    activity = float(request.form['physical_activity'])
    test_score = float(request.form['test_score'])
    
    # Save to SQLite daily logs
    db.add_daily_log(
        user_id, log_date, study_hours, sleep_hours, attendance, distraction, activity, test_score
    )
    
    # Sync user profile details to match latest logged stats dynamically
    profile_update = {
        'study_hours': study_hours,
        'sleep_hours': sleep_hours,
        'attendance': attendance,
        'distraction_level': distraction,
        'physical_activity': activity,
        'test_score': test_score
    }
    db.update_user_profile(user_id, profile_update)
    
    flash("Daily progress saved and AI profile synchronized!")
    return redirect(url_for('progress'))

@app.route('/ai-advisor')
def ai_advisor():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    user = db.get_user_by_id(user_id)
    
    # Run Random Forest classifier prediction
    plan = predict_study_plan(user)
    today_sub, _ = get_today_subject_and_hours(user_id, user)
    
    return render_template(
        'ai_advisor.html',
        active_page='ai_advisor',
        user=user,
        study_plan=plan,
        today_subject=today_sub
    )

# API: Toggle Holiday Mode
@app.route('/api/toggle_holiday/<int:day_number>', methods=['POST'])
def api_toggle_holiday(day_number):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
    user_id = session['user_id']
    schedule = db.get_schedule(user_id)
    
    day_row = next((d for d in schedule if d['day_number'] == day_number), None)
    if not day_row:
        return jsonify({'success': False, 'error': 'Day not found'}), 404
        
    # Toggle (0 -> 1, 1 -> 0)
    new_mode = 0 if day_row['holiday_mode'] else 1
    db.update_day_holiday_mode(user_id, day_number, new_mode)
    
    return jsonify({'success': True, 'holiday_mode': new_mode})

# API: Pomodoro Log
@app.route('/api/log_pomodoro', methods=['POST'])
def api_log_pomodoro():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
    user_id = session['user_id']
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    user = db.get_user_by_id(user_id)
    
    # Fetch today's log or create default
    logs = db.get_user_logs(user_id)
    today_log = next((l for l in logs if l['log_date'] == today_str), None)
    
    if today_log:
        count = today_log['completed_pomodoros'] + 1
        db.add_daily_log(
            user_id,
            today_str,
            today_log['study_hours_completed'] + 0.4, # add 25 min study contribution
            today_log['sleep_hours'],
            today_log['attendance'],
            today_log['distraction_level'],
            today_log['physical_activity'],
            today_log['test_score'],
            count
        )
    else:
        count = 1
        # Use profile standards if no log today
        db.add_daily_log(
            user_id,
            today_str,
            user['study_hours'] + 0.4,
            user['sleep_hours'],
            user['attendance'],
            user['distraction_level'],
            user['physical_activity'],
            user['test_score'],
            count
        )
        
    # Refetch user to get updated streak
    updated_user = db.get_user_by_id(user_id)
    
    return jsonify({'success': True, 'today_count': count, 'streak': updated_user['streak']})

# API: Progress data for Chart.js
@app.route('/api/progress_data')
def api_progress_data():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
    user_id = session['user_id']
    user = db.get_user_by_id(user_id)
    logs = db.get_user_logs(user_id)
    schedule = db.get_schedule(user_id)
    
    # 1. Completed vs Scheduled hours
    study_dates = []
    hours_completed = []
    hours_scheduled = []
    
    # Align logs with schedules
    # We take matching dates or indices
    for i, log in enumerate(logs[-10:]): # past 10 logs
        study_dates.append(log['log_date'])
        hours_completed.append(log['study_hours_completed'])
        
        # get scheduled hours matching index mod 30
        sched_idx = i % 30
        if sched_idx < len(schedule):
            hours_scheduled.append(schedule[sched_idx]['hours_scheduled'])
        else:
            hours_scheduled.append(4.0)
            
    # 2. Subject difficulties
    subjects = get_subjects_by_class(user['student_class'])
    difficulties = [get_subject_difficulty(user, sub) for sub in subjects]
    
    # 3. Productivity score trend
    productivity_dates = []
    productivity_scores = []
    for log in logs[-15:]: # past 15 logs
        productivity_dates.append(log['log_date'])
        # Create a mock user dict to pass to score calculator
        temp_user = {
            'sleep_hours': log['sleep_hours'],
            'attendance': log['attendance'],
            'distraction_level': log['distraction_level'],
            'physical_activity': log['physical_activity'],
            'test_score': log['test_score']
        }
        productivity_scores.append(calculate_productivity_score(temp_user))
        
    return jsonify({
        'study_dates': study_dates,
        'hours_completed': hours_completed,
        'hours_scheduled': hours_scheduled,
        'subjects': subjects,
        'difficulties': difficulties,
        'productivity_dates': productivity_dates,
        'productivity_scores': productivity_scores
    })

# CSV / JSON Timetable Exports
@app.route('/export/csv')
def export_csv():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    schedule = db.get_schedule(user_id)
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Day Number', 'Date', 'Subject Focus', 'Hours Scheduled', 'Holiday Mode Active'])
    
    for row in schedule:
        hours = row['hours_scheduled']
        if row['holiday_mode']:
            hours = round(hours * 0.5, 1)
        cw.writerow([row['day_number'], row['date_string'], row['subject'], hours, 'YES' if row['holiday_mode'] else 'NO'])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=study_schedule.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/export/json')
def export_json():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    schedule = db.get_schedule(user_id)
    
    data = []
    for row in schedule:
        hours = row['hours_scheduled']
        if row['holiday_mode']:
            hours = round(hours * 0.5, 1)
        data.append({
            'day_number': row['day_number'],
            'date_string': row['date_string'],
            'subject': row['subject'],
            'hours_scheduled': hours,
            'holiday_mode_active': True if row['holiday_mode'] else False
        })
        
    response = make_response(json.dumps(data, indent=2))
    response.headers["Content-Disposition"] = "attachment; filename=study_schedule.json"
    response.headers["Content-type"] = "application/json"
    return response

# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------

@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = db.get_admin_stats()
    recent_audit = db.get_audit_log(limit=10)
    return render_template('admin/dashboard.html', active_page='admin_dashboard', stats=stats, recent_audit=recent_audit)

@app.route('/admin/users')
@admin_required
def admin_users():
    search = request.args.get('q', '').strip() or None
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 25
    users = db.get_all_users(search=search, limit=per_page, offset=(page - 1) * per_page)
    total = db.count_users(search=search)
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template(
        'admin/users.html', active_page='admin_users',
        users=users, search=search or '', page=page, total_pages=total_pages, total=total
    )

@app.route('/admin/users/<int:target_id>')
@admin_required
def admin_user_detail(target_id):
    target = db.get_user_by_id(target_id)
    if not target:
        abort(404)
    logs = db.get_user_logs(target_id)
    schedule = db.get_schedule(target_id)
    return render_template('admin/user_detail.html', active_page='admin_users', target=target, logs=logs, schedule=schedule)

@app.route('/admin/users/<int:target_id>/toggle_admin', methods=['POST'])
@admin_required
def admin_toggle_admin(target_id):
    actor_id = session['user_id']
    target = db.get_user_by_id(target_id)
    if not target:
        abort(404)

    # Prevent an admin from removing their own admin rights if they're the
    # last admin — this would lock everyone out of the panel permanently.
    if target_id == actor_id and target['is_admin'] and db.count_admins() <= 1:
        flash("You're the last remaining admin — promote someone else before removing your own access.")
        return redirect(url_for('admin_user_detail', target_id=target_id))

    new_status = not target['is_admin']
    db.set_admin_status(target_id, new_status)
    db.log_admin_action(actor_id, 'grant_admin' if new_status else 'revoke_admin', target_id)
    flash(f"Admin access {'granted to' if new_status else 'revoked from'} {target['username']}.")
    return redirect(url_for('admin_user_detail', target_id=target_id))

@app.route('/admin/users/<int:target_id>/toggle_disabled', methods=['POST'])
@admin_required
def admin_toggle_disabled(target_id):
    actor_id = session['user_id']
    target = db.get_user_by_id(target_id)
    if not target:
        abort(404)
    if target_id == actor_id:
        flash("You can't disable your own account.")
        return redirect(url_for('admin_user_detail', target_id=target_id))

    new_status = not target['is_disabled']
    db.set_disabled_status(target_id, new_status)
    db.log_admin_action(actor_id, 'disable_user' if new_status else 'enable_user', target_id)
    flash(f"Account {'disabled' if new_status else 're-enabled'} for {target['username']}.")
    return redirect(url_for('admin_user_detail', target_id=target_id))

@app.route('/admin/users/<int:target_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(target_id):
    actor_id = session['user_id']
    target = db.get_user_by_id(target_id)
    if not target:
        abort(404)
    if target_id == actor_id:
        flash("You can't delete your own account from here.")
        return redirect(url_for('admin_user_detail', target_id=target_id))

    # Confirmation step: require the admin to re-type the username before deleting.
    confirm = request.form.get('confirm_username', '').strip()
    if confirm != target['username']:
        flash("Username confirmation didn't match — user was not deleted.")
        return redirect(url_for('admin_user_detail', target_id=target_id))

    db.log_admin_action(actor_id, 'delete_user', target_id, details=f"username={target['username']}")
    db.delete_user(target_id)
    flash(f"Deleted account '{target['username']}'.")
    return redirect(url_for('admin_users'))

@app.route('/admin/audit-log')
@admin_required
def admin_audit_log():
    entries = db.get_audit_log(limit=200)
    return render_template('admin/audit_log.html', active_page='admin_audit', entries=entries)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    # debug=True enables the Werkzeug interactive debugger, which allows
    # arbitrary remote code execution if the app is ever reachable from
    # outside your machine. It must never be on in production — it's now
    # driven by FLASK_ENV so a deployment can't accidentally ship with it on.
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(debug=debug_mode, port=5000)
