
#!/usr/bin/env bash

set -Eeuo pipefail

# Deployment configuration
APP_DIR="/opt/quickbuy"
BUCKET="quickbuy-deployment-artifacts-2026"
REGION="eu-north-1"
PROJECT_NAME="quickbuy"

# Receive image tag from GitHub Actions
IMAGE_TAG="${1:?Image tag is required}"

if [[ ! "$IMAGE_TAG" =~ ^[0-9a-f]{7}$ ]]; then
    echo "Invalid image tag"
    exit 1
fi

ARTIFACT="quickbuy-build-${IMAGE_TAG}.zip"

cd "$APP_DIR"

# Prevent simultaneous deployments
exec 9>"$APP_DIR/.deploy.lock"
flock -n 9

# Create temporary deployment directory
TEMP_DIR=$(mktemp -d "$APP_DIR/.deploy-XXXXXX")
trap 'rm -rf "$TEMP_DIR"' EXIT

echo "Deploying QuickBuy version: $IMAGE_TAG"

# Step 1: Verify production environment file
test -f "$APP_DIR/.env"

# Step 2: Download artifact from S3
echo "Downloading deployment artifact..."

aws s3 cp \
    "s3://$BUCKET/builds/$ARTIFACT" \
    "$TEMP_DIR/$ARTIFACT" \
    --region "$REGION" \
    --only-show-errors

# Step 3: Verify and extract artifact
echo "Verifying artifact integrity..."

unzip -tq "$TEMP_DIR/$ARTIFACT"

unzip -q "$TEMP_DIR/$ARTIFACT" \
    -d "$TEMP_DIR"

# Step 4: Load prebuilt Docker images
echo "Loading prebuilt Docker images..."

docker load -i "$TEMP_DIR/quickbuy-images.tar"

docker image inspect \
    "quickbuy-inventory:$IMAGE_TAG" \
    "quickbuy-order:$IMAGE_TAG" \
    "quickbuy-notification:$IMAGE_TAG" \
    >/dev/null

# Step 5: Update application files
echo "Updating deployment files..."

cp -a "$TEMP_DIR/frontend/." "$APP_DIR/frontend/"
cp -a "$TEMP_DIR/database/." "$APP_DIR/database/"
cp -a "$TEMP_DIR/gateway/." "$APP_DIR/gateway/"

cp "$TEMP_DIR/compose.yaml" "$APP_DIR/compose.yaml"

# Step 6: Update image tag without changing credentials
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$IMAGE_TAG/" \
    "$APP_DIR/.env"

chmod 600 "$APP_DIR/.env"

# Step 7: Validate Docker Compose configuration
docker compose -p "$PROJECT_NAME" config --quiet

# Step 8: Start updated application containers
echo "Starting updated containers..."

docker compose -p "$PROJECT_NAME" up \
    -d \
    --no-build \
    --pull never \
    --remove-orphans

# Restart gateway to refresh upstream connections
docker compose -p "$PROJECT_NAME" restart gateway

# Step 9: Verify application availability
echo "Performing post-deployment smoke tests..."

HEALTHY=false

for attempt in $(seq 1 15); do
    if curl -fsS --max-time 5 \
           http://localhost:8080/ >/dev/null \
       && curl -fsS --max-time 5 \
           http://localhost:8080/api/products >/dev/null \
       && curl -fsS --max-time 5 \
           http://localhost:8080/api/orders >/dev/null \
       && curl -fsS --max-time 5 \
           http://localhost:8080/api/notifications >/dev/null; then

        HEALTHY=true
        break
    fi

    echo "Waiting for application: attempt $attempt"
    sleep 5
done

if [ "$HEALTHY" != "true" ]; then
    echo "Deployment smoke tests failed"
    docker compose -p "$PROJECT_NAME" ps -a
    exit 1
fi

# Step 10: Remove initial deployment archives
echo "Cleaning temporary deployment files..."

rm -f "$APP_DIR/quickbuy-images.tar"
rm -f "$APP_DIR/quickbuy-build-d52cd6c.zip"

# Remove obsolete, unused QuickBuy application images
for repository in \
    quickbuy-inventory \
    quickbuy-order \
    quickbuy-notification; do

    docker image ls "$repository" \
        --format '{{.Repository}}:{{.Tag}}' |
    while IFS= read -r image; do
        if [ "$image" != "$repository:$IMAGE_TAG" ]; then
            docker image rm "$image" || true
        fi
    done
done

# Step 11: Report successful deployment
docker compose -p "$PROJECT_NAME" ps

df -h /

echo "QuickBuy deployment successful: $IMAGE_TAG"
