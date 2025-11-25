from flask import Flask, request

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
    return "Aleks Trading Bot is running!"

@app.route('/signal', methods=['POST'])
def signal():
    data = request.json
    print("New signal:", data)
    return {"status": "received"}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
