import json
import pprint
import flask
import dotenv
import os
import random
from bigcommerce.api import BigcommerceApi
from string import Template

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

app.secret_key = app.config['SESSION_SECRET']

# We need a separate client for each user (typically users will be different stores)
# (you could throw everything into a class if globals make your stomach turn)
# TODO: add timeout for sessions (at the moment, they stay forever)
user_clients = {}


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
        return t.substitute(context)

def client_id():
    return app.config['APP_CLIENT_ID']

def client_secret():
    return app.config['APP_CLIENT_SECRET']

#
# OAuth pages
#

@app.route('/bigcommerce/load')  # the load url
def auth_start():
    # get and check payload
    user_data = BigcommerceApi.oauth_verify_payload(flask.request.args['signed_payload'], client_secret())
    if not user_data:
        return "You Shall Not Pass!!!"

    # retrieve the user's token from a json file
    # better to use a database, but this is simpler so...
    userid = int(user_data['user']['id'])
    with open('data/user{}.json'.format(userid), 'r') as f:
        token = json.load(f)

    # make a client for this user
    global user_clients
    if not userid in user_clients:
        client = BigcommerceApi(client_id=client_id(),
                                store_hash=user_data['store_hash'],
                                access_token=token['access_token'])
        user_clients[userid] = client
    flask.session['userid'] = userid

    return render('templates/start.html', {'user_data':user_data, 'token': token})


@app.route('/bigcommerce/callback')  # the callback url
def auth_callback():
    # grab the GET params
    code = flask.request.args['code']
    context = flask.request.args['context']
    scope = flask.request.args['scope']
    store_hash = context.split('/')[1]

    # Compose redirect
    redirect = app.config['APP_URL'] + flask.url_for('auth_callback')

    # Create api client
    client = BigcommerceApi(client_id=client_id(), store_hash=store_hash)

    # as a side-effect, also sets up the client object to be ready for future requests
    token = client.oauth_fetch_token(client_secret(), code, context, scope, redirect)

    # save the user's data in a json file for when they want to
    userid = int(token['user']['id'])
    with open('data/user{}.json'.format(userid), 'w') as f:  # note that this errors if data directory does not exist
        json.dump(token, f)

    # save client for this user
    global user_clients
    user_clients[userid] = client
    flask.session['userid'] = userid

    return render('templates/callback.html', {})


#
# App interface
#

@app.route('/')
def index():
    # Fetch some products to display
    global user_clients
    client = user_clients[flask.session['userid']]
    products = ["<li>{} - {}</li>".format(p.name, p.price) for p in client.Products.all(limit=5)]
    return render('templates/index.html', {'products': '\n'.join(products)})


if __name__ == "__main__":
    app.run(app.config['LISTEN_HOST'], app.config['LISTEN_PORT'])
