import streamlit as st
import pandas as pd
import random
import mysql.connector
import pickle
import re
import datetime
import sqlalchemy

INSTANCE_CONNECTION_NAME = "prime-bridge-394911:us-central1:task"
DB_USER = "root"
DB_PASS = "123456"
DB_NAME = "hdb"

# Load the best model from the pickle file
# (Make sure to provide the correct file path for your 'best_model.pkl' file)
with open('best_model.pkl', 'rb') as file:
    xgb_model = pickle.load(file)

# Load the pickles for scaler, PCA, and label encoders
# (Make sure to provide the correct file paths for your pickle files)
with open('scaler.pkl', 'rb') as file:
    scaler = pickle.load(file)

with open('pca.pkl', 'rb') as file:
    pca = pickle.load(file)

with open('VEHICLETYPE_label_encoder.pkl', 'rb') as file:
    vehicletype_label_encoder = pickle.load(file)

with open('LABEL_TYPE_label_encoder.pkl', 'rb') as file:
    label_type_label_encoder = pickle.load(file)

# Create a function to preprocess the input data
def preprocess_input_data(data):
    # Handle VEHICLETYPE column (if it has three options 'C', 'M', and 'E')
    data['VEHICLETYPE'] = vehicletype_label_encoder.transform(data['VEHICLETYPE'])

    # Handle TOTAL_CHARGE column (if it's numeric)
    data['TOTAL_CHARGE'] = data['TOTAL_CHARGE'].astype(float)

    # Handle duration column (if it's numeric)
    data['DURATION'] = data['DURATION'].astype(float)

    # Apply the loaded scaler to scale the input features
    scaled_data = scaler.transform(data)

    # Apply PCA to reduce feature dimensions
    pca_data = pca.transform(scaled_data)
    return pca_data

# Create a function to make predictions using the XGBoost model
def predict_label_type(features):
    # Preprocess the input data
    preprocessed_data = preprocess_input_data(features)
    # Make predictions using the XGBoost model
    predictions = xgb_model.predict(preprocessed_data)
    # Inverse transform the label-encoded predictions to get the original labels
    original_predictions = label_type_label_encoder.inverse_transform(predictions)
    return original_predictions

# Function to create a MySQL connection
def create_connection():
    return mysql.connector.connect(
        host=INSTANCE_CONNECTION_NAME,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )

# Function to insert parking data in Database
def insert_parking_details(user_id, vehicle_type, predicted_label, lot_no, duration, total_charge):
    connection = create_connection()
    if connection is not None:
        cursor = connection.cursor()
        query = "SELECT * FROM parkingDetails WHERE user_id = %s"
        data = (user_id,)
        cursor.execute(query, data)
        existing_parking = cursor.fetchone()

        if existing_parking:
            st.warning("You are already parked.")
        else:
            # User is not already parked, proceed with insertion
            query = "INSERT INTO parkingDetails (user_id, vehicle_type, predicted_label, lot_no, duration, session_start, total_charge) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            session_start = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            data = (user_id, vehicle_type, predicted_label, lot_no, duration, session_start, total_charge)
            cursor.execute(query, data)
            connection.commit()
            connection.close()
            # Return the session start timestamp
            return session_start

# Function to validate email
def is_valid_email(email):
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_pattern, email)

# Function to validate name
def is_valid_name(name):
    name_pattern = r'^[a-zA-Z ]+$'
    return re.match(name_pattern, name)

# Function to validate phone number and account number
def is_valid_number(number):
    number_pattern = r'^\d{8}$'
    return re.match(number_pattern, number)

def is_valid_account_number(number):
    number_pattern = r'^\d{7,15}$'
    return re.match(number_pattern, number)

def show_parking_details(user_id):
    connection = create_connection()
    if connection is not None:
        cursor = connection.cursor()
        query = "SELECT * FROM parkingDetails WHERE user_id = %s"
        data = (user_id,)
        cursor.execute(query, data)
        parking_details = cursor.fetchone()
        connection.close()

        if parking_details:
            st.write('User ID:', parking_details[0])
            st.write('Vehicle:', parking_details[1])
            st.write('Predicted Label:', parking_details[2])
            st.write('Allotted lot no:', parking_details[3])
            st.write('Duration:', parking_details[4])
            st.write('Session started at:', parking_details[5])
            st.write('Total Charge:', parking_details[6])
        else:
            st.warning("No parking details found.")

# Function to check parking capacity
def check_parking_capacity():
    connection = create_connection()
    if connection is not None:
        cursor = connection.cursor()
        query = "SELECT lot_no FROM parkingDetails"
        cursor.execute(query)
        all_parked_lots = cursor.fetchall()
        connection.close()

        # Create a set to store allotted lot numbers
        allotted_lots = set(lot[0] for lot in all_parked_lots)

        # Create a set to store not allotted lot numbers
        not_allotted_lots = set(range(1, 501)) - allotted_lots

        # Calculate the percentage of allotted parking lots
        total_allotted = len(allotted_lots)
        total_not_allotted = len(not_allotted_lots)
        percentage = (total_allotted / (total_allotted + total_not_allotted)) * 100

        st.subheader('Parking Capacity Check')
        st.write(f'{percentage:.2f}% of Parking Lot is currently occupied.')
        st.write(f'Allotted Lot Numbers: {", ".join(str(lot) for lot in sorted(allotted_lots))}')

# Function to get a lot number after checking the database
def get_lot_number(range_option):
    connection = create_connection()
    if connection is not None:
        cursor = connection.cursor()
        query = "SELECT lot_no FROM parkingDetails"
        cursor.execute(query)
        alloted_lots = set(lot[0] for lot in cursor.fetchall())
        connection.close()

        if range_option == 1:
            min_lot, max_lot = 1, 160
        elif range_option == 2:
            min_lot, max_lot = 161, 480
        elif range_option == 3:
            min_lot, max_lot = 481, 500
        else:
            raise ValueError("Invalid range_option. It should be 1, 2, or 3.")

        # Generate a random lot number and check if it's already allotted and within the correct range
        while True:
            lot_no = random.randint(min_lot, max_lot)
            if lot_no not in alloted_lots:
                return lot_no

# Function to report parking
def report_parking(user_id, lot_no, vehicle_type, predicted_label, description):
    connection = create_connection()
    if connection is not None:
        cursor = connection.cursor()
        query = "INSERT INTO parkingReports (user_id, lot_no, vehicle_type, predicted_label, description) VALUES (%s, %s, %s, %s, %s)"
        data = (user_id, lot_no, vehicle_type, predicted_label, description)
        cursor.execute(query, data)
        connection.commit()
        connection.close()
        st.success('Parking report submitted successfully!')

# Function to check whether already reported or not
def check_existing_report(user_id):
    connection = create_connection()
    if connection is not None:
        cursor = connection.cursor()
        query = "SELECT * FROM parkingReports WHERE user_id = %s"
        data = (user_id,)
        cursor.execute(query, data)
        existing_report = cursor.fetchone()
        connection.close()
        return existing_report is not None
    return False

# Create a class for session state
class SessionState:
    def __init__(self):
        self.user_logged_in = False
        self.user_details = {}



# Streamlit app
def main():

    st.markdown('<h1 style="color: #1abc9c;">HDB Smart Parking System</h1>', unsafe_allow_html=True)

    # Use SessionState to store user login status and details
    if 'user_session' not in st.session_state:
        st.session_state.user_session = SessionState()

    prediction_successful = False
    option = st.sidebar.radio('Choose an option:', ('Signup', 'Login'))

    # Signup functionality
    if option == 'Signup':
        st.subheader('Signup')
        email = st.text_input('Email')
        name = st.text_input('Name')
        phone = st.text_input('Phone No.')
        bank_options = ['POSB', 'OCBC', 'UOB', 'CITIBANK', 'HSBC']
        bank_name = st.selectbox('Bank Account', bank_options)
        account_no = st.text_input('Bank Account No.')
        billing_address = st.text_input('Billing Address')
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")

        if st.button('Register'):
            # Perform validation checks for input parameters
            if not is_valid_email(email):
                st.error("Invalid email format. Please enter a valid email.")
            elif not is_valid_name(name):
                st.error("Invalid name format. Please enter a valid name (letters and spaces only).")
            elif not is_valid_number(phone):
                st.error("Invalid phone number format. Please enter a valid phone number (numbers only and 8 digits).")
            elif not is_valid_account_number(account_no):
                st.error("Invalid account number format. Please enter a valid account number (within the range 7 to 15 digits).")
            elif password != confirm_password:
                st.error("Password and Confirm Password do not match.")
            else:
                # Check if the email is already present in the database
                connection = create_connection()
                if connection is not None:
                    cursor = connection.cursor()
                    query = "SELECT * FROM userDetails WHERE email = %s"
                    data = (email,)
                    cursor.execute(query, data)
                    existing_user = cursor.fetchone()
                    if existing_user:
                        st.error("This email is already registered. Please use a different email.")
                    else:
                        # Store the user details in the MySQL database
                        query = "INSERT INTO userDetails (email, phone, name, password, bank_name, account_no, billing_address) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                        data = (email, phone, name, password, bank_name, account_no, billing_address)
                        cursor.execute(query, data)
                        connection.commit()
                        connection.close()
                        st.success('User registered successfully!')


    elif option == 'Login':
        st.subheader('Login')
        email = st.text_input('Email')
        password = st.text_input('Password', type='password')

        if st.button('Login'):
            # Check the user credentials in the MySQL database
            connection = create_connection()
            if connection is not None:
                cursor = connection.cursor()
                query = "SELECT * FROM userDetails WHERE email = %s AND password = %s"
                data = (email, password)
                cursor.execute(query, data)
                user = cursor.fetchone()
                connection.close()
                if user:
                    # Update the session state with user details
                    st.session_state.user_session.user_logged_in = True
                    st.session_state.user_session.user_details = {
                        'user_id': user[0],
                        'email': user[1],
                        'name': user[3],
                        'phone': user[2],
                        'bank_name': user[5],
                        'account_no': user[6],
                        'billing_address': user[7]
                    }
                    st.success('Login successful! Welcome, ' + user[3] + '!')


    if st.session_state.user_session.user_logged_in:
        # Access the user details from session state
        user_details = st.session_state.user_session.user_details

        #check already parked, if yes, some details not shown
        connection = create_connection()
        if connection is not None:
            cursor = connection.cursor()
            query = "SELECT * FROM parkingDetails WHERE user_id = %s"
            data = (user_details['user_id'],)
            cursor.execute(query, data)
            existing_parking = cursor.fetchone()
            connection.close()

        # Create input fields for each feature
        st.sidebar.markdown('<h3 style="color: #3498db;">Parking Details</h3>', unsafe_allow_html=True)
        VEHICLETYPE = st.sidebar.selectbox('VEHICLETYPE', ['C', 'M', 'E'])
        TOTAL_CHARGE = st.sidebar.number_input('TOTAL_CHARGE', value=0.0)
        DURATION = st.sidebar.number_input('DURATION', value=0)

        # Combine the feature inputs into a DataFrame with a single row
        input_data = {'VEHICLETYPE': [VEHICLETYPE], 'TOTAL_CHARGE': [TOTAL_CHARGE], 'DURATION': [DURATION]}
        input_df = pd.DataFrame(input_data)

        # Add a colorful start parking button
        if st.sidebar.button('Start Parking'):

            if existing_parking:
                st.warning("You are already parked.")

            # Make predictions when the user clicks the "Predict" button
            else:
                with st.spinner('Predicting...'):
                    # Check if the selected vehicle type is "M"
                    if VEHICLETYPE == 'M':
                        # If the vehicle type is "M" (Motorcycle), provide the specific parking lot information
                        predictions = predict_label_type(input_df)
                        predicted_label = predictions[0]
                        parking_lot_info = 'Motorcycle Parking – Parking Lots 481 – 500'
                    else:
                        # If the vehicle type is not "M", use the XGBoost model to predict the label type
                        predictions = predict_label_type(input_df)
                        predicted_label = predictions[0]
                        parking_lot_info = 'No specific parking lot information available for non-motorcycles.'

                st.success('Prediction completed!')
                prediction_successful = True
                user_id = user_details['user_id']


                # Display the prediction result with the allocated parking lot
                st.subheader('Prediction Result')
                st.write('Type of Parking:', predicted_label)

                if VEHICLETYPE == 'M':
                    lot_no = get_lot_number(3)
                elif predicted_label == 'season_W':
                    lot_no = get_lot_number(1)
                elif predicted_label == 'SHORT TERM':
                    lot_no = get_lot_number(2)

                # Store the parking details in the parkingDetails table
                session_start_timestamp = insert_parking_details(user_id, VEHICLETYPE, predicted_label, lot_no, DURATION, TOTAL_CHARGE)


                    # Add a colorful allocation message based on the predicted label
                if VEHICLETYPE == 'M':
                    st.markdown('<p style="color: #2ecc71; font-size: 18px;">Allocated Parking Lot: Parking Lots 481 – 500</p>', unsafe_allow_html=True)
                elif predicted_label == 'season_W':
                    st.markdown('<p style="color: #e74c3c; font-size: 18px;">Allocated Parking Lot: Parking Lots 161 – 480</p>', unsafe_allow_html=True)
                elif predicted_label == 'SHORT TERM':
                    st.markdown('<p style="color: #e74c3c; font-size: 18px;">Allocated Parking Lot: Parking Lots 1 – 160</p>', unsafe_allow_html=True)
        # Use a button to wrap the report parking input fields

            st.markdown('<style>body{color: #444;}</style>', unsafe_allow_html=True)
            st.markdown('<style>h1{color: #1abc9c;}</style>', unsafe_allow_html=True)
            st.markdown('<style>h2{color: #2ecc71;}</style>', unsafe_allow_html=True)
            st.markdown('<style>h3{color: #3498db;}</style>', unsafe_allow_html=True)
            st.markdown('<style>h4{color: #9b59b6;}</style>', unsafe_allow_html=True)
            st.markdown('<style>h5{color: #f39c12;}</style>', unsafe_allow_html=True)
            st.markdown('<style>h6{color: #e74c3c;}</style>', unsafe_allow_html=True)
            st.markdown('<style>.sidebar .sidebar-content{background-color: #f1c40f;}</style>', unsafe_allow_html=True)
            st.markdown('<style>footer{visibility: hidden;}</style>', unsafe_allow_html=True)

            # Hide Streamlit's default menu button to improve the appearance
            hide_menu_style = """
                    <style>
                    #MainMenu {visibility: hidden;}
                    footer {visibility: hidden;}
                    </style>
                    """
            st.markdown(hide_menu_style, unsafe_allow_html=True)

        st.markdown('<h3 style="color: #e74c3c;">Parking Details</h3>', unsafe_allow_html=True)
        if st.button('Show my Parking Details'):
            show_parking_details(user_details['user_id'])

        st.markdown('<h3 style="color: #e74c3c;">Parking Capacity Check</h3>', unsafe_allow_html=True)
        if st.button('Check Capacity'):
            check_parking_capacity()


        st.markdown('<h3 style="color: #e74c3c;">Report Parking</h3>', unsafe_allow_html=True)

        with st.expander('Report Parking', expanded=False):
            lot_no = st.selectbox('Select parked car lot number', list(range(1, 501)))
            vehicle_type = st.selectbox('Select parked car vehicle type', ['C', 'M', 'E'])
            predicted_label = st.selectbox('Predicted Label', ['SHORT TERM', 'Season_W'])
            description = st.text_area('Describe the issue (optional)', height=100)

            if st.button('Submit Report'):
                if check_existing_report(user_details['user_id']):
                    st.warning("You have already submitted a report.")
                else:
                    report_parking(user_details['user_id'], lot_no, vehicle_type, predicted_label, description)
                    # Clear the fields after submitting the report
                    lot_no = None
                    vehicle_type = None
                    predicted_label = ""
                    description = ""
                    st.success('Parking report submitted successfully!')
    else:
        st.empty()
        st.empty()
        st.empty()
            # Optionally, show a message asking the user to log in first
        st.warning('Please log in to access the dashboard.')

if __name__ == '__main__':
    main()
