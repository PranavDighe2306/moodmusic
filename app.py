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

# ── Core config (set BEFORE OAuth init) ──────────────────────────────────────
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-antigravity-key')

db_uri = os.environ.get('DATABASE_URL',
         os.environ.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///antigravity.db'))
if db_uri and db_uri.startswith("postgres://"):
    db_uri = db_uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ── Mail config ───────────────────────────────────────────────────────────────
app.config['MAIL_SERVER']   = 'smtp.gmail.com'
app.config['MAIL_PORT']     = 587
app.config['MAIL_USE_TLS']  = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['SEND_OTP_EMAIL'] = os.environ.get('SEND_OTP_EMAIL', 'False').lower() in ['true', '1', 'yes']

# ── Google OAuth config (read from .env) ─────────────────────────────────────
app.config['GOOGLE_CLIENT_ID']     = os.environ.get('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET')
app.config['GOOGLE_REDIRECT_URI'] = os.environ.get('GOOGLE_REDIRECT_URI')

# ── Extensions ────────────────────────────────────────────────────────────────
db.init_app(app)
bcrypt  = Bcrypt(app)
mail    = Mail(app)

oauth  = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# ── Helpers ───────────────────────────────────────────────────────────────────
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

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        name     = request.form.get('name')
        email    = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'danger')
            return redirect(url_for('signup'))

        otp = generate_otp()
        session['signup_data'] = {
            'name':     name,
            'email':    email,
            'password': bcrypt.generate_password_hash(password).decode('utf-8'),
        }
        session['otp'] = otp

        if app.config['SEND_OTP_EMAIL'] and app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
            try:
                msg = Message(
                    'MoodMusicz Email Verification',
                    sender=app.config['MAIL_USERNAME'],
                    recipients=[email],
                )
                msg.body = (
                    f"Hello {name},\n\n"
                    f"Your OTP for MoodMusicz account verification is:\n\n{otp}\n\n"
                    "This OTP is valid for a few minutes.\n\n"
                    "Thank you!\nMoodMusicz Team"
                )
                mail.send(msg)
                flash('OTP sent to your email.', 'success')
                return redirect(url_for('verify_otp'))
            except Exception as e:
                print(e)
                flash('Failed to send OTP email.', 'danger')
                return redirect(url_for('signup'))

        # Fallback when email verification is not configured.
        new_user = User(
            name=name,
            email=email,
            password=session['signup_data']['password'],
            is_verified=True,
        )
        db.session.add(new_user)
        db.session.commit()
        session.pop('signup_data', None)
        session.pop('otp', None)
        flash('Account created successfully without email verification.', 'success')
        login_user(new_user)
        return redirect(url_for('home'))

    return render_template('signup.html')

@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        if request.form.get('otp') == session.get('otp'):
            data = session.get('signup_data')
            new_user = User(
                name=data['name'],
                email=data['email'],
                password=data['password'],
                is_verified=True,
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
        email    = request.form.get('email')
        password = request.form.get('password')
        user     = User.query.filter_by(email=email).first()

        if user and user.password and bcrypt.check_password_hash(user.password, password):
            if not user.is_verified:
                flash('Please verify your email first.', 'warning')
                return redirect(url_for('login'))
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Login unsuccessful. Check email and password.', 'danger')

    return render_template('login.html')

# ── Google OAuth routes ───────────────────────────────────────────────────────
@app.route('/auth/google')
def auth_google():
    redirect_uri = app.config['GOOGLE_REDIRECT_URI'] or url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')   # GET only — Google always redirects via GET
def google_callback():
    token = google.authorize_access_token()
    user_info = token.get('userinfo') or token.get('id_token')

    if not user_info:
        flash('Failed to retrieve Google account information.', 'danger')
        return redirect(url_for('login'))

    google_id = user_info.get('sub')
    email = user_info.get('email')
    name = user_info.get('name') or (email.split('@')[0] if email else 'Google User')

    if not email:
        flash('Google account did not provide an email address.', 'danger')
        return redirect(url_for('login'))

    user = None
    if google_id:
        user = User.query.filter_by(google_id=google_id).first()

    if not user:
        user = User.query.filter_by(email=email).first()

    if not user:
        user = User(name=name, email=email, password=None, google_id=google_id, is_verified=True)
        db.session.add(user)
        db.session.commit()
    elif not user.google_id and google_id:
        user.google_id = google_id
        user.is_verified = True
        db.session.commit()

    login_user(user)
    flash(f'Welcome, {user.name}!', 'success')
    return redirect(url_for('home'))

# ── Other routes ──────────────────────────────────────────────────────────────
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/profile')
@login_required
def profile():
    history = MoodHistory.query.filter_by(user_id=current_user.id)\
                               .order_by(MoodHistory.date.desc()).all()
    return render_template('profile.html', history=history)

@app.route('/mood')
def mood():
    mood_type = request.args.get('type', 'happy').lower()
    if current_user.is_authenticated:
        db.session.add(MoodHistory(mood=mood_type, user_id=current_user.id))
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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port       = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']
    app.run(host='0.0.0.0', port=port, debug=debug_mode)