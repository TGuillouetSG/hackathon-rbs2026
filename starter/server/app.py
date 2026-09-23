
from pathlib import Path
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    index_path = Path(__file__).resolve().parent / 'pages' / 'index.html'
    with open(index_path, 'r') as file:
        return file.read()

@app.route("/test")
def test_get():
    print("Hello World !")

    return "test"