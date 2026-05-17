import os

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
import csv
from models import db, User, MoodHistory

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-antigravity-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///antigravity.db'
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
    flash('Google login is not fully configured yet. Please use email.', 'info')
    return redirect(url_for('login'))

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

@app.route('/scanner')
def scanner():
    return render_template('scanner.html')

@app.route('/api/detect_emotion', methods=['POST'])
def detect_emotion():
    try:
        import base64
        import cv2
        import numpy as np
        from deepface import DeepFace
        data = request.json
        image_data = data['image'].split(',')[1]
        nparr = np.frombuffer(base64.b64decode(image_data), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        result = DeepFace.analyze(img, actions=['emotion'], enforce_detection=False)
        emotion = result[0]['dominant_emotion'] if isinstance(result, list) else result['dominant_emotion']
        
        # Mapping DeepFace emotions to our app moods
        mood_map = {
            'happy': 'happy',
            'sad': 'sad',
            'angry': 'angry',
            'fear': 'tired',
            'disgust': 'angry',
            'surprise': 'party',
            'neutral': 'chill'
        }
        mapped_mood = mood_map.get(emotion, 'chill')
        
        return jsonify({'emotion': emotion, 'mapped_mood': mapped_mood})
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', debug=True)
