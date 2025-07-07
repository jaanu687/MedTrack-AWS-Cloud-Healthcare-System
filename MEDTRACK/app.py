from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import uuid
import boto3  # <-- AWS SDK added

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Temporary in-memory "databases"
users = {}
appointments = []

# AWS Setup
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')  # ✅ Set your region
sns = boto3.client('sns', region_name='us-east-1')

# DynamoDB tables
users_table = dynamodb.Table('Users')  # Ensure this table exists in AWS
appointments_table = dynamodb.Table('Appointments')

# Your SNS Topic ARN (replace with real one)
sns_topic_arn = 'arn:aws:sns:us-east-1:123456789012:YourSNSTopic'  # <-- Replace with actual ARN


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if username in users:
            flash('Username already exists.', 'error')
        elif password != confirm_password:
            flash('Passwords do not match.', 'error')
        else:
            users[username] = {'email': email, 'password': password}

            # ✅ Save user to DynamoDB
            try:
                users_table.put_item(Item={
                    'username': username,
                    'email': email,
                    'password': password
                })

                # ✅ Send SNS notification
                sns.publish(
                    TopicArn=sns_topic_arn,
                    Message=f"New user signup: {username} ({email})",
                    Subject="Signup Alert"
                )
            except Exception as e:
                flash(f"DynamoDB/SNS error: {str(e)}", 'error')

            flash('Signup successful! Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = users.get(username)

        if user and user['password'] == password:
            session['username'] = username
            flash('Login successful.', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials.', 'error')

    return render_template('login.html')


@app.route('/home')
def home():
    if 'username' not in session:
        flash('Please log in first.', 'error')
        return redirect(url_for('login'))

    username = session['username']
    user = users.get(username)
    role = user.get('role')

    today = datetime.today().strftime('%Y-%m-%d')

    if role == 'doctor':
        doctor_appts = [a for a in appointments if a['doctor'] == username]
        total_appointments = len(doctor_appts)
        pending_appointments = [a for a in doctor_appts if a['date'] >= today]

        return render_template('home.html',
            role=role,
            doctor_name=username,
            total_appointments=total_appointments,
            pending_appointments=len(pending_appointments),
            appointments_list=doctor_appts
        )

    else:  # patient
        user_appts = [a for a in appointments if a['user'] == username]
        upcoming = [a for a in user_appts if a['date'] >= today]

        return render_template('home.html',
            role=role,
            username=username,
            total_appointments=len(user_appts),
            upcoming_appointments=len(upcoming),
            upcoming_appointments_list=upcoming
        )


@app.route('/book_appointment', methods=['GET', 'POST'])
def book_appointment():
    if 'username' not in session:
        flash('Please log in to book an appointment.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        appointment = {
            'appointment_id': str(uuid.uuid4()),
            'user': session['username'],
            'patient': request.form['patient_name'],
            'doctor': request.form['doctor'],
            'date': request.form['date'],
            'time': request.form['time'],
            'reason': request.form.get('reason', '')
        }
        appointments.append(appointment)

        # ✅ Save appointment to DynamoDB
        try:
            appointments_table.put_item(Item=appointment)

            # ✅ Send SNS notification
            sns.publish(
                TopicArn=sns_topic_arn,
                Message=f"New appointment booked by {appointment['user']} with Dr. {appointment['doctor']} on {appointment['date']} at {appointment['time']}",
                Subject="New Appointment Booking"
            )
        except Exception as e:
            flash(f"DynamoDB/SNS error: {str(e)}", 'error')

        flash('Appointment booked successfully! Redirecting to home page...', 'success')
        return redirect(url_for('home'))

    return render_template('book_appointment.html')


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')

        if not name or not email or not message:
            flash('Please fill in all fields.', 'error')
        else:
            flash('Thank you for contacting us!', 'success')
        return redirect(url_for('contact'))

    return render_template('contact.html')


@app.route('/doctor_dashboard')
def doctor_dashboard():
    if 'username' not in session:
        flash('Please log in to access the doctor dashboard.', 'error')
        return redirect(url_for('login'))

    doctor_name = session['username']
    today = datetime.today().strftime('%Y-%m-%d')

    doctor_appts = [a for a in appointments if a['doctor'] == doctor_name]
    total_appointments = len(doctor_appts)
    pending_appointments = [a for a in doctor_appts if a['date'] >= today]

    return render_template('doctor_dashboard.html',
        doctor_name=doctor_name,
        total_appointments=total_appointments,
        pending_appointments=len(pending_appointments),
        appointments_list=doctor_appts
    )


@app.route('/patient_dashboard')
def patient_dashboard():
    if 'username' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('login'))

    username = session['username']
    today = datetime.today().strftime('%Y-%m-%d')
    user_appts = [a for a in appointments if a['user'] == username]
    upcoming = [a for a in user_appts if a['date'] >= today]

    return render_template('patient_dashboard.html',
        username=username,
        total_appointments=len(user_appts),
        upcoming_appointments=len(upcoming),
        upcoming_appointments_list=upcoming
    )


@app.route('/patient_appointments')
def patient_appointments():
    if 'username' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('login'))

    user_appts = [a for a in appointments if a['user'] == session['username']]
    return render_template('patient_appointments.html', appointments=user_appts)


@app.route('/patient_details')
def patient_details():
    if 'username' not in session:
        flash('Please log in to view your details.', 'error')
        return redirect(url_for('login'))

    username = session['username']
    user = users.get(username)

    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('login'))

    return render_template('patient_details.html', username=username, email=user['email'])


@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
