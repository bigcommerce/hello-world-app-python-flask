import json
import pprint
import flask
import bigcommerce as api
from string import Template

app = flask.Flask(__name__)  # do __name__.split('.')[0] if initialising from a file not at project root
app.config.from_pyfile('config.py')
app.secret_key = "SUPER_SECRET_KEY"  # otherwise can't use session

# We need a separate client for each user (typically users will be different stores)
# (you could throw everything into a class if globals make your stomach turn)
# TODO: add timeout for sessions (at the moment, they stay forever)
user_clients = {}

# Set up some error handling first

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


# OAuth pages

@app.route('/auth/start')  # the load url
def auth_start():
    # get and check payload
    user_data = api.OAuthConnection.verify_payload(flask.request.args['signed_payload'],
                                                   app.config['APP_CLIENT_SECRET'])

    if not user_data: return "You Shall Not Pass!!!"  # verification failed

    # retrieve the user's token from a json file
    # better to use a database, but this is simpler so...
    userid = int(user_data['user']['id'])
    with open('data/user{}.json'.format(userid), 'r') as f:
        token = json.load(f)
    cid = app.config['APP_CLIENT_ID']

    # make a client for this user
    global user_clients
    if not userid in user_clients:
        client = api.OAuthConnection(cid,
                                     user_data['store_hash'],
                                     access_token=token['access_token'])
        user_clients[userid] = client
    flask.session['userid'] = userid

    return render('templates/start.html', {'user_data':user_data, 'token': token})


@app.route('/auth/callback')  # the callback url
def auth_callback():
    # grab the GET params
    code = flask.request.args['code']
    context = flask.request.args['context']
    scope = flask.request.args['scope']

    # grab our settings
    secret = app.config['APP_CLIENT_SECRET']
    redirect = app.config['APP_URL'] + flask.url_for('auth_callback')

    client = api.OAuthConnection(app.config['APP_CLIENT_ID'],
                                 context.split('/')[1])  # this is the store hash

    # as a side-effect, also sets up the client object to be ready for future requests
    token = client.fetch_token(secret, code, context, scope, redirect, 'https://login.bigcommerce.com/oauth2/token')

    # save the user's data in a json file for when they want to
    userid = int(token['user']['id'])
    with open('data/user{}.json'.format(userid), 'w') as f:  # note that this errors if data directory does not exist
        json.dump(token, f)

    # save client for this user
    global user_clients
    user_clients[userid] = client
    flask.session['userid'] = userid

    return render('templates/callback.html', {})


@app.route('/')
def index():
    # Fetch some products to display
    global user_clients
    client = user_clients[flask.session['userid']]
    products = ["<li>{} - {}</li>".format(p.name, p.price) for p in client.get('products', limit=5)]
    return render('templates/index.html', {'products': '\n'.join(products)})

if __name__ == "__main__":
    app.run()
