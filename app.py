from authlib.integrations.flask_client import OAuth
import os
from dotenv import load_dotenv
load_dotenv()


from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
import csv
from models import db, User, MoodHistory
from flask_mail import Mail, Message
import random

app = Flask(__name__)
app.config['GOOGLE_CLIENT_ID'] = 'your-client-id'
app.config['GOOGLE_CLIENT_SECRET'] = 'your-client-secret'
oauth = OAuth(app)

google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# Deployment configurations via environment variables
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-antigravity-key')
db_uri = os.environ.get('DATABASE_URL', os.environ.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///antigravity.db'))
if db_uri and db_uri.startswith("postgres://"):
    db_uri = db_uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your_app_password'
app.config['MAIL_PASSWORD']

db.init_app(app)
bcrypt = Bcrypt(app)

mail = Mail(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def load_songs():
    data = {}
    with open('songs.csv', newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            mood = row['mood']
            if mood not in data:
                data[mood] = {
                    'langs':   {},
                    'quote':   row['quote'],
                    'bg_from': row['bg_from'],
                    'bg_mid':  row['bg_mid'],
                    'bg_to':   row['bg_to'],
                }
            data[mood]['langs'][row['language']] = row['playlist']
    return data
def generate_otp():
    return str(random.randint(100000, 999999))

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():

    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':

        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash('Email already exists.', 'danger')
            return redirect(url_for('signup'))

        otp = generate_otp()

        session['signup_data'] = {
            'name': name,
            'email': email,
            'password': bcrypt.generate_password_hash(password).decode('utf-8')
        }

        session['otp'] = otp

        try:
            msg = Message(
                'MoodMusicz Email Verification',
                sender=app.config['MAIL_USERNAME'],
                recipients=[email]
            )

            msg.body = f'''
Hello {name},

Your OTP for MoodMusicz account verification is:

{otp}

This OTP is valid for a few minutes.

Thank you!
MoodMusicz Team
'''

            mail.send(msg)

            flash('OTP sent to your email.', 'success')
            return redirect(url_for('verify_otp'))

        except Exception as e:
            print(e)
            flash('Failed to send OTP email.', 'danger')

    return render_template('signup.html')
@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():

    if request.method == 'POST':

        entered_otp = request.form.get('otp')
        real_otp = session.get('otp')

        if entered_otp == real_otp:

            signup_data = session.get('signup_data')

            new_user = User(
                name=signup_data['name'],
                email=signup_data['email'],
                password=signup_data['password'],
                is_verified=True
            )

            db.session.add(new_user)
            db.session.commit()

            session.pop('otp', None)
            session.pop('signup_data', None)

            flash('Account verified successfully!', 'success')

            return redirect(url_for('login'))

        else:
            flash('Invalid OTP.', 'danger')

    return render_template('verify_otp.html')

@app.route('/login', methods=['GET', 'POST'])
def login():

    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and user.password and bcrypt.check_password_hash(user.password, password):

            if not user.is_verified:
                flash('Please verify your email first.', 'warning')
                return redirect(url_for('login'))

            login_user(user)
            return redirect(url_for('home'))

        else:
            flash('Login unsuccessful. Check email and password.', 'danger')

    return render_template('login.html')

@app.route('/auth/google')
def auth_google():
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback', methods=['POST'])
@app.route('/auth/google/callback')
def google_callback():
    token = google.authorize_access_token()
    user_info = token['userinfo']

    email = user_info['email']
    name = user_info['name']

    user = User.query.filter_by(email=email).first()

    if not user:
        user = User(
            name=name,
            email=email,
            password=None,
            is_verified=True
        )
        db.session.add(user)
        db.session.commit()

    login_user(user)

    return redirect(url_for('home'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/profile')
@login_required
def profile():
    history = MoodHistory.query.filter_by(user_id=current_user.id).order_by(MoodHistory.date.desc()).all()
    return render_template('profile.html', history=history)

@app.route('/mood')
def mood():
    mood_type = request.args.get('type', 'happy').lower()
    
    if current_user.is_authenticated:
        history_entry = MoodHistory(mood=mood_type, user_id=current_user.id)
        db.session.add(history_entry)
        db.session.commit()

    songs = load_songs()
    if mood_type not in songs:
        return render_template('index.html')
    d = songs[mood_type]
    return render_template('result.html',
        mood    = mood_type,
        langs   = d['langs'],
        quote   = d['quote'],
        bg_from = d['bg_from'],
        bg_mid  = d['bg_mid'],
        bg_to   = d['bg_to'],
    )

# AI face scanner endpoints removed to clean up heavy dependencies and prevent template errors

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # Dynamic port binding for modern deployment platforms (Render, Heroku, Fly.io, etc.)
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
