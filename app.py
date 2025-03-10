# pip install -r requirements.txt



from flask import Flask, render_template, request, redirect, url_for, flash, session
from firebase_admin import credentials, firestore, initialize_app
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

# Flask app setup
app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Firestore setup
cred = credentials.Certificate('services.json')
initialize_app(cred)
db = firestore.client()
users_collection = db.collection('users')  # Firestore collection for user data
coordinates_collection = db.collection('Coordinates')  # Firestore collection for latitude and longitude

# Routes
@app.route('/')
def home():
    if 'username' in session:
        return redirect(url_for('update_location'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
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
            return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/update_location', methods=['GET', 'POST'])
def update_location():
    if 'username' not in session:
        return redirect(url_for('login'))

    # Initialize form data variables
    form_data = {
        'name': '',
        'latitude': '',
        'longitude': ''
    }

    if request.method == 'POST':
        # Get the name from the form (if provided)
        name = request.form.get('name')

        # If no name is provided, use the last name from the session
        if not name:
            name = session.get('last_location_name')
            if not name:
                flash('Please enter a location name for the first submission.', 'danger')
                return redirect(url_for('update_location'))

        latitude = request.form['latitude']
        longitude = request.form['longitude']

        # Check if a document for this name already exists
        name_doc_ref = coordinates_collection.document(name)
        name_doc = name_doc_ref.get()

        if name_doc.exists:
            # If the document exists, get the last suffix and increment it
            last_suffix = name_doc.to_dict().get('last_suffix', 0)
            new_suffix = last_suffix + 1
        else:
            # If the document doesn't exist, start with suffix 1
            new_suffix = 1

        # Create the new document name with the incremented suffix
        new_doc_name = f"{name}_{new_suffix}"

        try:
            # Create a new document with the unique name
            coordinates_collection.document(new_doc_name).set({
                'name': new_doc_name,  # Store the full name
                'location': f"{latitude},{longitude}"
            })

            # Update the last_suffix for the location name
            name_doc_ref.set({'last_suffix': new_suffix}, merge=True)

            # Store the last used name in the session
            session['last_location_name'] = name

            flash(f'Location updated successfully as {new_doc_name}!', 'success')

            # Repopulate form data
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
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form.get('name')  # Get the name from the form

        if not name:
            flash('Please enter a location name to delete.', 'danger')
            return redirect(url_for('update_location'))

        try:
            # Query Firestore for documents with the given prefix
            docs = coordinates_collection.where('name', '>=', name).where('name', '<=', name + '\uf8ff').stream()

            # Delete all matching documents
            deleted_count = 0
            for doc in docs:
                doc.reference.delete()
                deleted_count += 1

            # Also delete the document tracking the last suffix (if it exists)
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
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
