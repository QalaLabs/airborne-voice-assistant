#!/bin/bash
# =========================================================
# Deploy the ADK conversational agent to Vertex AI Agent Engine
# (Gemini Enterprise Agent Platform runtime).
#
# THIS SCRIPT IS A STARTING POINT, NOT VERIFIED SYNTAX.
# The exact `agents-cli`/`vertexai.agent_engines` deploy command could not be
# confirmed at write time (google.github.io/agents-cli and
# docs.cloud.google.com were unreachable from the dev environment this was
# written in -- see the plan's "Unverified facts" section). Confirm the real
# command against current docs before relying on this script.
#
# Run this BEFORE deploying/updating the Cloud Run service with
# USE_AGENT_ENGINE=true, so AGENT_ENGINE_RESOURCE_NAME is known.
# =========================================================

set -e

PROJECT_ID="airborne-aviation-505100"
LOCATION="asia-south1"   # confirm Agent Engine supports this region -- may
                          # differ from Cloud Run/Cloud SQL's region.
AGENT_DISPLAY_NAME="airborne-admissions-agent"

echo "================================================="
echo "Deploying ADK agent '$AGENT_DISPLAY_NAME'"
echo "Project: $PROJECT_ID | Location: $LOCATION"
echo "================================================="

cd "$(dirname "$0")"

# --- Placeholder deploy step -----------------------------------------
# Replace with the confirmed agents-cli or Agent Engine SDK deploy command,
# e.g. (syntax unverified):
#   agents deploy --project "$PROJECT_ID" --location "$LOCATION" \
#     --display-name "$AGENT_DISPLAY_NAME" --agent-module agent:root_agent
# or, via a short Python script using the vertexai SDK:
#   python -c "
#   import vertexai
#   from vertexai import agent_engines
#   from agent import root_agent
#   vertexai.init(project='$PROJECT_ID', location='$LOCATION')
#   remote_agent = agent_engines.create(root_agent, requirements='requirements.txt')
#   print(remote_agent.resource_name)
#   "
echo "TODO: replace this placeholder with the confirmed agents-cli/Agent Engine deploy command."
exit 1

# echo ""
# echo "================================================="
# echo "DEPLOYMENT SUCCESSFUL!"
# echo "Agent Engine resource name: <printed above>"
# echo "Set AGENT_ENGINE_RESOURCE_NAME to this value on the Cloud Run deploy"
# echo "(deploy.sh / deploy.ps1) before enabling USE_AGENT_ENGINE=true."
# echo "================================================="
