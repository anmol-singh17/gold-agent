import os
import sys
import uuid
from datetime import datetime
import random
from dotenv import load_dotenv

# Load env before importing db
load_dotenv()

# Add agent directory to sys.path so we can import db
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent'))
import db

def seed_data():
    conn = db.get_conn()
    if not conn:
        print("Failed to connect to database.")
        return

    cur = conn.cursor()

    fake_data = [
        ("18k gold ring 5.2g", 250, "18k gold ring weighing 5.2 grams. Excellent condition."),
        ("14k gold chain 8g Italy", 320, "Beautiful 14k gold chain from Italy. Weighs 8 grams."),
        ("22k gold bangle 15g", 400, "Stunning 22k gold bangle. 15 grams total weight."),
        ("10k gold pendant 3.5g", 120, "Small 10k gold pendant. Weight is 3.5g."),
        ("18k gold earrings 4g", 180, "18 karat gold earrings, 4 grams pair."),
        ("14k gold bracelet 10g", 380, "Solid 14k gold bracelet. 10g on the scale."),
        ("24k gold coin ring 7g", 350, "Ring with a 24k gold coin. Total weight 7g."),
        ("18k white gold ring 6g", 280, "18k white gold ring. 6 grams weight."),
        ("14k rose gold chain 12g", 400, "14k rose gold chain, 12 grams. Stamped 585."),
        ("10k gold mens ring 9g", 220, "Mens 10k gold ring. 9g. Good condition.")
    ]

    platforms = ["kijiji", "craigslist"]

    print("Seeding database with 10 fake listings...")

    for title, price, description in fake_data:
        listing_id = str(uuid.uuid4())
        external_id = f"fake_{listing_id[:8]}"
        platform = random.choice(platforms)
        url = f"https://fakeurl.com/{external_id}"
        created_at = datetime.now()

        try:
            cur.execute("""
                INSERT INTO listings 
                (external_id, platform, url, title, description, price_cad, city, status, created_at, notified)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                external_id, platform, url, title, description, price, 'toronto', 'new', created_at, False
            ))
            print(f"Inserted: {title} | {platform} | ${price}")
        except Exception as e:
            print(f"Error inserting {title}: {e}")

    conn.commit()
    cur.close()
    conn.close()
    print("Seeding complete.")

if __name__ == "__main__":
    seed_data()
