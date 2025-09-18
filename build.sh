#!/bin/bash

# Build script for Railway deployment
# This script installs Chrome and ChromeDriver for the RRC Monitor app

echo "🔧 Installing system dependencies..."

# Update package list
apt-get update

# Install basic dependencies
apt-get install -y wget gnupg unzip curl xvfb

# Add Google Chrome repository
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list

# Update package list again
apt-get update

# Install Google Chrome
apt-get install -y google-chrome-stable

# Install Python dependencies
pip install -r requirements.txt

echo "✅ Build completed successfully!"
