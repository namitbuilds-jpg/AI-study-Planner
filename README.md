An intelligent web based study management application developed using Python, Flask, HTML, CSS, JavaScript and Machine Learning. The AI Study Timer helps students to organize their academic schedules, manage study sessions, monitor productivity, and track their learning progress via an interactive dashboard.

It brings together study planning, time management, progress tracking and AI-powered help in a single platform.

✨ Main Features

### 1. 📊 Student Dashboard
- Interactive dashboard for accessing important study information.
- Overview of study activities and productivity.
- Easy navigation between different sections of the application.

### 2. ⏱️ Pomodoro Timer for Learning
• Timer to help you concentrate on your study sessions.
- Helps students to schedule their study time and breaks.
• Timer functionality using JavaScript.

### 3. 🤖  Help with AI Study
- AI study plan feature.- Integration of machine learning model into the application.
- Assists students in study related recommendations and planning.

### 4. 📅 Exam Dates- Calendar interface dedicated to viewing and organizing study activities.
- Assists students with their academic timetables.

### 5. 📈 Tracking Progress
- Keep track of study progress in a dedicated progress section.
- Visualize study and productivity related information.
- Interactive graphs show relevant data.

### 6. 🎙️ Voice Features
- Includes JavaScript-based voice functionality.
- Provides voice-related interaction capabilities.

### 7. 🔐 User Authentication
- Login and registration pages.
- Separate student-facing and administrative interfaces.
- Flask-based application structure.

---

## 🛠️ Technologies Used

| Technology | Purpose |
|---|---|
| Python | Backend development |
| Flask | Web application framework |
| Machine Learning | AI-based study functionality |
| Scikit-learn | Machine Learning model support |
| Pandas & NumPy | Data processing |
| HTML & CSS | Frontend design |
| JavaScript | Interactive functionality |
| CSV | Data storage and processing |

---

## 🚀 How to Install and Run the Project

Follow these instructions to run the AI Study Timer on your computer.

### Step 1: Download the project

1. Open the GitHub repository.
2. Click the green Code button.
3. Select Download ZIP.
4. Extract the downloaded ZIP file.
5. Open the extracted project folder.

### Step 2: Open the project in VS Code

1. Open Visual Studio Code.
2. Select **File → Open Folder**.
3. Select the extracted `AI_Study_Planner_with_admin_panel` folder.
4. Open the integrated terminal using:

   `Ctrl + Shift + ~`

### Step 3: Navigate to the application folder

In the terminal, execute:

```bash
cd "AI study timer"
```

This folder contains the main Flask application, `app.py`.

### Step 4: Create a virtual environment

Make sure Python is installed on your computer.

Run:

```bash
python -m venv .venv
```

Activate the virtual environment.

**Windows PowerShell:**

```powershell
.venv\Scripts\Activate.ps1
```

**Windows Command Prompt:**

```cmd
.venv\Scripts\activate.bat
```

### Step 5: Install the dependencies

Run:

```bash
pip install -r requirements.txt
```

This installs the Python packages required by the application.

### Step 6: Start the application

Run:

```bash
python app.py
```

Wait for Flask to start.

### Step 7: Open the application

Open your browser and visit:

`http://127.0.0.1:5000`

You should now be able to access the AI Study Timer locally.

Register or log in using the application's authentication interface. Administrative access depends on the admin account configured in the application.

---

## 📁 Project Structure

```text
AI_Study_Planner_with_admin_panel/
│
├── .gitignore
│
└── AI study timer/
    │
    ├── app.py
    ├── database.py
    ├── study_planner.py
    ├── train_ai.py
    ├── generate_data.py
    ├── study_planner_model.pkl
    ├── data.csv
    ├── requirements.txt
    ├── README.md
    ├── .env.example
    │
    ├── static/
    │   ├── css/
    │   ├── js/
    │   ├── img/
    │   └── video/
    │
    └── templates/
        ├── admin/
        ├── ai_advisor.html
        ├── base.html
        ├── calendar.html
        ├── dashboard.html
        ├── login.html
        ├── progress.html
        └── register.html
```

## 🎯 Why This Project?

Students often struggle with managing their study schedules, maintaining consistency and understanding their academic productivity.

The AI Study Timer aims to address these challenges by combining time management, study planning, progress tracking and AI-assisted functionality in a single web application.

It is designed to make studying more organised, structured and productive.

## 👨‍💻 Developer

**Namit Nigam**

An AI and technology enthusiast interested in Python, Artificial Intelligence, Machine Learning, robotics and software development.

---

*Built with Python, Flask and Machine Learning.*
