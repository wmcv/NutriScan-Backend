from dotenv import load_dotenv
import os
import eventlet
eventlet.monkey_patch()
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import cv2
import httpx
import numpy as np
import base64
import time
from flask_cors import CORS
from pyzbar.pyzbar import decode
import json
from promptloader import return_prompt

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="http://localhost:5173")

load_dotenv()
user_scanning_states = {}

@app.route("/")
def home():
    return "Flask WebSocket server is running!"

@socketio.on("connect")
def on_connect():
    sid = request.sid
    user_scanning_states[sid] = True
    print(f"user connected: {sid}")

@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    user_scanning_states.pop(sid, None)
    print(f"user {sid} disconnected.")

@socketio.on("send_items")
def handle_frame(data):
    sid = request.sid

    if sid not in user_scanning_states:
        user_scanning_states[sid] = True

    if not user_scanning_states[sid]:
        print(f"scanning paused for user {sid}, ignoring frame.")
        return

    try:
        print(f"received frame from {sid}")

        frame_data = data["frame"].split(",")[1]
        frame_bytes = base64.b64decode(frame_data)
        np_arr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        detectedBarcode = decode(frame)

        if detectedBarcode:
            for barcode in detectedBarcode:
                if barcode.data:
                    barcode_data = barcode.data.decode("utf-8")
                    print(f'sending barcode to {sid}: {barcode_data}')
                    emit("product_info", barcode_data, room=sid)
                    user_scanning_states[sid] = False
                    socketio.start_background_task(resume_scanning, sid)
                    break

    except Exception as e:
        print(f"error processing frame from {sid}: {e}")

def resume_scanning(sid):
    time.sleep(1)
    user_scanning_states[sid] = True
    print(f"resuming scanning for user {sid}")

@socketio.on("restart")
def restart_stream():
    sid = request.sid
    user_scanning_states[sid] = True
    print(f"restarting scanning for user {sid}")
    emit("restart_ack", room=sid)


@app.route("/analyze_product", methods=["POST"])
def analyze_product_route():
    try:
        request_data = request.get_json(force=True)
        print("incoming JSON received")

        product_name = request_data.get('product_name')
        product_ingredients = request_data.get("product_ingredients")
        ecoscore_grade = request_data.get("ecoscore_grade")
        food_groups = request_data.get("food_groups")
        print(ecoscore_grade)
        print(food_groups)
        product_nutrients = request_data.get("product_nutrients")
        user_preferences = request_data.get("user_preferences", {})

        if not product_name or not isinstance(product_ingredients, (str, list)) or not isinstance(product_nutrients, dict):
            print("missing or invalid required fields.")
            return jsonify({
                "error": "Missing or invalid required fields: product_name (str), product_ingredients (str/list), product_nutrients (dict)"
            }), 400

        if isinstance(product_ingredients, list):
            product_ingredients = ", ".join(product_ingredients)

        try:
            nutrients_str = json.dumps(product_nutrients, indent=2)
            preferences_str = json.dumps(user_preferences, indent=2)
        except Exception as e:
            print("error serializing JSON inputs:", e)
            return jsonify({"error": "Invalid input structure"}), 400

        prompt = return_prompt(product_name, product_ingredients, nutrients_str, preferences_str)

        api_key = os.getenv("GROQ_API_KEY")
        url = 'https://api.groq.com/openai/v1/chat/completions'

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': 'llama-3.3-70b-versatile',
            'messages': [
                {'role': 'system', 'content': 'You are a helpful nutrition assistant.'},
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 500,
            'temperature': 0.7,
            'top_p': 1.0
        }

        print("sending request to AI model")
        with httpx.Client(timeout=20) as client:
            response = client.post(url, json=payload, headers=headers)
        print("AI model response received")

        try:
            result = response.json()
            ai_response = result['choices'][0]['message']['content']
        except Exception as decode_err:
            print(f"failed to decode response JSON: {decode_err}")
            print("raw Response:", response.text)
            return jsonify({"error": "Invalid response from AI"}), 502

        return jsonify({"message": ai_response})

    except Exception as e:
        print(f"server Error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("🟢 Flask WebSocket Server Running...")
    with app.app_context():
        socketio.run(app, debug=True, host="0.0.0.0", port=5001)
