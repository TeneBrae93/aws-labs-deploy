import os
import subprocess
import threading
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# --- Configuration ---
CLOUDGOAT_PATH = "cloudgoat"
CLOUDGOAT_SCENARIOS = [
    "iam_enum_basics",
    "sns_secrets"
    # Add all other scenario names you want available here
]

app = Flask(__name__)
CORS(app)

# --- Job Tracker ---
# Stores job statuses. Format: { "job_id": {"status": "running"|"complete"|"failed", "output": ""} }
# Note: Since this is in-memory, jobs will clear if the Flask server restarts. 
# This is usually fine for lab environments.
jobs = {}

# --- Helper Functions ---

def execute_cloudgoat_command(command_parts, input_data=None, timeout=900):
    """Executes the shell command synchronously (used by threads and fast routes)."""
    try:
        result = subprocess.run(
            [CLOUDGOAT_PATH] + command_parts,
            input=input_data,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout
        )
        return True, result.stdout + "\n" + result.stderr
    except subprocess.CalledProcessError as e:
        error_output = f"Command failed with exit code {e.returncode}:\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
        return False, error_output
    except subprocess.TimeoutExpired:
        return False, "Command timed out."
    except FileNotFoundError:
        return False, f"Error: '{CLOUDGOAT_PATH}' command not found. Ensure CloudGoat is installed."
    except Exception as e:
        return False, f"An unexpected error occurred: {str(e)}"

def run_cloudgoat_in_background(job_id, command_parts, input_data=None):
    """Runs the command in a thread and updates the global jobs dictionary."""
    success, output = execute_cloudgoat_command(command_parts, input_data)
    
    if success:
        jobs[job_id] = {"status": "complete", "output": output}
    else:
        jobs[job_id] = {"status": "failed", "output": output}

# --- Routes ---

@app.route('/')
def serve_index():
    """Serves the frontend HTML file."""
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

@app.route('/scenarios', methods=['GET'])
def get_scenarios():
    """Returns the list of available scenario names."""
    return jsonify(CLOUDGOAT_SCENARIOS)

@app.route('/status/<job_id>', methods=['GET'])
def check_job_status(job_id):
    """Endpoint for the frontend to poll for job completion."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"success": False, "output": "Job not found or expired."}), 404
    
    return jsonify(job), 200

@app.route('/create', methods=['POST'])
def create_scenario():
    """Handles the creation of a CloudGoat scenario asynchronously."""
    data = request.json
    scenario_name = data.get('scenario')

    if not scenario_name or scenario_name not in CLOUDGOAT_SCENARIOS:
        return jsonify({"success": False, "output": "Invalid scenario name provided."}), 400

    app.logger.info(f"Attempting to create scenario: {scenario_name}")
    
    # 1. Generate a Job ID and record it as running
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running", "output": "Initiating Creation..."}

    # 2. Start the Terraform process in a background thread
    thread = threading.Thread(
        target=run_cloudgoat_in_background, 
        args=(job_id, ["create", scenario_name])
    )
    thread.start()

    # 3. Immediately return the Job ID so the proxy doesn't time out
    return jsonify({"success": True, "job_id": job_id, "status": "running"}), 202

@app.route('/destroy', methods=['POST'])
def destroy_scenario():
    """Handles the destruction of a CloudGoat scenario asynchronously."""
    data = request.json
    scenario_name = data.get('scenario')

    if not scenario_name or scenario_name not in CLOUDGOAT_SCENARIOS:
        return jsonify({"success": False, "output": "Invalid scenario name provided."}), 400

    app.logger.info(f"Attempting to destroy scenario: {scenario_name}")
    
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running", "output": "Initiating Destruction..."}

    input_data = "y\n" 
    
    thread = threading.Thread(
        target=run_cloudgoat_in_background, 
        args=(job_id, ["destroy", scenario_name], input_data)
    )
    thread.start()

    return jsonify({"success": True, "job_id": job_id, "status": "running"}), 202

@app.route('/whitelist', methods=['POST'])
def whitelist_ip():
    """Handles the IP whitelisting. Left synchronous as it executes quickly."""
    data = request.json
    ip_address = data.get('ip')

    if not ip_address:
        return jsonify({"success": False, "output": "No IP address provided."}), 400
    
    app.logger.info(f"Attempting to whitelist IP: {ip_address}")
    
    input_data = f"y\n{ip_address}\n"
    success, output = execute_cloudgoat_command(["config", "whitelist"], input_data=input_data, timeout=60)

    if success:
        return jsonify({"success": True, "output": output}), 200
    else:
        return jsonify({"success": False, "output": output}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)
