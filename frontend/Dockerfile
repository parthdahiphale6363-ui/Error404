# ==============================================================================
# Corporate Risk Radar - Frontend Container (React 19 + Vite + Nginx)
# ==============================================================================

# --- Stage 1: Build Static Assets ---
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency manifests
COPY package*.json ./

# Install npm dependencies
RUN npm ci || npm install

# Copy frontend source code and configuration files
COPY . ./

# Build production distribution bundle
RUN npm run build

# --- Stage 2: Production Nginx Server ---
FROM nginx:alpine

# Clean default Nginx web root
RUN rm -rf /usr/share/nginx/html/*

# Copy compiled SPA production assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration with reverse proxy for /api and SSE streaming
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose HTTP port 3000
EXPOSE 3000

# Start Nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
