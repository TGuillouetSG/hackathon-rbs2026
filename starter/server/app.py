
from flask import Flask, render_template

app = Flask(__name__, static_folder='static', static_url_path='/static')

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/rdv")
def rdv():
    return render_template('rdv.html')

@app.route("/test")
def test_get():
    print("Hello World !")
    return "test"