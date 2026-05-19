from flask import Flask,request,jsonify,send_from_directory
import requests
import os

app=Flask(__name__)

OPENAI_KEY=os.getenv(
"OPENAI_API_KEY"
)

@app.route("/")
def index():

    return send_from_directory(
    ".",
    "index.html"
    )

@app.route(
"/chat",
methods=["POST"]
)

def chat():

    text=request.json["message"]

    r=requests.post(

    "https://openrouter.ai/api/v1/chat/completions",

    headers={

    "Authorization":
    f"Bearer {OPENAI_KEY}",

    "Content-Type":
    "application/json"

    },

    json={

    "model":
    "openai/gpt-4.1-mini",

    "messages":[
    {
    "role":"user",
    "content":text
    }]

    })

    return jsonify(
    r.json()
    )

if __name__=="__main__":

 app.run(
 host="0.0.0.0",
 port=3000
 )
