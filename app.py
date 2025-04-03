from flask import Flask, render_template, request, redirect, url_for, flash, session
from firebase_admin import credentials, firestore, initialize_app
from werkzeug.security import generate_password_hash, check_password_hash
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
import firebase_admin

# Flask app setup
app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Firestore setup
load_dotenv()

cred = credentials.Certificate({
    "type": os.getenv("FIREBASE_TYPE"),
    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace('\\n', '\n'),
    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
    "auth_uri": os.getenv("FIREBASE_AUTH_URI"),
    "token_uri": os.getenv("FIREBASE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_CERT_URL"),
    "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL")
})

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()
users_collection = db.collection('users')
coordinates_collection = db.collection('Coordinates')
complaints_collection = db.collection('Complaints')

@app.route('/')
def landing_page():
    return render_template('landing.html')

@app.route('/report_complaint', methods=['POST'])
def report_complaint():
    if request.method == 'POST':
        name = request.form.get('name')
        complaint = request.form.get('complaint')
        location = request.form.get('location')

        if name and complaint and location:
            try:
                complaints_collection.add({
                    'name': name,
                    'complaint': complaint,
                    'location': location,
                    'status': 'pending',
                    'reported_at': firestore.SERVER_TIMESTAMP
                })
                flash('Complaint reported successfully!', 'success')
            except Exception as e:
                flash(f'Error: {str(e)}', 'danger')
        else:
            flash('Please fill all fields.', 'danger')

    return redirect(url_for('landing_page'))

@app.route('/view_complaints')
def view_complaints():
    if 'username' not in session:
        return redirect(url_for('admin_login'))
    
    complaints_ref = db.collection('Complaints')
    complaints = complaints_ref.where('status', '!=', 'completed').stream()
    
    complaints_list = []
    for complaint in complaints:
        complaint_data = complaint.to_dict()
        complaint_data['id'] = complaint.id
        complaints_list.append(complaint_data)
    
    return render_template('complaints.html', complaints=complaints_list)

@app.route('/mark_completed', methods=['POST'])
def mark_completed():
    if 'username' not in session:
        return redirect(url_for('admin_login'))
    
    complaint_id = request.form.get('complaint_id')
    if complaint_id:
        try:
            db.collection('Complaints').document(complaint_id).update({
                'status': 'completed',
                'resolved_by': session['username'],
                'resolved_at': firestore.SERVER_TIMESTAMP
            })
            flash('Complaint marked as completed!', 'success')
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('view_complaints'))

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_doc = users_collection.document(username).get()

        if user_doc.exists and check_password_hash(user_doc.to_dict()['password'], password):
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('update_location'))
        else:
            flash('Invalid username or password', 'danger')
            return redirect(url_for('landing_page'))  # Redirect to landing page

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        if users_collection.document(username).get().exists:
            flash('Username already exists.', 'danger')
        else:
            users_collection.document(username).set({'password': hashed_password})
            flash('Signup successful! Please log in.', 'success')
            return redirect(url_for('admin_login'))

    return render_template('signup.html')

@app.route('/update_location', methods=['GET', 'POST'])
def update_location():
    if 'username' not in session:
        return redirect(url_for('admin_login'))

    # Initialize form data variables
    form_data = {
        'name': '',
        'latitude': '',
        'longitude': ''
    }

    if request.method == 'POST':
        name = request.form.get('name')

        if not name:
            name = session.get('last_location_name')
        
        if not name:
            flash('Please enter a location name for the first submission.', 'danger')
            return render_template('update_location.html', form_data=form_data)

        latitude = request.form['latitude']
        longitude = request.form['longitude']

        name_doc_ref = coordinates_collection.document(name)
        name_doc = name_doc_ref.get()

        if name_doc.exists:
            last_suffix = name_doc.to_dict().get('last_suffix', 0)
            new_suffix = last_suffix + 1
        else:
            new_suffix = 1

        new_doc_name = f"{name}_{new_suffix}"

        try:
            coordinates_collection.document(new_doc_name).set({
                'name': new_doc_name,
                'location': f"{latitude},{longitude}"
            })

            name_doc_ref.set({'last_suffix': new_suffix}, merge=True)
            session['last_location_name'] = name

            flash(f'Location updated successfully as {new_doc_name}!', 'success')

            form_data = {
                'name': name,
                'latitude': latitude,
                'longitude': longitude
            }

        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')

    return render_template('update_location.html', form_data=form_data)

@app.route('/delete_location', methods=['POST'])
def delete_location():
    if 'username' not in session:
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        name = request.form.get('name')

        if not name:
            flash('Please enter a location name to delete.', 'danger')
            return redirect(url_for('update_location'))

        try:
            docs = coordinates_collection.where('name', '>=', name).where('name', '<=', name + '\uf8ff').stream()
            deleted_count = 0
            for doc in docs:
                doc.reference.delete()
                deleted_count += 1

            name_doc_ref = coordinates_collection.document(name)
            if name_doc_ref.get().exists:
                name_doc_ref.delete()

            flash(f'Successfully deleted {deleted_count} documents with prefix "{name}".', 'success')

        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('update_location'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('landing_page'))

if __name__ == '__main__':
    app.run(debug=True)
