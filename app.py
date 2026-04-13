import os
import sqlite3
import uuid
from flask import Flask, render_template, request, redirect, session
from werkzeug.utils import secure_filename
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = "supersecret"

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ---------------- DATABASE ---------------- #
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    print("✅ Creating tables...")

    # STUDENTS TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS students(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll TEXT UNIQUE,
        name TEXT,
        email TEXT,
        password TEXT
    )
    """)

    # CONFIDENTIAL ADMINS
    c.execute("""
    CREATE TABLE IF NOT EXISTS conf_admins(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        role TEXT,
        email TEXT UNIQUE,
        password TEXT
    )
    """)

    # PROFESSIONAL ADMINS
    c.execute("""
    CREATE TABLE IF NOT EXISTS prof_admins(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        role TEXT,
        email TEXT UNIQUE,
        password TEXT
    )
    """)

    # COMPLAINTS TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS complaints(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_id TEXT,
        type TEXT,
        roll TEXT,
        name TEXT,
        year TEXT,
        department TEXT,
        issue TEXT,
        priority TEXT,
        title TEXT,
        description TEXT,
        image TEXT,
        status TEXT DEFAULT 'Pending',
        remarks TEXT,
        assigned_admin TEXT,
        rating INTEGER,
        feedback TEXT
    )
    """)

    conn.commit()
    conn.close()

    print("✅ Database Ready!")
         

# ---------------- ISSUE MAPPING ---------------- #

CONFIDENTIAL_MAPPING = {
    "Attendance": ["HOD"],
    "Marks": ["Class Teacher"],
    "Exam Paper Leak": ["HOD"],
    "Ragging": ["HOD"],
    "Faculty Explanation": ["CR","Class Teacher","HOD"],
    "Favoritism": ["Class Teacher"],
    "Irregular Classes": ["CR"],
    "Lack of Syllabus Coverage": ["Class Teacher"],
    "Not Providing Study Material": ["Class Teacher"],
    "Class Discipline": ["CR","Class Teacher","HOD"]
}

PROFESSIONAL_MAPPING = {
    "Library Facility": ["Library Management"],
    "Hostel Facility": ["Nagendra Sir"],
    "Water & Plumbing": ["Subareddy"],
    "Electricity Issues": ["Subareddy"],
    "Fee Related Issues": ["Account Section"],
    "Poor Internet/Wifi": ["HOD","Principal"],
    "Transport Issues": ["Principal"],
    "Canteen": ["HOD"],
    "Lab & Equipment": ["HOD","Principal"]
}
ADMIN_EMAILS = {

    # Confidential Admins
    "CR": "cr_admin@gmail.com",
    "Class Teacher": "saiswarupakoduru316@gmail.com",
    "HOD": "sujanakommera@gmail.com",

    # Professional Admins
    "Library Management": "library_admin@gmail.com",
    "Nagendra Sir": "hostel_admin@gmail.com",
    "Subareddy": "maintenance_admin@gmail.com",
    "Account Section": "shiva16140@gmail.com",
    "Principal": "jagadeeshkoduru9494@gmail.com"

}

# ---------------- HOME ---------------- #

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/student")
def student():
    return render_template("student.html")
# ---------------- STUDENT REGISTER ---------------- #

@app.route("/student_register", methods=["GET","POST"])
def student_register():

    if request.method == "POST":

        roll = request.form["roll"]
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("SELECT * FROM students WHERE roll=?", (roll,))
        if c.fetchone():
            conn.close()
            return "Student already registered"

        c.execute("""
        INSERT INTO students (roll,name,email,password)
        VALUES (?,?,?,?)
        """,(roll,name,email,password))

        conn.commit()
        conn.close()

        return redirect("/student_login")

    return render_template("student_register.html")


# ---------------- STUDENT LOGIN ---------------- #

@app.route("/student_login", methods=["GET","POST"])
def student_login():

    if request.method == "POST":

        roll = request.form["roll"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("""
        SELECT * FROM students
        WHERE roll=? AND password=?
        """,(roll,password))

        student = c.fetchone()
        conn.close()

        if student:
            session["student"] = student[2]
            session["roll"] = student[1]
            return redirect("/student_dashboard")

        return "Invalid Login"

    return render_template("student_login.html")

# ---------------- STUDENT DASHBOARD ---------------- #

@app.route("/student_dashboard")
def student_dashboard():

    if "student" not in session:
        return redirect("/student_login")

    roll = session["roll"]

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
        SELECT * FROM complaints
        WHERE roll=?
    """,(roll,))

    complaints = c.fetchall()
    conn.close()

    return render_template("student_dashboard.html",
                           complaints=complaints)
#-------------------Feedback-------------------------------#
@app.route("/feedback/<tracking>", methods=["GET","POST"])
def feedback(tracking):

    if "student" not in session:
        return redirect("/student_login")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # Get complaint
    c.execute("SELECT * FROM complaints WHERE tracking_id=?", (tracking,))
    complaint = c.fetchone()

    # ✅ Allow only if resolved
    if complaint[12] != "Resolved":
        conn.close()
        return "Feedback allowed only after complaint is resolved"

    if request.method == "POST":

        rating = request.form["rating"]
        feedback = request.form["feedback"]

        c.execute("""
        UPDATE complaints
        SET rating=?, feedback=?
        WHERE tracking_id=?
        """,(rating, feedback, tracking))

        conn.commit()
        conn.close()

        return redirect("/track")

    conn.close()

    return render_template("feedback.html", complaint=complaint)

# ---------------- CONFIDENTIAL COMPLAINT ---------------- #

@app.route("/confidential", methods=["GET","POST"])
def confidential():

    if request.method == "POST":

        issue = request.form["issue"]
        title = request.form["title"]
        description = request.form["description"]

        tracking_id = str(uuid.uuid4())[:8]
        assigned_admin = ",".join(CONFIDENTIAL_MAPPING[issue])

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("""
        INSERT INTO complaints
        (tracking_id,type,issue,title,description,assigned_admin)
        VALUES (?,?,?,?,?,?)
        """,
        (tracking_id,"Confidential",issue,title,description,assigned_admin))

        conn.commit()
        conn.close()

        # -------- SEND EMAIL TO ADMINS -------- #

        admins = CONFIDENTIAL_MAPPING[issue]

        for role in admins:

            email = ADMIN_EMAILS.get(role)

            if email:

                subject = "New Confidential Complaint Raised"

                body = f"""
New Complaint Submitted

Tracking ID: {tracking_id}
Issue: {issue}
Title: {title}

Description:
{description}

Please login to the system to review the complaint.
"""

                send_email(email, subject, body)

        return f"Complaint Submitted! Tracking ID: {tracking_id}"

    return render_template("confidential.html",
                           issues=CONFIDENTIAL_MAPPING.keys())
# ---------------- CONF ADMIN REGISTER ---------------- #

@app.route("/conf_register", methods=["GET","POST"])
def conf_register():

    if request.method == "POST":

        name = request.form["name"]
        role = request.form["role"]
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("SELECT * FROM conf_admins WHERE email=?", (email,))
        if c.fetchone():
            conn.close()
            return "Email already registered"

        c.execute("INSERT INTO conf_admins (name,role,email,password) VALUES (?,?,?,?)",
                  (name,role,email,password))

        conn.commit()
        conn.close()

        return redirect("/conf_login")

    return render_template("conf_register.html")

# ---------------- CONF ADMIN LOGIN ---------------- #

@app.route("/conf_login", methods=["GET","POST"])
def conf_login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("""
        SELECT * FROM conf_admins
        WHERE email=? AND password=?
        """,(email,password))

        admin = c.fetchone()
        conn.close()

        if admin:
            session["conf_admin"] = admin[2]
            return redirect("/conf_dashboard")

        return "Invalid Login"

    return render_template("conf_login.html")

# ---------------- PROFESSIONAL COMPLAINT ---------------- #

@app.route("/professional", methods=["GET","POST"])
def professional():

    if request.method == "POST":

        roll = request.form["roll"]
        name = request.form["name"]
        year = request.form["year"]
        dept = request.form["department"]
        issue = request.form["issue"]
        priority = request.form["priority"]
        title = request.form["title"]
        description = request.form["description"]

        file = request.files["image"]
        filename = ""

        if file and file.filename != "":
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        tracking_id = str(uuid.uuid4())[:8]
        assigned_admin = ",".join(PROFESSIONAL_MAPPING[issue])

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("""
        INSERT INTO complaints
        (tracking_id,type,roll,name,year,department,
        issue,priority,title,description,image,assigned_admin)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (tracking_id,"Professional",roll,name,year,dept,
         issue,priority,title,description,filename,assigned_admin))

        conn.commit()
        conn.close()

        # -------- SEND EMAIL TO RESPONSIBLE ADMINS -------- #

        admins = PROFESSIONAL_MAPPING[issue]

        for role in admins:

            email = ADMIN_EMAILS.get(role)

            if email:

                subject = "New Professional Complaint Raised"

                body = f"""
New Complaint Submitted

Tracking ID: {tracking_id}

Student Name: {name}
Roll Number: {roll}
Year: {year}
Department: {dept}

Issue: {issue}
Title: {title}

Description:
{description}

Please login to the complaint system to review it.
"""

                send_email(email, subject, body)

        return f"Complaint Submitted! Tracking ID: {tracking_id}"

    return render_template("professional.html",
                           issues=PROFESSIONAL_MAPPING.keys())

# ---------------- PROF ADMIN REGISTER ---------------- #

@app.route("/prof_register", methods=["GET","POST"])
def prof_register():

    if request.method == "POST":

        name = request.form["name"]
        role = request.form["role"]
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("SELECT * FROM prof_admins WHERE email=?", (email,))
        if c.fetchone():
            conn.close()
            return "Email already registered"

        c.execute("INSERT INTO prof_admins (name,role,email,password) VALUES (?,?,?,?)",
                  (name,role,email,password))

        conn.commit()
        conn.close()

        return redirect("/prof_login")

    return render_template("prof_register.html")

# ---------------- PROF ADMIN LOGIN ---------------- #

@app.route("/prof_login", methods=["GET","POST"])
def prof_login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("""
        SELECT * FROM prof_admins
        WHERE email=? AND password=?
        """,(email,password))

        admin = c.fetchone()
        conn.close()

        if admin:
            session["prof_admin"] = admin[2]
            return redirect("/prof_dashboard")

        return "Invalid Login"

    return render_template("prof_login.html")

# ---------------- CONF DASHBOARD ---------------- #

@app.route("/conf_dashboard")
def conf_dashboard():
    if "conf_admin" not in session:
        return redirect("/conf_login")

    role = session["conf_admin"]
    selected_issue = request.args.get("issue")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if selected_issue:
        c.execute("""
            SELECT * FROM complaints
            WHERE type='Confidential'
            AND assigned_admin LIKE ?
            AND issue=?
        """, ('%'+role+'%', selected_issue))
    else:
        c.execute("""
            SELECT * FROM complaints
            WHERE type='Confidential'
            AND assigned_admin LIKE ?
        """, ('%'+role+'%',))

    complaints = c.fetchall()
    conn.close()

    assigned_issues = [i for i,a in CONFIDENTIAL_MAPPING.items() if role in a]

    return render_template("conf_dashboard.html",
                           complaints=complaints,
                           issues=assigned_issues,
                           role=role)

# ---------------- PROF DASHBOARD ---------------- #

@app.route("/prof_dashboard")
def prof_dashboard():
    if "prof_admin" not in session:
        return redirect("/prof_login")

    role = session["prof_admin"]
    selected_issue = request.args.get("issue")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if selected_issue:
        c.execute("""
            SELECT * FROM complaints
            WHERE type='Professional'
            AND assigned_admin LIKE ?
            AND issue=?
        """, ('%'+role+'%', selected_issue))
    else:
        c.execute("""
            SELECT * FROM complaints
            WHERE type='Professional'
            AND assigned_admin LIKE ?
        """, ('%'+role+'%',))

    complaints = c.fetchall()
    conn.close()

    assigned_issues = [i for i,a in PROFESSIONAL_MAPPING.items() if role in a]

    return render_template("prof_dashboard.html",
                           complaints=complaints,
                           issues=assigned_issues,
                           role=role)

# ---------------- VIEW COMPLAINT ---------------- #

@app.route("/view/<tracking>")
def view_complaint(tracking):

    if "conf_admin" not in session and "prof_admin" not in session:
        return redirect("/")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT * FROM complaints WHERE tracking_id=?", (tracking,))
    complaint = c.fetchone()

    if complaint and complaint[11] == "Pending":
        c.execute("UPDATE complaints SET status='Viewed' WHERE tracking_id=?", (tracking,))
        conn.commit()

        c.execute("SELECT * FROM complaints WHERE tracking_id=?", (tracking,))
        complaint = c.fetchone()

    conn.close()

    return render_template("view_complaint.html", complaint=complaint)

# ---------------- UPDATE STATUS ---------------- #

@app.route("/update/<tracking>", methods=["POST"])
def update_status(tracking):
    status = request.form["status"]
    remarks = request.form["remarks"]

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
        UPDATE complaints
        SET status=?, remarks=?
        WHERE tracking_id=?
    """, (status, remarks, tracking))

    conn.commit()
    conn.close()

    return redirect(request.referrer)

# ---------------- TRACK ---------------- #
# ---------------- TRACK ---------------- #

@app.route("/track", methods=["GET","POST"])
def track():
    result = None
    message = ""

    if request.method == "POST":
        # Get tracking id and remove spaces
        tid = request.form.get("tracking", "").strip()

        if tid:
            conn = sqlite3.connect("database.db")
            c = conn.cursor()

            # Case-insensitive match
            c.execute("""
                SELECT * FROM complaints
                WHERE LOWER(tracking_id) = LOWER(?)
            """, (tid,))

            result = c.fetchone()
            conn.close()

            if not result:
                message = "Invalid Tracking ID"
        else:
            message = "Please enter Tracking ID"

    return render_template("track.html",
                           result=result,
                           message=message)
# ---------------- PRINCIPAL LOGIN ---------------- #

@app.route("/principal_login", methods=["GET","POST"])
def principal_login():
    if request.method == "POST":
        session["principal"] = "Principal"
        return redirect("/principal_dashboard")
    return render_template("principal_login.html")

# ---------------- PRINCIPAL DASHBOARD ---------------- #

@app.route("/principal_dashboard")
def principal_dashboard():

    if "principal" not in session:
        return redirect("/principal_login")

    complaint_type = request.args.get("type")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if complaint_type == "Confidential":
        c.execute("SELECT * FROM complaints WHERE type='Confidential'")
        complaints = c.fetchall()

    elif complaint_type == "Professional":
        c.execute("SELECT * FROM complaints WHERE type='Professional'")
        complaints = c.fetchall()

    else:
        complaints = []

    conn.close()

    return render_template("principal_dashboard.html",
                           complaints=complaints,
                           complaint_type=complaint_type)




def send_email(to_email, subject, body):

    sender_email = "sujanakommera123@gmail.com"
    sender_password = "hnuybqocfnpowzly"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
    except:
        print("Email sending failed")

# ---------------- LOGOUT ---------------- #

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- RUN ---------------- #

if __name__ == "__main__":

    # ✅ Create DB if not exists
    if not os.path.exists("database.db"):
        print("📁 Database not found. Creating new database...")
        init_db()
    else:
        print("✅ Database already exists")

    app.run(debug=True)