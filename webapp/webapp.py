from flask import Flask, Response, request, jsonify, make_response
from numpy import genfromtxt
from sqlalchemy import create_engine, Column, String, Integer, TIMESTAMP, func, ForeignKey, CheckConstraint
from sqlalchemy_utils import database_exists, create_database
from sqlalchemy.dialects.postgresql import UUID, VARCHAR
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.engine.reflection import Inspector
import psycopg2
import uuid
import os
from flask_bcrypt import Bcrypt
from flask_httpauth import HTTPBasicAuth
from dotenv import load_dotenv
import logging
import json

# Create a custom JSON formatter for logging in json format
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "function": record.funcName,
            "module": record.module,
        }
        return json.dumps(log_data)

# Create a custom logger
logger = logging.getLogger('webapp')
logger.setLevel(logging.INFO)

# Create a file handler and set the log level
file_handler = logging.FileHandler("/opt/webapp.log")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(JsonFormatter())

# Add the file handler to the logger
logger.addHandler(file_handler)

# Create instances of Flask, Bcrypt, and HTTPBasicAuth
app = Flask(__name__)
bcrypt = Bcrypt(app)
auth = HTTPBasicAuth()

# Define the file path to fetch database details from
file_path = '/opt/webapp.properties'
if os.path.exists(file_path):
    load_dotenv(file_path)
    # log info to the log file
    logger.info(f'Fetching database credentials from location: {file_path}')
else:
    load_dotenv()
    # log info to the log file
    logger.info('Fetching database credentials from environment variables')

# Get database details from environment file
rds_hostname = os.getenv("RDS_HOSTNAME")
rds_username = os.getenv("RDS_USERNAME")
rds_password = os.getenv("RDS_PASSWORD")
rds_database = os.getenv("RDS_DATABASE")
database_url = os.getenv("DATABASE_URL")

# Log info level log messages to the log file
logger.info("Value fetched for rds_hostname")
logger.info("Value fetched for rds_username")
logger.info("Value fetched for rds_password")
logger.info("Value fetched for rds_database")
logger.info("Value fetched for database_url")

# Function to apply bcrypt encryption to all the user passwords in the database
def encrypt(password):
    encrypted_password = bcrypt.generate_password_hash(password).decode('utf-8')
    return encrypted_password

# Create Database if it does not already exist
engine = create_engine(database_url)
if database_exists(engine.url):
    # log database exist warning to the log file
    logger.warning(f"Database \'{rds_database}\' already exist")
if not database_exists(engine.url):
    create_database(engine.url)
    # log database created info to the log file
    logger.info(f"Created database \'{rds_database}\'")

# Function to establish a connection to the database
def check_db_connection():
    
    try:
        db_connection = psycopg2.connect(database_url)
        # log connection info to the log file
        logger.info(f'Successfully connected to the database \'{rds_database}\'')

        db_connection.close()
        return True
    
    except Exception as e:
        # log connection error to the log file
        logger.error(f'Error occurred while trying to connect to the database \'{rds_database}\': {e}')
        return False

# If database connection is successful, then run below functions
if check_db_connection():
        # Function to load data from csv
        def LoadData(file_name):
            data = genfromtxt(file_name, delimiter=',', skip_header=1, dtype=str)
            return data.tolist()
        
        # Function to add data from csv file to Account table
        def add_user_data():
            Session = sessionmaker(bind=engine)
            session = Session()
            try:
                file_name = "./users.csv"
                if os.path.exists("/opt/users.csv"):
                    file_name = "/opt/users.csv"
                data = LoadData(file_name) # Call LoadData function to load the data from csv

                # Loop to add one row at a time from data variable
                for i in data:
                    if not session.query(Account).filter_by(email = i[2]).first():
                        i[3] = encrypt(i[3]) # Calling encrypt function to encrypt user's password
                        record = Account(**{
                            'first_name': i[0],
                            'last_name': i[1],
                            'email': i[2],
                            'password': i[3]
                            })
                        session.add(record)
                        session.commit()
                        # log data insertion info to the log file
                        logger.info(f"Data inserted successfully to \'Account\' table")
                    else:
                        # log warning for duplicate data entry attempt to the log file
                        logger.warning(f"Data for the user already exist in \'Account\' table")
                        continue
            except Exception as e:
                session.rollback()
                # log error to the log file
                logger.error(f"Error occurred while trying to add data to \'Account\' table: {e}")
            finally:
                session.close()
                # log info to the log file
                logger.info("Session for adding data to '\Account'\ table closed")

        # Create session
        Session = sessionmaker(bind=engine)
        session = Session()

        Base = declarative_base()

        #Defining table schema
        class Account(Base):
            __tablename__ = 'Account'

            id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True)
            first_name = Column(VARCHAR(80).with_variant(String(80), "postgresql"), nullable=False)
            last_name = Column(VARCHAR(80).with_variant(String(80), "postgresql"), nullable=False)
            email = Column(VARCHAR(100).with_variant(String(100), "postgresql"), nullable=False, unique=True)
            password = Column(String, nullable=False)
            account_created = Column(TIMESTAMP(), server_default=func.now())
            account_updated = Column(TIMESTAMP(), server_default=func.now())

        class Assignment(Base):
            __tablename__ = 'Assignment'

            id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True)
            name = Column(String, nullable=False, unique=True)
            points = Column(Integer, nullable=False) # must be between 1 to 100
            num_of_attempts = Column(Integer, nullable=False)# Max attempts should be between 1 and 3 inclusively
            deadline = Column(TIMESTAMP(), nullable=False)
            assignment_created = Column(TIMESTAMP(), server_default=func.now())
            assignment_updated = Column(TIMESTAMP(), server_default=func.now(), onupdate=func.now())
            created_by  = Column(UUID(as_uuid=True), ForeignKey('Account.id')) # foreign key to build a relationship between Account & Assignment tables

            account = relationship('Account', backref='assignments')

            # Column level check constraints to limit value ranges for points and num_of_attempts
            __table_args__ = (CheckConstraint('points >= 1 AND points <= 100', name='check_points_range'),
                              CheckConstraint('num_of_attempts >= 1 AND num_of_attempts <=3', name='check_num_of_attempts'),
            )


        # Create all schemas
        Base.metadata.create_all(engine)

        # Get a list of table names using the Inspector
        inspector = Inspector.from_engine(engine)
        table_names = inspector.get_table_names()

        # log table names to the log file
        logger.info(f"Tables created: {', '.join(table_names)}")

        # Add data to Account schema
        add_user_data()

# Set headers for all the responses
@app.after_request
def set_response_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Type'] = 'application/json'
    return response

# healthz endpoint configuration - checks connection of the webapp with the database
@app.route('/healthz', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def health_check_api():
    # if connection to database is successful and request is GET
    if check_db_connection() and request.method == 'GET':
        # condition to not allow any arguments with the GET request
        if (request.args) or (request.data) or (request.form) or (request.files):
            response = Response(status=400)
            # log warning when status response is 400 to the log file
            logger.warning(f"GET request to /healthz returned status {response.status_code} for a bad request - NO payload allowed")
            return response
        else:
            response = Response(status=200)
            # log info when status response is 200 to the log file
            logger.info(f"GET request to /healthz returned status {response.status_code} for a successful request")
            return response
    # if the request is not GET
    elif not request.method == 'GET':
        response = Response(status=405)
        # log warning when status response is 405 to the log file
        logger.warning(f"Request to /healthz returned status {response.status_code} for a method not allowed - ONLY GET method is allowed")
        return response
    # if database connection is unsuccessful
    else:
        response = Response(status=503)
        # log error when status response is 503 to the log file
        logger.error(f"Request to /healthz returned status {response.status_code} for service unavailable - Database connection failure")
        return response

# /v1/assignments endpoint configuration for GET request - returns a list of assignments
@app.route('/v1/assignments', methods=['GET'])
@auth.login_required # checks if the user requesting the access is authenticated
def get_assignments():
    # if database connection is unsuccessful
    if not check_db_connection():
            response = Response(status=503)
            logger.error(f"GET request to /v1/assignments returned status {response.status_code} for service unavailable - Database connection failure")
            return response
    # condition to not allow any arguments with the GET request
    if (request.args) or (request.data) or (request.form) or (request.files):
        response = Response(status=400)
        logger.warning(f"GET request to /v1/assignments returned status {response.status_code} for a bad request - NO payload allowed")
        return response
    # if the request is authenticated and valid, query the database to fetch the data
    else:
        assignments = session.query(Assignment).all()
        output = []

        for assignment in assignments:
            assignment_data = {}
            assignment_data['id'] = assignment.id
            assignment_data['name'] = assignment.name
            assignment_data['points'] = assignment.points
            assignment_data['num_of_attempts'] = assignment.num_of_attempts
            assignment_data['deadline'] = assignment.deadline
            assignment_data['assignment_created'] = assignment.assignment_created
            assignment_data['assignment_updated'] = assignment.assignment_updated
            assignment_data['created_by'] = assignment.created_by
            output.append(assignment_data)
        response = Response(status=200)
        logger.info(f"GET request to /v1/assignments returned status {response.status_code} for a successful request")
        return jsonify({'assignments' : output})

# /v1/assignments endpoint configuration for POST request - allows adding data to `Assignment` table to authenticated users
@app.route('/v1/assignments', methods=['POST'])
@auth.login_required # checks if the user sending data through request is authenticated
def create_assignments():
    # if database connection is unsuccessful
    if not check_db_connection():
            response = Response(status=503)
            logger.error(f"POST request to /v1/assignments returned status {response.status_code} for service unavailable - Database connection failure")
            return response
    
    # Check if body is json or not
    if request.is_json:
        data = request.get_json() # save request payload to data
        existing_assignment = session.query(Assignment).filter_by(name = data['name']).first()
        account_email = auth.current_user() # check if the user sending the request is authenticated
        account_details = session.query(Account).filter_by(email=account_email).first()
        # Check whether points and num_of_attempts have values under their specified range
        points = int(data.get('points'))
        if not (1<= points <=100):
            response = jsonify({'error' : 'Points must be between 1 and 100 inclusively.'})
            response.status_code = 400
            logger.warning(f"POST request to /v1/assignments returned status {response.status_code} for a bad request for assignment \'{existing_assignment.name}\' - value for \'points\' must be between 1 and 100 inclusively")
            return response
        num_of_attempts = int(data.get('num_of_attempts'))
        if not (1<= num_of_attempts <=3):
            response = jsonify({'error' : 'num_of_attempts must be between 1 and 3 inclusively.'})
            response.status_code = 400
            logger.warning(f"POST request to /v1/assignments returned status {response.status_code} for a bad request for assignment \'{existing_assignment.name}\' - value for \'num_of_attempts\' must be between 1 and 3 inclusively")
            return response

        # Return "409 Conflict" if the assignment with the same name exists
        if existing_assignment:
            response = Response(status=409)
            logger.warning(f"POST request to /v1/assignments returned status {response.status_code} for conflict - assignment with the name \'{existing_assignment.name}\' already exist")
            return response

        # Create new assignment
        else:
            new_assignment = Assignment(name=data['name'], points=data['points'], num_of_attempts=data['num_of_attempts'], deadline=data['deadline'], created_by=account_details.id)
            session.add(new_assignment)
            session.commit()
            response_data = {
                'id': str(new_assignment.id),
                'name': new_assignment.name,
                'points': new_assignment.points,
                'num_of_attempts': new_assignment.num_of_attempts,
                'deadline': new_assignment.deadline.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                'assignment_created': new_assignment.assignment_created.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                'assignment_updated': new_assignment.assignment_updated.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                'created_by' : account_details.id
            }

            response = jsonify(response_data)
            response.status_code = 201
            logger.info(f"POST request to /v1/assignments returned status {response.status_code} - assignment \'{new_assignment.id}\' creation successful")
            return response
    # If any argument other than json is passed, then return "400 Bad request"
    elif (request.args) or (request.data) or (request.form) or (request.files):
        response = jsonify({'message' : 'Payload must be json.'})
        response = Response(status=400)
        logger.warning(f"POST request to /v1/assignments returned status {response.status_code} for a bad request - NO payload except JSON allowed")
        return response
    
    # If there is not content at all, return "400 bad request"
    else:
        response = jsonify({'message' : 'No payload found!'})
        response.status_code = 400
        logger.warning(f"POST request to /v1/assignments/ returned status {response.status_code} for a bad request - no payload found")
        return response

# /v1/assignments/<id> endpoint configuration for GET request - fetches data for a particular assignment based on its id
@app.route('/v1/assignments/<id>', methods=['GET'])
@auth.login_required  # checks if the user sending data through request is authenticated
def get_one_assignment(id):
    try:
        # if database connection is unsuccessful
        if not check_db_connection():
            response = Response(status=503)
            logger.error(f"GET request to /v1/assignments/{id} returned status {response.status_code} for service unavailable - Database connection failure")
            return response
        # try catch block to ensure that id is of type uuid
        try:
            uuid.UUID(id)
        except ValueError:
            response = jsonify({'message' : 'Invalid UUID format for id'})
            response.status_code = 400
            logger.warning(f"GET request for /v1/assignments/{id} returned status {response.status_code} for a bad request - format for the 'id' is incorrect: UUID expected")
            return response
        # Ensure that there are no args in the request body
        if (request.args) or (request.data) or (request.form) or (request.files):
            response = Response(status=400)
            logger.warning(f"GET request to /v1/assignments/{id} returned status {response.status_code} for a bad request - NO argument allowed")
            return response
        assignment = session.query(Assignment).filter_by(id=id).first()

        # If assignment id is not present in the table, return "404 Not found"
        if not assignment:
            response = jsonify({'message' : 'No Assignment found!'})
            response.status_code = 404
            logger.warning(f"GET request to /v1/assignments/{id} returned status {response.status_code} - NO assignment found with specified id")
            return response

        # If assignment id exist in the table, get all the data for that id
        else:
            assignment_data = {}
            assignment_data['id'] = assignment.id
            assignment_data['name'] = assignment.name
            assignment_data['points'] = assignment.points
            assignment_data['num_of_attempts'] = assignment.num_of_attempts
            assignment_data['deadline'] = assignment.deadline
            assignment_data['assignment_created'] = assignment.assignment_created
            assignment_data['assignment_updated'] = assignment.assignment_updated

            response = jsonify({'assignment' : assignment_data})
            response.status_code = 200
            logger.warning(f"GET request to /v1/assignments/{id} returned status {response.status_code} - fetched data successfully")
            return response
    except Exception as e:
        # Log the exception to help with debugging
        print(f"An error occurred: {str(e)}")
        response = Response(status=501)
        logger.error(f"GET request to /v1/assignments/{id} returned status {response.status_code} - Not implemented: {str(e)}")
        return response

# /v1/assignments/<id> endpoint configuration for PUT request - Allow to modifiy data for a particular assignment based on its id
# only if the owner of that assignment is the one modifying it
@app.route('/v1/assignments/<id>', methods=['PUT'])
@auth.login_required # checks if the user sending data through request is authenticated
def modify_assignment(id):
    try:
        # if database connection is unsuccessful
        if not check_db_connection():
            response = Response(status=503)
            logger.error(f"PUT request to /v1/assignments/{id} returned status {response.status_code} for service unavailable - Database connection failure")
            return response
        # try catch block to ensure that id is of type uuid
        try:
            uuid.UUID(id)
        except ValueError:
            response = jsonify({'message' : 'Invalid UUID format for id'})
            response.status_code = 400
            logger.warning(f"PUT request for /v1/assignments/{id} returned status {response.status_code} for a bad request - format for the 'id' is incorrect: UUID expected")
            return response
        assignment = session.query(Assignment).filter_by(id=id).first()

        # If assignment id is not present in the table, return "404 Bad request"
        if not assignment:
            response = jsonify({'message' : 'No Assignment found!'})
            response.status_code = 404
            logger.warning(f"PUT request to /v1/assignments/{id} returned status {response.status_code} - NO assignment found with specified id")
            return response

        owner = assignment.created_by # get the owner of the assignment id in the PUT request
        get_user = auth.current_user() # get the email of the person sending the PUT request
        user_details = session.query(Account).filter_by(email=get_user).first() # get the details of the person sending PUT request from get_user
        user = user_details.id # get user id of the person sending the PUT request
        # condition to check if the person sending the PUT request is the owner of the assignment 
        if owner == user:
            # Check if body is json or not
            if request.is_json:
                data = request.get_json()

                # Check if the JSON payload is empty or contains unexpected keys
                expected_fields = {'name', 'points', 'num_of_attempts', 'deadline', 'assignment_created', 'assignment_updated'}
                if not data or not isinstance(data, dict) or not set(data.keys()).issubset(expected_fields):
                    response = jsonify({'error': 'Invalid or missing JSON payload'})
                    response.status_code = 400
                    logger.warning(f"PUT request for /v1/assignments/{id} returned status {response.status_code} for a bad request - Invalid or missing JSON payload")
                    return response
                # Check whether points and num_of_attempts have values under their specified range
                points = int(data.get('points'))
                if not (1<= points <=100):
                    response = jsonify({'error' : 'Points must be between 1 and 100 inclusively.'})
                    response.status_code = 400
                    logger.warning(f"PUT request for /v1/assignments/{id} returned status {response.status_code} for a bad request - value for \'points\' must be between 1 and 100 inclusively")
                    return response
                num_of_attempts = int(data.get('num_of_attempts'))
                if not (1<= num_of_attempts <=3):
                    response = jsonify({'error' : 'num_of_attempts must be between 1 and 3 inclusively.'})
                    response.status_code = 400
                    logger.warning(f"PUT request to /v1/assignments/{id} returned status {response.status_code} for a bad request - value for \'num_of_attempts\' must be between 1 and 3 inclusively")
                    return response
                
                # Overwriting data to existing entry
                assignment.name = data['name']
                assignment.points = data['points']
                assignment.num_of_attempts = data['num_of_attempts']
                assignment.deadline = data['deadline']

                # update database
                session.commit()
                
                # response body of the request
                response_data = {
                'name': assignment.name,
                'points': assignment.points,
                'num_of_attempts': assignment.num_of_attempts,
                'deadline': assignment.deadline
                }

                response = jsonify(response_data)
                response.status_code = 201
                logger.info(f"PUT request to /v1/assignments/{id} returned status {response.status_code} - assignment \'{assignment.name}\' updated successfully!")
                return response
            # If any argument other than json is passed, then return "400 Bad request"
            elif (request.args) or (request.data) or (request.form) or (request.files):
                response = Response(status=400)
                logger.info(f"PUT request to /v1/assignments/{id} returned status {response.status_code} for a bad request - NO payload except JSON allowed")
                return response
            # If there is not content at all, return "400 Bad Request"
            else:
                response = jsonify({'message' : 'No payload found!'})
                response.status_code = 400
                logger.warning(f"PUT request to /v1/assignments/{id} returned status {response.status_code} for a bad request - no payload found")
                return response
            
        # If user is not the owner of the assignment, return "403 Forbidden"
        else:
            response = jsonify({'message' : 'User forbidden!'})
            response.status_code = 403
            logger.warning(f"PUT request to /v1/assignments/{id} returned status {response.status_code} for a bad request - only owner can modify the assignment. USER FORBIDDEN")
            return response
    except Exception as e:
        # Log the exception to help with debugging
        response = Response(status=501)
        logger.error(f"PUT request to /v1/assignments/{id} returned status {response.status_code} - Not implemented: {str(e)}")
        return response

# /v1/assignments/<id> endpoint configuration for DELETE request - Allow to delete assignment based on its id only if 
# the owner of that assignment is the one modifying it
@app.route('/v1/assignments/<id>', methods=['DELETE'])
@auth.login_required # checks if the user sending data through request is authenticated
def delete_assignment(id):
    try:
        # if database connection is unsuccessful
        if not check_db_connection():
            response = Response(status=503)
            logger.error(f"DELETE request to /v1/assignments/{id} returned status {response.status_code} for service unavailable - Database connection failure")
            return response
        # try catch block to ensure that id is of type uuid
        try:
            uuid.UUID(id)
        except ValueError:
            response = jsonify({'message' : 'Invalid UUID format for id'})
            response.status_code = 400
            logger.warning(f"DELETE request for /v1/assignments/{id} returned status {response.status_code} for a bad request - format for the 'id' is incorrect: UUID expected")
            return response
        
        # Get assignment details from database using provided id
        assignment = session.query(Assignment).filter_by(id=id).first()

        # If assignment id is not present in the table, return "404 Bad request"
        if not assignment:
            response = jsonify({'message' : 'No Assignment found!'})
            response.status_code = 404
            logger.warning(f"DELETE request for /v1/assignments/{id} returned status {response.status_code} - assignment with given id not found")
            return response
        # Ensure that no payload is attached with the request
        if (request.args) or (request.data) or (request.form) or (request.files):
            response = Response(status=400)
            logger.warning(f"DELETE request for /v1/assignments/{id} returned status {response.status_code} for a bad request - NO payload allowed")
            return response
        owner = assignment.created_by # get the owner of the assignment id in the DELETE request
        get_user = auth.current_user() # get the email of the person sending the DELETE request
        user_details = session.query(Account).filter_by(email=get_user).first() # get the details of the person sending DELETE request from get_user
        user = user_details.id # get user id of the person sending the DELETE request
        # condition to check if the person sending the DELETE request is the owner of the assignment
        if owner == user:
            session.delete(assignment) # delete assignment
            session.commit() # make changes to the database
            response = jsonify({"message" : "Assignment deleted!"})
            response.status_code = 200
            logger.info(f"DELETE request to /v1/assignments/{id} returned status {response.status_code} - assignment \'{assignment.name}\' deleted successfully!")
            return response
        else:
            response = jsonify({'message' : 'User forbidden!'})
            response.status_code = 403
            logger.info(f"DELETE request to /v1/assignments/{id} returned status {response.status_code} for a bad request - only owner can delete the assignment. USER FORBIDDEN")
            return response

    except Exception as e:
        # Log the exception to help with debugging
        response = Response(status=501)
        logger.error(f"DELETE request to /v1/assignments/{id} returned status {response.status_code} - Not implemented: {str(e)}")
        return response

# function to authenticate user based on their credentials
@auth.verify_password
def verify_password(username, password):
    if not check_db_connection():
        response = Response(503)
        return response
    elif check_db_connection():
        account = session.query(Account).filter_by(email=username).first()
        if account:
            return bcrypt.check_password_hash(account.password, password)
    return False

# run application
if __name__ == '__main__':
    app.run()
