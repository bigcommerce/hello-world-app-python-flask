from bigcommerce.api import BigcommerceApi
import dotenv
import flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
import os

# do __name__.split('.')[0] if initialising from a file not at project root
app = flask.Flask(__name__)

# Look for a .env file
if os.path.exists('.env'):
    dotenv.load_dotenv('.env')

# Load configuration from environment, with defaults
app.config['DEBUG'] = True if os.getenv('DEBUG') == 'True' else False
app.config['LISTEN_HOST'] = os.getenv('LISTEN_HOST', '0.0.0.0')
app.config['LISTEN_PORT'] = int(os.getenv('LISTEN_PORT', '5000'))
app.config['APP_URL'] = os.getenv('APP_URL', 'http://localhost:5000')  # must be https to avoid browser issues
app.config['APP_CLIENT_ID'] = os.getenv('APP_CLIENT_ID')
app.config['APP_CLIENT_SECRET'] = os.getenv('APP_CLIENT_SECRET')
app.config['SESSION_SECRET'] = os.getenv('SESSION_SECRET', os.urandom(64))
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///data/hello_world.sqlite')
app.config['SQLALCHEMY_ECHO'] = app.config['DEBUG']

# Setup secure cookie secret
app.secret_key = app.config['SESSION_SECRET']

# Setup db
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bc_id = db.Column(db.Integer, nullable=False)
    email = db.Column(db.String(120), nullable=False)
    storeusers = relationship("StoreUser", backref="user")

    def __init__(self, bc_id, email):
        self.bc_id = bc_id
        self.email = email

    def __repr__(self):
        return '<User id=%d bc_id=%d email=%s>' % (self.id, self.bc_id, self.email)


class StoreUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('store.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    admin = db.Column(db.Boolean, nullable=False, default=False)

    def __init__(self, store, user, admin=False):
        self.store_id = store.id
        self.user_id = user.id
        self.admin = admin

    def __repr__(self):
        return '<StoreUser id=%d email=%s user_id=%s store_id=%d  admin=%s>' \
               % (self.id, self.user.email, self.user_id,  self.store.store_id, self.admin)


class Store(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    store_hash = db.Column(db.String(16), nullable=False, unique=True)
    access_token = db.Column(db.String(128), nullable=False)
    scope = db.Column(db.Text(), nullable=False)
    admin_storeuser_id = relationship("StoreUser",
                                      primaryjoin="and_(StoreUser.store_id==Store.id, StoreUser.admin==True)")
    storeusers = relationship("StoreUser", backref="store")

    def __init__(self, store_hash, access_token, scope):
        self.store_hash = store_hash
        self.access_token = access_token
        self.scope = scope

    def __repr__(self):
        return '<Store id=%d store_hash=%s access_token=%s scope=%s>' \
               % (self.id, self.store_hash, self.access_token, self.scope)


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
    return flask.render_template(template, **context)


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

    # Fetch a permanent oauth token. This will throw an exception on error,
    # which will get caught by our error handler above.
    client = BigcommerceApi(client_id=client_id(), store_hash=store_hash)
    token = client.oauth_fetch_token(client_secret(), code, context, scope, redirect)
    bc_user_id = token['user']['id']
    email = token['user']['email']
    access_token = token['access_token']

    # Create or update store
    store = Store.query.filter_by(store_hash=store_hash).first()
    if store is None:
        store = Store(store_hash, access_token, scope)
        db.session.add(store)
        db.session.commit()
    else:
        store.access_token = access_token
        store.scope = scope
        db.session.add(store)
        db.session.commit()
        # If the app was installed before, make sure the old admin user is no longer marked as the admin
        oldadminuser = StoreUser.query.filter_by(store_id=store.id, admin=True).first()
        if oldadminuser:
            oldadminuser.admin = False
            db.session.add(oldadminuser)

    # Create or update global BC user
    user = User.query.filter_by(bc_id=bc_user_id).first()
    if user is None:
        user = User(bc_user_id, email)
        db.session.add(user)
    elif user.email != email:
        user.email = email
        db.session.add(user)

    # Create or update store user
    storeuser = StoreUser.query.filter_by(user_id=user.id, store_id=store.id).first()
    if not storeuser:
        storeuser = StoreUser(store, user, admin=True)
    else:
        storeuser.admin = True
    db.session.add(storeuser)
    db.session.commit()

    # Log user in and redirect to app home
    flask.session['storeuserid'] = storeuser.id
    return flask.redirect(app.config['APP_URL'])


# The Load URL. See https://developer.bigcommerce.com/api/load
@app.route('/bigcommerce/load')
def load():
    # Decode and verify payload
    payload = flask.request.args['signed_payload']
    user_data = BigcommerceApi.oauth_verify_payload(payload, client_secret())
    if user_data is False:
        return "Payload verification failed!", 401

    bc_user_id = user_data['user']['id']
    email = user_data['user']['email']
    store_hash = user_data['store_hash']

    # Lookup store
    store = Store.query.filter_by(store_hash=store_hash).first()
    if store is None:
        return "Store not found!", 401

    # Lookup user and create if doesn't exist (this can happen if you enable multi-user
    # when registering your app)
    user = User.query.filter_by(bc_id=bc_user_id).first()
    if user is None:
        user = User(bc_user_id, email)
        db.session.add(user)
        db.session.commit()
    storeuser = StoreUser.query.filter_by(user_id=user.id, store_id=store.id).first()
    if storeuser is None:
        storeuser = StoreUser(store, user)
        db.session.add(storeuser)
        db.session.commit()

    # Log user in and redirect to app interface
    flask.session['storeuserid'] = storeuser.id
    return flask.redirect(app.config['APP_URL'])


# The Uninstall URL. See https://developer.bigcommerce.com/api/load
@app.route('/bigcommerce/uninstall')
def uninstall():
    # Decode and verify payload
    payload = flask.request.args['signed_payload']
    user_data = BigcommerceApi.oauth_verify_payload(payload, client_secret())
    if user_data is False:
        return "Payload verification failed!", 401

    # Lookup store
    store_hash = user_data['store_hash']
    store = Store.query.filter_by(store_hash=store_hash).first()
    if store is None:
        return "Store not found!", 401

    # Clean up: delete store associated users. This logic is up to you.
    # You may decide to keep these records around in case the user installs
    # your app again.
    storeusers = StoreUser.query.filter_by(store_id=store.id)
    for storeuser in storeusers:
        db.session.delete(storeuser)
    db.session.delete(store)
    db.session.commit()

    return flask.Response('Deleted', status=204)


# The Remove User Callback URL.
@app.route('/bigcommerce/remove-user')
def remove_user():
    # Decode and verify payload
    payload = flask.request.args['signed_payload']
    user_data = BigcommerceApi.oauth_verify_payload(payload, client_secret())
    if user_data is False:
        return "Payload verification failed!", 401

    # Lookup store
    store_hash = user_data['store_hash']
    store = Store.query.filter_by(store_hash=store_hash).first()
    if store is None:
        return "Store not found!", 401

    # Lookup user and delete it
    bc_user_id = user_data['user']['id']
    user = User.query.filter_by(bc_id=bc_user_id).first()
    if user is not None:
        storeuser = StoreUser.query.filter_by(user_id=user.id, store_id=store.id).first()
        db.session.delete(storeuser)
        db.session.commit()

    return flask.Response('Deleted', status=204)


#
# App interface
#
@app.route('/')
def index():
    # Lookup user
    storeuser = StoreUser.query.filter_by(id=flask.session['storeuserid']).first()
    if storeuser is None:
        return "Not logged in!", 401
    store = storeuser.store
    user = storeuser.user

    # Construct api client
    client = BigcommerceApi(client_id=client_id(),
                            store_hash=store.store_hash,
                            access_token=store.access_token)

    # Fetch a few products
    products = client.Products.all(limit=10)

    # Render page
    context = dict()
    context['products'] = products
    context['user'] = user
    context['store'] = store
    context['client_id'] = client_id()
    context['api_url'] = client.connection.host
    return render('index.html', context)


@app.route('/instructions')
def instructions():
    if not app.config['DEBUG']:
        return "Forbidden - instructions only visible in debug mode"
    context = dict()
    return render('instructions.html', context)


if __name__ == "__main__":
    db.create_all()
    app.run(app.config['LISTEN_HOST'], app.config['LISTEN_PORT'])
