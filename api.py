from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd

from main import pack_loads_by_weight

app = Flask(__name__)
CORS(app)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/pack_loads", methods=["POST"])
def pack_loads():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    missing = [f for f in ("items", "capacity_kg", "weight_col") if f not in body]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    if not isinstance(body["items"], list):
        return jsonify({"error": "'items' must be a list"}), 400

    try:
        df = pd.DataFrame(body["items"])
        packed = pack_loads_by_weight(
            df,
            weight_col=body["weight_col"],
            capacity_kg=body["capacity_kg"],
            client_col=body.get("client_col"),
            date_col=body.get("date_col"),
        )
        return jsonify(packed.to_dict(orient="records"))
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 422


if __name__ == "__main__":
    app.run(debug=True)
