"""Creates a Jenkins API token for the dashboard and writes it into backend/.env.
Usage (inside backend, venv active):  python jenkins_token.py"""
import getpass
import os
import sys
import time

import httpx

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def update_env(values: dict[str, str]) -> None:
    """Replace (or add) KEY=value lines, removing duplicates of those keys."""
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f:
            lines = f.read().splitlines()
    kept = [ln for ln in lines if ln.split("=", 1)[0].strip() not in values]
    kept += [f"{k}={v}" for k, v in values.items()]
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + "\n")


def main() -> None:
    url = (input("Jenkins URL [http://localhost:8081]: ").strip() or "http://localhost:8081").rstrip("/")
    user = input("Jenkins user ID [advaithegde]: ").strip() or "advaithegde"
    password = getpass.getpass("Jenkins password (hidden, press Enter when done): ")

    with httpx.Client(base_url=url, auth=(user, password), timeout=20) as client:
        me = client.get("/me/api/json")
        if me.status_code == 401:
            sys.exit("ERROR: Jenkins rejected the user ID or password. Log in at "
                     f"{url} with the same values to check them.")
        me.raise_for_status()
        print(f"Logged in as: {me.json().get('fullName')} (id {me.json().get('id')})")

        # Anti-CSRF "crumb": Jenkins ties it to the session cookie, so the POST
        # below must send back the cookie from this response.
        crumb = client.get("/crumbIssuer/api/json")
        headers = {}
        if crumb.status_code == 200:
            c = crumb.json()
            headers[c["crumbRequestField"]] = c["crumb"]
            cookies = {**dict(me.cookies.items()), **dict(crumb.cookies.items())}
            if cookies:
                headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())

        name = f"dashboard-{time.strftime('%Y%m%d-%H%M%S')}"
        resp = client.post(
            f"/user/{user}/descriptorByName/jenkins.security.ApiTokenProperty/generateNewToken",
            data={"newTokenName": name}, headers=headers)
        if resp.status_code != 200:
            sys.exit(f"ERROR: could not create the token (HTTP {resp.status_code}).")
        token = resp.json()["data"]["tokenValue"]

    check = httpx.get(f"{url}/api/json", auth=(user, token), timeout=20)
    if check.status_code != 200:
        sys.exit(f"ERROR: the new token did not work (HTTP {check.status_code}).")

    update_env({"JENKINS_URL": url, "JENKINS_USER": user, "JENKINS_TOKEN": token})
    print(f"OK: token '{name}' created, tested (HTTP 200) and saved to {ENV_PATH}")
    print("Now restart the backend (Ctrl+C, then: python -m uvicorn app.main:app --reload --port 8000)")


if __name__ == "__main__":
    main()