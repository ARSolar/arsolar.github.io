import sys
import os
import hashlib

def xor_crypt(data: bytes, password: str) -> bytes:
    key = hashlib.sha256(password.encode()).digest()
    out = bytearray()
    for i, b in enumerate(data):
        block_idx = i // 32
        byte_idx = i % 32
        block_key = hashlib.sha256(key + block_idx.to_bytes(4, 'big')).digest()
        out.append(b ^ block_key[byte_idx])
    return bytes(out)

def main():
    if len(sys.argv) < 3:
        print("Usage: python crypt_helper.py <encrypt|decrypt> <password>")
        sys.exit(1)
        
    action = sys.argv[1].lower()
    password = sys.argv[2]
    
    # Set working directory to script location
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    config_path = "config.json"
    enc_path = "config.json.enc"
    
    if action == "encrypt":
        if not os.path.exists(config_path):
            print(f"Error: {config_path} not found.")
            sys.exit(1)
        with open(config_path, "rb") as f:
            data = f.read()
        encrypted = xor_crypt(data, password)
        with open(enc_path, "wb") as f:
            f.write(encrypted)
        print("Successfully encrypted config.json to config.json.enc")
        
    elif action == "decrypt":
        if not os.path.exists(enc_path):
            print(f"Error: {enc_path} not found.")
            sys.exit(1)
        with open(enc_path, "rb") as f:
            data = f.read()
        decrypted = xor_crypt(data, password)
        with open(config_path, "wb") as f:
            f.write(decrypted)
        print("Successfully decrypted config.json.enc to config.json")
        
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

if __name__ == "__main__":
    main()
