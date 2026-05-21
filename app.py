import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
import csv
from models import db, User, MoodHistory

app = Flask(__name__)

# Deployment configurations via environment variables
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-antigravity-key')
db_uri = os.environ.get('DATABASE_URL', os.environ.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///antigravity.db'))
if db_uri and db_uri.startswith("postgres://"):
    db_uri = db_uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
bcrypt = Bcrypt(app)

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
        
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already exists.', 'danger')
            return redirect(url_for('signup'))
            
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(name=name, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and user.password and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Login unsuccessful. Check email and password.', 'danger')
    return render_template('login.html')

@app.route('/auth/google')
def auth_google():
    return render_template('google_login.html')

@app.route('/auth/google/callback', methods=['POST'])
def auth_google_callback():
    data = request.get_json() or {}
    email = data.get('email')
    name = data.get('name')
    
    if not email:
        return jsonify({'error': 'Email is required'}), 400
        
    if not name:
        name = email.split('@')[0].capitalize()
        
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(name=name, email=email, password=None, google_id='google_' + email.split('@')[0])
        db.session.add(user)
        db.session.commit()
    elif not user.google_id:
        user.google_id = 'google_' + email.split('@')[0]
        db.session.commit()
        
    login_user(user)
    return jsonify({'success': True, 'redirect': url_for('home')})

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
