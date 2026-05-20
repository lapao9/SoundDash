from werkzeug.security import generate_password_hash

hash_seguro = generate_password_hash("admin13", method='pbkdf2:sha256:500')
print(hash_seguro)
