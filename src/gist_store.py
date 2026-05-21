import json
import os
import requests

def load_state(gist_id=None, pat=None):
    """
    Loads state data from a GitHub Gist, or falls back to a local JSON file.
    """
    # Fallback to local file if credentials are not provided
    if not gist_id or not pat:
        local_path = os.path.join("data", "state_local.json")
        print(f"No Gist credentials provided. Using local state file: {local_path}")
        if os.path.exists(local_path):
            try:
                with open(local_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading local state: {e}")
        return {"last_report_time": 0, "snapshots": {}}

    url = f"https://api.github.com/gists/{gist_id}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {pat}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            gist_data = response.json()
            files = gist_data.get("files", {})
            if "state.json" in files:
                content = files["state.json"].get("content", "")
                if content:
                    return json.loads(content)
            print("Gist found but state.json was missing or empty.")
            return {"last_report_time": 0, "snapshots": {}}
        else:
            print(f"Failed to fetch Gist (Status code: {response.status_code}): {response.text}")
            return {"last_report_time": 0, "snapshots": {}}
    except Exception as e:
        print(f"Error loading state from Gist: {e}")
        return {"last_report_time": 0, "snapshots": {}}

def save_state(state_data, gist_id=None, pat=None):
    """
    Saves state data to a GitHub Gist, or falls back to a local JSON file.
    """
    if not gist_id or not pat:
        local_path = os.path.join("data", "state_local.json")
        os.makedirs("data", exist_ok=True)
        try:
            with open(local_path, "w") as f:
                json.dump(state_data, f, indent=2)
            print(f"Saved state to local file: {local_path}")
            return True
        except Exception as e:
            print(f"Failed to save state to local file: {e}")
            return False

    url = f"https://api.github.com/gists/{gist_id}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {pat}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    payload = {
        "files": {
            "state.json": {
                "content": json.dumps(state_data, indent=2)
            }
        }
    }

    try:
        response = requests.patch(url, headers=headers, json=payload)
        if response.status_code == 200:
            print("Successfully updated state in GitHub Gist.")
            return True
        else:
            print(f"Failed to update Gist (Status code: {response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"Error saving state to Gist: {e}")
        return False
