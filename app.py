from bigcommerce.api import BigcommerceApi
import dotenv
import flask
from flask.ext.sqlalchemy import SQLAlchemy
from jinja2 import Template
import json
import os
import random

# do __name__.split('.')[0] if initialising from a file not at project root
app = flask.Flask(__name__)

# Look for a .env file
if os.path.exists('.env'):
    dotenv.load_dotenv('.env')

# Load configuration from environment, with defaults
app.config['DEBUG'] = True if os.getenv('DEBUG') == 'True' else False
app.config['LISTEN_HOST'] = os.getenv('LISTEN_HOST', '0.0.0.0')
app.config['LISTEN_PORT'] = int(os.getenv('LISTEN_PORT', '5000'))
app.config['APP_URL'] = os.getenv('APP_URL', 'http://localhost:5000') # must be https to avoid browser issues
app.config['APP_CLIENT_ID'] = os.getenv('APP_CLIENT_ID')
app.config['APP_CLIENT_SECRET'] = os.getenv('APP_CLIENT_SECRET')
app.config['SESSION_SECRET'] = os.getenv('SESSION_SECRET', os.urandom(64))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///%s' % os.getenv('DATABASE_PATH', 'data/hello_world.db')
app.config['SQLALCHEMY_ECHO'] = app.config['DEBUG']


# Setup secure cookie secret
app.secret_key = app.config['SESSION_SECRET']

# Setup db
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bc_id = db.Column(db.Integer, nullable=False)
    email = db.Column(db.String(120), nullable=False)

    store_id = db.Column(db.Integer, db.ForeignKey('store.id'), nullable=False)
    store = db.relationship('Store', backref=db.backref('users', lazy='dynamic'))

    def __init__(self, bc_id, email, store):
        self.bc_id = bc_id
        self.email = email
        self.store = store

    def __repr__(self):
        return '<User id=%d bc_id=%d email=%s store_id=%d>' % (self.id, self.bc_id, self.email, self.store_id)


class Store(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    store_hash = db.Column(db.String(16), nullable=False, unique=True)
    access_token = db.Column(db.String(128), nullable=False)

    def __init__(self, store_hash, access_token):
        self.store_hash = store_hash
        self.access_token = access_token

    def __repr__(self):
        return '<Store id=%d store_hash=%s access_token=%s>' % (self.id, self.store_hash, self.access_token)


#
# Error handling and helpers
#

def error_info(e):
    content = ""
    try:  # it's probably a HttpException, if you're using the bigcommerce client
        content += str(e.headers) + "<br>" + str(e.content) + "<br>"
        req = e.response.request
        content += "<br>Request:<br>" + req.url + "<br>" + str(req.headers) + "<br>" + str(req.body)
    except AttributeError as e:  # not a HttpException
        content += "<br><br> (This page threw an exception: {})".format(str(e))
    return content

@app.errorhandler(500)
def internal_server_error(e):
    content = "Internal Server Error: " + str(e) + "<br>"
    content += error_info(e)
    return content, 500

@app.errorhandler(400)
def bad_request(e):
    content = "Bad Request: " + str(e) + "<br>"
    content += error_info(e)
    return content, 400

# Helper for template rendering
def render(template, context):
    with open(template, 'r') as f:
        t = Template(f.read())
        return t.render(context)

def client_id():
    return app.config['APP_CLIENT_ID']

def client_secret():
    return app.config['APP_CLIENT_SECRET']


#
# OAuth pages
#

# The Auth Callback URL. See https://developer.bigcommerce.com/api/callback
@app.route('/bigcommerce/callback')
def auth_callback():
    # Put together params for token request
    code = flask.request.args['code']
    context = flask.request.args['context']
    scope = flask.request.args['scope']
    store_hash = context.split('/')[1]
    redirect = app.config['APP_URL'] + flask.url_for('auth_callback')

    # Fetch the permanent oauth token. As a side-effect, also sets up the client
    # object to be ready for future requests. This will throw an exception on error,
    # which will get caught by our error handler above.
    client = BigcommerceApi(client_id=client_id(), store_hash=store_hash)
    token = client.oauth_fetch_token(client_secret(), code, context, scope, redirect)
    bc_user_id = token['user']['id']
    email = token['user']['email']
    access_token = token['access_token']

    # Create or update store
    store = Store.query.filter_by(store_hash=store_hash).first()
    if store is None:
        store = Store(store_hash, access_token)
    else:
        store.access_token = access_token

    db.session.add(store)
    db.session.commit()

    # Create or update user
    user = User.query.filter_by(bc_id=bc_user_id).first()
    if user is None:
        user = User(bc_user_id, email, store)
    else:
        user.email = email
        user.store = store

    db.session.add(user)
    db.session.commit()

    # Log user in and redirect to app home
    flask.session['userid'] = user.id
    return flask.redirect(flask.url_for('index'))


# The Load URL. See https://developer.bigcommerce.com/api/load
@app.route('/bigcommerce/load')
def load():
    # Decode and verify payload
    payload = flask.request.args['signed_payload']
    user_data = BigcommerceApi.oauth_verify_payload(payload, client_secret())
    if user_data is False:
        return "Payload verification failed!", 401

    # Lookup user
    user = User.query.filter_by(bc_id=user_data['user']['id']).first()
    if user is None:
        return "Not installed!", 401

    # Log user in and redirect to app interface
    flask.session['userid'] = user.id
    return flask.redirect(flask.url_for('index'))


# The Uninstall URL. See https://developer.bigcommerce.com/api/load
@app.route('/bigcommerce/uninstall')
def uninstall():
    # Decode and verify payload
    payload = flask.request.args['signed_payload']
    user_data = BigcommerceApi.oauth_verify_payload(payload, client_secret())
    if user_data is False:
        return "Payload verification failed!", 401

    # Lookup store
    user = User.query.filter_by(bc_id=user_data['user']['id']).first()
    if user is None:
        return "Not installed!", 401

    # Clean up: delete store owner and associated store. This logic is up to
    # you. You may decide to keep these records around in case the user installs
    # your app again.
    db.session.delete(user)
    db.session.delete(user.store)
    db.session.commit()

    # Log user out and return
    flask.session.clear()
    return flask.Response('Deleted', status=201)


#
# App interface
#

@app.route('/')
def index():
    # Lookup user
    user = User.query.filter_by(id=flask.session['userid']).first()
    if user is None:
        return "Not logged in!", 401

    # Construct api client
    client = BigcommerceApi(client_id=client_id(),
                            store_hash=user.store.store_hash,
                            access_token=user.store.access_token)

    # Fetch a few products
    products = client.Products.all(limit=10)

    # Render page
    context = dict()
    context['products'] = products
    context['user'] = user
    context['client_id'] = client_id()
    context['api_url'] = client.connection.host
    return render('templates/index.html', context)


if __name__ == "__main__":
    db.create_all()
    app.run(app.config['LISTEN_HOST'], app.config['LISTEN_PORT'])
