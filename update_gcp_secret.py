#!/usr/bin/env python3
"""
Rule 7 Guardrail: Safe GCP Secret Manager Update (Zero String Encoding Corruption)
Prevents PowerShell pipe ASCII integer byte-array serialization that corrupts JWTs and secrets.
"""

import sys
import os
import tempfile
import subprocess
import argparse

def update_secret(secret_name: str, secret_value: str, project_id: str = "airborne-aviation-505100", account: str = "adminairborne@gmail.com"):
    if not secret_value:
        raise ValueError("Secret value cannot be empty.")

    # Create temporary file without BOM or trailing newline
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tf:
        tf.write(secret_value)
        temp_path = tf.name

    try:
        print(f"🔐 Rule 7 Guardrail: Uploading '{secret_name}' via clean --data-file to GCP Secret Manager ({project_id})...")
        
        # Check if secret exists
        check_cmd = [
            "gcloud", "secrets", "describe", secret_name,
            f"--project={project_id}", f"--account={account}", "--format=value(name)"
        ]
        res = subprocess.run(check_cmd, capture_output=True, text=True, check=False)
        exists = (res.returncode == 0)

        if exists:
            cmd = [
                "gcloud", "secrets", "versions", "add", secret_name,
                f"--data-file={temp_path}",
                f"--project={project_id}",
                f"--account={account}"
            ]
        else:
            cmd = [
                "gcloud", "secrets", "create", secret_name,
                f"--data-file={temp_path}",
                f"--project={project_id}",
                f"--account={account}",
                "--replication-policy=automatic"
            ]

        run_res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if run_res.returncode == 0:
            print(f"✅ Successfully updated secret '{secret_name}' with zero byte corruption!")
            return True
        else:
            print(f"❌ Failed to update secret '{secret_name}': {run_res.stderr.strip()}", file=sys.stderr)
            return False
    finally:
        if os.path.exists(temp_path):
            try:
                # Scrub before deleting
                with open(temp_path, "w") as f:
                    f.write("0" * 32)
            except Exception:
                pass
            os.remove(temp_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rule 7: Safe GCP Secret Manager Upload")
    parser.add_argument("secret_name", help="Name of secret (e.g. AGENT_TOKEN)")
    parser.add_argument("secret_value", nargs="?", help="Secret value (if omitted, prompts securely)")
    parser.add_argument("--project", default="airborne-aviation-505100", help="GCP Project ID")
    parser.add_argument("--account", default="adminairborne@gmail.com", help="GCP Account")

    args = parser.parse_args()
    val = args.secret_value
    if not val:
        import getpass
        val = getpass.getpass(f"Enter secret value for '{args.secret_name}': ")

    success = update_secret(args.secret_name, val, args.project, args.account)
    sys.exit(0 if success else 1)
