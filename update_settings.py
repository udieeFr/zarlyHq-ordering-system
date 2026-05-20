with open('zarlyOs/settings.py', 'r') as f:
    content = f.read()

content = content.replace("os.getenv('DB_NAME'", "os.getenv('DATABASE_NAME'")
content = content.replace("os.getenv('DB_USER'", "os.getenv('DATABASE_USER'")
content = content.replace("os.getenv('DB_PASSWORD'", "os.getenv('DATABASE_PASSWORD'")
content = content.replace("os.getenv('DB_HOST'", "os.getenv('DATABASE_HOST'")
content = content.replace("os.getenv('DB_PORT'", "os.getenv('DATABASE_PORT'")
content = content.replace("'5433'", "'5432'")

with open('zarlyOs/settings.py', 'w') as f:
    f.write(content)

print("Settings updated successfully!")
