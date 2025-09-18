#!/usr/bin/env python3
"""
Generate VAPID keys for push notifications
Run this script to generate your VAPID private and public keys
"""

from pywebpush import WebPushException
import base64
import json
import os

def generate_vapid_keys():
    """Generate VAPID keys for push notifications"""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.backends import default_backend
        
        # Generate private key
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        
        # Get public key
        public_key = private_key.public_key()
        
        # Serialize keys
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        # Convert to base64 for web push
        private_b64 = base64.urlsafe_b64encode(private_pem).decode('utf-8').rstrip('=')
        public_b64 = base64.urlsafe_b64encode(public_pem).decode('utf-8').rstrip('=')
        
        print("VAPID Keys Generated Successfully!")
        print("=" * 50)
        print(f"Private Key: {private_b64}")
        print(f"Public Key:  {public_b64}")
        print("=" * 50)
        print("\nAdd these to your environment variables:")
        print(f"VAPID_PRIVATE_KEY={private_b64}")
        print(f"VAPID_PUBLIC_KEY={public_b64}")
        print("\nOr add them to your .env file:")
        print(f"VAPID_PRIVATE_KEY={private_b64}")
        print(f"VAPID_PUBLIC_KEY={public_b64}")
        
        return private_b64, public_b64
        
    except ImportError:
        print("Error: cryptography library not installed.")
        print("Install it with: pip install cryptography")
        return None, None
    except Exception as e:
        print(f"Error generating VAPID keys: {e}")
        return None, None

if __name__ == "__main__":
    generate_vapid_keys()
