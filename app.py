import os
import subprocess
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# --- Configuration ---
# NOTE: CloudGoat should be installed and configured to run from the context
# where this application is executed.
CLOUDGOAT_PATH = "cloudgoat"
CLOUDGOAT_SCENARIOS = [
    "sns_secrets"
    # Add all other scenario names you want available here
]

app = Flask(__name__)
# IMPORTANT: Since this is only accessible via a private VPN, we enable CORS for simplicity.
# If this server were publicly accessible, you MUST restrict origins.
CORS(app)

# Helper function to execute shell commands
def execute_cloudgoat_command(command_parts, input_data=None, timeout=900):
    try:
        # Run the command and capture output (stdout and stderr)
        result = subprocess.run(
            [CLOUDGOAT_PATH] + command_parts,
            input=input_data, # Input data for interactive commands
            capture_output=True,
            text=True,
            check=True, # Raise exception for non-zero exit codes
            timeout=timeout # Timeout set by caller
        )
        # Return success with combined output
        return True, result.stdout + "\n" + result.stderr
    except subprocess.CalledProcessError as e:
        # Handle non-zero exit codes (command failed)
        error_output = f"Command failed with exit code {e.returncode}:\n"
        error_output += f"STDOUT: {e.stdout}\n"
        error_output += f"STDERR: {e.stderr}"
        return False, error_output
    except subprocess.TimeoutExpired:
        return False, "Command timed out."
    except FileNotFoundError:
        return False, f"Error: '{CLOUDGOAT_PATH}' command not found. Ensure CloudGoat is installed and in the system PATH."
    except Exception as e:
        return False, f"An unexpected error occurred: {str(e)}"

@app.route('/')
def serve_index():
    """Serves the frontend HTML file."""
    # Assumes index.html is in the same directory as app.py
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

@app.route('/scenarios', methods=['GET'])
def get_scenarios():
    """Returns the list of available scenario names."""
    return jsonify(CLOUDGOAT_SCENARIOS)

@app.route('/create', methods=['POST'])
def create_scenario():
    """Handles the creation of a CloudGoat scenario."""
    data = request.json
    scenario_name = data.get('scenario')

    if not scenario_name or scenario_name not in CLOUDGOAT_SCENARIOS:
        return jsonify({"success": False, "output": "Invalid scenario name provided."}), 400

    app.logger.info(f"Attempting to create scenario: {scenario_name}")
    
    # Execute: cloudgoat create [scenario_name]
    success, output = execute_cloudgoat_command(["create", scenario_name])

    if success:
        return jsonify({"success": True, "output": output}), 200
    else:
        return jsonify({"success": False, "output": output}), 500

@app.route('/destroy', methods=['POST'])
def destroy_scenario():
    """Handles the destruction of a CloudGoat scenario."""
    data = request.json
    scenario_name = data.get('scenario')

    if not scenario_name or scenario_name not in CLOUDGOAT_SCENARIOS:
        return jsonify({"success": False, "output": "Invalid scenario name provided."}), 400

    app.logger.info(f"Attempting to destroy scenario: {scenario_name}")
    
    # FIX: Pass 'y' to the subprocess stdin to automatically confirm destruction
    input_data = "y\n" 
    
    # Execute: cloudgoat destroy [scenario_name]
    success, output = execute_cloudgoat_command(["destroy", scenario_name], input_data=input_data)

    if success:
        return jsonify({"success": True, "output": output}), 200
    else:
        return jsonify({"success": False, "output": output}), 500

@app.route('/whitelist', methods=['POST'])
def whitelist_ip():
    """Handles the IP whitelisting using cloudgoat config whitelist."""
    data = request.json
    ip_address = data.get('ip')

    if not ip_address:
        return jsonify({"success": False, "output": "No IP address provided."}), 400
    
    app.logger.info(f"Attempting to whitelist IP: {ip_address}")
    
    # Construct the input to automate 'y' response and IP entry
    # Note: CloudGoat expects the input to be terminated by a newline.
    input_data = f"y\n{ip_address}\n"
    
    # Execute: cloudgoat config whitelist (with automated input)
    # Set a short timeout as this command should be fast
    success, output = execute_cloudgoat_command(["config", "whitelist"], input_data=input_data, timeout=60)

    if success:
        return jsonify({"success": True, "output": output}), 200
    else:
        return jsonify({"success": False, "output": output}), 500


if __name__ == '__main__':
    # Ensure CloudGoat scenarios directory is available if necessary
    # In a real environment, you'd run this with a production WSGI server like Gunicorn or uWSGI
    # For simplicity, we run the built-in Flask server on port 8000
    app.run(host='0.0.0.0', port=8000, debug=False)
