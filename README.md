[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy) [(Heroku instructions)](#getting-started-heroku-version)
# BigCommerce Sample App: Python
This is a small Flask application that implements the OAuth callback flow for BigCommerce [Single Click Apps][single_click_apps]
and uses the [BigCommerce API][api_client] to pull a list of products on a BigCommerce store. For information on how to develop apps
for BigCommerce stores, see our [Developer Portal][devportal].

We hope this sample gives you a good starting point for building your next killer app! What follows are steps specific
to running and installing this sample application.



### Getting started
1. Clone this repo: `git clone git@github.com:bigcommerce/hello-world-app-python-flask.git`
2. Change to the repo directory: `cd hello-world-app-python-flask`
3. Create a virtual environment: `python3 -m venv venv && source venv/bin/activate`
4. Install dependencies with pip: `pip install -r requirements.txt`
5. Make a free account with [Heroku](https://heroku.com/)
6. Provision resources with Heroku
   ```
   heroku login
   heroku create
   heroku addons:create heroku-postgresql:hobby-dev
   ```
7. Get the deployment URL from `heroku domains | tail -1`. Substitute this value for all instances of `<app hostname>`
   below.
8. Register the app with BigCommerce:
   1. Create a trial store on [BigCommerce](https://www.bigcommerce.com/)
   2. Go to the [Developer Portal][devportal] and log in by going to "My Apps"
   3. Click the button "Create an app", enter a name for the new app, and then click "Create"
   4. You don't have to fill out all the details for your app right away, but you do need
      to provide some core details in section 4 (Technical). Note that if you are just getting
      started, you can use `localhost` for your hostname, but ultimately you'll need to host your
      app on the public Internet.
   * _Auth Callback URL_: `https://<app hostname>/bigcommerce/callback`
   * _Load Callback URL_: `https://<app hostname>/bigcommerce/load`
   * _Uninstall Callback URL_: `https://<app hostname>/bigcommerce/uninstall`
   * _Remove User Callback URL_: `https://<app hostname>/bigcommerce/remove-user` (if enabling your app for multiple users)
   5. Enable the _Products - Read Only_ scope under _OAuth scopes_, which is what this sample app needs.
   6. Click `Save & Close` on the top right of the dialog.
   7. You'll now see your app in a list in the _My Apps_ section of Developer Portal. Hover over it and click
      _View Client ID_. You'll need these values in the next step.
9. Copy `.env-example` to `.env`
10. Edit `.env`:
  * Set `BC_CLIENT_ID` and `BC_CLIENT_SECRET` to the values obtained from Developer Portal.
  * Set `APP_URL` to `https://<app hostname>`.
  * Set `DATABASE_URL` to the value obtained from `heroku config`
  * Set `SESSION_SECRET` to a long random string, such as that generated by
    ```
    python -c "import os; print(os.urandom(64).hex())"
    ```
11. Make sure to populate the database by opening a Python shell from within the app and running 
    ```
    from app import db
    db.create_all()
    ```
7. Run the app: `python ./app.py`
8. Then follow the steps under Installing the app in your trial store.

### Hosting the app
In order to install this app in a BigCommerce store, it must be hosted on the public Internet. You can get started in development
by simply running `python app.py` to run it locally, and then use `localhost` in your URLs, but ultimately you will need to host
it somewhere to use the app anywhere other than your development system.

### Getting started (Heroku version)

1. Click this button: [![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)
2. Fill in the details from the app portal on the Heroku deployment page
  * See [Registering the app with BigCommerce](#registering-the-app-with-bigcommerce) above. Ignore the callback URLs, just save the app to get the Client ID and Client Secret.
3. Deploy the app, and click "view" when it's done
4. Take the callback URLs from the instructions page and plug them into the dev portal.
5. Then follow the steps under Installing the app in your trial store.

### Installing the app in your trial store
* Login to your trial store
* Go to the Marketplace and click _My Drafts_. Find the app you just created and click it.
* A details dialog will open. Click _Install_ and the draft app will be installed in your store.

[single_click_apps]: https://developer.bigcommerce.com/api/#building-oauth-apps
[api_client]: https://pypi.python.org/pypi/bigcommerce
[devportal]: https://developer.bigcommerce.com
