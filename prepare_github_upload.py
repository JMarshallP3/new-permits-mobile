#!/usr/bin/env python3
"""
Script to prepare files for GitHub upload
"""

import os
import shutil

def prepare_for_github():
    """Copy only essential files to a clean directory for GitHub upload"""
    
    # Create clean directory
    clean_dir = "github-upload"
    if os.path.exists(clean_dir):
        shutil.rmtree(clean_dir)
    os.makedirs(clean_dir)
    
    # Essential files to copy
    essential_files = [
        "app.py",
        "requirements.txt", 
        "generate_vapid_keys.py",
        "Dockerfile",
        "Procfile",
        "nixpacks.toml",
        ".gitignore",
        ".railwayignore",
        "README.md"
    ]
    
    # Copy essential files
    for file in essential_files:
        if os.path.exists(file):
            shutil.copy2(file, clean_dir)
            print(f"✅ Copied {file}")
        else:
            print(f"⚠️  {file} not found (optional)")
    
    # Copy essential directories
    essential_dirs = ["static", "templates"]
    for dir_name in essential_dirs:
        if os.path.exists(dir_name):
            shutil.copytree(dir_name, os.path.join(clean_dir, dir_name))
            print(f"✅ Copied {dir_name}/ directory")
        else:
            print(f"⚠️  {dir_name}/ directory not found")
    
    print(f"\n🎉 Clean files ready in '{clean_dir}' folder!")
    print("📁 Upload the contents of this folder to GitHub")
    print("🚀 Then connect Railway to your GitHub repository")

if __name__ == "__main__":
    prepare_for_github()
